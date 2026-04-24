"""
ea_confirmations.py — Python port of the v14 EA's C1/C2/C3 gate
================================================================

Why this exists
---------------
The MT5 EA (`AI_SUPERBB_v14_TrendMaster.mq5`) refuses to enter unless three
confirmations all agree:

    C1  TREND : EMA(20) > EMA(50) > EMA(200)  AND  SuperTrend(10, 3.0)
                aligned with the trend  AND  ADX >= 22  AND  price beyond
                the slow EMA.
    C2  VOLA  : Price closes above (long) / below (short) the BB(20, 2)
                middle band  AND  current BB width >= median(last 50) × 0.9
                (avoids low-vol/squeeze setups).
    C3  MOMO  : MACD(12,26,9) histogram rising and > 0 (long), or falling
                and < 0 (short)  OR  MACD line above signal and > 0 (long),
                symmetric for short.

Until now this logic only existed in MQL5. That meant the Python brain
ranked features and the EA voted 3-of-3 — but a backtest written in
Python couldn't reproduce the EA's decision exactly. So strategy tweaks
went straight to live without any historical validation.

This module reproduces FillConfirmations() bar-for-bar in pandas. A
backtest now sees the same accept/reject the EA will make in production.

Usage
-----
    from ai_trading_agents.ea_confirmations import compute_confirmations

    df = brain.pull_bars("M5", 500, symbol="XAUUSD")
    conf = compute_confirmations(df)             # row-aligned DataFrame
    last = conf.iloc[-2]                         # shift=1 = last closed bar
    if last["c1_trend"] and last["c2_vola"] and last["c3_momo"]:
        print("EA would enter:", last["trend_dir"])

The output frame columns mirror the MQL5 ConfSet struct so you can grep
across both languages and trust that names mean the same thing:

    trend_dir, c1_trend, c2_vola, c3_momo, agreed,
    atr, ema_fast, ema_slow, ema_trend, adx,
    bb_upper, bb_mid, bb_lower, bb_width_med,
    macd_main, macd_sig, macd_hist, macd_hist_prev,
    st_line, st_dir
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# Defaults mirror the EA's input declarations — keep these in lockstep.
@dataclass(frozen=True)
class EAParams:
    ema_fast: int = 20
    ema_slow: int = 50
    ema_trend: int = 200
    adx_period: int = 14
    adx_min: float = 22.0
    atr_period: int = 14
    bb_period: int = 20
    bb_dev: float = 2.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_sig: int = 9
    st_period: int = 10  # SuperTrend ATR length
    st_mult: float = 3.0  # SuperTrend ATR multiplier
    bb_width_lookback: int = 50
    bb_width_floor_pct: float = 0.9  # current width >= median * this


# ─── indicators (pure pandas, vectorised) ─────────────────────────────────
def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _atr_wilder(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    """Wilder's ATR — same averaging MT5's iATR uses (RMA, not SMA)."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    # Wilder = EWMA with alpha=1/n
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def _adx_wilder(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    """Standard ADX with Wilder smoothing — matches MT5 iADX(0, ...)."""
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    atr = _atr_wilder(high, low, close, n).replace(0, np.nan)
    pdi = 100 * plus_dm.ewm(alpha=1.0 / n, adjust=False).mean() / atr
    mdi = 100 * minus_dm.ewm(alpha=1.0 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1.0 / n, adjust=False).mean()


def _macd(close: pd.Series, fast: int, slow: int, sig: int):
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd = ema_fast - ema_slow
    signal = _ema(macd, sig)
    hist = macd - signal
    return macd, signal, hist


def _bbands(close: pd.Series, n: int, dev: float):
    mid = close.rolling(n).mean()
    std = close.rolling(n).std(ddof=0)  # MT5 uses population std
    upper = mid + dev * std
    lower = mid - dev * std
    return upper, mid, lower


def _supertrend(high: pd.Series, low: pd.Series, close: pd.Series, period: int, mult: float):
    """
    Hand-rolled SuperTrend — matches the EA's EnsureSuperTrend logic
    bar-for-bar (same final-band carry-forward, same direction flip).
    """
    atr = _atr_wilder(high, low, close, period)
    hl2 = (high + low) / 2.0
    upper_basic = hl2 + mult * atr
    lower_basic = hl2 - mult * atr

    n = len(close)
    st_line = np.full(n, np.nan)
    st_dir = np.zeros(n, dtype=int)

    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)

    # Need at least period+1 bars to start.
    start = period + 1
    if n <= start:
        return (pd.Series(st_line, index=close.index), pd.Series(st_dir, index=close.index))

    final_upper[start - 1] = upper_basic.iloc[start - 1]
    final_lower[start - 1] = lower_basic.iloc[start - 1]
    st_dir[start - 1] = 1
    st_line[start - 1] = lower_basic.iloc[start - 1]

    cl = close.values
    ub = upper_basic.values
    lb = lower_basic.values

    for i in range(start, n):
        # final upper/lower = inherit prior unless basic tightened it,
        # or unless prior close already pierced it.
        if ub[i] < final_upper[i - 1] or cl[i - 1] > final_upper[i - 1]:
            final_upper[i] = ub[i]
        else:
            final_upper[i] = final_upper[i - 1]
        if lb[i] > final_lower[i - 1] or cl[i - 1] < final_lower[i - 1]:
            final_lower[i] = lb[i]
        else:
            final_lower[i] = final_lower[i - 1]

        prev_dir = st_dir[i - 1] or 1
        if prev_dir == 1:
            if cl[i] < final_lower[i]:
                st_dir[i] = -1
                st_line[i] = final_upper[i]
            else:
                st_dir[i] = 1
                st_line[i] = final_lower[i]
        else:
            if cl[i] > final_upper[i]:
                st_dir[i] = 1
                st_line[i] = final_lower[i]
            else:
                st_dir[i] = -1
                st_line[i] = final_upper[i]

    return (pd.Series(st_line, index=close.index), pd.Series(st_dir, index=close.index, dtype=int))


# ─── master function ──────────────────────────────────────────────────────
def compute_confirmations(df: pd.DataFrame, params: Optional[EAParams] = None) -> pd.DataFrame:
    """
    Given an OHLCV DataFrame indexed by time, return a row-aligned frame
    with the EA's ConfSet fields per bar.

    The interpretation matches `FillConfirmations(..., shift=1)` in MQL5:
    to ask "would the EA enter on bar T?", read row T-1 (the last *closed*
    bar at time T). Use `iloc[-2]` for the most recent fully closed bar
    in a live brain context.
    """
    p = params or EAParams()
    out = pd.DataFrame(index=df.index)

    high = df["high"]
    low = df["low"]
    close = df["close"]

    out["atr"] = _atr_wilder(high, low, close, p.atr_period)
    out["ema_fast"] = _ema(close, p.ema_fast)
    out["ema_slow"] = _ema(close, p.ema_slow)
    out["ema_trend"] = _ema(close, p.ema_trend)
    out["adx"] = _adx_wilder(high, low, close, p.adx_period)

    bbU, bbM, bbL = _bbands(close, p.bb_period, p.bb_dev)
    out["bb_upper"] = bbU
    out["bb_mid"] = bbM
    out["bb_lower"] = bbL
    bb_width = bbU - bbL
    out["bb_width_med"] = bb_width.rolling(p.bb_width_lookback).median()

    macd, sig, hist = _macd(close, p.macd_fast, p.macd_slow, p.macd_sig)
    out["macd_main"] = macd
    out["macd_sig"] = sig
    out["macd_hist"] = hist
    out["macd_hist_prev"] = hist.shift(1)

    st_line, st_dir = _supertrend(high, low, close, p.st_period, p.st_mult)
    out["st_line"] = st_line
    out["st_dir"] = st_dir

    # ── C1 TREND ──────────────────────────────────────────────────────
    ema_bull = (out["ema_fast"] > out["ema_slow"]) & (out["ema_slow"] > out["ema_trend"])
    ema_bear = (out["ema_fast"] < out["ema_slow"]) & (out["ema_slow"] < out["ema_trend"])
    adx_ok = out["adx"] >= p.adx_min
    st_bull = out["st_dir"] == 1
    st_bear = out["st_dir"] == -1

    c1_long = ema_bull & st_bull & adx_ok & (close > out["ema_slow"])
    c1_short = ema_bear & st_bear & adx_ok & (close < out["ema_slow"])

    trend_dir = pd.Series(0, index=df.index, dtype=int)
    trend_dir = trend_dir.mask(c1_long, 1)
    trend_dir = trend_dir.mask(c1_short, -1)
    out["trend_dir"] = trend_dir
    out["c1_trend"] = c1_long | c1_short

    # ── C2 VOLATILITY ──────────────────────────────────────────────────
    width_ok = bb_width >= out["bb_width_med"] * p.bb_width_floor_pct
    c2 = pd.Series(False, index=df.index)
    c2 = c2.mask((trend_dir == 1) & (close > out["bb_mid"]) & width_ok, True)
    c2 = c2.mask((trend_dir == -1) & (close < out["bb_mid"]) & width_ok, True)
    out["c2_vola"] = c2

    # ── C3 MOMENTUM ────────────────────────────────────────────────────
    hist_up = (out["macd_hist"] > out["macd_hist_prev"]) & (out["macd_hist"] > 0)
    hist_dn = (out["macd_hist"] < out["macd_hist_prev"]) & (out["macd_hist"] < 0)
    macd_up = (out["macd_main"] > out["macd_sig"]) & (out["macd_main"] > 0)
    macd_dn = (out["macd_main"] < out["macd_sig"]) & (out["macd_main"] < 0)
    c3 = pd.Series(False, index=df.index)
    c3 = c3.mask((trend_dir == 1) & (hist_up | macd_up), True)
    c3 = c3.mask((trend_dir == -1) & (hist_dn | macd_dn), True)
    out["c3_momo"] = c3

    out["agreed"] = out["c1_trend"].astype(int) + out["c2_vola"].astype(int) + out["c3_momo"].astype(int)

    return out


def ea_would_enter(df: pd.DataFrame, params: Optional[EAParams] = None, shift: int = 1) -> int:
    """
    Convenience wrapper for live use: returns +1/-1/0 mirroring what the
    EA would decide on the *closed* bar `shift` (default 1 = last closed,
    matching `FillConfirmations(..., shift=1)`).
    """
    conf = compute_confirmations(df, params)
    if len(conf) <= shift:
        return 0
    row = conf.iloc[-(shift + 1)]
    if int(row.get("agreed", 0)) == 3 and int(row.get("trend_dir", 0)) != 0:
        return int(row["trend_dir"])
    return 0


__all__ = ["EAParams", "compute_confirmations", "ea_would_enter"]
