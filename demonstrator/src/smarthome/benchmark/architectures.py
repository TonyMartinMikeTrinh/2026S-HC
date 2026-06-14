"""Architecture variants (edge / cloud / hybrid) and their inference backends.

A profile is a transparent *model* of an architecture's inference path: where the
model runs, the simulated network round-trip, a relative compute factor for the
device class, whether the variant breaks during a cloud outage, whether personal
data leaves the home, and whether it can fall back locally. The latency figures
are modelled (and seeded for reproducibility), not wall-clock measured, because
the default backends are deterministic mock models.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ..llm.base import Decision, LLMBackend, ToolCall
from ..llm.rule_backend import RuleBackend, _area


@dataclass(frozen=True)
class ArchitectureProfile:
    key: str
    label: str
    site: str
    description: str
    net_latency_ms: float       # simulated round-trip to the inference site (0 = local)
    compute_scale: float        # compute time multiplier for the device class
    cloud_dependent: bool       # requests fail outright during a cloud/uplink outage
    data_egress: bool           # personal data leaves the home
    has_fallback: bool          # degrades to the on-device model instead of failing

    @property
    def primary_is_cloud(self) -> bool:
        return self.net_latency_ms > 0

    def public_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "site": self.site,
            "description": self.description, "net_latency_ms": self.net_latency_ms,
            "cloud_dependent": self.cloud_dependent, "data_egress": self.data_egress,
            "has_fallback": self.has_fallback,
        }


PROFILES: dict[str, ArchitectureProfile] = {
    "edge": ArchitectureProfile(
        key="edge", label="Edge / On-device", site="On-device NPU",
        description=("Inference runs entirely on the device/hub. No network hop, "
                     "no cloud dependency and no data leaves the home — but a "
                     "small, constrained model with limited language coverage."),
        net_latency_ms=0.0, compute_scale=1.7, cloud_dependent=False,
        data_egress=False, has_fallback=False),
    "cloud": ArchitectureProfile(
        key="cloud", label="Cloud", site="Cloud datacenter",
        description=("Requests go to a large model in the cloud — highest "
                     "capability, but adds network latency, sends data "
                     "off-premises and is unavailable during an internet/cloud "
                     "outage."),
        net_latency_ms=130.0, compute_scale=0.5, cloud_dependent=True,
        data_egress=True, has_fallback=False),
    "hybrid": ArchitectureProfile(
        key="hybrid", label="Hybrid (cloud + edge fallback)", site="Cloud, edge on outage",
        description=("Uses the capable cloud model when reachable and "
                     "transparently falls back to the on-device model during an "
                     "outage — staying available with graceful degradation."),
        net_latency_ms=130.0, compute_scale=0.5, cloud_dependent=False,
        data_egress=True, has_fallback=True),
}

DEFAULT_ORDER = ["edge", "cloud", "hybrid"]


# --- backends --------------------------------------------------------------
class CloudBackend(RuleBackend):
    """A *simulated* capable cloud LLM.

    Models a large, general model that the constrained on-device parser is not:
    it tells questions apart from commands, parses quantitative phrasings
    ("to 30%", "to 21 degrees"), handles explicit on/off-with-area light commands
    and a few extra comfort synonyms. Anything it does not specifically handle is
    delegated to the on-device parser (:class:`RuleBackend`), so its coverage is a
    strict superset of the edge model's. Set ``SH_BENCH_CLOUD_MODEL`` with a
    running Ollama to benchmark a real model instead (see :func:`make_cloud_backend`).
    """

    name = "cloud-sim"

    def decide(self, text: str, world_summary: str) -> Decision:
        t = text.lower().strip()

        # A capable model answers questions instead of executing them.
        if t.endswith("?"):
            return Decision([], "Current home state:\n" + world_summary)

        area = _area(t)
        light_word = any(w in t for w in ("light", "lights", "licht", "lamp", "lampe"))

        # "... to N%" -> set brightness
        m = re.search(r"(\d{1,3})\s*%", t)
        if m and (light_word or any(w in t for w in ("dim", "bright", "hell"))):
            b = max(0, min(100, int(m.group(1))))
            return Decision([ToolCall("control_light",
                                      ({"area": area} if area else {}) | {"brightness": b})],
                            f"Setting brightness to {b}%.")

        # "... to N degrees / N°" -> set thermostat
        m = re.search(r"(\d{1,2}(?:\.\d)?)\s*(?:°|degree|degrees|grad)", t)
        if not m and ("temperature" in t or "temperatur" in t):
            m = re.search(r"to\s+(\d{1,2}(?:\.\d)?)", t)
        if m and any(w in t for w in ("temp", "thermostat", "degree", "grad", "°")):
            sp = float(m.group(1))
            return Decision([ToolCall("set_thermostat",
                                      ({"area": area} if area else {}) | {"setpoint": sp})],
                            f"Setting the temperature to {sp:g}°C.")

        # explicit on/off of a named light ("turn on the kitchen light")
        if light_word:
            if any(k in t for k in ("turn on", "switch on", "anschalt", "einschalt")) \
                    and "off" not in t and "aus" not in t:
                return Decision([ToolCall("control_light",
                                          ({"area": area} if area else {}) | {"on": True})],
                                "Turning the light on.")
            if any(k in t for k in ("turn off", "switch off", "off", "aus")):
                return Decision([ToolCall("control_light",
                                          ({"area": area} if area else {}) | {"on": False})],
                                "Turning the light off.")

        # extra comfort synonyms the small parser lacks
        if any(k in t for k in ("chilly", "freezing", "frostig", "fröstel", "froestel")):
            return Decision([ToolCall("set_thermostat",
                                      ({"area": area} if area else {}) | {"setpoint": 23})],
                            "Warming it up.")

        # everything else: inherit the on-device parser's full capability set
        return super().decide(text, world_summary)


def make_edge_backend() -> LLMBackend:
    """The constrained on-device model (deterministic keyword parser)."""
    return RuleBackend()


def make_cloud_backend() -> LLMBackend:
    """The capable cloud model.

    Uses a real Ollama model when ``SH_BENCH_CLOUD_MODEL`` is set and the server
    is reachable; otherwise the deterministic :class:`CloudBackend` simulation so
    the benchmark always runs (and stays reproducible)."""
    model = os.getenv("SH_BENCH_CLOUD_MODEL")
    if model:
        try:
            from ..llm.ollama_backend import OllamaBackend
            backend = OllamaBackend(model=model)
            if backend.available():
                return backend
        except Exception:  # noqa: BLE001 — fall back to the simulation
            pass
    return CloudBackend()
