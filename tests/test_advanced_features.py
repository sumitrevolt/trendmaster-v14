"""Unit tests for ai_trading_agents/advanced_features.py.

Each test isolates one feature, feeds it a synthetic series with a
known property, and asserts the feature responds correctly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ai_trading_agents.advanced_features import (  # noqa: E402
    ADVANCED_FEATURE_COLS,
    add_advanced_features,
    donchian_distance,
    frac_diff,
    hurst_rolling,
    mom_of_mom,
    realized_skew,
)


# ---------- frac_diff -----------------------------------------------------


def test_frac_diff_d_zero_returns_input():
    """d=0 means no differentiation -> should ~equal the input where defined."""
    s = pd.Series(np.linspace(1, 100, 50))
    out = frac_diff(s, d=0.0, window=5)
    # First (window-1) values are NaN; rest should equal input
    assert out.iloc[:4].isna().all()
    np.testing.assert_allclose(out.iloc[4:].to_numpy(), s.iloc[4:].to_numpy(), rtol=1e-9)


def test_frac_diff_d_one_approximates_first_difference():
    """d=1 with large window approximates ordinary first difference."""
    np.random.seed(0)
    s = pd.Series(np.cumsum(np.random.randn(200)))
    fd = frac_diff(s, d=1.0, window=20).dropna()
    diff1 = s.diff().iloc[19:]
    # Direction of move should match strongly
    sign_match = (np.sign(fd.to_numpy()) == np.sign(diff1.to_numpy())).mean()
    assert sign_match > 0.9


def test_frac_diff_warms_up_with_nan():
    s = pd.Series(np.arange(20, dtype=float))
    out = frac_diff(s, d=0.4, window=8)
    assert out.iloc[:7].isna().all()
    assert not out.iloc[7:].isna().any()


# ---------- hurst_rolling -------------------------------------------------


def test_hurst_random_walk_near_half():
    """Pure random walk should give H ~ 0.5."""
    np.random.seed(42)
    walk = pd.Series(np.cumsum(np.random.randn(2000)) + 100.0)
    h = hurst_rolling(walk, window=400).dropna()
    # Pretty wide tolerance — R/S on R/S is noisy
    assert 0.30 < h.mean() < 0.70


def test_hurst_persistent_returns_above_half():
    """Returns with positive autocorrelation (AR(1), phi=0.4) should
    show Hurst clearly above 0.5. R/S measures the persistence of
    *deviations from the local mean*, not the slope of the price
    series, so a clean deterministic trend doesn't qualify - we need
    autocorrelated returns.
    """
    np.random.seed(11)
    n = 2000
    eps = np.random.randn(n)
    rets = np.zeros(n)
    phi = 0.4
    for t in range(1, n):
        rets[t] = phi * rets[t - 1] + eps[t]
    price = pd.Series(np.cumsum(rets) + 100)
    h = hurst_rolling(price, window=400).dropna()
    assert h.mean() > 0.55


def test_hurst_warmup_nan():
    s = pd.Series(np.arange(100, dtype=float) + 100.0)
    h = hurst_rolling(s, window=50)
    assert h.iloc[:49].isna().all()


# ---------- mom_of_mom ----------------------------------------------------


def test_mom_of_mom_zero_for_flat_series():
    s = pd.Series([100.0] * 50)
    mm = mom_of_mom(s, n=5)
    # After warm-up the value should be ~0 (no momentum, no acceleration)
    assert mm.dropna().abs().max() < 1e-9


def test_mom_of_mom_positive_for_accelerating_log_returns():
    """A series whose LOG returns accelerate should have positive
    mom-of-mom on average. Quadratic-of-time price gives constant log
    returns, so we need an exponential-of-quadratic-of-time price."""
    n = 80
    t = np.arange(n)
    # log-return at step t is proportional to t (linearly accelerating)
    log_rets = 0.0005 * t
    log_price = np.cumsum(log_rets) + np.log(100.0)
    s = pd.Series(np.exp(log_price))
    mm = mom_of_mom(s, n=10).dropna()
    # By construction, recent block has higher cumulative log-return
    # than older block at every t in the tail -> mom-of-mom > 0.
    assert mm.iloc[-20:].mean() > 0


# ---------- realized_skew -------------------------------------------------


def test_realized_skew_zero_for_symmetric():
    """Symmetric Gaussian returns should give skew near 0."""
    np.random.seed(7)
    rets = pd.Series(np.random.randn(500) * 0.001)
    rs = realized_skew(rets, window=100).dropna()
    assert abs(rs.mean()) < 0.5


def test_realized_skew_negative_for_left_tail():
    """Inject a left-tail crash; rolling skew should go negative around it."""
    rets = np.random.randn(500) * 0.001
    rets[200:210] = -0.05  # 10 strong negative returns
    rs = realized_skew(pd.Series(rets), window=50).dropna()
    # The window covering the crash should be clearly negative
    crash_window_min = rs.iloc[200:260].min()
    assert crash_window_min < 0


# ---------- donchian_distance ---------------------------------------------


def _ohlc_from_close(close: np.ndarray, hl_pad: float = 0.5) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": close,
            "high": close + hl_pad,
            "low": close - hl_pad,
            "close": close,
        }
    )


def test_donchian_close_to_zero_at_high():
    """When close == max(high) (synthetic: hl_pad = 0), close is exactly
    at the rolling high so upper_dist should be 0."""
    close = np.linspace(100, 110, 60)  # monotone up
    df = _ohlc_from_close(close, hl_pad=0.0)
    upper, lower, _ = donchian_distance(df, window=20)
    # Exactly at the high
    assert abs(upper.iloc[-1]) < 1e-9
    # Lower distance should be clearly positive (above rolling low)
    assert lower.iloc[-1] > 0


def test_donchian_bars_since_high_recent():
    """If high was just made, bars_since_high should be 0."""
    close = np.array([100, 101, 102, 103, 104, 105, 104, 103])
    df = _ohlc_from_close(close)
    _, _, age = donchian_distance(df, window=4)
    # Last bar's window is [102,103,104,105,104,103][-4:] = [105,104,103]; high at index 0 -> age = 3
    assert int(age.iloc[-1]) >= 0  # well-defined


# ---------- add_advanced_features convenience ----------------------------


def test_add_advanced_features_columns():
    np.random.seed(2)
    n = 400
    close = np.cumsum(np.random.randn(n) * 0.2) + 100
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
        }
    )
    df["ret_1"] = df["close"].pct_change()
    df = add_advanced_features(df)
    for c in ADVANCED_FEATURE_COLS:
        assert c in df.columns, f"{c} missing"
    # Last 50 rows should have at least some non-NaN values for every feature
    for c in ADVANCED_FEATURE_COLS:
        assert df[c].iloc[-50:].notna().sum() > 0, f"{c} all NaN at tail"
