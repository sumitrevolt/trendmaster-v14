"""Unit tests for ai_trading_agents/ea_confirmations.py.

We feed synthetic OHLCV with known regime characteristics (strong uptrend,
strong downtrend, choppy sideways) and assert that compute_confirmations
and ea_would_enter respond as the EA's gate would.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from ai_trading_agents.ea_confirmations import (
    EAParams,
    compute_confirmations,
    ea_would_enter,
)


_EXPECTED_COLUMNS = {
    "trend_dir", "c1_trend", "c2_vola", "c3_momo", "agreed",
    "atr", "ema_fast", "ema_slow", "ema_trend", "adx",
    "bb_upper", "bb_mid", "bb_lower", "bb_width_med",
    "macd_main", "macd_sig", "macd_hist", "macd_hist_prev",
    "st_line", "st_dir",
}


# ─── synthetic OHLCV generators ────────────────────────────────────────────
def _make_ohlcv(n: int, drift: float, vol: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    steps = rng.normal(drift, vol, size=n)
    close = np.cumsum(steps) + 1000.0
    high = close + rng.uniform(0.10, 1.00, size=n)
    low = close - rng.uniform(0.10, 1.00, size=n)
    open_ = close - rng.normal(0.0, 0.20, size=n)
    vol_arr = rng.integers(100, 1000, size=n)
    idx = pd.date_range(datetime(2026, 1, 1, tzinfo=timezone.utc),
                        periods=n, freq="5min")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low,
         "close": close, "volume": vol_arr},
        index=idx,
    )


@pytest.fixture
def bull_df():
    # Strong upward drift, modest noise → C1 long should fire.
    return _make_ohlcv(n=600, drift=0.50, vol=0.30, seed=11)


@pytest.fixture
def bear_df():
    return _make_ohlcv(n=600, drift=-0.50, vol=0.30, seed=23)


@pytest.fixture
def chop_df():
    # Zero drift, high noise → no clean trend, EA should rarely 3-of-3 agree.
    return _make_ohlcv(n=600, drift=0.0, vol=1.20, seed=5)


# ─── output frame schema ───────────────────────────────────────────────────
def test_compute_confirmations_returns_all_expected_columns(bull_df):
    out = compute_confirmations(bull_df)
    assert _EXPECTED_COLUMNS.issubset(set(out.columns))


def test_compute_confirmations_has_exactly_twenty_columns(bull_df):
    out = compute_confirmations(bull_df)
    assert len(out.columns) == 20


def test_compute_confirmations_row_aligned_with_input(bull_df):
    out = compute_confirmations(bull_df)
    assert len(out) == len(bull_df)
    assert (out.index == bull_df.index).all()


# ─── bull regime ───────────────────────────────────────────────────────────
@pytest.mark.slow
def test_bull_regime_produces_some_three_of_three_long_bars(bull_df):
    out = compute_confirmations(bull_df)
    long_full = (out["agreed"] == 3) & (out["trend_dir"] == 1)
    assert long_full.sum() > 0


@pytest.mark.slow
def test_bull_regime_has_more_long_than_short_trend_bars(bull_df):
    out = compute_confirmations(bull_df)
    longs = (out["trend_dir"] == 1).sum()
    shorts = (out["trend_dir"] == -1).sum()
    assert longs > shorts


# ─── bear regime ───────────────────────────────────────────────────────────
@pytest.mark.slow
def test_bear_regime_produces_some_short_trend_bars(bear_df):
    out = compute_confirmations(bear_df)
    assert (out["trend_dir"] == -1).sum() > 0


@pytest.mark.slow
def test_bear_regime_has_more_short_than_long_trend_bars(bear_df):
    out = compute_confirmations(bear_df)
    longs = (out["trend_dir"] == 1).sum()
    shorts = (out["trend_dir"] == -1).sum()
    assert shorts > longs


# ─── chop regime ───────────────────────────────────────────────────────────
@pytest.mark.slow
def test_chop_regime_has_fewer_three_of_three_bars_than_bull(chop_df, bull_df):
    """Pure chop should produce strictly fewer 3-of-3 agreement bars than a
    clean bull regime. Absolute counts vary with the synthetic seed, so we
    compare regimes against each other rather than hard-coding a threshold."""
    chop_full = (compute_confirmations(chop_df)["agreed"] == 3).sum()
    bull_full = (compute_confirmations(bull_df)["agreed"] == 3).sum()
    assert chop_full < bull_full


# ─── ea_would_enter ────────────────────────────────────────────────────────
@pytest.mark.slow
def test_ea_would_enter_returns_long_in_bull_regime(bull_df):
    # Walk forward until we find a bar the EA would enter long on.
    found = False
    for end in range(300, len(bull_df), 5):
        if ea_would_enter(bull_df.iloc[:end]) == 1:
            found = True
            break
    assert found, "EA never voted long in a clear bull regime"


@pytest.mark.slow
def test_ea_would_enter_returns_short_in_bear_regime(bear_df):
    found = False
    for end in range(300, len(bear_df), 5):
        if ea_would_enter(bear_df.iloc[:end]) == -1:
            found = True
            break
    assert found, "EA never voted short in a clear bear regime"


def test_ea_would_enter_returns_zero_for_too_short_input():
    tiny = _make_ohlcv(n=5, drift=0.0, vol=0.1, seed=1)
    assert ea_would_enter(tiny) == 0


def test_ea_would_enter_returns_int_type(bull_df):
    result = ea_would_enter(bull_df)
    assert isinstance(result, int)
    assert result in (-1, 0, 1)


# ─── EAParams ──────────────────────────────────────────────────────────────
def test_ea_params_defaults_match_ea_inputs():
    p = EAParams()
    assert p.ema_fast == 20
    assert p.ema_slow == 50
    assert p.ema_trend == 200
    assert p.adx_min == 22.0
    assert p.bb_period == 20
    assert p.bb_dev == 2.0
    assert p.st_period == 10
    assert p.st_mult == 3.0


def test_ea_params_is_frozen():
    p = EAParams()
    with pytest.raises(Exception):  # FrozenInstanceError subclass of AttributeError
        p.ema_fast = 999  # type: ignore[misc]


def test_compute_confirmations_accepts_custom_params(bull_df):
    custom = EAParams(adx_min=10.0)  # looser gate → at least as many entries
    out_default = compute_confirmations(bull_df)
    out_custom = compute_confirmations(bull_df, custom)
    assert (out_custom["c1_trend"].sum()) >= (out_default["c1_trend"].sum())
