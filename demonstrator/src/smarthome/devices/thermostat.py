"""Simulated thermostat with a small thermal model.

The measured ``temperature`` lags towards the ``setpoint`` while heating and
towards ambient while off, with a little sensor noise — so the telemetry looks
like a real, slowly-changing physical quantity rather than a step function.
"""
from __future__ import annotations

import random

from ..core.model import DeviceType
from .base import SimulatedDevice, run_device

AMBIENT = 18.0


class Thermostat(SimulatedDevice):
    device_type = DeviceType.THERMOSTAT
    capabilities = ["temperature", "setpoint", "mode"]

    def initial_attrs(self) -> dict:
        self._last_pub_temp = 19.5
        return {"temperature": 19.5, "setpoint": 21.0, "mode": "heat", "humidity": 45}

    def apply_command(self, attrs: dict) -> bool:
        changed = False
        if "setpoint" in attrs:
            sp = round(max(5.0, min(30.0, float(attrs["setpoint"]))), 1)
            if sp != self.attrs["setpoint"]:
                self.attrs["setpoint"] = sp
                changed = True
        if "mode" in attrs and attrs["mode"] in ("heat", "off"):
            if attrs["mode"] != self.attrs["mode"]:
                self.attrs["mode"] = attrs["mode"]
                changed = True
        return changed

    def step(self, dt: float) -> bool:
        if self.attrs["mode"] == "heat":
            target, k = self.attrs["setpoint"], 0.06
        else:
            target, k = AMBIENT, 0.03
        temp = self.attrs["temperature"]
        temp += (target - temp) * k * dt + random.uniform(-0.04, 0.04)
        self.attrs["temperature"] = round(temp, 2)
        # Report only on a perceptible change; the heartbeat covers steady state.
        if abs(self.attrs["temperature"] - self._last_pub_temp) >= 0.1:
            self._last_pub_temp = self.attrs["temperature"]
            return True
        return False


if __name__ == "__main__":
    run_device(Thermostat)
