"""Persistent device registry — the local Source of Truth (A-16/A-17/A-18).

Directly answers the research's headline failure mode ("devices get forgotten"):

* Device identity, descriptor and binding are **persisted to SQLite**, so they
  survive a registry restart — on startup the inventory is reloaded and
  re-published, nothing is forgotten.
* A returning device proves its identity with a credential **fingerprint**; if it
  matches, the registry **re-binds it transparently (no re-pairing)** and, if the
  device was stale/offline, heals the binding instead of forcing a reset.
* A *mismatching* fingerprint for a known ``device_id`` is flagged as a security
  alert rather than silently trusted (Zero-Trust posture, A-22).

Run standalone::  python -m smarthome.services.registry
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time

from ..core import config, topics
from ..core.model import Announcement, Availability, DeviceState, Event, now
from ..core.mqtt_component import MqttComponent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id   TEXT PRIMARY KEY,
    descriptor  TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    status      TEXT NOT NULL DEFAULT 'unknown'
);
"""


class Registry(MqttComponent):
    def __init__(self) -> None:
        super().__init__("registry", client_id="registry", clean_session=False)
        config.ensure_state_dirs()
        self._db_lock = threading.Lock()
        self.db = sqlite3.connect(config.REGISTRY_DB, check_same_thread=False)
        self.db.execute(_SCHEMA)
        self.db.commit()

        self.on_topic(topics.ALL_ANNOUNCES, self._on_announce)
        self.on_topic(topics.ALL_AVAILABILITY, self._on_availability)
        self.on_topic(topics.ALL_STATES, self._on_state)

    # --- lifecycle ---------------------------------------------------------
    def on_connected(self) -> None:
        known = self._count()
        self.log.info("loaded [b]%d[/] known device(s) from persistent registry", known)
        self._publish_inventory()

    # --- handlers ----------------------------------------------------------
    def _on_announce(self, topic: str, payload: bytes) -> None:
        try:
            ann = Announcement.model_validate_json(payload)
        except Exception:  # noqa: BLE001
            return
        d = ann.descriptor
        row = self._get(d.device_id)
        desc_json = d.model_dump_json()

        if row is None:
            with self._db_lock:
                self.db.execute(
                    "INSERT INTO devices VALUES (?,?,?,?,?,?)",
                    (d.device_id, desc_json, ann.fingerprint, now(), now(), "online"))
                self.db.commit()
            self.log.info("[green]registered new device[/] %s (%s)", d.name, d.device_id)
            self._event("registry", f"registered new device '{d.name}'", d.device_id,
                        {"type": d.type.value, "protocol": d.protocol})
        elif row["fingerprint"] == ann.fingerprint:
            was = row["status"]
            with self._db_lock:
                self.db.execute(
                    "UPDATE devices SET descriptor=?, last_seen=?, status='online' "
                    "WHERE device_id=?", (desc_json, now(), d.device_id))
                self.db.commit()
            healed = " (healed stale session)" if was != "online" else ""
            self.log.info("[cyan]device returned, re-bound without re-pairing[/]%s — %s",
                          healed, d.name)
            self._event("registry", f"'{d.name}' re-bound without re-pairing{healed}",
                        d.device_id)
        else:
            self.log.warning("[red]identity mismatch[/] for %s — rejecting fingerprint",
                             d.device_id)
            self._event("alert", f"identity fingerprint mismatch for '{d.name}'",
                        d.device_id)
        self._publish_inventory()

    def _on_availability(self, topic: str, payload: bytes) -> None:
        try:
            av = Availability.model_validate_json(payload)
        except Exception:  # noqa: BLE001
            return
        if self._get(av.device_id) is None:
            return
        with self._db_lock:
            self.db.execute("UPDATE devices SET status=?, last_seen=? WHERE device_id=?",
                            (av.status, now(), av.device_id))
            self.db.commit()
        self._event("lifecycle", f"device went {av.status}", av.device_id)
        self._publish_inventory()

    def _on_state(self, topic: str, payload: bytes) -> None:
        try:
            st = DeviceState.model_validate_json(payload)
        except Exception:  # noqa: BLE001
            return
        with self._db_lock:
            self.db.execute("UPDATE devices SET last_seen=? WHERE device_id=?",
                            (now(), st.device_id))
            self.db.commit()

    # --- helpers -----------------------------------------------------------
    def _get(self, device_id: str) -> dict | None:
        with self._db_lock:
            cur = self.db.execute(
                "SELECT device_id, descriptor, fingerprint, first_seen, last_seen, "
                "status FROM devices WHERE device_id=?", (device_id,))
            r = cur.fetchone()
        if r is None:
            return None
        keys = ["device_id", "descriptor", "fingerprint", "first_seen", "last_seen", "status"]
        return dict(zip(keys, r))

    def _count(self) -> int:
        with self._db_lock:
            return self.db.execute("SELECT COUNT(*) FROM devices").fetchone()[0]

    def _event(self, kind: str, message: str, device_id: str | None = None,
               data: dict | None = None) -> None:
        self.publish_model(topics.EVENTS, Event(source="registry", kind=kind,
                           message=message, device_id=device_id, data=data or {}))

    def _publish_inventory(self) -> None:
        with self._db_lock:
            rows = self.db.execute(
                "SELECT device_id, descriptor, fingerprint, first_seen, last_seen, "
                "status FROM devices ORDER BY first_seen").fetchall()
        devices = [{
            "device_id": r[0],
            "descriptor": json.loads(r[1]),
            "fingerprint": r[2],
            "first_seen": r[3],
            "last_seen": r[4],
            "status": r[5],
        } for r in rows]
        payload = json.dumps({"ts": now(), "devices": devices})
        self.client.publish(topics.INVENTORY, payload, qos=1, retain=True)

    def run(self) -> None:
        self.start()
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


def main() -> None:
    Registry().run()


if __name__ == "__main__":
    main()
