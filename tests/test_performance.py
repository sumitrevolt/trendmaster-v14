"""Unit tests for ai_trading_agents.performance."""

from __future__ import annotations

import time

import pytest

from ai_trading_agents.performance import (
    PerfMetrics,
    by_symbol,
    by_team,
    calibration,
    compute,
    heatmap_day_of_week,
    heatmap_hour_of_day,
    snapshot,
)


def _make_trades(n=50, seed=7):
    """Deterministic synthetic trade list."""
    import random

    rng = random.Random(seed)
    now = int(time.time())
    trades = []
    symbols = ["XAUUSD", "EURUSD", "GBPJPY"]
    for i in range(n):
        pnl = rng.choice([-2.0, -1.0, 0.5, 1.5, 3.0, -0.5, 2.0])
        trades.append(
            {
                "ts": now - (n - i) * 3600,
                "symbol": rng.choice(symbols),
                "pnl": pnl,
                "r_mult": pnl,
            }
        )
    return trades


def test_compute_handles_empty():
    m = compute([])
    assert m.n_trades == 0
    assert m.reason


def test_compute_ratios_sensible():
    trades = _make_trades(100)
    m = compute(trades)
    assert m.n_trades == 100
    assert 0 <= m.win_rate <= 1
    assert m.max_drawdown >= 0


def test_by_symbol_buckets():
    trades = _make_trades(60)
    bysym = by_symbol(trades)
    assert len(bysym) > 0
    assert all(k in ("XAUUSD", "EURUSD", "GBPJPY") for k in bysym.keys())
    # Sorted by total_pnl descending.
    pnls = [v["total_pnl"] for v in bysym.values()]
    assert pnls == sorted(pnls, reverse=True)


def test_by_team():
    trades = _make_trades(60)

    def team(s):
        return "METALS" if s == "XAUUSD" else "FOREX"

    bt = by_team(trades, team)
    assert "METALS" in bt or "FOREX" in bt


def test_hour_heatmap_all_24_buckets():
    trades = _make_trades(30)
    h = heatmap_hour_of_day(trades)
    assert len(h) == 24
    for hour in range(24):
        assert hour in h


def test_day_of_week_heatmap():
    trades = _make_trades(30)
    h = heatmap_day_of_week(trades)
    assert set(h.keys()) == {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}


def test_calibration_buckets():
    trades = [
        {"ts": 1, "confidence": 0.62, "pnl": 1.0},
        {"ts": 2, "confidence": 0.62, "pnl": -1.0},
        {"ts": 3, "confidence": 0.82, "pnl": 1.0},
        {"ts": 4, "confidence": 0.82, "pnl": 1.0},
    ]
    out = calibration(trades, confidence_buckets=(0.5, 0.7, 0.9, 1.0))
    assert len(out) == 3


def test_snapshot_has_all_keys():
    trades = _make_trades(40)
    snap = snapshot(trades)
    assert "windows" in snap
    assert "by_symbol_30d" in snap
    assert "hour_30d" in snap
    assert "dow_30d" in snap
    assert "calibration_30d" in snap


def test_float_entries_also_work():
    trades = [1.0, -0.5, 1.2, -0.3, 2.0]
    m = compute(trades)
    assert m.n_trades == 5
    assert m.total_pnl == pytest.approx(3.4, abs=0.001)
