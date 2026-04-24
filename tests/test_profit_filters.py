"""Unit tests for ai_trading_agents/profit_filters.py."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from ai_trading_agents.profit_filters import (
    spread_guard,
    volatility_regime,
    daily_profit_lock,
    loss_streak_cooldown,
    session_window,
    evaluate_all,
)


# ---------- spread guard ----------
def test_spread_guard_allows_tight_spread():
    d = spread_guard(spread_price=0.05, atr_price=1.0, max_ratio=0.25)
    assert d.allow
    assert d.score_adjust > 0  # bonus when spread is tiny


def test_spread_guard_blocks_wide_spread():
    d = spread_guard(spread_price=0.30, atr_price=1.0, max_ratio=0.25)
    assert not d.allow
    assert d.score_adjust < 0


def test_spread_guard_zero_atr_blocks():
    d = spread_guard(0.10, 0.0)
    assert not d.allow


# ---------- volatility regime ----------
def _atr_sample(seed=1, n=300, scale=1.0):
    rng = np.random.default_rng(seed)
    return pd.Series(np.abs(rng.normal(loc=1.0, scale=0.3, size=n)) * scale)


def test_vol_regime_dead_market_blocks():
    base = _atr_sample()
    s = pd.concat([base, pd.Series([0.0001])], ignore_index=True)
    d = volatility_regime(s)
    assert not d.allow
    assert "dead" in d.reason


def test_vol_regime_spike_blocks():
    base = _atr_sample()
    s = pd.concat([base, pd.Series([base.max() * 5])], ignore_index=True)
    d = volatility_regime(s)
    assert not d.allow
    assert "spike" in d.reason


def test_vol_regime_normal_allows():
    s = _atr_sample()
    d = volatility_regime(s)
    assert d.allow


def test_vol_regime_insufficient_samples_passes():
    s = pd.Series(np.random.rand(10))
    d = volatility_regime(s)
    assert d.allow  # don't block when we can't judge


# ---------- daily profit lock ----------
def test_profit_lock_blocks_after_target():
    d = daily_profit_lock(equity_now=1025, equity_start_of_day=1000, target_pct=2.0)
    assert not d.allow
    assert "profit lock" in d.reason


def test_profit_lock_allows_below_target():
    d = daily_profit_lock(equity_now=1010, equity_start_of_day=1000, target_pct=2.0)
    assert d.allow


# ---------- loss-streak cooldown ----------
def test_loss_streak_blocks_after_three_losses():
    d = loss_streak_cooldown([10, -5, -8, -3], max_consec_losses=3)
    assert not d.allow


def test_loss_streak_allows_when_short():
    d = loss_streak_cooldown([10, -5, -8], max_consec_losses=3)
    assert d.allow


def test_loss_streak_cooldown_flag_overrides():
    d = loss_streak_cooldown([10, 20, 30], max_consec_losses=3, cooldown_active=True)
    assert not d.allow


# ---------- session window ----------
def test_session_window_inside_best_hours():
    t = datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc)
    d = session_window(now_utc=t)
    assert d.allow
    assert d.score_adjust > 0  # 13 UTC is peak overlap → bonus


def test_session_window_blocks_off_hours():
    t = datetime(2026, 4, 22, 3, 0, tzinfo=timezone.utc)
    d = session_window(now_utc=t)
    assert not d.allow


# ---------- combined ----------
def test_evaluate_all_happy_path():
    s = _atr_sample()
    d = evaluate_all(
        spread_price=0.05,
        atr_price=1.0,
        atr_series=s,
        equity_now=1010,
        equity_start_of_day=1000,
        recent_results=[5, -2, 3],
        cooldown_active=False,
        now_utc=datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )
    assert d.allow
    assert d.score_adjust > 0  # tight spread + peak hour ⇒ net boost


def test_evaluate_all_any_veto_blocks():
    s = _atr_sample()
    d = evaluate_all(
        spread_price=0.50,
        atr_price=1.0,  # spread too wide → VETO
        atr_series=s,
        equity_now=1010,
        equity_start_of_day=1000,
        recent_results=[5, -2, 3],
        now_utc=datetime(2026, 4, 22, 13, 0, tzinfo=timezone.utc),
    )
    assert not d.allow
    assert any("spread" in r for r in d.reasons)
