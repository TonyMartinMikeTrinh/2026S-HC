"""Semantic MQTT topic scheme + topic-filter matching.

Devices are addressed by their stable ``device_id``; the human-facing ``area``
travels as metadata inside the payload, so addressing never depends on where a
device is grouped.

    home/devices/<device_id>/state          retained  device state snapshot
    home/devices/<device_id>/descriptor     retained  static identity/capabilities
    home/devices/<device_id>/command                  command to a device
    home/devices/<device_id>/availability   retained  online/offline (LWT)
    home/devices/<device_id>/announce       retained  identity + fingerprint
    home/registry/inventory                 retained  full inventory snapshot
    home/events                                       automation / alerts / lifecycle
    home/agent/request                                natural-language request
    home/agent/audit                                  agent decision audit trail
    home/controller/leader                  retained  controller leader lease
"""
from __future__ import annotations

from .config import TOPIC_PREFIX

P = TOPIC_PREFIX


def state(device_id: str) -> str:
    return f"{P}/devices/{device_id}/state"


def descriptor(device_id: str) -> str:
    return f"{P}/devices/{device_id}/descriptor"


def command(device_id: str) -> str:
    return f"{P}/devices/{device_id}/command"


def availability(device_id: str) -> str:
    return f"{P}/devices/{device_id}/availability"


def announce(device_id: str) -> str:
    return f"{P}/devices/{device_id}/announce"


# Wildcard subscriptions ----------------------------------------------------
ALL_STATES = f"{P}/devices/+/state"
ALL_DESCRIPTORS = f"{P}/devices/+/descriptor"
ALL_AVAILABILITY = f"{P}/devices/+/availability"
ALL_ANNOUNCES = f"{P}/devices/+/announce"

INVENTORY = f"{P}/registry/inventory"
EVENTS = f"{P}/events"
AGENT_REQUEST = f"{P}/agent/request"
AGENT_AUDIT = f"{P}/agent/audit"
CONTROLLER_LEADER = f"{P}/controller/leader"


def device_id_from_state(topic: str) -> str:
    """Extract ``<device_id>`` from a ``home/devices/<id>/state`` topic."""
    return topic.split("/")[2]


def matches(topic_filter: str, topic: str) -> bool:
    """Return True if an MQTT ``topic`` matches a subscription ``topic_filter``
    (supporting the ``+`` single-level and ``#`` multi-level wildcards)."""
    f = topic_filter.split("/")
    t = topic.split("/")
    for i, part in enumerate(f):
        if part == "#":
            return True
        if i >= len(t):
            return False
        if part == "+":
            continue
        if part != t[i]:
            return False
    return len(f) == len(t)
