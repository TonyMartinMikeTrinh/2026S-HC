"""``SimulatedDevice`` — base for every digital-twin device.

Provides the device-side behaviour the architecture asks for:

* **Persistent identity (A-16):** loads/creates a stable identity on start.
* **Announce + descriptor + retained state** on every (re)connect, so registry,
  controller and dashboard pick the device up regardless of start order.
* **Idempotent commands (A-08):** duplicate ``command_id``s are ignored and
  ``apply_command`` only reports a change when state actually changes.
* **Realistic behaviour:** ``step(dt)`` advances a per-device simulation; the run
  loop publishes on change and on a periodic heartbeat.
"""
from __future__ import annotations

import argparse
import collections
import threading
import time

from ..core import topics
from ..core.identity import load_or_create
from ..core.mqtt_component import MqttComponent
from ..core.model import (
    Announcement,
    Command,
    DeviceDescriptor,
    DeviceState,
    DeviceType,
    Event,
)


class SimulatedDevice(MqttComponent):
    device_type: DeviceType
    capabilities: list[str] = []
    protocol: str = "matter"
    component_label: str | None = None      # override the log/component name

    def __init__(self, logical_name: str, area: str, name: str | None = None,
                 manufacturer: str = "ACME", model: str = "sim-1") -> None:
        ident = load_or_create(logical_name, self.device_type)
        super().__init__(self.component_label or self.device_type.value,
                         client_id=ident.device_id,
                         device_id=ident.device_id, clean_session=False)
        self.identity = ident
        self.area = area
        self.descriptor = DeviceDescriptor(
            device_id=ident.device_id, type=self.device_type,
            name=name or logical_name, area=area, manufacturer=manufacturer,
            model=model, protocol=self.protocol, capabilities=list(self.capabilities),
        )
        self._lock = threading.Lock()
        self.attrs: dict = self.initial_attrs()
        self._recent_cmds: collections.deque = collections.deque(maxlen=64)
        self.on_topic(topics.command(self.device_id), self._on_command)

    # --- to override -------------------------------------------------------
    def initial_attrs(self) -> dict:
        return {}

    def apply_command(self, attrs: dict) -> bool:
        """Apply desired attributes idempotently; return True if state changed."""
        return False

    def step(self, dt: float) -> bool:
        """Advance the simulation by ``dt`` seconds; return True if state changed."""
        return False

    # --- publishing helpers -----------------------------------------------
    def on_connected(self) -> None:
        # Retained descriptor + retained announce (so a late/restarted registry
        # instantly re-learns every device) + retained state.
        self.client.publish(topics.descriptor(self.device_id),
                            self.descriptor.model_dump_json(), qos=1, retain=True)
        ann = Announcement(descriptor=self.descriptor,
                           fingerprint=self.identity.fingerprint)
        self.client.publish(topics.announce(self.device_id),
                            ann.model_dump_json(), qos=1, retain=True)
        self.publish_state()

    def publish_state(self) -> None:
        with self._lock:
            st = DeviceState(device_id=self.device_id, type=self.device_type,
                             attrs=dict(self.attrs))
        self.publish_model(topics.state(self.device_id), st, qos=1, retain=True)

    def emit_event(self, kind: str, message: str, data: dict | None = None) -> None:
        self.publish_model(topics.EVENTS, Event(source=self.device_id, kind=kind,
                           message=message, device_id=self.device_id, data=data or {}))

    # --- command handling --------------------------------------------------
    def _on_command(self, topic: str, payload: bytes) -> None:
        try:
            cmd = Command.model_validate_json(payload)
        except Exception:  # noqa: BLE001
            self.log.warning("ignored malformed command on %s", topic)
            return
        if cmd.command_id in self._recent_cmds:        # idempotent de-dupe
            return
        self._recent_cmds.append(cmd.command_id)
        with self._lock:
            changed = self.apply_command(cmd.attrs)
        if changed:
            self.log.info("command from %s -> %s", cmd.source, cmd.attrs)
            self.publish_state()

    # --- run loop ----------------------------------------------------------
    def run(self, tick: float = 1.0, heartbeat: float = 10.0) -> None:
        self.start()
        last_hb = time.monotonic()
        try:
            while True:
                time.sleep(tick)
                with self._lock:
                    changed = self.step(tick)
                if changed or (time.monotonic() - last_hb >= heartbeat):
                    self.publish_state()
                    last_hb = time.monotonic()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


def run_device(cls: type[SimulatedDevice]) -> None:
    """CLI entry point shared by every device module."""
    p = argparse.ArgumentParser(description=f"Run a simulated {cls.__name__}")
    p.add_argument("--name", required=True, help="logical (persistent) name")
    p.add_argument("--area", required=True, help="room / area, e.g. living_room")
    p.add_argument("--display-name", default=None)
    p.add_argument("--tick", type=float, default=1.0)
    a = p.parse_args()
    cls(logical_name=a.name, area=a.area, name=a.display_name).run(tick=a.tick)
