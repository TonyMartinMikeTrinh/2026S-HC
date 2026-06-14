"""Simulated dimmable light (OnOff + brightness)."""
from __future__ import annotations

from ..core.model import DeviceType
from .base import SimulatedDevice, run_device


class Light(SimulatedDevice):
    device_type = DeviceType.LIGHT
    capabilities = ["onoff", "brightness"]

    def initial_attrs(self) -> dict:
        return {"on": False, "brightness": 0}

    def apply_command(self, attrs: dict) -> bool:
        changed = False
        if "brightness" in attrs:
            b = max(0, min(100, int(attrs["brightness"])))
            if b != self.attrs["brightness"]:
                self.attrs["brightness"] = b
                self.attrs["on"] = b > 0
                changed = True
        if "on" in attrs:
            on = bool(attrs["on"])
            if on != self.attrs["on"]:
                self.attrs["on"] = on
                # sensible default brightness when switched on without a value
                if on and self.attrs["brightness"] == 0:
                    self.attrs["brightness"] = 80
                if not on:
                    self.attrs["brightness"] = 0
                changed = True
        return changed


if __name__ == "__main__":
    run_device(Light)
