"""``MqttComponent`` — the common MQTT plumbing shared by every component.

It encapsulates the qualities the architecture demands so individual components
don't reimplement them:

* **Loose coupling (A-10):** components only ever talk to the broker; handlers
  are registered per topic filter.
* **Persistent session (A-07/A-18):** a stable ``client_id`` + ``clean_session
  =False`` lets the broker keep the session across reconnects.
* **Auto-reconnect (A-07):** ``connect_async`` + ``loop_start`` + exponential
  backoff reconnect with no re-pairing; ``on_connect`` re-subscribes and
  re-announces automatically.
* **Availability (A-05):** a retained Last-Will-and-Testament flips the device to
  ``offline`` the moment it drops; ``online`` is (re)published on every connect.
"""
from __future__ import annotations

import threading
from typing import Callable

import paho.mqtt.client as mqtt
from pydantic import BaseModel

from . import config, topics
from .logging import get_logger
from .model import Availability, now

Handler = Callable[[str, bytes], None]


class MqttComponent:
    def __init__(
        self,
        component: str,
        client_id: str,
        *,
        device_id: str | None = None,
        clean_session: bool = False,
    ) -> None:
        self.component = component
        self.client_id = client_id
        self.device_id = device_id
        self.log = get_logger(component)
        self._subs: list[tuple[str, Handler]] = []
        self._connected = threading.Event()

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=clean_session,
        )
        self.client.reconnect_delay_set(min_delay=1, max_delay=16)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # Retained Last-Will: if we drop, the broker marks us offline for everyone.
        if device_id is not None:
            will = Availability(device_id=device_id, status="offline")
            self.client.will_set(
                topics.availability(device_id),
                will.model_dump_json(),
                qos=1,
                retain=True,
            )

    # --- subscriptions -----------------------------------------------------
    def on_topic(self, topic_filter: str, handler: Handler) -> None:
        """Register a message handler for a topic filter (supports +/#)."""
        self._subs.append((topic_filter, handler))
        if self._connected.is_set():
            self.client.subscribe(topic_filter, qos=1)

    # --- publishing --------------------------------------------------------
    def publish_model(self, topic: str, model: BaseModel, *, qos: int = 1,
                      retain: bool = False) -> None:
        self.client.publish(topic, model.model_dump_json(), qos=qos, retain=retain)

    def publish_availability(self, status: str) -> None:
        if self.device_id is None:
            return
        msg = Availability(device_id=self.device_id, status=status)  # type: ignore[arg-type]
        self.client.publish(topics.availability(self.device_id),
                            msg.model_dump_json(), qos=1, retain=True)

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        """Connect asynchronously and run the network loop in a background
        thread. ``connect_async`` keeps retrying if the broker isn't up yet."""
        self.client.connect_async(config.BROKER_HOST, config.BROKER_PORT,
                                  keepalive=config.KEEPALIVE)
        self.client.loop_start()

    def wait_connected(self, timeout: float = 10.0) -> bool:
        return self._connected.wait(timeout)

    def stop(self) -> None:
        try:
            self.publish_availability("offline")
        except Exception:  # noqa: BLE001 — best effort on shutdown
            pass
        self.client.loop_stop()
        self.client.disconnect()

    # --- overridable hook --------------------------------------------------
    def on_connected(self) -> None:
        """Called after (re)connect + (re)subscribe. Override to announce state."""

    # --- paho callbacks (v2) ----------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            self.log.warning("connect failed: %s", reason_code)
            return
        first = not self._connected.is_set()
        self._connected.set()
        for topic_filter, _ in self._subs:
            client.subscribe(topic_filter, qos=1)
        self.publish_availability("online")
        self.log.info("[green]connected[/] as %s%s", self.client_id,
                      "" if first else " (reconnected)")
        self.on_connected()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self._connected.clear()
        if reason_code != 0:
            self.log.warning("[red]disconnected[/] (rc=%s) — auto-reconnecting", reason_code)

    def _on_message(self, client, userdata, message):
        payload = message.payload
        for topic_filter, handler in self._subs:
            if topics.matches(topic_filter, message.topic):
                try:
                    handler(message.topic, payload)
                except Exception:  # noqa: BLE001
                    self.log.exception("handler error on %s", message.topic)
