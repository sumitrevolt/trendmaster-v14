"""Unit tests for tools/model_registry.py — no lightgbm required."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import model_registry as R


class _FakeBooster:
    """Duck-types lightgbm.Booster.save_model for registry tests."""

    def __init__(self, payload: str = "mdl"):
        self.payload = payload

    def save_model(self, path: str) -> None:
        Path(path).write_text(self.payload)


@pytest.fixture(autouse=True)
def _redirect(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MODELS", tmp_path / "models")
    monkeypatch.setattr(R, "INDEX", tmp_path / "models" / "index.json")


def test_register_and_list():
    p = R.register_model("EURUSD", _FakeBooster("v1"), {"note": "first"})
    assert p.exists()
    assert p.read_text() == "v1"
    vers = R.list_versions("EURUSD")
    assert len(vers) == 1
    meta = R.latest_metadata("EURUSD")
    assert meta and meta["note"] == "first"
    latest = R.latest_model_path("EURUSD")
    assert latest and latest.read_text() == "v1"


def test_rollback(tmp_path):
    v1 = R.register_model("XAUUSD", _FakeBooster("m1"), {"note": "v1"})
    v2 = R.register_model("XAUUSD", _FakeBooster("m2"), {"note": "v2"})
    assert R.latest_model_path("XAUUSD").read_text() == "m2"

    versions = R.list_versions("XAUUSD")
    first = versions[0]
    assert R.rollback_to("XAUUSD", first)
    assert R.latest_model_path("XAUUSD").read_text() == "m1"
    meta = R.latest_metadata("XAUUSD")
    assert meta["note"] == "v1"


def test_rollback_missing_version_fails():
    R.register_model("GBPUSD", _FakeBooster("a"), {"note": "a"})
    assert not R.rollback_to("GBPUSD", "DOES_NOT_EXIST")
