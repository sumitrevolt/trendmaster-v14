"""Unit tests for ai_trading_agents.event_log (JSONL append-only)."""

from __future__ import annotations

import json

import pytest

from ai_trading_agents.event_log import Event, EventLog


def test_append_and_read_roundtrip(tmp_path):
    log = EventLog(path=tmp_path / "evt.jsonl", flush_every_s=0)
    log.append(kind="signal", symbol="EURUSD", payload={"direction": "BUY", "conf": 0.72})
    log.append(kind="fill", symbol="EURUSD", payload={"price": 1.1003, "lots": 0.01})
    log.flush()
    # Read back via helper.
    rows = log.read_since(0)
    assert len(rows) == 2
    assert rows[0]["k"] == "signal"
    assert rows[1]["k"] == "fill"


def test_kind_filter_applies(tmp_path):
    log = EventLog(path=tmp_path / "evt.jsonl", flush_every_s=0)
    log.append("signal", "X", {"a": 1})
    log.append("fill", "X", {"b": 2})
    log.append("signal", "X", {"a": 3})
    log.flush()
    only_signals = log.read_since(0, kinds=["signal"])
    assert len(only_signals) == 2
    assert all(r["k"] == "signal" for r in only_signals)


def test_since_ts_filter(tmp_path):
    log = EventLog(path=tmp_path / "evt.jsonl", flush_every_s=0)
    log.append("signal", "A", {"n": 1})
    log.flush()
    # Read from "future" ⇒ empty.
    assert log.read_since(10**10) == []


def test_buffered_writes_eventually_flush(tmp_path):
    log = EventLog(path=tmp_path / "evt.jsonl", buffer_max=3, flush_every_s=0)
    for i in range(10):
        log.append("signal", "X", {"n": i})
    log.flush()
    rows = log.read_since(0)
    assert len(rows) == 10


def test_event_line_is_valid_json():
    ev = Event(ts=123, kind="signal", symbol="X", payload={"a": 1}, corr_id="c1")
    line = ev.as_line()
    obj = json.loads(line)
    assert obj["k"] == "signal"
    assert obj["p"] == {"a": 1}
    assert obj["cid"] == "c1"


def test_corr_id_default_populates(tmp_path):
    log = EventLog(path=tmp_path / "evt.jsonl", flush_every_s=0)
    log.append("signal", "EURUSD", {"direction": "BUY"})
    log.flush()
    rows = log.read_since(0)
    assert rows[0]["cid"]
    assert "EURUSD" in rows[0]["cid"]


def test_read_missing_file_returns_empty(tmp_path):
    log = EventLog(path=tmp_path / "never.jsonl", flush_every_s=0)
    # Before any append, file still touched by __post_init__, so read
    # returns []. Even if deleted, read_since must not raise.
    (tmp_path / "never.jsonl").unlink()
    rows = log.read_since(0)
    assert rows == []
