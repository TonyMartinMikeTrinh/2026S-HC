"""Semantic model round-trips and topic-filter matching (A-11)."""
from smarthome.core import topics
from smarthome.core.model import Command, DeviceState, DeviceType


def test_state_roundtrip():
    st = DeviceState(device_id="light-1", type=DeviceType.LIGHT,
                     attrs={"on": True, "brightness": 60})
    again = DeviceState.model_validate_json(st.model_dump_json())
    assert again.device_id == "light-1"
    assert again.type is DeviceType.LIGHT
    assert again.attrs == {"on": True, "brightness": 60}


def test_command_roundtrip():
    cmd = Command(command_id="c1", device_id="d1", attrs={"setpoint": 22.0}, source="agent")
    again = Command.model_validate_json(cmd.model_dump_json())
    assert again.command_id == "c1" and again.source == "agent"
    assert again.attrs == {"setpoint": 22.0}


def test_topic_builders():
    assert topics.state("light-1") == "home/devices/light-1/state"
    assert topics.command("light-1") == "home/devices/light-1/command"
    assert topics.announce("light-1") == "home/devices/light-1/announce"


def test_topic_matching():
    assert topics.matches("home/devices/+/state", "home/devices/light-1/state")
    assert not topics.matches("home/devices/+/state", "home/devices/light-1/command")
    assert topics.matches("home/#", "home/anything/deep/here")
    assert not topics.matches("home/devices/+/state", "home/devices/light-1/state/extra")
    assert topics.device_id_from_state("home/devices/light-1/state") == "light-1"
