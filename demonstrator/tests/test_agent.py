"""Agent intent resolution + guardrails with the deterministic backend (A-21/A-22)."""
import pytest

from smarthome.core import config
from smarthome.services.agent import Agent


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setattr(config, "AGENT_BACKEND", "rules")
    a = Agent()
    a._descriptors = {
        "l1": {"device_id": "l1", "type": "light", "name": "Lamp",
               "area": "living_room", "protocol": "matter"},
        "lk": {"device_id": "lk", "type": "door_lock", "name": "Door",
               "area": "hallway", "protocol": "matter"},
    }
    a._states = {"l1": {"on": True, "brightness": 80}, "lk": {"locked": False}}
    return a


def _actions(audit):
    return {(x["device_id"], tuple(sorted(x["attrs"].items()))) for x in audit.actions}


def test_good_night_scene(agent):
    audit = agent.handle("good night")
    assert audit.backend == "rules"
    acts = _actions(audit)
    assert ("l1", (("on", False),)) in acts
    assert ("lk", (("locked", True),)) in acts


def test_unrecognised_request_does_nothing(agent):
    audit = agent.handle("hello there, nice weather")
    assert audit.actions == []


def test_status_request_reports_without_acting(agent):
    audit = agent.handle("status")
    assert audit.actions == []
    assert "living_room" in audit.reply


def test_guardrail_rejects_missing_device_type(agent):
    # No thermostat exists -> the set_thermostat intent must be rejected, not crash.
    audit = agent.handle("it's cold in here")
    assert audit.actions == []
    assert any(r.get("reason") == "no matching device" for r in audit.rejected)
