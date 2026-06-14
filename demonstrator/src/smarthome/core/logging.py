"""Structured, colourful logging via Rich — one logger per component.

Each component gets a distinct colour so a combined console (the launcher tails
all subprocesses) stays readable during the live demo.
"""
from __future__ import annotations

import logging
import os

from rich.console import Console
from rich.logging import RichHandler

_CONSOLE = Console(stderr=True)
_CONFIGURED = False


def get_logger(component: str) -> logging.Logger:
    """Return a configured logger tagged with the component name."""
    global _CONFIGURED
    if not _CONFIGURED:
        level = os.getenv("SH_LOG_LEVEL", "INFO").upper()
        logging.basicConfig(
            level=level,
            format="%(name)s | %(message)s",
            datefmt="%H:%M:%S",
            handlers=[RichHandler(console=_CONSOLE, rich_tracebacks=True,
                                  show_path=False, markup=True)],
        )
        # amqtt is very chatty at DEBUG/INFO — keep the demo console clean.
        logging.getLogger("amqtt").setLevel(logging.WARNING)
        logging.getLogger("transitions").setLevel(logging.WARNING)
        _CONFIGURED = True
    return logging.getLogger(component)
