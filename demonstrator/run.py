#!/usr/bin/env python
"""Convenience entry point: `python run.py up` (and other subcommands).

Identical to the installed ``smarthome`` console script — see `python run.py
--help`.
"""
from smarthome.cli import app

if __name__ == "__main__":
    app()
