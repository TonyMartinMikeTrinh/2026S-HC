"""Architecture benchmark: determinism, the edge-vs-cloud trade-off, robustness."""
import json

import pytest

from smarthome.benchmark import run_benchmark
from smarthome.benchmark.architectures import PROFILES
from smarthome.benchmark.report import render_report_html
from smarthome.benchmark.suite import (
    CANONICAL_ROOMS,
    MAX_DEVICES,
    MAX_ROOMS,
    build_world,
    world_dimensions,
)


@pytest.fixture
def report():
    return run_benchmark(seed=42)


def _by_key(report):
    return {a.profile["key"]: a for a in report.architectures}


def test_all_default_architectures_present(report):
    keys = {a.profile["key"] for a in report.architectures}
    assert keys == set(PROFILES)


def test_deterministic_for_a_fixed_seed():
    # Same seed -> byte-identical results (latency model + scoring are pure).
    assert run_benchmark(seed=7).to_dict() == run_benchmark(seed=7).to_dict()


def test_cloud_model_is_at_least_as_capable_as_edge(report):
    archs = _by_key(report)
    # The cloud model is a strict superset of the on-device parser.
    assert archs["cloud"].normal.success_pct > archs["edge"].normal.success_pct


def test_cloud_adds_network_latency(report):
    archs = _by_key(report)
    assert archs["cloud"].normal.avg_latency_ms > archs["edge"].normal.avg_latency_ms


def test_edge_is_unaffected_by_a_cloud_outage(report):
    edge = _by_key(report)["edge"]
    assert edge.outage.availability_pct == 100.0
    assert edge.outage.success_pct == edge.normal.success_pct


def test_cloud_only_collapses_during_an_outage(report):
    cloud = _by_key(report)["cloud"]
    assert cloud.outage.availability_pct == 0.0
    assert cloud.outage.success_pct == 0.0


def test_hybrid_stays_available_but_degrades_to_edge(report):
    archs = _by_key(report)
    hybrid, edge = archs["hybrid"], archs["edge"]
    assert hybrid.outage.availability_pct == 100.0            # graceful degradation
    assert hybrid.outage.success_pct == edge.normal.success_pct  # falls back to edge model
    assert hybrid.normal.success_pct == archs["cloud"].normal.success_pct


def test_subset_selection(report):
    only_edge = run_benchmark(arch_keys=["edge"])
    assert [a.profile["key"] for a in only_edge.architectures] == ["edge"]
    # Unknown keys are ignored; empty selection falls back to the full default set.
    assert len(run_benchmark(arch_keys=["nonsense"]).architectures) == len(PROFILES)


def test_report_is_json_serialisable(report):
    json.dumps(report.to_dict())  # must not raise


def test_default_world_is_the_baseline_topology():
    devices, rooms = world_dimensions(build_world())
    assert (devices, rooms) == (10, 4)


def test_canonical_rooms_always_present_even_when_growing():
    world = build_world(rooms=10, devices=30)
    areas = {d["area"] for d in world}
    assert set(CANONICAL_ROOMS) <= areas


def test_world_size_is_configurable_and_clamped():
    devices, rooms = world_dimensions(build_world(rooms=8, devices=24))
    assert rooms == 8 and devices == 24
    # devices clamped up to the structural minimum the room count needs
    d, r = world_dimensions(build_world(rooms=12, devices=10))
    assert r == 12 and d >= 10
    # both dimensions clamped to their maxima
    d, r = world_dimensions(build_world(rooms=999, devices=999))
    assert r == MAX_ROOMS and d == MAX_DEVICES


def test_success_rate_is_independent_of_home_size():
    # Capability is about the model, not the number of devices/rooms.
    small = _by_key(run_benchmark(seed=42, rooms=4, devices=10))
    large = _by_key(run_benchmark(seed=42, rooms=10, devices=35))
    for key in PROFILES:
        assert small[key].normal.success_pct == large[key].normal.success_pct


def test_latency_grows_with_home_size():
    small = _by_key(run_benchmark(seed=42, rooms=4, devices=10))
    large = _by_key(run_benchmark(seed=42, rooms=10, devices=35))
    assert large["edge"].normal.avg_latency_ms > small["edge"].normal.avg_latency_ms


def test_report_records_world_dimensions():
    rep = run_benchmark(seed=42, rooms=6, devices=20)
    assert rep.world_rooms == 6 and rep.world_devices == 20


def test_renders_full_page_and_fragment(report):
    page = render_report_html(report, full_page=True)
    frag = render_report_html(report, full_page=False)
    assert page.lstrip().startswith("<!doctype html>")
    assert not frag.lstrip().startswith("<!doctype html>")
    assert "Per-prompt results" in frag
    assert "Edge / On-device" in frag
