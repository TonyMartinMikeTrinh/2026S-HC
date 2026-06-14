"""Benchmark harness: run the suite through each architecture and score it.

For every architecture and both scenarios (normal / cloud-outage) it resolves the
backend's predicted tool calls and the gold tool calls against the fixed world
(applying the same A-22 guardrails as the live agent), then reports:

* **availability** — share of requests the architecture could serve at all,
* **accuracy** — correct actions among the requests it served,
* **success rate** — correct actions over the whole suite (unserved = failure),
* **latency** — modelled per-request, seeded for reproducibility.

The harness is self-contained: it needs neither the MQTT broker nor any running
component, so it is fast and deterministic.
"""
from __future__ import annotations

import datetime as _dt
import math
import random
from dataclasses import asdict, dataclass, field

from ..llm.base import ALLOWED_TOOLS, LLMBackend
from ..services.guardrails import resolve_tool_call, summarize_world
from .architectures import (
    DEFAULT_ORDER,
    PROFILES,
    ArchitectureProfile,
    make_cloud_backend,
    make_edge_backend,
)
from .suite import CASES, Case, build_world, world_dimensions

MODES = ("normal", "outage")


# --- result data structures ------------------------------------------------
@dataclass
class CaseResult:
    id: str
    text: str
    served: bool
    correct: bool
    latency_ms: float | None
    backend: str
    note: str


@dataclass
class ScenarioResult:
    mode: str
    availability_pct: float
    accuracy_pct: float
    success_pct: float
    avg_latency_ms: float
    p95_latency_ms: float
    cases: list[CaseResult] = field(default_factory=list)


@dataclass
class ArchResult:
    profile: dict
    normal: ScenarioResult
    outage: ScenarioResult


@dataclass
class BenchmarkReport:
    generated_at: str
    seed: int
    suite_size: int
    world_devices: int
    world_rooms: int
    architectures: list[ArchResult]

    def to_dict(self) -> dict:
        return asdict(self)


# --- scoring helpers -------------------------------------------------------
def _action_set(tool_calls, world: list[dict]) -> set[tuple[str, frozenset]]:
    """Resolve abstract tool calls into a comparable set of device commands."""
    acts: set[tuple[str, frozenset]] = set()
    for call in tool_calls:
        if call.name not in ALLOWED_TOOLS:
            continue
        for device_id, attrs in resolve_tool_call(call, world):
            acts.add((device_id, frozenset(attrs.items())))
    return acts


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return round(s[int(k)], 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def _modelled_latency(profile: ArchitectureProfile, case: Case, cloud_path: bool,
                      n_devices: int, rng: random.Random) -> float:
    """Reproducible per-request latency: compute (device-class scaled) + network.

    Grows mildly with the home size (more devices to reason over / address)."""
    base = 25.0 + 3.0 * len(case.text.split()) + 0.6 * n_devices
    latency = base * profile.compute_scale
    if cloud_path:
        latency += profile.net_latency_ms
    latency += rng.uniform(-8.0, 8.0)
    return round(max(1.0, latency), 1)


# --- scenario execution ----------------------------------------------------
def _run_scenario(profile: ArchitectureProfile, mode: str, world: list[dict],
                  summary: str, edge: LLMBackend, cloud: LLMBackend,
                  seed: int) -> ScenarioResult:
    cloud_up = mode == "normal"
    n_devices = len(world)
    rng = random.Random(f"{seed}|{profile.key}|{mode}")

    # Pick the serving path for this scenario from the profile's fields.
    served = True
    if not profile.primary_is_cloud:                 # edge-primary: always local
        backend, cloud_path = edge, False
    elif cloud_up:                                   # cloud reachable: use cloud
        backend, cloud_path = cloud, True
    elif profile.has_fallback:                       # outage + hybrid: degrade local
        backend, cloud_path = edge, False
    else:                                            # outage + cloud-only: unavailable
        backend, cloud_path, served = edge, False, False

    results: list[CaseResult] = []
    for case in CASES:
        if not served:
            results.append(CaseResult(case.id, case.text, served=False, correct=False,
                                      latency_ms=None, backend="(offline)",
                                      note="cloud unreachable"))
            continue
        decision = backend.decide(case.text, summary)
        predicted = _action_set(decision.tool_calls, world)
        gold = _action_set(case.gold, world)
        correct = predicted == gold
        latency = _modelled_latency(profile, case, cloud_path, n_devices, rng)
        results.append(CaseResult(case.id, case.text, served=True, correct=correct,
                                  latency_ms=latency, backend=backend.name, note=case.note))

    n = len(results)
    served_cases = [r for r in results if r.served]
    n_correct = sum(1 for r in results if r.correct)
    lats = [r.latency_ms for r in served_cases if r.latency_ms is not None]
    return ScenarioResult(
        mode=mode,
        availability_pct=round(100.0 * len(served_cases) / n, 1) if n else 0.0,
        accuracy_pct=round(100.0 * n_correct / len(served_cases), 1) if served_cases else 0.0,
        success_pct=round(100.0 * n_correct / n, 1) if n else 0.0,
        avg_latency_ms=round(sum(lats) / len(lats), 1) if lats else 0.0,
        p95_latency_ms=_percentile(lats, 0.95),
        cases=results,
    )


def run_benchmark(arch_keys: list[str] | None = None, seed: int = 42,
                  rooms: int = 4, devices: int | None = None) -> BenchmarkReport:
    """Run the suite for the requested architectures over a configurable world.

    ``rooms`` / ``devices`` size the simulated home (see :func:`build_world`); the
    canonical rooms the suite addresses are always present, so correctness stays
    comparable while latency scales with the home size."""
    keys = [k for k in (arch_keys or DEFAULT_ORDER) if k in PROFILES]
    if not keys:
        keys = list(DEFAULT_ORDER)

    world = build_world(rooms=rooms, devices=devices)
    n_devices, n_rooms = world_dimensions(world)
    summary = summarize_world(world)
    edge, cloud = make_edge_backend(), make_cloud_backend()

    arch_results: list[ArchResult] = []
    for key in keys:
        profile = PROFILES[key]
        arch_results.append(ArchResult(
            profile=profile.public_dict(),
            normal=_run_scenario(profile, "normal", world, summary, edge, cloud, seed),
            outage=_run_scenario(profile, "outage", world, summary, edge, cloud, seed),
        ))

    return BenchmarkReport(
        generated_at=_dt.datetime.now().isoformat(timespec="seconds"),
        seed=seed,
        suite_size=len(CASES),
        world_devices=n_devices,
        world_rooms=n_rooms,
        architectures=arch_results,
    )
