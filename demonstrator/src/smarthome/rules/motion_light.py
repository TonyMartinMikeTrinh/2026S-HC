"""Motion + darkness -> light on; auto-off after a quiet period."""
from __future__ import annotations

from .base import Rule, RuleContext

OFF_DELAY = 20.0      # seconds of no motion before auto-off
ON_BRIGHTNESS = 80


class MotionLightRule(Rule):
    name = "motion_light"

    def evaluate(self, ctx: RuleContext) -> None:
        # memory: {area: last_motion_ts} for areas the rule switched on
        auto_on: dict = ctx.memory.setdefault("auto_on", {})

        for sensor in ctx.devices(type="motion_sensor"):
            dark = sensor.attrs.get("illuminance", 1000) < 50
            if sensor.attrs.get("motion") and dark:
                for light in ctx.devices(type="light", area=sensor.area):
                    if not light.attrs.get("on"):
                        ctx.command(light.device_id, on=True, brightness=ON_BRIGHTNESS)
                        ctx.event(f"motion in {sensor.area} -> light on",
                                  light.device_id)
                    auto_on[light.device_id] = ctx.now

        # auto-off lights we turned on, once their area has been quiet long enough
        for light_id, ts in list(auto_on.items()):
            light = ctx.get(light_id)
            if light is None or not light.attrs.get("on"):
                auto_on.pop(light_id, None)
                continue
            motion_now = any(s.attrs.get("motion") for s in
                             ctx.devices(type="motion_sensor", area=light.area))
            if motion_now:
                auto_on[light_id] = ctx.now
            elif ctx.now - ts >= OFF_DELAY:
                ctx.command(light_id, on=False)
                ctx.event(f"no motion in {light.area} -> light off", light_id)
                auto_on.pop(light_id, None)
