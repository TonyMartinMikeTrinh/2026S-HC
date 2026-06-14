"""FastAPI + WebSocket dashboard.

A read-mostly observer that bridges the MQTT bus to the browser: a paho client
subscribes to everything, keeps a live snapshot, and pushes every update to all
connected WebSocket clients. A small REST surface lets the page send
natural-language requests to the agent.

Run standalone::  python -m smarthome.dashboard.app
"""
from __future__ import annotations

import asyncio
import collections
import contextlib
import json
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from ..benchmark.report import render_report_html
from ..benchmark.runner import run_benchmark
from ..benchmark.architectures import DEFAULT_ORDER, PROFILES
from ..core import config, topics
from ..core.model import AgentRequest

STATIC = Path(__file__).parent / "static"


class Bridge:
    """Holds the live snapshot and fans MQTT messages out to WebSocket clients."""

    def __init__(self) -> None:
        self.descriptors: dict[str, dict] = {}
        self.states: dict[str, dict] = {}
        self.availability: dict[str, str] = {}
        self.inventory: dict = {"devices": []}
        self.events: collections.deque = collections.deque(maxlen=150)
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queue: asyncio.Queue = asyncio.Queue()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id="dashboard", clean_session=True)
        self.client.on_connect = lambda c, u, f, rc, p=None: c.subscribe("home/#", qos=1)
        self.client.on_message = self._on_message

    # --- snapshot ----------------------------------------------------------
    def snapshot(self) -> dict:
        devices = []
        for did, desc in self.descriptors.items():
            devices.append({**desc,
                            "attrs": self.states.get(did, {}),
                            "availability": self.availability.get(did, "unknown")})
        return {"devices": devices, "inventory": self.inventory,
                "events": list(self.events)}

    # --- mqtt --------------------------------------------------------------
    def _on_message(self, client, userdata, msg) -> None:
        topic, payload = msg.topic, msg.payload
        update: dict | None = None
        try:
            if topics.matches(topics.ALL_STATES, topic):
                d = json.loads(payload)
                self.states[d["device_id"]] = d["attrs"]
                update = {"kind": "state", "device_id": d["device_id"], "attrs": d["attrs"]}
            elif topics.matches(topics.ALL_DESCRIPTORS, topic):
                d = json.loads(payload)
                self.descriptors[d["device_id"]] = d
                update = {"kind": "descriptor", "device_id": d["device_id"], "descriptor": d}
            elif topics.matches(topics.ALL_AVAILABILITY, topic):
                d = json.loads(payload)
                self.availability[d["device_id"]] = d["status"]
                update = {"kind": "availability", "device_id": d["device_id"], "status": d["status"]}
            elif topic == topics.INVENTORY:
                self.inventory = json.loads(payload)
                update = {"kind": "inventory", "inventory": self.inventory}
            elif topic == topics.EVENTS:
                ev = json.loads(payload)
                self.events.appendleft(ev)
                update = {"kind": "event", "event": ev}
            elif topic == topics.AGENT_AUDIT:
                update = {"kind": "audit", "audit": json.loads(payload)}
        except Exception:  # noqa: BLE001 — never let a bad payload kill the bridge
            return
        if update and self.loop is not None:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, {"type": "update", **update})

    async def broadcaster(self) -> None:
        while True:
            item = await self.queue.get()
            for ws in list(self.clients):
                try:
                    await ws.send_json(item)
                except Exception:  # noqa: BLE001
                    self.clients.discard(ws)


bridge = Bridge()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    bridge.loop = asyncio.get_running_loop()
    bridge.client.connect_async(config.BROKER_HOST, config.BROKER_PORT, config.KEEPALIVE)
    bridge.client.loop_start()
    task = asyncio.create_task(bridge.broadcaster())
    try:
        yield
    finally:
        task.cancel()
        bridge.client.loop_stop()
        bridge.client.disconnect()


app = FastAPI(title="Smart-Home Demonstrator", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/devices")
async def api_devices() -> dict:
    return {"devices": bridge.snapshot()["devices"]}


@app.get("/api/registry")
async def api_registry() -> dict:
    return bridge.inventory


@app.get("/api/events")
async def api_events() -> dict:
    return {"events": list(bridge.events)}


@app.get("/benchmark", response_class=HTMLResponse)
async def benchmark_page() -> str:
    return (STATIC / "benchmark.html").read_text(encoding="utf-8")


@app.get("/api/benchmark/architectures")
async def api_benchmark_architectures() -> dict:
    return {"architectures": [PROFILES[k].public_dict() for k in DEFAULT_ORDER]}


@app.post("/api/benchmark/run")
async def api_benchmark_run(body: dict) -> dict:
    body = body or {}
    keys = body.get("architectures") or None

    def _int(name: str, default: int) -> int:
        try:
            return int(body.get(name, default))
        except (TypeError, ValueError):
            return default

    seed, rooms, devices = _int("seed", 42), _int("rooms", 4), _int("devices", 10)
    # Self-contained + fast (no MQTT, no real sleeps), so it's fine to run inline.
    report = run_benchmark(arch_keys=keys, seed=seed, rooms=rooms, devices=devices)
    return {"report": report.to_dict(),
            "html": render_report_html(report, full_page=False)}


@app.post("/api/agent")
async def api_agent(body: dict) -> dict:
    text = (body or {}).get("text", "").strip()
    if not text:
        return {"ok": False, "error": "empty request"}
    req = AgentRequest(request_id=uuid.uuid4().hex, text=text, source="dashboard")
    bridge.client.publish(topics.AGENT_REQUEST, req.model_dump_json(), qos=1)
    return {"ok": True, "request_id": req.request_id}


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    bridge.clients.add(websocket)
    await websocket.send_json({"type": "snapshot", **bridge.snapshot()})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        bridge.clients.discard(websocket)


def main() -> None:
    import uvicorn
    uvicorn.run(app, host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT,
                log_level="warning")


if __name__ == "__main__":
    main()
