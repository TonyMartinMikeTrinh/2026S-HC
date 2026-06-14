"""Rule plugin contract + the context handed to rules on each evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class DeviceView:
    device_id: str
    type: str
    area: str
    name: str
    protocol: str
    attrs: dict[str, Any]
    reachable: bool = True


@dataclass
class RuleContext:
    """Read-only world snapshot + side-effect helpers passed to every rule."""
    world: dict[str, DeviceView]
    now: float
    memory: dict[str, Any]                       # per-rule scratch space (persists)
    _command: Callable[[str, dict], bool]
    _event: Callable[[str, str, str | None, dict | None], None]

    def devices(self, *, type: str | None = None,
                area: str | None = None) -> list[DeviceView]:
        out = []
        for dv in self.world.values():
            if type is not None and dv.type != type:
                continue
            if area is not None and dv.area != area:
                continue
            out.append(dv)
        return out

    def get(self, device_id: str) -> DeviceView | None:
        return self.world.get(device_id)

    def is_dark(self, threshold: int = 50) -> bool:
        """Night/dark heuristic from the darkest motion-sensor lux reading."""
        lux = [dv.attrs.get("illuminance", 1000) for dv in self.devices(type="motion_sensor")]
        return bool(lux) and min(lux) < threshold

    def command(self, device_id: str, **attrs: Any) -> bool:
        """Send a desired-state command. Returns True if anything was sent
        (the controller skips it when the device already matches — idempotent)."""
        return self._command(device_id, attrs)

    def alert(self, message: str, device_id: str | None = None,
              data: dict | None = None) -> None:
        self._event("alert", message, device_id, data)

    def event(self, message: str, device_id: str | None = None,
              data: dict | None = None) -> None:
        self._event("automation", message, device_id, data)


class Rule:
    """Base class for automation rules. Subclass + implement :meth:`evaluate`."""
    name: str = "rule"

    def evaluate(self, ctx: RuleContext) -> None:  # pragma: no cover - interface
        raise NotImplementedError
