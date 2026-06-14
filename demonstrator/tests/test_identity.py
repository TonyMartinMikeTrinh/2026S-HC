"""Persistent device identity — the basis for re-binding without re-pairing (A-16)."""
from smarthome.core.identity import load_or_create
from smarthome.core.model import DeviceType


def test_identity_is_persistent():
    first = load_or_create("living_room_light", DeviceType.LIGHT)
    second = load_or_create("living_room_light", DeviceType.LIGHT)
    # A reboot must yield the SAME identity, not a new "forgotten" device.
    assert first.device_id == second.device_id
    assert first.secret == second.secret
    assert first.fingerprint == second.fingerprint


def test_fingerprint_is_stable_and_opaque():
    ident = load_or_create("front_door", DeviceType.DOOR_LOCK)
    assert ident.fingerprint == ident.fingerprint
    assert ident.secret not in ident.fingerprint        # not the raw secret
    assert len(ident.fingerprint) == 16


def test_distinct_devices_get_distinct_ids():
    a = load_or_create("dev_a", DeviceType.LIGHT)
    b = load_or_create("dev_b", DeviceType.LIGHT)
    assert a.device_id != b.device_id
