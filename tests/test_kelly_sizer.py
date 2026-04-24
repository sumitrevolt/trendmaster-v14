"""Unit tests for ai_trading_agents.kelly_sizer."""
from __future__ import annotations

import pytest

from ai_trading_agents.kelly_sizer import (
    KellyConfig,
    KellyDecision,
    apply,
    compute_multiplier,
)


def test_insufficient_samples_returns_identity():
    cfg = KellyConfig(min_samples=20)
    d = compute_multiplier([-1, 2, -1], cfg)
    assert d.multiplier == 1.0
    assert "insufficient" in d.reason
    assert d.samples_used == 3


def test_all_wins_returns_identity():
    cfg = KellyConfig(min_samples=3)
    d = compute_multiplier([1.0, 2.0, 3.0, 1.5], cfg)
    assert d.multiplier == 1.0
    assert "degenerate" in d.reason


def test_all_losses_returns_identity():
    cfg = KellyConfig(min_samples=3)
    d = compute_multiplier([-1.0, -2.0, -0.5], cfg)
    assert d.multiplier == 1.0
    assert "degenerate" in d.reason


def test_balanced_mix_scales_above_one():
    # Win rate 60%, avg_win=$1, avg_loss=$1 (R=1)
    # Full Kelly = 0.6 - 0.4/1 = 0.2
    # Half Kelly = 0.1 → multiplier = 1.1
    cfg = KellyConfig(min_samples=4, kelly_fraction=0.5,
                      floor_fraction=0.25, max_fraction=2.0)
    results = [1.0, 1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0, -1.0, 1.0]  # 7W/3L
    d = compute_multiplier(results, cfg)
    assert d.win_rate == pytest.approx(0.7, abs=0.0001)
    assert d.multiplier > 1.0
    assert d.multiplier <= 2.0


def test_multiplier_is_clamped_to_max():
    # Force a very favourable stream. Kelly should want > 2.0 but we cap.
    cfg = KellyConfig(min_samples=4, kelly_fraction=1.0,   # full Kelly
                      floor_fraction=0.25, max_fraction=1.5)
    results = [3.0, 3.0, 3.0, 3.0, -0.5]
    d = compute_multiplier(results, cfg)
    assert d.multiplier == pytest.approx(1.5)


def test_dict_shape_via_trade_tracker():
    # Entries can be dicts (trade_tracker shape) — should still work.
    cfg = KellyConfig(min_samples=4)
    results = [
        {"pnl":  1.0, "ts": 0, "symbol": "XAUUSD"},
        {"pnl": -1.0, "ts": 1, "symbol": "XAUUSD"},
        {"pnl":  1.5, "ts": 2, "symbol": "XAUUSD"},
        {"pnl":  2.0, "ts": 3, "symbol": "XAUUSD"},
        {"pnl": -0.5, "ts": 4, "symbol": "XAUUSD"},
        {"pnl":  1.0, "ts": 5, "symbol": "XAUUSD"},
    ]
    d = compute_multiplier(results, cfg)
    assert d.samples_used == 6


def test_shadow_mode_does_not_apply():
    cfg = KellyConfig(min_samples=3, kelly_fraction=0.5,
                      shadow_mode=True)
    results = [1.0, 1.0, 1.0, -1.0]
    base = 0.5
    # In shadow mode apply() must return the base unchanged even though
    # compute_multiplier would have returned > 1.
    assert apply(results, base, cfg) == 0.5


def test_live_mode_scales_base():
    cfg = KellyConfig(min_samples=4, kelly_fraction=0.5)
    results = [1.0, 1.0, 1.0, 1.0, -1.0]  # 80% WR, R=1
    base = 1.0
    sized = apply(results, base, cfg)
    assert sized > base
    assert sized <= base * cfg.max_fraction


def test_break_even_not_counted():
    cfg = KellyConfig(min_samples=4)
    # 4 real trades + 2 break-even. min_samples hits only on the reals.
    results = [1.0, -1.0, 1.0, -1.0, 0.0, 0.0]
    d = compute_multiplier(results, cfg)
    assert d.samples_used == 4


def test_floor_caps_downside():
    cfg = KellyConfig(min_samples=4, kelly_fraction=0.5,
                      floor_fraction=0.5, max_fraction=2.0)
    # 30% win rate, R=1 → full Kelly = 0.3 - 0.7 = -0.4
    # frac = max(0, -0.4) * 0.5 = 0; multiplier = 1.0 + 0 = 1.0
    # Floor at 0.5 is higher than 1.0? No — 0.5 < 1.0, so clamp is a ceiling-below-1 case.
    # Expected: multiplier = max(0.5, 1.0) = 1.0
    results = [1.0, -1.0, -1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, -1.0]
    d = compute_multiplier(results, cfg)
    assert d.multiplier == pytest.approx(1.0)


def test_decision_as_dict_roundtrip():
    cfg = KellyConfig(min_samples=2)
    results = [1.0, -1.0, 1.0]
    d = compute_multiplier(results, cfg)
    out = d.as_dict()
    assert isinstance(out, dict)
    assert "multiplier" in out
    assert "win_rate" in out
    assert "reason" in out
