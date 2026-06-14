"""Pure, guardrailed resolution of abstract tool calls into concrete commands.

Extracted so the live :mod:`~smarthome.services.agent` and the architecture
benchmark (:mod:`smarthome.benchmark`) enforce the *same* A-22 guardrails:

* only the whitelisted abstract tools (``control_light`` …) are honoured,
* a tool call is only ever expanded onto devices that **actually exist** and
  match the requested ``type`` (and ``area`` when given),
* malformed / out-of-range arguments are clamped or rejected, never crash.

A ``world`` is a list of plain device dicts with at least ``device_id``, ``type``
and ``area`` keys (plus ``name``/``attrs`` for :func:`summarize_world`).
"""
from __future__ import annotations

from ..llm.base import ToolCall


def light_attrs(a: dict) -> dict | None:
    """Build a light command from tool arguments (on/off and/or 0-100 brightness)."""
    attrs: dict = {}
    if "on" in a and a["on"] is not None:
        attrs["on"] = bool(a["on"])
    if a.get("brightness") is not None:
        attrs["brightness"] = max(0, min(100, int(a["brightness"])))
    return attrs or None


# Maps each whitelisted tool onto (target device type, argument -> attrs builder).
_SPEC = {
    "control_light": ("light", light_attrs),
    "set_thermostat": ("thermostat", lambda x: {"setpoint": float(x["setpoint"])}
                       if "setpoint" in x else None),
    "control_lock": ("door_lock", lambda x: {"locked": bool(x["lock"])}
                     if "lock" in x else None),
    "control_plug": ("smart_plug", lambda x: {"on": bool(x["on"])}
                     if "on" in x else None),
}


def resolve_tool_call(call: ToolCall, world: list[dict]) -> list[tuple[str, dict]]:
    """Expand one abstract tool call into ``(device_id, attrs)`` device commands.

    Returns an empty list when the tool is unknown, the arguments are invalid,
    or no existing device matches the requested type/area (the caller treats an
    empty result as a guardrail rejection)."""
    a = call.arguments or {}
    area = a.get("area")
    if isinstance(area, str):
        area = area.strip().lower().replace(" ", "_")
    if area in ("", "all", "everywhere", "alle"):
        area = None

    spec = _SPEC.get(call.name)
    if spec is None:
        return []
    dtype, builder = spec
    try:
        attrs = builder(a)
    except (KeyError, TypeError, ValueError):
        attrs = None
    if not attrs:
        return []
    return [(d["device_id"], dict(attrs)) for d in world
            if d["type"] == dtype and (area is None or d["area"] == area)]


def summarize_world(world: list[dict]) -> str:
    """Render the world snapshot as the compact context string given to a backend."""
    if not world:
        return "(no devices known yet)"
    return "\n".join(
        f"- {d['area']} {d['type']} '{d.get('name', d['device_id'])}' "
        f"({d['device_id']}): {d.get('attrs', {})}"
        for d in world)
