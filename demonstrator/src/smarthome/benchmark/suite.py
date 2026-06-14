"""Fixed test world + natural-language test suite with gold-standard intents.

The *world* mirrors the demonstrator's default 10-device topology so the
guardrailed resolver (:mod:`smarthome.services.guardrails`) expands intents onto
exactly the devices the live system would have.

Each :class:`Case` carries its expected ("gold") abstract tool calls. Correctness
is scored by resolving both the gold and the predicted tool calls against the
world and comparing the resulting *device-command sets* — so a backend is right
iff it would have driven the same devices to the same attributes, regardless of
phrasing. Several prompts are deliberately beyond the constrained on-device
parser (e.g. quantitative phrasings, question vs. command) to expose the
edge-vs-cloud capability trade-off.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from ..llm.base import ToolCall

# (type, device_id, area, name, protocol) — mirrors cli.DEFAULT_TOPOLOGY
# (the kitchen zigbee light is normalised onto type "light" by the bridge).
WORLD_TOPOLOGY = [
    ("light",         "living_room_light",      "living_room", "Floor Lamp",              "matter"),
    ("motion_sensor", "living_room_motion",     "living_room", "Living Room PIR",         "matter"),
    ("thermostat",    "living_room_thermostat", "living_room", "Living Room Thermostat",  "matter"),
    ("smart_plug",    "living_room_tv_plug",    "living_room", "TV Plug",                 "matter"),
    ("light",         "kitchen_zigbee_light",   "kitchen",     "Kitchen Light (Zigbee)",  "zigbee"),
    ("motion_sensor", "kitchen_motion",         "kitchen",     "Kitchen PIR",             "matter"),
    ("light",         "bedroom_light",          "bedroom",     "Bedroom Light",           "matter"),
    ("thermostat",    "bedroom_thermostat",     "bedroom",     "Bedroom Thermostat",      "matter"),
    ("door_lock",     "front_door_lock",        "hallway",     "Front Door",              "matter"),
    ("motion_sensor", "hallway_motion",         "hallway",     "Hallway PIR",             "matter"),
]

# Plausible default live attributes per type (used for the world-state summary).
_DEFAULT_ATTRS = {
    "light":         {"on": False, "brightness": 0},
    "thermostat":    {"temperature": 19.5, "setpoint": 21.0, "mode": "heat"},
    "motion_sensor": {"motion": False, "illuminance": 120},
    "door_lock":     {"locked": True, "battery": 95},
    "smart_plug":    {"on": False, "power_w": 0.0},
}

# The four rooms the test suite addresses are always present (so area-specific
# prompts stay meaningful); extra rooms are appended from this pool.
CANONICAL_ROOMS = ["living_room", "kitchen", "bedroom", "hallway"]
EXTRA_ROOMS = ["office", "bathroom", "garage", "guest_room",
               "study", "basement", "garden", "nursery"]
# Device types used to grow the home (locks are intentionally not auto-added).
FILL_TYPES = ["light", "smart_plug", "thermostat", "motion_sensor"]

MIN_ROOMS, MAX_ROOMS = len(CANONICAL_ROOMS), len(CANONICAL_ROOMS) + len(EXTRA_ROOMS)
MAX_DEVICES = 40


def _device(dtype: str, did: str, area: str, name: str, proto: str = "matter") -> dict:
    return {"device_id": did, "type": dtype, "area": area, "name": name,
            "protocol": proto, "attrs": dict(_DEFAULT_ATTRS.get(dtype, {}))}


def build_world(rooms: int = MIN_ROOMS, devices: int | None = None) -> list[dict]:
    """Build a device world of roughly ``devices`` devices across ``rooms`` rooms.

    The canonical four rooms and the baseline 10-device topology are always
    included so the test suite resolves identically; ``rooms`` adds extra rooms
    (each seeded with a light + motion sensor) and ``devices`` tops the home up
    with additional devices (round-robin over rooms and types). ``devices`` is
    clamped to at least the structural minimum the chosen room count requires, so
    the returned size may exceed a very small request — callers read the real
    counts back from the resulting world."""
    rooms = max(MIN_ROOMS, min(MAX_ROOMS, int(rooms)))

    # 1) baseline topology (covers all canonical rooms the suite references)
    world = [_device(dtype, did, area, name, proto)
             for dtype, did, area, name, proto in WORLD_TOPOLOGY]
    room_list = list(CANONICAL_ROOMS)

    # 2) extra rooms, each seeded with a light + a motion sensor
    for i in range(MIN_ROOMS, rooms):
        area = EXTRA_ROOMS[i - MIN_ROOMS]
        room_list.append(area)
        disp = area.replace("_", " ").title()
        world.append(_device("light", f"{area}_light", area, f"{disp} Light"))
        world.append(_device("motion_sensor", f"{area}_motion", area, f"{disp} PIR"))

    # 3) top up to the requested device count, round-robin over rooms + types
    target = len(world) if devices is None else max(len(world),
                                                    min(MAX_DEVICES, int(devices)))
    rooms_cycle = itertools.cycle(room_list)
    types_cycle = itertools.cycle(FILL_TYPES)
    counters: dict[tuple[str, str], int] = {}
    while len(world) < target:
        area, dtype = next(rooms_cycle), next(types_cycle)
        n = counters.get((area, dtype), 0) + 1
        counters[(area, dtype)] = n
        disp = area.replace("_", " ").title()
        world.append(_device(dtype, f"{area}_{dtype}_{n}", area,
                             f"{disp} {dtype.replace('_', ' ').title()} {n}"))
    return world


def world_dimensions(world: list[dict]) -> tuple[int, int]:
    """Return ``(device_count, room_count)`` for a built world."""
    return len(world), len({d["area"] for d in world})


@dataclass(frozen=True)
class Case:
    id: str
    text: str
    gold: tuple[ToolCall, ...]      # expected abstract intents (may be empty)
    note: str = ""                  # what the case exercises


def _tc(name: str, **args) -> ToolCall:
    return ToolCall(name=name, arguments=args)


# The suite: scenes, single commands, quantitative phrasings, a question, and an
# intentionally ambiguous prompt. Roughly a third are beyond the edge parser.
CASES: list[Case] = [
    Case("c01", "good night",
         (_tc("control_light", on=False), _tc("control_lock", lock=True)),
         "multi-action scene"),
    Case("c02", "guten morgen",
         (_tc("control_light", on=True, brightness=70), _tc("set_thermostat", setpoint=22)),
         "German scene"),
    Case("c03", "make it cozy",
         (_tc("control_light", on=True, brightness=35), _tc("set_thermostat", setpoint=22)),
         "scene"),
    Case("c04", "it's cold in here",
         (_tc("set_thermostat", setpoint=23),),
         "comfort -> all thermostats"),
    Case("c05", "unlock the front door",
         (_tc("control_lock", lock=False),),
         "lock control"),
    Case("c06", "lights off",
         (_tc("control_light", on=False),),
         "all lights off"),
    Case("c07", "turn on the kitchen light",
         (_tc("control_light", area="kitchen", on=True),),
         "explicit on + area (edge miss)"),
    Case("c08", "set the bedroom light to 30%",
         (_tc("control_light", area="bedroom", brightness=30),),
         "quantitative brightness (edge miss)"),
    Case("c09", "set the temperature to 21 degrees",
         (_tc("set_thermostat", setpoint=21),),
         "quantitative setpoint (edge miss)"),
    Case("c10", "turn off the tv plug in the living room",
         (_tc("control_plug", area="living_room", on=False),),
         "plug + area"),
    Case("c11", "dim the living room lights",
         (_tc("control_light", area="living_room", brightness=20),),
         "dim + area"),
    Case("c12", "status",
         (),
         "status query -> no action"),
    Case("c13", "movie night",
         (_tc("control_light", on=True, brightness=35), _tc("set_thermostat", setpoint=22)),
         "scene synonym"),
    Case("c14", "lock everything",
         (_tc("control_lock", lock=True),),
         "lock all"),
    Case("c15", "is the front door locked?",
         (),
         "question, NOT a command (edge false-positive)"),
    Case("c16", "I'm feeling chilly in the bedroom",
         (_tc("set_thermostat", area="bedroom", setpoint=23),),
         "comfort synonym + area (edge miss)"),
    Case("c17", "make the whole house warm and bright for the party",
         (_tc("control_light", on=True, brightness=100), _tc("set_thermostat", setpoint=23)),
         "ambiguous multi-intent (hard for both)"),
]
