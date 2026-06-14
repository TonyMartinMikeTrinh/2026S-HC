"""Energy: sustained high power draw on a smart plug -> alert (on threshold cross)."""
from __future__ import annotations

from .base import Rule, RuleContext

THRESHOLD_W = 2000.0


class HighPowerRule(Rule):
    name = "high_power"

    def evaluate(self, ctx: RuleContext) -> None:
        over: set = ctx.memory.setdefault("over", set())
        for plug in ctx.devices(type="smart_plug"):
            power = plug.attrs.get("power_w", 0.0)
            if power > THRESHOLD_W and plug.device_id not in over:
                ctx.alert(f"high power draw on '{plug.name}': {power:.0f} W",
                          plug.device_id, {"power_w": power})
                over.add(plug.device_id)
            elif power <= THRESHOLD_W:
                over.discard(plug.device_id)
