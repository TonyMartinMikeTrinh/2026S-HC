"""On-device orchestration agent (A-19/A-21).

Subscribes to natural-language requests, builds a shared world context from the
bus, asks an LLM backend (Ollama, or the deterministic fallback) which actions to
take, then enforces guardrails before issuing device commands:

* only whitelisted tools (A-21),
* only devices that actually exist and match the requested type/area (A-22),
* every decision written to an audit trail (A-23).

Run standalone::  python -m smarthome.services.agent
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from ..core import config, topics
from ..core.model import AgentAudit, AgentRequest, Command, DeviceState, Event
from ..core.mqtt_component import MqttComponent
from ..llm.base import ALLOWED_TOOLS, Decision, LLMBackend, ToolCall
from ..llm.ollama_backend import OllamaBackend
from ..llm.rule_backend import RuleBackend
from .guardrails import resolve_tool_call, summarize_world


class Agent(MqttComponent):
    def __init__(self) -> None:
        super().__init__("agent", client_id="agent", clean_session=False)
        self._world_lock = threading.Lock()
        self._descriptors: dict[str, dict] = {}
        self._states: dict[str, dict] = {}
        self._rules = RuleBackend()
        self._ollama: OllamaBackend | None = None
        self._ollama_ok = False
        try:
            self._ollama = OllamaBackend()
        except Exception:  # noqa: BLE001 — ollama lib import / init issue
            self._ollama = None
        self._stop = threading.Event()
        # Probe Ollama in the background so the request path never blocks on it.
        if self._ollama is not None and config.AGENT_BACKEND in ("auto", "ollama"):
            threading.Thread(target=self._probe_loop, daemon=True).start()

        self.on_topic(topics.ALL_DESCRIPTORS, self._on_descriptor)
        self.on_topic(topics.ALL_STATES, self._on_state)
        self.on_topic(topics.AGENT_REQUEST, self._on_request)

    def on_connected(self) -> None:
        self.log.info("agent online (backend preference: %s)", config.AGENT_BACKEND)

    def _probe_loop(self) -> None:
        while not self._stop.is_set():
            ok = bool(self._ollama and self._ollama.available())
            if ok != self._ollama_ok:
                self.log.info("Ollama backend %s", "available" if ok else "unavailable")
            self._ollama_ok = ok
            self._stop.wait(15.0)

    # --- world model -------------------------------------------------------
    def _on_descriptor(self, topic: str, payload: bytes) -> None:
        try:
            d = json.loads(payload)
            with self._world_lock:
                self._descriptors[d["device_id"]] = d
        except Exception:  # noqa: BLE001
            pass

    def _on_state(self, topic: str, payload: bytes) -> None:
        try:
            st = DeviceState.model_validate_json(payload)
            with self._world_lock:
                self._states[st.device_id] = st.attrs
        except Exception:  # noqa: BLE001
            pass

    def _world(self) -> list[dict]:
        with self._world_lock:
            return [{
                "device_id": did, "type": d["type"], "area": d["area"],
                "name": d["name"], "protocol": d.get("protocol", "matter"),
                "attrs": dict(self._states.get(did, {})),
            } for did, d in self._descriptors.items()]

    @staticmethod
    def _summary(world: list[dict]) -> str:
        return summarize_world(world)

    # --- backend selection -------------------------------------------------
    def _choose_backend(self) -> LLMBackend:
        pref = config.AGENT_BACKEND
        if pref in ("ollama", "auto") and self._ollama is not None and self._ollama_ok:
            return self._ollama
        if pref == "ollama" and not self._ollama_ok:
            self.log.warning("Ollama unavailable — using rule backend")
        return self._rules

    # --- request handling --------------------------------------------------
    def _on_request(self, topic: str, payload: bytes) -> None:
        try:
            req = AgentRequest.model_validate_json(payload)
        except Exception:  # noqa: BLE001
            return
        self.handle(req.text, req.request_id, req.source)

    def handle(self, text: str, request_id: str | None = None,
               source: str = "user") -> AgentAudit:
        request_id = request_id or uuid.uuid4().hex
        world = self._world()
        backend = self._choose_backend()
        try:
            decision = backend.decide(text, self._summary(world))
        except Exception as exc:  # noqa: BLE001
            self.log.exception("backend '%s' failed", backend.name)
            decision = Decision([], f"agent error: {exc}")

        actions: list[dict] = []
        rejected: list[dict] = []
        for call in decision.tool_calls:
            if call.name not in ALLOWED_TOOLS:
                rejected.append({"tool": call.name, "reason": "tool not allowed"})
                continue
            targets = self._resolve(call, world)
            if not targets:
                rejected.append({"tool": call.name, "args": call.arguments,
                                 "reason": "no matching device"})
                continue
            for device_id, attrs in targets:
                self._send(device_id, attrs)
                actions.append({"device_id": device_id, "attrs": attrs, "tool": call.name})

        audit = AgentAudit(request_id=request_id, text=text, backend=backend.name,
                           actions=actions, rejected=rejected, reply=decision.reply)
        self.publish_model(topics.AGENT_AUDIT, audit)
        self.publish_model(topics.EVENTS, Event(
            source="agent", kind="agent",
            message=f"'{text}' -> {len(actions)} action(s) via {backend.name}",
            data={"reply": decision.reply, "rejected": len(rejected)}))
        self.log.info("[magenta]request[/] '%s' -> %d action(s), %d rejected [%s]",
                      text, len(actions), len(rejected), backend.name)
        return audit

    # --- guardrailed resolution -------------------------------------------
    def _resolve(self, call: ToolCall, world: list[dict]) -> list[tuple[str, dict]]:
        # Shared with the architecture benchmark, so both enforce identical A-22
        # guardrails (existing devices only, matching type/area).
        return resolve_tool_call(call, world)

    def _send(self, device_id: str, attrs: dict) -> None:
        cmd = Command(command_id=uuid.uuid4().hex, device_id=device_id,
                      attrs=attrs, source="agent")
        self.publish_model(topics.command(device_id), cmd)

    def run(self) -> None:
        self.start()
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            self._stop.set()
            self.stop()


def main() -> None:
    Agent().run()


if __name__ == "__main__":
    main()
