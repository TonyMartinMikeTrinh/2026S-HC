"""Simulated PIR motion sensor with an ambient-light (lux) reading.

Combines occupancy detection with an illuminance value that follows a compressed
day/night cycle, so the "motion AND it's dark -> switch the light on" automation
has something realistic to react to.
"""
from __future__ import annotations

import random

from ..core.model import DeviceType
from .base import SimulatedDevice, run_device

CYCLE_SECONDS = 60.0      # compressed day/night cycle for the demo
DAY_FRACTION = 0.5        # first half of the cycle is "day"
MOTION_HOLD = 8.0         # seconds a detection stays active
P_MOTION_PER_S = 0.06     # probability of a new detection per second


class MotionSensor(SimulatedDevice):
    device_type = DeviceType.MOTION_SENSOR
    capabilities = ["motion", "illuminance"]

    def initial_attrs(self) -> dict:
        self._t = 0.0
        self._day = True
        return {"motion": False, "illuminance": 400, "last_motion": 0.0}

    def _illuminance(self) -> tuple[int, bool]:
        phase = (self._t % CYCLE_SECONDS) / CYCLE_SECONDS
        day = phase < DAY_FRACTION
        lux = 400 if day else 5
        return lux, day

    def step(self, dt: float) -> bool:
        self._t += dt
        changed = False

        lux, day = self._illuminance()
        self.attrs["illuminance"] = lux
        if day != self._day:                 # day/night flip is worth publishing
            self._day = day
            changed = True

        if self.attrs["motion"]:
            if self._t - self.attrs["last_motion"] > MOTION_HOLD:
                self.attrs["motion"] = False
                changed = True
        elif random.random() < P_MOTION_PER_S * dt:
            self._trigger()
            changed = True
        return changed

    def _trigger(self) -> None:
        self.attrs["motion"] = True
        self.attrs["last_motion"] = self._t
        self.emit_event("automation", "motion detected", {"area": self.area})

    def force_motion(self) -> None:
        """Deterministically trigger motion (used by the guided scenario)."""
        with self._lock:
            self._trigger()
        self.publish_state()


if __name__ == "__main__":
    run_device(MotionSensor)
