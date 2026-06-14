"""Simulated smart door lock (security device)."""
from __future__ import annotations

import random

from ..core.model import DeviceType
from .base import SimulatedDevice, run_device


class DoorLock(SimulatedDevice):
    device_type = DeviceType.DOOR_LOCK
    capabilities = ["lock", "tamper", "battery"]

    def initial_attrs(self) -> dict:
        return {"locked": True, "tamper": False, "battery": 95}

    def apply_command(self, attrs: dict) -> bool:
        changed = False
        if "locked" in attrs:
            locked = bool(attrs["locked"])
            if locked != self.attrs["locked"]:
                self.attrs["locked"] = locked
                changed = True
                self.emit_event("automation",
                                f"door {'locked' if locked else 'unlocked'}")
        return changed

    def step(self, dt: float) -> bool:
        # Battery trickles down very slowly (cosmetic telemetry).
        if random.random() < 0.01 and self.attrs["battery"] > 0:
            self.attrs["battery"] -= 1
            return True
        return False


if __name__ == "__main__":
    run_device(DoorLock)
