"""Embedded pure-Python MQTT broker (amqtt) — the pub/sub backbone.

Run standalone::

    python -m smarthome.broker

Default binds 127.0.0.1:1883, anonymous auth, no retained-message persistence
across broker restarts (intentional: see the "graceful degradation" demo).

*Plan B:* if amqtt ever misbehaves, swap in Mosquitto via Docker — the rest of
the stack is unaffected because everyone speaks plain MQTT::

    docker run -it --rm -p 1883:1883 eclipse-mosquitto:2 \
        mosquitto -c /mosquitto-no-auth.conf
"""
from __future__ import annotations

import asyncio

from amqtt.broker import Broker

from .core import config
from .core.logging import get_logger

log = get_logger("broker")


def _broker_config() -> dict:
    return {
        "listeners": {
            "default": {
                "type": "tcp",
                "bind": f"{config.BROKER_HOST}:{config.BROKER_PORT}",
            },
        },
        "plugins": {
            # Anonymous auth keeps the demo frictionless. A FileAuthPlugin /
            # TLS listener is the drop-in path to the Zero-Trust target (A-22).
            "amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
        },
    }


async def run() -> None:
    broker = Broker(_broker_config())
    await broker.start()
    log.info("[green]MQTT broker up[/] on %s:%s", config.BROKER_HOST, config.BROKER_PORT)
    try:
        await asyncio.Event().wait()        # run until cancelled / Ctrl+C
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await broker.shutdown()
        log.info("broker stopped")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
