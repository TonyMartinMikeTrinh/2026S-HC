"""LLM backend contract + the tool schema shared by all backends."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class Decision:
    tool_calls: list[ToolCall] = field(default_factory=list)
    reply: str = ""


# Tool schema (OpenAI/Ollama function-calling format). Every backend resolves
# these abstract intents; the agent maps them onto concrete device commands.
TOOLS = [
    {"type": "function", "function": {
        "name": "control_light",
        "description": "Turn lights on or off and/or set brightness. "
                       "Omit 'area' to affect every room.",
        "parameters": {"type": "object", "properties": {
            "area": {"type": "string",
                     "description": "room id e.g. living_room, kitchen, bedroom, hallway"},
            "on": {"type": "boolean"},
            "brightness": {"type": "integer", "description": "0-100"},
        }, "required": []}}},
    {"type": "function", "function": {
        "name": "set_thermostat",
        "description": "Set the target temperature of thermostats.",
        "parameters": {"type": "object", "properties": {
            "area": {"type": "string"},
            "setpoint": {"type": "number", "description": "target °C, 5-30"},
        }, "required": ["setpoint"]}}},
    {"type": "function", "function": {
        "name": "control_lock",
        "description": "Lock or unlock door locks.",
        "parameters": {"type": "object", "properties": {
            "area": {"type": "string"},
            "lock": {"type": "boolean", "description": "true = lock, false = unlock"},
        }, "required": ["lock"]}}},
    {"type": "function", "function": {
        "name": "control_plug",
        "description": "Switch smart plugs on or off.",
        "parameters": {"type": "object", "properties": {
            "area": {"type": "string"},
            "on": {"type": "boolean"},
        }, "required": ["on"]}}},
]

ALLOWED_TOOLS = {t["function"]["name"] for t in TOOLS}

SYSTEM_PROMPT = (
    "You are the orchestration agent of a LOCAL smart home. Translate the user's "
    "request into tool calls that control devices. Only use the provided tools. "
    "Use the current home state to pick rooms/devices; omit 'area' to target all "
    "rooms of a type. Keep actions minimal. For pure status questions, do not call "
    "tools — answer from the state. Reply with one short confirmation sentence."
)


class LLMBackend:
    name: str = "base"

    def available(self) -> bool:
        return True

    def decide(self, text: str, world_summary: str) -> Decision:  # pragma: no cover
        raise NotImplementedError
