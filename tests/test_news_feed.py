"""Unit tests for ai_trading_agents.news_feed (merge + normaliser).

We don't hit the network in unit tests — merge_events is the core
logic we care about.
"""
from __future__ import annotations

import json

import pytest

from ai_trading_agents.news_feed import (
    FetchResult,
    _ff_json_to_event,
    merge_events,
)


def test_ff_json_to_event_parses_happy():
    raw = {
        "title":   "USD Non-Farm Payrolls",
        "country": "USD",
        "date":    "2026-05-01T12:30:00+00:00",
        "impact":  "High",
    }
    out = _ff_json_to_event(raw)
    assert out is not None
    assert out["ts_utc"] == "2026-05-01T12:30:00Z"
    assert out["event"] == "USD Non-Farm Payrolls"
    assert out["impact"] == "high"
    assert out["currency"] == "USD"


def test_ff_json_to_event_maps_colours():
    for colour, expected in (("red", "high"), ("Orange", "medium"),
                             ("Yellow", "low"), ("Holiday", "none"),
                             ("unknown", "none")):
        out = _ff_json_to_event({
            "title": "X", "date": "2026-05-01T00:00:00Z", "impact": colour,
        })
        assert out is not None
        assert out["impact"] == expected


def test_ff_json_to_event_handles_missing_fields():
    assert _ff_json_to_event({}) is None
    assert _ff_json_to_event({"title": "X"}) is None
    assert _ff_json_to_event({"date": "not-a-date"}) is None


def test_merge_creates_file_when_missing(tmp_path):
    cal = tmp_path / "news.json"
    events = [
        {"ts_utc": "2026-05-01T12:30:00Z", "event": "A", "impact": "high"},
        {"ts_utc": "2026-05-02T12:30:00Z", "event": "B", "impact": "high"},
    ]
    res = merge_events(cal, events)
    assert res.appended == 2
    assert res.duplicates == 0
    assert cal.exists()


def test_merge_is_idempotent(tmp_path):
    cal = tmp_path / "news.json"
    events = [
        {"ts_utc": "2026-05-01T12:30:00Z", "event": "A", "impact": "high"},
    ]
    merge_events(cal, events)
    r2 = merge_events(cal, events)
    assert r2.appended == 0
    assert r2.duplicates == 1


def test_merge_preserves_header_row(tmp_path):
    cal = tmp_path / "news.json"
    seed = [
        {"ts_utc": "1970-01-01T00:00:00Z", "event": "__HEADER__", "impact": "none"},
        {"ts_utc": "2026-05-01T12:30:00Z", "event": "X", "impact": "high"},
    ]
    with open(cal, "w", encoding="utf-8") as f:
        json.dump(seed, f)
    res = merge_events(cal, [
        {"ts_utc": "2026-05-02T12:30:00Z", "event": "Y", "impact": "high"},
    ])
    with open(cal, "r", encoding="utf-8") as f:
        out = json.load(f)
    assert out[0]["event"] == "__HEADER__"
    # Plus 2 real events.
    assert len([e for e in out if e.get("event") != "__HEADER__"]) == 2


def test_merge_sorts_by_ts(tmp_path):
    cal = tmp_path / "news.json"
    events = [
        {"ts_utc": "2026-05-03T12:30:00Z", "event": "Late", "impact": "high"},
        {"ts_utc": "2026-05-01T12:30:00Z", "event": "Early", "impact": "high"},
    ]
    merge_events(cal, events)
    with open(cal, "r", encoding="utf-8") as f:
        out = json.load(f)
    ts_seq = [e["ts_utc"] for e in out]
    assert ts_seq == sorted(ts_seq)


def test_fetch_result_as_dict_shape():
    r = FetchResult(fetched=5, appended=3, duplicates=2, source_url="x", path_written="y")
    d = r.as_dict()
    for k in ("fetched", "appended", "duplicates", "filtered_out",
              "source_url", "path_written", "note"):
        assert k in d
