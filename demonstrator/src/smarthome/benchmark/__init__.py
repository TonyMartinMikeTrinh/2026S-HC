"""Architecture benchmark — compares smart-home *architecture variants*.

The variants differ in where inference runs — **edge / cloud / hybrid** — and the
harness measures, for a fixed natural-language test suite, how each architecture
scores on latency, action correctness, success rate and robustness (behaviour
during a cloud/uplink outage). Results feed the dashboard ``/benchmark`` tab and
the standalone ``python run.py benchmark`` HTML report.
"""
from .architectures import DEFAULT_ORDER, PROFILES, ArchitectureProfile
from .runner import run_benchmark
from .suite import CASES, build_world

__all__ = [
    "ArchitectureProfile",
    "PROFILES",
    "DEFAULT_ORDER",
    "CASES",
    "build_world",
    "run_benchmark",
]
