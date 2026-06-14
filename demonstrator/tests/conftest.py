"""Test fixtures: redirect all persistent state into a throwaway tmp dir."""
import pytest

from smarthome.core import config


@pytest.fixture(autouse=True)
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "IDENTITY_DIR", tmp_path / "identities")
    monkeypatch.setattr(config, "REGISTRY_DB", tmp_path / "registry.db")
    (tmp_path / "identities").mkdir(parents=True, exist_ok=True)
    yield
