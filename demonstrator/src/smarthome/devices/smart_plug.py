"""Simulated metering smart plug (OnOff + live power / energy)."""
from __future__ import annotations

import random

from ..core.model import DeviceType
from .base import SimulatedDevice, run_device


class SmartPlug(SimulatedDevice):
    device_type = DeviceType.SMART_PLUG
    capabilities = ["onoff", "power_w", "energy_kwh"]
    base_watts = 800.0

    def initial_attrs(self) -> dict:
        self._last_pub_power = 0.0
        return {"on": False, "power_w": 0.0, "energy_kwh": 0.0}

    def apply_command(self, attrs: dict) -> bool:
        if "on" in attrs:
            on = bool(attrs["on"])
            if on != self.attrs["on"]:
                self.attrs["on"] = on
                return True
        return False

    def step(self, dt: float) -> bool:
        if self.attrs["on"]:
            # Appliance-like draw with the occasional spike (e.g. a heater coil).
            spike = random.choice([0.0, 0.0, 0.0, 1500.0]) if random.random() < 0.05 else 0.0
            self.attrs["power_w"] = round(max(0.0, self.base_watts
                                              + random.uniform(-60, 60) + spike), 1)
        else:
            self.attrs["power_w"] = 0.0
        self.attrs["energy_kwh"] = round(
            self.attrs["energy_kwh"] + self.attrs["power_w"] * dt / 3_600_000.0, 5)
        if abs(self.attrs["power_w"] - self._last_pub_power) >= 50.0:
            self._last_pub_power = self.attrs["power_w"]
            return True
        return False


if __name__ == "__main__":
    run_device(SmartPlug)
