"""Common semantic data model — the contract between all components (A-11, A-13).

This is a deliberately small, Matter-cluster-inspired model: a device exposes a
``type`` and a set of ``capabilities``; its live values live in a flat,
semantically named ``attrs`` map (e.g. ``on``, ``brightness``, ``temperature``,
``setpoint``, ``locked``, ``motion``, ``illuminance``, ``power_w``). Heterogeneous
devices (incl. legacy Zigbee behind a bridge) are normalised onto this model so
the rest of the system speaks one language.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from .config import SCHEMA_VERSION


def now() -> float:
    return time.time()


class DeviceType(str, Enum):
    LIGHT = "light"
    THERMOSTAT = "thermostat"
    MOTION_SENSOR = "motion_sensor"
    DOOR_LOCK = "door_lock"
    SMART_PLUG = "smart_plug"


class DeviceDescriptor(BaseModel):
    """Static identity / capabilities of a device (published on announce)."""
    device_id: str
    type: DeviceType
    name: str
    area: str
    manufacturer: str = "ACME"
    model: str = "sim-1"
    protocol: str = "matter"           # "matter" natively, "zigbee" behind a bridge
    capabilities: list[str] = Field(default_factory=list)
    schema_version: str = SCHEMA_VERSION


class DeviceState(BaseModel):
    """Live state snapshot (published retained on every change)."""
    device_id: str
    type: DeviceType
    attrs: dict[str, Any] = Field(default_factory=dict)
    reachable: bool = True
    ts: float = Field(default_factory=now)


class Command(BaseModel):
    """A desired-state command targeted at one device."""
    command_id: str
    device_id: str
    attrs: dict[str, Any] = Field(default_factory=dict)
    source: str = "unknown"            # controller | agent | user | scenario
    ts: float = Field(default_factory=now)


class Announcement(BaseModel):
    """Device announces itself + proves its identity via a credential fingerprint.

    The ``fingerprint`` is derived from a locally persisted secret. A returning
    device presents the *same* fingerprint, which lets the registry re-bind it
    without re-pairing (A-16/A-17)."""
    descriptor: DeviceDescriptor
    fingerprint: str
    ts: float = Field(default_factory=now)


class Availability(BaseModel):
    device_id: str
    status: Literal["online", "offline"]
    ts: float = Field(default_factory=now)


class Event(BaseModel):
    """Cross-cutting event/alert/automation/lifecycle message (home/events)."""
    source: str
    kind: str                          # automation | alert | agent | registry | lifecycle
    message: str
    device_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    ts: float = Field(default_factory=now)


class AgentRequest(BaseModel):
    request_id: str
    text: str
    source: str = "user"
    ts: float = Field(default_factory=now)


class AgentAudit(BaseModel):
    """Audit trail of an agent decision (A-21 guardrails, A-23 audit logging)."""
    request_id: str
    text: str
    backend: str                       # ollama | rules
    actions: list[dict[str, Any]] = Field(default_factory=list)
    rejected: list[dict[str, Any]] = Field(default_factory=list)
    reply: str = ""
    ts: float = Field(default_factory=now)
