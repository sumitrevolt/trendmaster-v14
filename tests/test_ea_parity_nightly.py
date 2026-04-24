"""Smoke tests for tools/ea_parity_nightly.py.

Covers the threshold-based divergence detector and the baseline
staleness helper. Does not invoke run_ea_parity_backtest (that path
requires real historical CSVs + the full brain import graph).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from ea_parity_nightly import (  # noqa: E402
    _baseline_age_days,
    diff_symbol,
    load_baseline,
)


# ---------- diff_symbol ---------------------------------------------------


def _cur(**kw):
    base = dict(symbol="XAUUSD", bars_scanned=10000, trades=100, win_rate=0.55, expectancy_R=0.30)
    base.update(kw)
    return base


def test_diff_within_tolerance():
    cur = _cur()
    base = _cur(bars_scanned=10050, trades=102, win_rate=0.56, expectancy_R=0.32)
    flagged, flags = diff_symbol(cur, base)
    assert not flagged
    assert flags == []


def test_diff_flags_bars_divergence():
    cur = _cur(bars_scanned=10500)  # +5%
    base = _cur(bars_scanned=10000)
    flagged, flags = diff_symbol(cur, base)
    assert flagged
    assert any("bars_scanned" in f for f in flags)


def test_diff_flags_trades_divergence():
    cur = _cur(trades=120)  # +20%
    base = _cur(trades=100)
    flagged, flags = diff_symbol(cur, base)
    assert flagged
    assert any("trades" in f for f in flags)


def test_diff_flags_win_rate_divergence():
    cur = _cur(win_rate=0.48)  # -7pp
    base = _cur(win_rate=0.55)
    flagged, flags = diff_symbol(cur, base)
    assert flagged
    assert any("win_rate" in f for f in flags)


def test_diff_flags_expectancy_divergence():
    cur = _cur(expectancy_R=0.10)  # -0.20
    base = _cur(expectancy_R=0.30)
    flagged, flags = diff_symbol(cur, base)
    assert flagged
    assert any("expectancy_R" in f for f in flags)


def test_diff_current_error_is_flagged():
    cur = {"symbol": "XAUUSD", "error": "CSV missing"}
    base = _cur()
    flagged, flags = diff_symbol(cur, base)
    assert flagged
    assert any("errored" in f for f in flags)


def test_diff_baseline_error_not_flagged():
    # Baseline had an error for this symbol — seed with current, don't alert.
    cur = _cur()
    base = {"symbol": "XAUUSD", "error": "CSV missing"}
    flagged, _ = diff_symbol(cur, base)
    assert not flagged


# ---------- baseline age --------------------------------------------------


def test_baseline_age_recent():
    ts = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    assert _baseline_age_days({"generated_at": ts}) == 3


def test_baseline_age_stale():
    ts = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    assert _baseline_age_days({"generated_at": ts}) == 45


def test_baseline_age_missing_cases():
    assert _baseline_age_days(None) is None
    assert _baseline_age_days({}) is None
    assert _baseline_age_days({"generated_at": "not a date"}) is None


# ---------- load_baseline -------------------------------------------------


def test_load_baseline_missing(tmp_path, monkeypatch):
    import ea_parity_nightly

    monkeypatch.setattr(ea_parity_nightly, "BASELINE_PATH", tmp_path / "nope.json")
    assert ea_parity_nightly.load_baseline() is None


def test_load_baseline_corrupt(tmp_path, monkeypatch):
    import ea_parity_nightly

    p = tmp_path / "baseline.json"
    p.write_text("{ this is not valid json", encoding="utf-8")
    monkeypatch.setattr(ea_parity_nightly, "BASELINE_PATH", p)
    assert ea_parity_nightly.load_baseline() is None
