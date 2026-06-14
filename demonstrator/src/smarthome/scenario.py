"""Guided, narrated end-to-end demo (`python run.py scenario`).

Runs the whole system in-process and walks through the architecture's headline
capabilities step by step, so the story is reproducible during the talk:

 1. Discovery + persistent registration (devices announce, registry persists them)
 2. Local-first automation (motion + dark -> light on)
 3. On-device agent orchestration (a natural-language request)
 4. Persistent re-registration (a device "reboots" and re-binds WITHOUT re-pairing)
 5. Fault tolerance (broker outage -> auto-reconnect, nothing forgotten)

For a clean, repeatable run it starts from a fresh registry DB and scenario
identities.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid

import paho.mqtt.client as mqtt
from rich.console import Console

from amqtt.broker import Broker

from .broker import _broker_config
from .core import config, topics
from .core.model import AgentRequest, Command
from .devices.door_lock import DoorLock
from .devices.light import Light
from .services.agent import Agent
from .services.controller import Controller
from .services.registry import Registry

console = Console()
MS_ID = "motion_sensor-scenario"          # the synthetic, deterministic motion sensor


class BrokerThread:
    """Runs the amqtt broker on its own asyncio loop so we can stop/restart it."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.broker: Broker | None = None

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()
        time.sleep(1.2)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)

        async def _start() -> None:                # Broker() needs a running loop
            self.broker = Broker(_broker_config())
            await self.broker.start()

        self.loop.run_until_complete(_start())
        self.loop.run_forever()

    def stop(self) -> None:
        fut = asyncio.run_coroutine_threadsafe(self.broker.shutdown(), self.loop)
        fut.result(timeout=5)


class Observer:
    """Read-only bus client used to narrate + inject deterministic stimuli."""

    def __init__(self) -> None:
        self.inventory: dict = {"devices": []}
        self.states: dict[str, dict] = {}
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="scenario-obs")
        self.c.on_connect = lambda cl, u, f, rc, p=None: cl.subscribe("home/#", qos=1)
        self.c.on_message = self._on
        self.c.connect(config.BROKER_HOST, config.BROKER_PORT, 30)
        self.c.loop_start()

    def _on(self, cl, u, m) -> None:
        try:
            if m.topic == topics.INVENTORY:
                self.inventory = json.loads(m.payload)
            elif topics.matches(topics.ALL_STATES, m.topic):
                d = json.loads(m.payload)
                self.states[d["device_id"]] = d["attrs"]
        except Exception:  # noqa: BLE001
            pass

    def _publish_motion(self, motion: bool, lux: int) -> None:
        state = {"device_id": MS_ID, "type": "motion_sensor",
                 "attrs": {"motion": motion, "illuminance": lux, "last_motion": time.time()},
                 "reachable": True, "ts": time.time()}
        self.c.publish(topics.state(MS_ID), json.dumps(state), qos=1, retain=True)

    def inject_dark_motion(self, area: str) -> None:
        desc = {"device_id": MS_ID, "type": "motion_sensor", "name": "Scenario PIR",
                "area": area, "manufacturer": "ACME", "model": "sim-1",
                "protocol": "matter", "capabilities": ["motion", "illuminance"],
                "schema_version": config.SCHEMA_VERSION}
        self.c.publish(topics.descriptor(MS_ID), json.dumps(desc), qos=1, retain=True)
        self._publish_motion(True, 5)

    def clear_motion(self) -> None:
        self._publish_motion(False, 400)

    def send_command(self, device_id: str, **attrs) -> None:
        cmd = Command(command_id=uuid.uuid4().hex, device_id=device_id,
                      attrs=attrs, source="scenario")
        self.c.publish(topics.command(device_id), cmd.model_dump_json(), qos=1)

    def ask_agent(self, text: str) -> None:
        req = AgentRequest(request_id=uuid.uuid4().hex, text=text, source="scenario")
        self.c.publish(topics.AGENT_REQUEST, req.model_dump_json(), qos=1)


def step(title: str) -> None:
    console.rule(f"[bold cyan]{title}")


def _reset_state() -> None:
    config.ensure_state_dirs()
    config.REGISTRY_DB.unlink(missing_ok=True)
    for p in config.IDENTITY_DIR.glob("scenario_*.json"):
        p.unlink(missing_ok=True)


def main() -> None:
    _reset_state()
    console.print("[bold]Smart-Home Demonstrator — guided scenario[/]\n")

    broker = BrokerThread(); broker.start()
    obs = Observer(); time.sleep(0.4)

    registry = Registry(); registry.start(); registry.wait_connected(5)
    controller = Controller("a"); controller.start(); controller.wait_connected(5)
    agent = Agent(); agent.start(); agent.wait_connected(5)
    time.sleep(0.5)

    light = Light("scenario_living_light", "living_room", name="Living Room Lamp")
    lock = DoorLock("scenario_front_lock", "hallway", name="Front Door")
    light.start(); light.wait_connected(5)
    lock.start(); lock.wait_connected(5)
    time.sleep(1.0)

    # 1 -------------------------------------------------------------------
    step("1) Discovery & persistent registration")
    console.print("Devices announced themselves; the registry persisted them as the "
                  "local source of truth (SQLite).")
    console.print(f"   registered devices: [b]{len(obs.inventory['devices'])}[/] "
                  f"-> {[d['descriptor']['name'] for d in obs.inventory['devices']]}")
    time.sleep(2.0)

    # 2 -------------------------------------------------------------------
    step("2) Local-first automation: motion + darkness -> light on")
    console.print("Injecting a dark-room motion event in the living room…")
    obs.inject_dark_motion("living_room")
    time.sleep(3.0)
    console.print(f"   living-room lamp is now: [b]{obs.states.get(light.device_id)}[/] "
                  "(decided locally by the controller, no cloud)")
    time.sleep(2.0)

    # 3 -------------------------------------------------------------------
    step("3) On-device agent: natural-language orchestration")
    obs.clear_motion()                       # person left; no automation override
    time.sleep(1.5)
    console.print("Sending request: [italic]\"good night\"[/]")
    obs.ask_agent("good night")
    time.sleep(2.5)
    console.print(f"   lamp: [b]{obs.states.get(light.device_id)}[/]")
    console.print(f"   door: [b]{obs.states.get(lock.device_id)}[/]  "
                  "(agent turned the light off and locked the door)")
    time.sleep(2.0)

    # 4 -------------------------------------------------------------------
    step("4) Persistent re-registration: a device reboots")
    before = len(obs.inventory["devices"])
    console.print(f"Inventory before reboot: [b]{before}[/] devices. "
                  "Killing the lamp process and starting a fresh one with the SAME identity…")
    light.stop()
    time.sleep(1.5)
    light2 = Light("scenario_living_light", "living_room", name="Living Room Lamp")
    light2.start(); light2.wait_connected(5)
    time.sleep(2.0)
    after = len(obs.inventory["devices"])
    console.print(f"   inventory after reboot: [b]{after}[/] devices — "
                  f"[green]re-bound without re-pairing, no duplicate[/] "
                  f"(same device_id {light2.device_id}).")
    time.sleep(2.0)

    # 5 -------------------------------------------------------------------
    step("5) Fault tolerance: broker outage & auto-reconnect")
    console.print("Stopping the MQTT broker for ~3 s (simulated network/cloud outage)…")
    broker.stop()
    time.sleep(3.0)
    console.print("Restarting the broker — components auto-reconnect with their "
                  "persistent sessions, nothing is forgotten…")
    broker2 = BrokerThread(); broker2.start()
    time.sleep(3.0)
    console.print(f"   reconnected; registry still knows "
                  f"[b]{len(obs.inventory['devices'])}[/] devices.")

    console.rule("[bold green]scenario complete")
    console.print("Tip: run [b]python run.py up[/] and open the dashboard to explore live.\n")

    for comp in (light2, lock, agent, controller, registry):
        try:
            comp.stop()
        except Exception:  # noqa: BLE001
            pass
    obs.c.loop_stop()
    broker2.stop()


if __name__ == "__main__":
    main()
