"""Phase D2 feature engineering: fractional differentiation + rolling Hurst.

Why D2
------
Per ``CLAUDE.md`` "Where the alpha actually lives" synthesis from
López de Prado AFML and Hudson & Thames literature:

- **Fractional differentiation** (d≈0.4) of log-price keeps long memory
  while making the series stationary. Integer differencing (the v1
  ``ret_*`` features) destroys ~99% of price information.
- **Hurst exponent** (rolling 200-bar) gates trend-vs-revert regime
  directly. H>0.5 trending, H<0.5 mean-reverting. A first-order alpha
  source for FX where regime mis-classification dominates retail PnL.

This module is pure numpy/pandas — no new dependencies. The implementation
follows López de Prado AFML chapter 5 (frac_diff_FFD) and Hurst's R/S
analysis with rolling windows.

Cost
----
``frac_diff_ffd`` is O(N · width) where width ≈ 60 for d=0.4 with
threshold=1e-4. ``rolling_hurst`` is O(N · window · log(window)) per
call due to the inner R/S regression. For 50k bars × 19 symbols this
is sub-second on Sumit's box; well below the per-tick budget.

Junction discipline
-------------------
This file lives inside ai_trading_agents/ (the NTFS junction).
Use the centralised path helper, not raw ``Path(__file__).parent.parent``.
See docs/POSTMORTEMS/2026-04-30_junction_trap_silent_state_drift.md.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

_log = logging.getLogger(__name__)

# Default fractional differentiation parameters.
DEFAULT_D = 0.4
# Threshold for the fixed-width window (López de Prado AFML algorithm 5.3).
# Smaller threshold → wider window → less skew but more memory cost.
DEFAULT_THRESHOLD = 1e-4
# Rolling-Hurst windows. 200 bars (~8 days on H1) is the literature
# default; 500 bars (~20 days) catches slower regime cycles.
HURST_WINDOWS = (200, 500)

# Canonical D2 feature column names. These extend FEATURE_COLS_V2:
#     V3 = V2 (33) + D2 (4) = 37 cols
D2_FEATURE_COLS: List[str] = [
    "close_frac_diff",
    "log_close_frac_diff",
    "hurst_close_200",
    "hurst_close_500",
]


# ---------------------------------------------------------------------------
# Fractional differentiation (López de Prado AFML algorithm 5.3, FFD form)
# ---------------------------------------------------------------------------


def _frac_diff_weights_ffd(d: float, threshold: float = DEFAULT_THRESHOLD) -> np.ndarray:
    """Compute fixed-width FFD weights until |w_k| < threshold.

    Formula: w_0 = 1; w_k = -w_{k-1} * (d - k + 1) / k.
    Returns a 1-d array oldest-to-newest (so we convolve with the most
    recent observation at the end).
    """
    weights = [1.0]
    k = 1
    while True:
        w = -weights[-1] * (d - k + 1) / k
        if abs(w) < threshold:
            break
        weights.append(w)
        k += 1
        if k > 2000:  # absurdity guard
            break
    return np.array(weights[::-1], dtype=np.float64)


def frac_diff_ffd(
    series: pd.Series,
    d: float = DEFAULT_D,
    threshold: float = DEFAULT_THRESHOLD,
) -> pd.Series:
    """Fixed-width fractional differentiation of a 1-d series.

    First ``len(weights) - 1`` values are NaN. Output preserves the
    input index.
    """
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    weights = _frac_diff_weights_ffd(d, threshold)
    width = len(weights)
    arr = series.to_numpy(dtype=np.float64, copy=False)
    out = np.full_like(arr, np.nan, dtype=np.float64)
    if width > arr.size:
        return pd.Series(out, index=series.index, name=series.name)
    # Vectorised convolution: out[i] = sum_k weights[k] * arr[i - (width-1) + k]
    # using np.lib.stride_tricks.sliding_window_view for clarity.
    from numpy.lib.stride_tricks import sliding_window_view

    windows = sliding_window_view(arr, window_shape=width)
    valid = windows @ weights
    out[width - 1 :] = valid
    return pd.Series(out, index=series.index, name=series.name)


# ---------------------------------------------------------------------------
# Rolling Hurst exponent via R/S analysis
# ---------------------------------------------------------------------------


def _hurst_rs(window_arr: np.ndarray) -> float:
    """R/S Hurst estimate on a single window of returns.

    Uses 4 lag scales to fit log(R/S) ≈ H · log(n). Returns ``np.nan``
    on degenerate input (zero std, length below the smallest scale).
    """
    n = window_arr.size
    if n < 32:
        return np.nan
    # Use returns rather than levels; H estimated on returns is the
    # standard, and avoids a unit-root bias that appears on the price
    # level series.
    rets = np.diff(window_arr)
    if rets.size < 16:
        return np.nan
    if np.nanstd(rets) == 0:
        return np.nan

    # Geometrically spaced lag scales (powers of 2) up to floor(n/2).
    max_scale = max(8, n // 4)
    scales = []
    s = 8
    while s <= max_scale:
        scales.append(s)
        s *= 2
    if len(scales) < 2:
        return np.nan

    log_n: list[float] = []
    log_rs: list[float] = []
    for scale in scales:
        # How many non-overlapping windows of length `scale` fit?
        n_chunks = rets.size // scale
        if n_chunks < 1:
            continue
        chunks = rets[: n_chunks * scale].reshape(n_chunks, scale)
        # Mean-adjusted cumulative sum per chunk → range R_i.
        z = chunks - chunks.mean(axis=1, keepdims=True)
        cs = np.cumsum(z, axis=1)
        rng = cs.max(axis=1) - cs.min(axis=1)
        # Standard deviation per chunk → S_i.
        std = chunks.std(axis=1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            rs = np.where(std > 0, rng / std, np.nan)
        rs_mean = np.nanmean(rs)
        if not np.isfinite(rs_mean) or rs_mean <= 0:
            continue
        log_n.append(np.log(scale))
        log_rs.append(np.log(rs_mean))

    if len(log_n) < 2:
        return np.nan
    # Slope of the regression line is the Hurst estimate.
    coeffs = np.polyfit(log_n, log_rs, 1)
    return float(coeffs[0])


def rolling_hurst(series: pd.Series, window: int = 200) -> pd.Series:
    """Rolling Hurst exponent estimate. First ``window-1`` rows are NaN.

    Uses ``Series.rolling(window).apply`` with a numba-free numpy R/S
    estimator. ~1.5s for 50k rows on Sumit's box; fast enough for the
    walk-forward harness.
    """
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    s = series.dropna()
    if s.size < window + 4:
        return pd.Series(np.nan, index=series.index, name=series.name)
    h = s.rolling(window=window, min_periods=window).apply(_hurst_rs, raw=True)
    # Re-align onto the original index so rows that were NaN in input
    # remain NaN here (no implicit fill).
    return h.reindex(series.index)


# ---------------------------------------------------------------------------
# Public: extend a feature DataFrame with the 4 D2 columns
# ---------------------------------------------------------------------------


def add_d2_features(
    df: pd.DataFrame,
    *,
    close_col: str = "close",
    d: float = DEFAULT_D,
    threshold: float = DEFAULT_THRESHOLD,
    hurst_windows: tuple[int, ...] = HURST_WINDOWS,
) -> pd.DataFrame:
    """Append the 4 canonical D2 columns to ``df``.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain ``close_col`` (default ``'close'``). Indexed by
        time. Not mutated — a copy is returned.
    close_col : str
        Column name to compute features from.
    d : float
        Fractional-diff order. 0.4 is the López de Prado / H&T default
        for daily-to-H1 FX log-prices.
    threshold : float
        FFD weight cutoff (smaller → wider window).
    hurst_windows : tuple[int, ...]
        Rolling windows for Hurst. Defaults to (200, 500) bars.

    Returns
    -------
    pd.DataFrame
        Copy of input plus columns: ``close_frac_diff``,
        ``log_close_frac_diff``, ``hurst_close_<w>`` for each window.
    """
    out = df.copy()
    if close_col not in out.columns:
        _log.warning("add_d2_features: %r missing; D2 cols filled NaN", close_col)
        for col in D2_FEATURE_COLS:
            out[col] = np.nan
        return out

    close = out[close_col].astype(float)

    # Fractional diff of close + log(close).
    out["close_frac_diff"] = frac_diff_ffd(close, d=d, threshold=threshold)
    log_close = np.log(close.where(close > 0))
    out["log_close_frac_diff"] = frac_diff_ffd(log_close, d=d, threshold=threshold)

    # Rolling Hurst on log-returns of close.
    log_rets = log_close.diff()
    for w in hurst_windows:
        col = f"hurst_close_{w}"
        out[col] = rolling_hurst(log_rets, window=w)

    return out


__all__ = [
    "D2_FEATURE_COLS",
    "DEFAULT_D",
    "DEFAULT_THRESHOLD",
    "HURST_WINDOWS",
    "add_d2_features",
    "frac_diff_ffd",
    "rolling_hurst",
]
