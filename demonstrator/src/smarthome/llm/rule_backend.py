"""Deterministic keyword intent parser — the offline fallback backend.

Maps common German/English smart-home phrases onto the same tool calls the LLM
would emit, so the agent works with no model loaded. Not meant to be exhaustive —
it covers the scenes used in the demo and degrades to a friendly "didn't
understand" otherwise.
"""
from __future__ import annotations

from .base import Decision, LLMBackend, ToolCall

AREAS = {
    "living_room": ["living", "wohnzimmer", "wohn"],
    "kitchen": ["kitchen", "küche", "kueche"],
    "bedroom": ["bedroom", "schlafzimmer", "schlaf"],
    "hallway": ["hallway", "flur", "diele"],
}


def _area(text: str) -> str | None:
    for area, kws in AREAS.items():
        if any(k in text for k in kws):
            return area
    return None


class RuleBackend(LLMBackend):
    name = "rules"

    def decide(self, text: str, world_summary: str) -> Decision:
        t = text.lower()
        area = _area(t)
        calls: list[ToolCall] = []

        def light(**kw):
            calls.append(ToolCall("control_light", ({"area": area} if area else {}) | kw))

        def lock(v):
            calls.append(ToolCall("control_lock", ({"area": area} if area else {}) | {"lock": v}))

        def thermo(sp):
            calls.append(ToolCall("set_thermostat", ({"area": area} if area else {}) | {"setpoint": sp}))

        # --- scenes ---------------------------------------------------------
        if any(k in t for k in ["good night", "gute nacht", "schlafen gehen", "bedtime"]):
            calls.append(ToolCall("control_light", {"on": False}))
            calls.append(ToolCall("control_lock", {"lock": True}))
            return Decision(calls, "Good night — lights off and doors locked.")
        if any(k in t for k in ["good morning", "guten morgen", "morgenroutine"]):
            calls.append(ToolCall("control_light", {"on": True, "brightness": 70}))
            calls.append(ToolCall("set_thermostat", {"setpoint": 22}))
            return Decision(calls, "Good morning — lights up and warming the place.")
        if any(k in t for k in ["cozy", "gemütlich", "gemuetlich", "movie", "film"]):
            light(on=True, brightness=35)
            thermo(22)
            return Decision(calls, "Cozy scene set.")

        # --- temperature ----------------------------------------------------
        if any(k in t for k in ["colder", "kälter", "kaelter", "cooler", "kühler", "kuehler"]):
            thermo(19); return Decision(calls, "Lowering the temperature.")
        if any(k in t for k in ["cold", "kalt", "wärmer", "waermer", "warmer", "heat", "heizen"]):
            thermo(23); return Decision(calls, "Warming it up.")

        # --- locks ----------------------------------------------------------
        if any(k in t for k in ["unlock", "aufschließen", "aufschliessen", "entriegel"]):
            lock(False); return Decision(calls, "Unlocking.")
        if any(k in t for k in ["lock", "verriegel", "abschließen", "abschliessen", "zuschließen"]):
            lock(True); return Decision(calls, "Locking up.")

        # --- lights ---------------------------------------------------------
        if any(k in t for k in ["brighter", "heller", "voll hell"]):
            light(on=True, brightness=100); return Decision(calls, "Brightening the lights.")
        if any(k in t for k in ["dim", "dunkler", "darker", "zu hell"]):
            light(brightness=20); return Decision(calls, "Dimming the lights.")
        if any(k in t for k in ["light on", "lights on", "licht an", "lichter an", "einschalten"]):
            light(on=True); return Decision(calls, "Lights on.")
        if any(k in t for k in ["light off", "lights off", "licht aus", "lichter aus", "ausschalten"]):
            light(on=False); return Decision(calls, "Lights off.")

        # --- plugs ----------------------------------------------------------
        if "plug" in t or "steckdose" in t or "stecker" in t:
            on = not any(k in t for k in ["off", "aus"])
            calls.append(ToolCall("control_plug", ({"area": area} if area else {}) | {"on": on}))
            return Decision(calls, f"Plug {'on' if on else 'off'}.")

        # --- status ---------------------------------------------------------
        if any(k in t for k in ["status", "zustand", "what is", "wie ist", "übersicht"]):
            return Decision([], "Current home state:\n" + world_summary)

        return Decision([], "Sorry, I didn't understand that request.")
