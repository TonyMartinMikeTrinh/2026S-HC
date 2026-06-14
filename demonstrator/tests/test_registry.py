"""Registry persistence + transparent re-bind / mismatch handling (A-16/17/18)."""
from smarthome.core import topics
from smarthome.core.model import Announcement, Availability, DeviceDescriptor, DeviceType
from smarthome.services.registry import Registry


def _announce(device_id, fingerprint, name="Lamp"):
    d = DeviceDescriptor(device_id=device_id, type=DeviceType.LIGHT, name=name,
                         area="living_room", capabilities=["onoff"])
    return Announcement(descriptor=d, fingerprint=fingerprint).model_dump_json().encode()


def test_registry_persists_across_restart():
    reg = Registry()
    reg._on_announce(topics.announce("light-1"), _announce("light-1", "fp123"))
    assert reg._count() == 1
    reg.db.close()

    reg2 = Registry()                          # fresh instance, same DB file
    assert reg2._count() == 1                   # device was NOT forgotten
    reg2.db.close()


def test_registry_rebinds_same_fingerprint_without_duplicate():
    reg = Registry()
    reg._on_announce(topics.announce("light-1"), _announce("light-1", "fp"))
    reg._on_announce(topics.announce("light-1"), _announce("light-1", "fp"))
    assert reg._count() == 1                     # re-bound, not duplicated
    reg.db.close()


def test_registry_rejects_fingerprint_mismatch():
    reg = Registry()
    reg._on_announce(topics.announce("light-1"), _announce("light-1", "good"))
    reg._on_announce(topics.announce("light-1"), _announce("light-1", "evil"))
    assert reg._count() == 1
    assert reg._get("light-1")["fingerprint"] == "good"   # original kept
    reg.db.close()


def test_registry_tracks_availability():
    reg = Registry()
    reg._on_announce(topics.announce("light-1"), _announce("light-1", "fp"))
    av = Availability(device_id="light-1", status="offline").model_dump_json().encode()
    reg._on_availability(topics.availability("light-1"), av)
    assert reg._get("light-1")["status"] == "offline"
    reg.db.close()
