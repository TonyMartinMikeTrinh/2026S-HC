"""Persistent device identity (A-16).

The headline problem from the research: devices get "forgotten" and must be
re-paired. The countermeasure here is twofold:

* Each device persists a stable identity (``device_id`` + a local ``secret``)
  to ``state/identities/<logical_name>.json``. After a reboot the device keeps
  the *same* identity instead of looking like a brand-new device.
* The device proves that identity to the registry with a ``fingerprint`` derived
  from the secret, so the registry can re-bind it transparently — no re-pairing.

Wiping the state directory is the analogue of a factory reset.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid

from pydantic import BaseModel

from . import config
from .model import DeviceType, now


class Identity(BaseModel):
    device_id: str
    logical_name: str
    type: DeviceType
    secret: str          # local credential, never published
    created_at: float

    @property
    def fingerprint(self) -> str:
        """Stable, non-reversible proof of identity presented on announce."""
        return hashlib.sha256(self.secret.encode()).hexdigest()[:16]


def load_or_create(logical_name: str, device_type: DeviceType) -> Identity:
    """Load a persisted identity or create + persist a new one on first run."""
    config.ensure_state_dirs()
    path = config.IDENTITY_DIR / f"{logical_name}.json"
    if path.exists():
        return Identity.model_validate_json(path.read_text(encoding="utf-8"))

    ident = Identity(
        device_id=f"{device_type.value}-{uuid.uuid4().hex[:8]}",
        logical_name=logical_name,
        type=device_type,
        secret=secrets.token_hex(16),
        created_at=now(),
    )
    path.write_text(ident.model_dump_json(indent=2), encoding="utf-8")
    return ident
