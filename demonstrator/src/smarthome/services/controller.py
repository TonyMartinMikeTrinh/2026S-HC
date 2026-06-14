"""Local-first automation controller (A-01/A-06/A-08/A-14).

Builds a live world model from retained descriptors + states, then evaluates a
set of **auto-discovered** rule plugins once per second and issues idempotent
device commands. It depends on nothing but the broker, so the home keeps
automating with the cloud and internet gone.

**Redundancy / failover (A-05):** several controllers may run at once. They share
a retained leader-lease topic; only the leader executes rules (so commands aren't
duplicated). If the leader dies, its lease goes stale and a standby takes over —
deterministically the smallest controller id wins.

Run standalone::  python -m smarthome.services.controller --id a
"""
from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import threading
import time
import uuid

from .. import rules as rules_pkg
from ..core import topics
from ..core.model import Command, DeviceState, Event, now
from ..core.mqtt_component import MqttComponent
from ..rules.base import DeviceView, Rule, RuleContext

LEASE_TIMEOUT = 6.0
HEARTBEAT = 2.0
EVAL_INTERVAL = 1.0


def discover_rules() -> list[Rule]:
    found: list[Rule] = []
    for mod_info in pkgutil.iter_modules(rules_pkg.__path__):
        if mod_info.name == "base":
            continue
        mod = importlib.import_module(f"{rules_pkg.__name__}.{mod_info.name}")
        for obj in vars(mod).values():
            if isinstance(obj, type) and issubclass(obj, Rule) and obj is not Rule:
                found.append(obj())
    return found


class Controller(MqttComponent):
    def __init__(self, controller_id: str | None = None) -> None:
        cid = controller_id or uuid.uuid4().hex[:4]
        self.controller_id = f"controller-{cid}"
        super().__init__(self.controller_id, client_id=self.controller_id,
                         clean_session=False)

        self._world_lock = threading.Lock()
        self._descriptors: dict[str, dict] = {}
        self._states: dict[str, dict] = {}
        self._rules = discover_rules()
        self._memory: dict[str, dict] = {r.name: {} for r in self._rules}

        self._leader_id: str | None = None
        self._leader_ts: float = 0.0
        self._is_leader = False
        self._stop = threading.Event()
        self._loop_thread: threading.Thread | None = None

        self.on_topic(topics.ALL_DESCRIPTORS, self._on_descriptor)
        self.on_topic(topics.ALL_STATES, self._on_state)
        self.on_topic(topics.CONTROLLER_LEADER, self._on_leader)

    def on_connected(self) -> None:
        self.log.info("controller online with %d rule(s): %s",
                      len(self._rules), ", ".join(r.name for r in self._rules))
        if self._loop_thread is None:           # start the control loop once
            self._loop_thread = threading.Thread(target=self._loop, daemon=True)
            self._loop_thread.start()

    # --- world model -------------------------------------------------------
    def _on_descriptor(self, topic: str, payload: bytes) -> None:
        try:
            d = json.loads(payload)
        except Exception:  # noqa: BLE001
            return
        with self._world_lock:
            self._descriptors[d["device_id"]] = d

    def _on_state(self, topic: str, payload: bytes) -> None:
        try:
            st = DeviceState.model_validate_json(payload)
        except Exception:  # noqa: BLE001
            return
        with self._world_lock:
            self._states[st.device_id] = {"attrs": st.attrs, "reachable": st.reachable}

    def _snapshot(self) -> dict[str, DeviceView]:
        world: dict[str, DeviceView] = {}
        with self._world_lock:
            for did, desc in self._descriptors.items():
                state = self._states.get(did, {})
                world[did] = DeviceView(
                    device_id=did, type=desc["type"], area=desc["area"],
                    name=desc["name"], protocol=desc.get("protocol", "matter"),
                    attrs=dict(state.get("attrs", {})),
                    reachable=state.get("reachable", True))
        return world

    # --- command + event sinks for rules -----------------------------------
    def _send(self, device_id: str, attrs: dict) -> bool:
        with self._world_lock:
            current = self._states.get(device_id, {}).get("attrs", {})
        # Idempotent: skip if the device already satisfies the desired attrs.
        if all(current.get(k) == v for k, v in attrs.items()):
            return False
        cmd = Command(command_id=uuid.uuid4().hex, device_id=device_id,
                      attrs=attrs, source=self.controller_id)
        self.publish_model(topics.command(device_id), cmd)
        return True

    def _emit(self, kind: str, message: str, device_id: str | None,
              data: dict | None) -> None:
        self.publish_model(topics.EVENTS, Event(source=self.controller_id, kind=kind,
                           message=message, device_id=device_id, data=data or {}))

    # --- leader election ---------------------------------------------------
    def _on_leader(self, topic: str, payload: bytes) -> None:
        try:
            d = json.loads(payload)
        except Exception:  # noqa: BLE001
            return
        self._leader_id, self._leader_ts = d.get("id"), d.get("ts", 0.0)

    def _claim(self) -> None:
        self.client.publish(topics.CONTROLLER_LEADER,
                            json.dumps({"id": self.controller_id, "ts": now()}),
                            qos=1, retain=True)
        self._leader_id, self._leader_ts = self.controller_id, now()

    def _refresh_leadership(self) -> None:
        fresh = (now() - self._leader_ts) < LEASE_TIMEOUT
        if self._leader_id is None or not fresh:
            self._claim()                                   # vacant / stale -> take it
        elif self._leader_id == self.controller_id:
            self._claim()                                   # renew my lease
        elif self.controller_id < self._leader_id:
            self._claim()                                   # smallest id preempts
        want = self._leader_id == self.controller_id
        if want and not self._is_leader:
            self.log.info("[green]became leader[/] (active controller)")
        elif not want and self._is_leader:
            self.log.info("[yellow]stepping down to standby[/]")
        self._is_leader = want

    # --- main loop ---------------------------------------------------------
    def _loop(self) -> None:
        last_eval = 0.0
        while not self._stop.is_set():
            self._refresh_leadership()
            if self._is_leader and (time.monotonic() - last_eval) >= EVAL_INTERVAL:
                self._evaluate()
                last_eval = time.monotonic()
            self._stop.wait(min(HEARTBEAT, EVAL_INTERVAL))

    def _evaluate(self) -> None:
        world = self._snapshot()
        for rule in self._rules:
            ctx = RuleContext(world=world, now=time.monotonic(),
                              memory=self._memory[rule.name],
                              _command=self._send, _event=self._emit)
            try:
                rule.evaluate(ctx)
            except Exception:  # noqa: BLE001
                self.log.exception("rule %s failed", rule.name)

    def run(self) -> None:
        self.start()        # control loop starts from on_connected()
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            self._stop.set()
            self.stop()


def main() -> None:
    p = argparse.ArgumentParser(description="Local-first automation controller")
    p.add_argument("--id", default=None, help="controller id suffix (for failover demo)")
    a = p.parse_args()
    Controller(controller_id=a.id).run()


if __name__ == "__main__":
    main()
