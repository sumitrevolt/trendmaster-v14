"""Unit tests for ai_trading_agents.daily_digest."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from ai_trading_agents.daily_digest import (
    ActionItem,
    generate_report,
    to_markdown,
    to_telegram,
    write_daily,
)


def _fake_state():
    now = int(time.time())
    return {
        "halted": False,
        "trading_paused": False,
        "restart_count": 3,
        "start_of_day_equity": 500.0,
        "daily_drawdown_peak_eq": 505.0,
        "drawdown_lockout_until": 0,
        "cooldown_until_ts": 0,
        "recent_results": [
            {"ts": now - 3600, "symbol": "XAUUSD", "pnl": 2.0, "r_mult": 2.0, "confidence": 0.72},
            {"ts": now - 7200, "symbol": "EURUSD", "pnl": -1.0, "r_mult": -1.0, "confidence": 0.65},
            {"ts": now - 10800, "symbol": "GBPJPY", "pnl": 3.0, "r_mult": 3.0, "confidence": 0.80},
        ],
    }


def test_generate_report_has_keys():
    digest = generate_report(_fake_state())
    for key in ("date", "generated_at", "performance", "state_summary", "action_items"):
        assert key in digest


def test_generate_report_handles_empty_state():
    digest = generate_report({})
    assert digest["performance"]
    assert digest["action_items"] == []


def test_markdown_renders():
    digest = generate_report(_fake_state())
    md = to_markdown(digest)
    assert "Daily Digest" in md
    assert "Performance windows" in md
    assert "Action items" in md


def test_telegram_renders():
    digest = generate_report(_fake_state())
    tg = to_telegram(digest)
    assert "Daily Digest" in tg
    assert "<b>" in tg


def test_write_daily(tmp_path):
    digest = generate_report(_fake_state())
    paths = write_daily(digest, tmp_path)
    assert Path(paths["json"]).exists()
    assert Path(paths["md"]).exists()
    # JSON must be valid round-trip.
    loaded = json.loads(Path(paths["json"]).read_text())
    assert loaded["date"] == digest["date"]


def test_action_items_flag_halted():
    s = _fake_state()
    s["halted"] = True
    digest = generate_report(s)
    titles = [a["title"] for a in digest["action_items"]]
    assert any("halted" in t.lower() for t in titles)


def test_action_items_flag_drawdown_lockout():
    s = _fake_state()
    s["drawdown_lockout_until"] = int(time.time() + 3600)
    digest = generate_report(s)
    titles = [a["title"] for a in digest["action_items"]]
    assert any("lockout" in t.lower() for t in titles)


def test_action_item_as_dict():
    a = ActionItem(severity="warn", title="T", detail="D")
    assert a.as_dict() == {"severity": "warn", "title": "T", "detail": "D"}
