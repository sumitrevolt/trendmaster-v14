"""Unit tests for ai_trading_agents/state_store.py."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ai_trading_agents.state_store import StateStore, _DEFAULTS, _MAX_RESULTS


# ─── load() ────────────────────────────────────────────────────────────────
def test_load_returns_defaults_when_file_missing(tmp_path: Path):
    store = StateStore(path=tmp_path / "fresh.json")
    state = store.load()
    for key in _DEFAULTS:
        assert key in state, f"missing default key: {key}"


def test_load_returns_dict_type(tmp_path: Path):
    store = StateStore(path=tmp_path / "fresh.json")
    assert isinstance(store.load(), dict)


def test_load_merges_defaults_with_existing_partial_file(tmp_path: Path):
    p = tmp_path / "partial.json"
    p.write_text(json.dumps({"restart_count": 7}), encoding="utf-8")
    store = StateStore(path=p)
    state = store.load()
    assert state["restart_count"] == 7
    # Defaults still present.
    assert "recent_results" in state
    assert state["cooldown_until_ts"] == 0


def test_load_recovers_from_corrupt_file(tmp_path: Path):
    p = tmp_path / "corrupt.json"
    p.write_text("{ not valid json", encoding="utf-8")
    store = StateStore(path=p)
    state = store.load()
    # Falls back to defaults, doesn't raise.
    assert state["restart_count"] == 0


# ─── save() round-trip ─────────────────────────────────────────────────────
def test_save_and_load_round_trip(tmp_path: Path):
    p = tmp_path / "rt.json"
    store = StateStore(path=p)
    state = store.load()
    state["restart_count"] = 42
    state["start_of_day_equity"] = 10_000.5
    assert store.save(state) is True

    state2 = StateStore(path=p).load()
    assert state2["restart_count"] == 42
    assert state2["start_of_day_equity"] == 10_000.5


def test_save_writes_atomically_no_tmp_left_behind(tmp_path: Path):
    p = tmp_path / "atomic.json"
    store = StateStore(path=p)
    store.save({"restart_count": 1})
    # No leftover .tmp files in the parent directory.
    leftovers = [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
    assert leftovers == []
    assert p.exists()


def test_save_updates_last_saved_at(tmp_path: Path):
    p = tmp_path / "ts.json"
    store = StateStore(path=p)
    state = dict(_DEFAULTS)
    store.save(state)
    assert state["last_saved_at"] > 0


# ─── recent_results trimming ───────────────────────────────────────────────
def test_load_trims_recent_results_to_max(tmp_path: Path):
    p = tmp_path / "big.json"
    huge = list(range(_MAX_RESULTS * 3))
    p.write_text(json.dumps({"recent_results": huge}), encoding="utf-8")
    store = StateStore(path=p)
    state = store.load()
    assert len(state["recent_results"]) == _MAX_RESULTS
    # Trim keeps the tail.
    assert state["recent_results"][-1] == huge[-1]


def test_save_trims_recent_results_to_max(tmp_path: Path):
    p = tmp_path / "save_trim.json"
    store = StateStore(path=p)
    state = dict(_DEFAULTS)
    state["recent_results"] = list(range(_MAX_RESULTS * 2))
    store.save(state)
    state2 = StateStore(path=p).load()
    assert len(state2["recent_results"]) == _MAX_RESULTS


# ─── append_result ─────────────────────────────────────────────────────────
def test_append_result_appends_value(tmp_path: Path):
    store = StateStore(path=tmp_path / "ap.json")
    state = store.load()
    store.append_result(state, 1.5)
    store.append_result(state, -0.5)
    assert state["recent_results"][-2:] == [1.5, -0.5]


def test_append_result_trims_when_exceeding_max(tmp_path: Path):
    store = StateStore(path=tmp_path / "trim.json")
    state = store.load()
    state["recent_results"] = list(range(_MAX_RESULTS))
    store.append_result(state, 999.0)
    assert len(state["recent_results"]) == _MAX_RESULTS
    assert state["recent_results"][-1] == 999.0


# ─── update_signal ─────────────────────────────────────────────────────────
def test_update_signal_writes_per_symbol_entry(tmp_path: Path):
    store = StateStore(path=tmp_path / "sig.json")
    state = store.load()
    store.update_signal(state, "XAUUSD", "long", 0.875)
    entry = state["last_signal_per_symbol"]["XAUUSD"]
    assert entry["direction"] == "long"
    assert entry["confidence"] == 0.875
    assert entry["ts"] > 0


def test_update_signal_overwrites_same_symbol(tmp_path: Path):
    store = StateStore(path=tmp_path / "sig2.json")
    state = store.load()
    store.update_signal(state, "EURUSD", "long", 0.5)
    store.update_signal(state, "EURUSD", "short", 0.7)
    entry = state["last_signal_per_symbol"]["EURUSD"]
    assert entry["direction"] == "short"
    assert entry["confidence"] == 0.7


def test_update_signal_keeps_other_symbols(tmp_path: Path):
    store = StateStore(path=tmp_path / "sig3.json")
    state = store.load()
    store.update_signal(state, "XAUUSD", "long", 0.6)
    store.update_signal(state, "BTCUSD", "short", 0.4)
    assert "XAUUSD" in state["last_signal_per_symbol"]
    assert "BTCUSD" in state["last_signal_per_symbol"]
