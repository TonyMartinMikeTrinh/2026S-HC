"""Security: door unlocked while it's dark/night -> raise an alert (once)."""
from __future__ import annotations

from .base import Rule, RuleContext


class NightLockRule(Rule):
    name = "night_lock"

    def evaluate(self, ctx: RuleContext) -> None:
        alerted: set = ctx.memory.setdefault("alerted", set())
        dark = ctx.is_dark()
        for lock in ctx.devices(type="door_lock"):
            unlocked = not lock.attrs.get("locked", True)
            if unlocked and dark and lock.device_id not in alerted:
                ctx.alert(f"door '{lock.name}' unlocked while dark", lock.device_id)
                alerted.add(lock.device_id)
            elif not unlocked:
                alerted.discard(lock.device_id)   # re-arm once re-locked
