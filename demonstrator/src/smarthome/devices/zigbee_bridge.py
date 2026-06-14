"""Legacy-Zigbee bridge — protocol abstraction / adapter layer (A-12, A-13).

A real deployment must integrate devices that do *not* speak the common model
natively (Zigbee, Z-Wave, proprietary). This bridge demonstrates that pattern: it
hosts a simulated "legacy" lamp whose interface is Zigbee-Cluster-Library style
(``cluster.attribute = value``, level 0..254) and translates in both directions
onto the unified semantic model (``on`` / ``brightness`` 0..100). To the rest of
the system it is just another light — only its ``protocol`` field reveals the
heterogeneity underneath.
"""
from __future__ import annotations

from ..core.model import DeviceType
from .base import SimulatedDevice, run_device


class _LegacyZigbeeLamp:
    """A device with a deliberately non-standard, cluster-based interface."""

    def __init__(self) -> None:
        self.attributes = {"genOnOff.onOff": 0, "genLevelCtrl.currentLevel": 0}

    def zcl_write(self, cluster: str, attribute: str, value: int) -> None:
        self.attributes[f"{cluster}.{attribute}"] = value

    def zcl_read(self) -> dict:
        return dict(self.attributes)


class ZigbeeBridge(SimulatedDevice):
    device_type = DeviceType.LIGHT
    capabilities = ["onoff", "brightness"]
    protocol = "zigbee"
    component_label = "zigbee-bridge"

    def initial_attrs(self) -> dict:
        self._lamp = _LegacyZigbeeLamp()
        return self._from_zigbee()

    # --- translation -------------------------------------------------------
    def _from_zigbee(self) -> dict:
        raw = self._lamp.zcl_read()
        level = raw["genLevelCtrl.currentLevel"]
        return {"on": bool(raw["genOnOff.onOff"]), "brightness": round(level / 254 * 100)}

    def apply_command(self, attrs: dict) -> bool:
        if "brightness" in attrs:
            level = round(max(0, min(100, int(attrs["brightness"]))) / 100 * 254)
            self._lamp.zcl_write("genLevelCtrl", "currentLevel", level)
            self._lamp.zcl_write("genOnOff", "onOff", 1 if level > 0 else 0)
        if "on" in attrs:
            on = bool(attrs["on"])
            self._lamp.zcl_write("genOnOff", "onOff", 1 if on else 0)
            if on and self._lamp.attributes["genLevelCtrl.currentLevel"] == 0:
                self._lamp.zcl_write("genLevelCtrl", "currentLevel", 200)
            if not on:
                self._lamp.zcl_write("genLevelCtrl", "currentLevel", 0)

        normalized = self._from_zigbee()
        if normalized != self.attrs:
            self.log.info("zigbee translate %s -> %s", self._lamp.zcl_read(), normalized)
            self.attrs = normalized
            return True
        return False


if __name__ == "__main__":
    run_device(ZigbeeBridge)
