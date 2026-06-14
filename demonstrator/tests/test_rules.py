"""Automation rule logic, exercised through RuleContext (A-14)."""
from smarthome.rules.base import DeviceView, RuleContext
from smarthome.rules.energy import HighPowerRule
from smarthome.rules.motion_light import MotionLightRule
from smarthome.rules.security import NightLockRule
from smarthome.services.controller import discover_rules


def make_ctx(world, now=100.0, memory=None):
    cmds, events = [], []
    ctx = RuleContext(
        world=world, now=now, memory=memory if memory is not None else {},
        _command=lambda did, attrs: (cmds.append((did, attrs)) or True),
        _event=lambda kind, msg, did, data: events.append((kind, msg, did)))
    return ctx, cmds, events


def dv(device_id, type, area, attrs):
    return DeviceView(device_id=device_id, type=type, area=area,
                      name=device_id, protocol="matter", attrs=attrs)


def test_motion_light_turns_on_when_dark():
    world = {
        "m1": dv("m1", "motion_sensor", "living_room", {"motion": True, "illuminance": 5}),
        "l1": dv("l1", "light", "living_room", {"on": False, "brightness": 0}),
    }
    ctx, cmds, _ = make_ctx(world)
    MotionLightRule().evaluate(ctx)
    assert ("l1", {"on": True, "brightness": 80}) in cmds


def test_motion_light_stays_off_when_bright():
    world = {
        "m1": dv("m1", "motion_sensor", "living_room", {"motion": True, "illuminance": 400}),
        "l1": dv("l1", "light", "living_room", {"on": False, "brightness": 0}),
    }
    ctx, cmds, _ = make_ctx(world)
    MotionLightRule().evaluate(ctx)
    assert cmds == []


def test_night_lock_alerts_when_unlocked_and_dark():
    world = {
        "m1": dv("m1", "motion_sensor", "hallway", {"motion": False, "illuminance": 5}),
        "lk": dv("lk", "door_lock", "hallway", {"locked": False}),
    }
    ctx, _, events = make_ctx(world)
    NightLockRule().evaluate(ctx)
    assert any(kind == "alert" for kind, _, _ in events)


def test_high_power_alerts_once_on_threshold_cross():
    world = {"p1": dv("p1", "smart_plug", "living_room", {"power_w": 2500.0})}
    memory: dict = {}
    ctx, _, events = make_ctx(world, memory=memory)
    HighPowerRule().evaluate(ctx)
    assert len(events) == 1
    # Second evaluation while still over threshold must not re-alert.
    ctx2, _, events2 = make_ctx(world, memory=memory)
    HighPowerRule().evaluate(ctx2)
    assert events2 == []


def test_rule_autodiscovery_finds_all_plugins():
    names = {r.name for r in discover_rules()}
    assert {"motion_light", "night_lock", "high_power"} <= names
