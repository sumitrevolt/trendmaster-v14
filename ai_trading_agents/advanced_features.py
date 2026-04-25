"""High-signal features for FX/commodity H1 direction prediction.

Why this module exists
----------------------
The current `build_features` in `trend_master_brain.py` produces 25
local-momentum-and-volatility features that, on a freshly retrained
model, give 0.344 holdout accuracy on a 3-class problem (random=0.333).
Research synthesis (Lopez de Prado, Hudson & Thames, MQL5 forum
2024-2026) identifies five features with documented edge that are
absent from the current set:

  1. Fractional differentiation of log-price (long memory + stationary)
  2. Hurst exponent (regime gate: trending vs mean-reverting)
  3. Momentum of momentum / acceleration (regime-shift detector)
  4. Realized skewness (intraday distribution shape)
  5. Donchian distance + bars-since-extreme (path-dependent context)

All implementations are pure pandas/numpy. No new third-party deps.
Each function returns a Series aligned to the input index, with NaN
during the warm-up window.

Use
---
    from ai_trading_agents.advanced_features import (
        frac_diff, hurst_rolling, mom_of_mom, realized_skew,
        donchian_distance,
    )
    x["frac_diff"]   = frac_diff(np.log(x["close"]), d=0.4, window=10)
    x["hurst"]       = hurst_rolling(x["close"], window=200)
    x["mom_of_mom"]  = mom_of_mom(x["close"], n=12)
    x["rskew"]       = realized_skew(x["ret_1"], window=24)
    upper, lower, age = donchian_distance(x, window=24)
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 1. Fractional differentiation (Lopez de Prado, AFML Ch. 5)


def _frac_diff_weights(d: float, k_max: int) -> np.ndarray:
    """Compute the truncated weights for fractional differentiation.

    w_0 = 1; w_k = -w_{k-1} * (d - k + 1) / k. Truncate at k_max.
    """
    w = [1.0]
    for k in range(1, k_max + 1):
        w_k = -w[-1] * (d - k + 1) / k
        w.append(w_k)
    return np.asarray(w, dtype=float)


def frac_diff(series: pd.Series, d: float = 0.4, window: int = 10) -> pd.Series:
    """Fixed-window fractional differentiation.

    Parameters
    ----------
    series : pd.Series
        Typically log(close).
    d : float
        Differentiation order. d=1.0 is integer differencing, d=0
        is no differencing. d ~= 0.3-0.5 keeps long memory and gives
        a stationary series for FX log-prices.
    window : int
        Truncation window. Higher = more memory, more warm-up NaNs.

    Returns
    -------
    pd.Series with NaN for the first `window-1` rows.
    """
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    weights = _frac_diff_weights(d, window - 1)
    out = pd.Series(index=series.index, dtype=float)
    arr = series.to_numpy()
    n = len(arr)
    if n < window:
        return out
    # Convolution: y[t] = sum_{k=0}^{window-1} w[k] * x[t-k]
    out_vals = np.full(n, np.nan)
    for t in range(window - 1, n):
        window_slice = arr[t - window + 1 : t + 1][::-1]  # reverse so x[t] aligns with w[0]
        if np.any(np.isnan(window_slice)):
            continue
        out_vals[t] = float(np.dot(weights, window_slice))
    out.iloc[:] = out_vals
    return out


# ---------------------------------------------------------------------------
# 2. Hurst exponent (rescaled range, R/S)


def _hurst_window(prices: np.ndarray) -> float:
    """Compute Hurst exponent on a single window via R/S analysis."""
    n = len(prices)
    if n < 20:
        return float("nan")
    log_p = np.log(prices)
    rets = np.diff(log_p)
    if len(rets) == 0 or np.std(rets) == 0:
        return float("nan")
    # Multiple sub-window sizes; fit log(R/S) ~ H * log(N).
    sizes = [s for s in (8, 16, 32, 64) if s <= len(rets)]
    if len(sizes) < 2:
        return float("nan")
    rs_vals = []
    log_sizes = []
    for s in sizes:
        chunks = len(rets) // s
        if chunks == 0:
            continue
        rs_chunk = []
        for c in range(chunks):
            chunk = rets[c * s : (c + 1) * s]
            mean_chunk = chunk.mean()
            cum = (chunk - mean_chunk).cumsum()
            r = cum.max() - cum.min()
            sd = chunk.std()
            if sd > 0 and r > 0:
                rs_chunk.append(r / sd)
        if rs_chunk:
            rs_vals.append(np.mean(rs_chunk))
            log_sizes.append(s)
    if len(rs_vals) < 2:
        return float("nan")
    slope, _ = np.polyfit(np.log(log_sizes), np.log(rs_vals), 1)
    return float(slope)


def hurst_rolling(close: pd.Series, window: int = 200) -> pd.Series:
    """Rolling Hurst exponent (R/S analysis).

    H ~ 0.5  -> random walk
    H >  0.5 -> trending (persistent)
    H <  0.5 -> mean-reverting (anti-persistent)

    Returns NaN for the first `window-1` rows.
    """
    if not isinstance(close, pd.Series):
        close = pd.Series(close)
    out = pd.Series(index=close.index, dtype=float)
    arr = close.to_numpy(dtype=float)
    n = len(arr)
    out_vals = np.full(n, np.nan)
    for t in range(window - 1, n):
        out_vals[t] = _hurst_window(arr[t - window + 1 : t + 1])
    out.iloc[:] = out_vals
    return out


# ---------------------------------------------------------------------------
# 3. Momentum of momentum (acceleration)


def mom_of_mom(close: pd.Series, n: int = 12) -> pd.Series:
    """Second-derivative momentum: log-return over [t-n, t] minus
    log-return over [t-2n, t-n].

    Captures regime *shifts* (drift -> mean-revert) rather than just
    velocity. Absent from the brain's current FEATURE_COLS.
    """
    if not isinstance(close, pd.Series):
        close = pd.Series(close)
    log_c = np.log(close.replace(0, np.nan))
    recent = log_c - log_c.shift(n)
    older = log_c.shift(n) - log_c.shift(2 * n)
    return recent - older


# ---------------------------------------------------------------------------
# 4. Realized skewness (intraday distribution shape)


def realized_skew(returns: pd.Series, window: int = 24) -> pd.Series:
    """Rolling realized skewness of returns.

    RS = (sqrt(n) * sum r^3) / (sum r^2)^1.5

    Captures asymmetry of the return distribution; high-frequency
    skewness predicts cross-section direction (Amaya et al.).
    """
    if not isinstance(returns, pd.Series):
        returns = pd.Series(returns)
    r2 = returns.pow(2)
    r3 = returns.pow(3)
    sum_r2 = r2.rolling(window).sum()
    sum_r3 = r3.rolling(window).sum()
    n = window
    denom = sum_r2.pow(1.5).replace(0, np.nan)
    return np.sqrt(n) * sum_r3 / denom


# ---------------------------------------------------------------------------
# 5. Donchian distance + bars-since-extreme


def donchian_distance(df: pd.DataFrame, window: int = 24) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Distance from current close to rolling high/low, normalized by ATR,
    plus bars-since-extreme.

    Returns (upper_dist, lower_dist, bars_since_high). Negative
    upper_dist means we are at/above the rolling high; positive
    lower_dist means we are above the rolling low.
    """
    high_w = df["high"].rolling(window).max()
    low_w = df["low"].rolling(window).min()
    # ATR-normalised distance
    tr = pd.concat(
        [
            (df["high"] - df["low"]),
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean().replace(0, np.nan)
    upper_dist = (df["close"] - high_w) / atr
    lower_dist = (df["close"] - low_w) / atr

    # bars-since-rolling-high
    bars_since = pd.Series(index=df.index, dtype=float)
    last_high_idx = -1
    last_high_val = -np.inf
    arr = df["high"].to_numpy()
    out = np.full(len(arr), np.nan)
    for t in range(len(arr)):
        if t < window - 1:
            continue
        # Find argmax in the last window
        slice_ = arr[t - window + 1 : t + 1]
        idx_in_slice = int(np.argmax(slice_))
        out[t] = float(window - 1 - idx_in_slice)
    bars_since.iloc[:] = out

    return upper_dist, lower_dist, bars_since


# ---------------------------------------------------------------------------
# Convenience wrapper for callers


def add_advanced_features(x: pd.DataFrame) -> pd.DataFrame:
    """Append the 5 advanced features to a DataFrame that already has
    `close`, `high`, `low`, and `ret_1`. Mutates and returns x."""
    x["frac_diff_close"] = frac_diff(np.log(x["close"].replace(0, np.nan)), d=0.4, window=10)
    x["hurst_200"] = hurst_rolling(x["close"], window=200)
    x["mom_of_mom_12"] = mom_of_mom(x["close"], n=12)
    x["rskew_24"] = realized_skew(x.get("ret_1", x["close"].pct_change()), window=24)
    upper, lower, age = donchian_distance(x, window=24)
    x["donchian_upper"] = upper
    x["donchian_lower"] = lower
    x["bars_since_high"] = age
    return x


ADVANCED_FEATURE_COLS = [
    "frac_diff_close",
    "hurst_200",
    "mom_of_mom_12",
    "rskew_24",
    "donchian_upper",
    "donchian_lower",
    "bars_since_high",
]
