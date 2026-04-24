"""Unit tests for ai_trading_agents.rolling_corr."""
from __future__ import annotations

import math
import random

import numpy as np
import pytest

from ai_trading_agents.rolling_corr import CorrViolation, RollingCorrMatrix


def _synthetic_walk(n, seed, drift=0.0, vol=0.01):
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, vol, size=n)
    return list(np.exp(np.cumsum(r)) * 100.0)


def test_corr_returns_none_when_window_not_full():
    rcm = RollingCorrMatrix(window=20)
    for i in range(10):
        rcm.update_bar({"EURUSD": 1.0 + i * 0.01, "GBPUSD": 1.2 + i * 0.01})
    assert rcm.corr("EURUSD", "GBPUSD") is None


def test_corr_near_plus_one_for_copy():
    rcm = RollingCorrMatrix(window=30)
    walk = _synthetic_walk(40, seed=7, drift=0.001, vol=0.005)
    for px in walk:
        # Feed the same series as two different symbols.
        rcm.update_bar({"A": px, "B": px})
    c = rcm.corr("A", "B")
    assert c is not None
    assert c > 0.99


def test_corr_near_minus_one_for_mirror():
    rcm = RollingCorrMatrix(window=30)
    walk = _synthetic_walk(40, seed=11, drift=0.0005, vol=0.007)
    # B mirrors A around an anchor value.
    for px in walk:
        rcm.update_bar({"A": px, "B": 200.0 - px})
    c = rcm.corr("A", "B")
    assert c is not None
    assert c < -0.99


def test_check_blocks_same_direction_high_corr():
    rcm = RollingCorrMatrix(window=30)
    walk = _synthetic_walk(40, seed=13)
    for px in walk:
        rcm.update_bar({"EURUSD": px, "GBPUSD": px})
    positions = [type("P", (), {"symbol": "GBPUSD", "direction": "BUY"})]
    v = rcm.check("EURUSD", "BUY", positions, threshold=0.8)
    assert v is not None
    assert v.other_symbol == "GBPUSD"
    assert "same-side" in v.reason


def test_check_blocks_anti_corr_with_opposite_side():
    rcm = RollingCorrMatrix(window=30)
    walk = _synthetic_walk(40, seed=15)
    for px in walk:
        rcm.update_bar({"EURUSD": px, "USDCHF": 200.0 - px})
    positions = [type("P", (), {"symbol": "USDCHF", "direction": "SELL"})]
    # BUY EURUSD + SELL USDCHF is effectively 2x long EUR.
    v = rcm.check("EURUSD", "BUY", positions, threshold=0.8)
    assert v is not None
    assert "anti-corr" in v.reason


def test_check_allows_independent_pair():
    rcm = RollingCorrMatrix(window=30)
    rng = random.Random(7)
    for _ in range(40):
        rcm.update_bar({"A": rng.gauss(1.0, 0.01), "B": rng.gauss(1.0, 0.01)})
    positions = [{"symbol": "B", "direction": "BUY"}]
    v = rcm.check("A", "BUY", positions, threshold=0.9)
    # Independent streams shouldn't trip the 0.9 threshold.
    assert v is None


def test_dict_positions_supported():
    rcm = RollingCorrMatrix(window=5)
    walk = _synthetic_walk(10, seed=19)
    for px in walk:
        rcm.update_bar({"A": px, "B": px})
    positions = [{"symbol": "B", "direction": "BUY"}]
    v = rcm.check("A", "BUY", positions, threshold=0.5)
    assert v is not None


def test_coverage_reports_per_symbol_bars():
    rcm = RollingCorrMatrix(window=10)
    rcm.update_bar({"A": 1.0})
    rcm.update_bar({"A": 1.1, "B": 2.0})
    c = rcm.coverage()
    assert c["A"] == 2
    assert c["B"] == 1


def test_invalid_price_ignored():
    rcm = RollingCorrMatrix(window=5)
    rcm.update_bar({"A": None, "B": "not-a-number"})
    assert "A" not in rcm._prices
    assert "B" not in rcm._prices
