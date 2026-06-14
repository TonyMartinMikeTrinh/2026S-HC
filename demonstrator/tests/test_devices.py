"""Device behaviour: idempotent commands (A-08) and Zigbee normalisation (A-12)."""
import uuid

from smarthome.core.model import Command
from smarthome.devices.door_lock import DoorLock
from smarthome.devices.light import Light
from smarthome.devices.smart_plug import SmartPlug
from smarthome.devices.thermostat import Thermostat
from smarthome.devices.zigbee_bridge import ZigbeeBridge


def test_light_command_idempotent():
    light = Light("t_light", "living_room")
    assert light.apply_command({"on": True, "brightness": 60}) is True
    assert light.attrs == {"on": True, "brightness": 60}
    # Re-applying the same desired state changes nothing (idempotent).
    assert light.apply_command({"on": True, "brightness": 60}) is False


def test_thermostat_setpoint_idempotent_and_clamped():
    th = Thermostat("t_thermo", "bedroom")
    assert th.apply_command({"setpoint": 23}) is True
    assert th.attrs["setpoint"] == 23.0
    assert th.apply_command({"setpoint": 23}) is False
    assert th.apply_command({"setpoint": 99}) is True
    assert th.attrs["setpoint"] == 30.0                 # clamped to max


def test_smart_plug_toggle():
    plug = SmartPlug("t_plug", "living_room")
    assert plug.apply_command({"on": True}) is True
    assert plug.apply_command({"on": True}) is False


def test_door_lock_toggle():
    lock = DoorLock("t_lock", "hallway")
    assert lock.attrs["locked"] is True
    assert lock.apply_command({"locked": False}) is True
    assert lock.apply_command({"locked": False}) is False


def test_command_id_dedupe():
    light = Light("t_light2", "living_room")
    cmd_on = Command(command_id="X", device_id=light.device_id, attrs={"on": True})
    light._on_command("t", cmd_on.model_dump_json().encode())
    assert light.attrs["on"] is True
    # Same command_id with a different effect must be ignored (de-duplicated).
    cmd_off = Command(command_id="X", device_id=light.device_id, attrs={"on": False})
    light._on_command("t", cmd_off.model_dump_json().encode())
    assert light.attrs["on"] is True


def test_zigbee_bridge_normalises_to_common_model():
    zb = ZigbeeBridge("t_zb", "kitchen")
    assert zb.protocol == "zigbee"
    assert zb.apply_command({"brightness": 50}) is True
    # 50% maps onto Zigbee level ~127/254 and back; on follows brightness.
    assert zb.attrs["brightness"] == 50
    assert zb.attrs["on"] is True
    assert zb._lamp.attributes["genLevelCtrl.currentLevel"] == 127
