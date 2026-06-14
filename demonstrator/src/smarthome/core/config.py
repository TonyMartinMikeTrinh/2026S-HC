"""Central configuration.

Every value can be overridden via an environment variable so the whole stack can
be reconfigured without code changes (12-factor style). Defaults make the system
run out-of-the-box on a single machine.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- MQTT pub/sub backbone -------------------------------------------------
BROKER_HOST: str = os.getenv("SH_BROKER_HOST", "127.0.0.1")
BROKER_PORT: int = int(os.getenv("SH_BROKER_PORT", "1883"))
KEEPALIVE: int = int(os.getenv("SH_KEEPALIVE", "15"))

# Topic namespace. Everything lives under this prefix.
TOPIC_PREFIX: str = os.getenv("SH_TOPIC_PREFIX", "home")

# --- Persistence -----------------------------------------------------------
# demonstrator/state  (this file: src/smarthome/core/config.py -> parents[3] == demonstrator)
_DEFAULT_STATE = Path(__file__).resolve().parents[3] / "state"
STATE_DIR: Path = Path(os.getenv("SH_STATE_DIR", str(_DEFAULT_STATE)))
IDENTITY_DIR: Path = STATE_DIR / "identities"
REGISTRY_DB: Path = STATE_DIR / "registry.db"

# --- Dashboard -------------------------------------------------------------
DASHBOARD_HOST: str = os.getenv("SH_DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT: int = int(os.getenv("SH_DASHBOARD_PORT", "8000"))

# --- On-device AI ----------------------------------------------------------
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL: str = os.getenv("SH_OLLAMA_MODEL", "llama3.1:latest")
# Force a specific agent backend ("ollama" | "rules" | "auto"). "auto" probes
# Ollama and silently falls back to the deterministic rule backend.
AGENT_BACKEND: str = os.getenv("SH_AGENT_BACKEND", "auto")

# --- Schema / contract version (A-11 versioned interface) ------------------
SCHEMA_VERSION: str = "1.0"


def ensure_state_dirs() -> None:
    """Create the local state directories on demand."""
    IDENTITY_DIR.mkdir(parents=True, exist_ok=True)
