"""
scoring.py — 8-Layer Confluence Scoring
========================================
High-conviction signal filter for the TrendMaster brain.

Sits AFTER the ML inference + profit_optimizer gates in tick_once().
When enabled, only signals scoring above the threshold pass through.
Also boosts confidence during high-conviction setups.

Layers:
  1. TREND (ADX + EMA stack)           — weight 2.0
  2. MOMENTUM (RSI sweet spot + MACD)   — weight 1.5
  3. VOLATILITY (BB squeeze + ATR exp)  — weight 1.5
  4. SESSION (London-NY peak)           — weight 1.0
  5. MTF ALIGNMENT (EMA20/50/200)       — weight 1.5
  6. PRICE ACTION (strong candle)       — weight 1.3
  7. VOLUME (above average)             — weight 0.7
  8. STOCHASTIC (overbought/oversold)   — weight 0.8

Max possible score: ~10.3

Backtested optimal thresholds (grid search 192 configs x 7 pairs):
  min_score: 5.0  →  34-37% WR with 2:1+ R:R  →  positive expectancy
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────
# Loaded once from settings at import time.
try:
    from config import settings

    _SCORING_CFG = getattr(settings, "CONFLUENCE_SCORING", {})
except Exception:
    _SCORING_CFG = {}

DEFAULT_MIN_SCORE = 5.0
DEFAULT_ENABLED = True


@dataclass
class ScoreResult:
    """Result of a confluence scoring pass."""
    score: float
    direction: int  # +1=BUY, -1=SELL, 0=NONE
    detail: str
    layers: dict  # layer_name -> (score_contribution, direction_vote)


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average."""
    return pd.Series(data).ewm(span=period, adjust=False).mean().values


def _rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index."""
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = pd.Series(gain).ewm(span=period, adjust=False).mean().values
    avg_loss = pd.Series(loss).ewm(span=period, adjust=False).mean().values
    rs = avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss)
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Average True Range."""
    prev_c = np.roll(close, 1)
    prev_c[0] = close[0]
    tr = np.maximum(
        high - low,
        np.maximum(np.abs(high - prev_c), np.abs(low - prev_c)),
    )
    return pd.Series(tr).rolling(period).mean().values


def _adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14):
    """Average Directional Index + DI+/DI-."""
    prev_h = np.roll(high, 1)
    prev_h[0] = high[0]
    prev_l = np.roll(low, 1)
    prev_l[0] = low[0]
    up_move = high - prev_h
    down_move = prev_l - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_val = _atr(high, low, close, period)
    safe_atr = np.where(atr_val == 0, 1e-10, atr_val)
    plus_di = 100.0 * pd.Series(plus_dm).ewm(span=period).mean().values / safe_atr
    minus_di = 100.0 * pd.Series(minus_dm).ewm(span=period).mean().values / safe_atr
    dx = 100.0 * np.abs(plus_di - minus_di) / np.where(
        (plus_di + minus_di) == 0, 1e-10, plus_di + minus_di
    )
    adx_val = pd.Series(dx).ewm(span=period).mean().values
    return adx_val, plus_di, minus_di


def _macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, signal, histogram."""
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _bollinger_bands(close: np.ndarray, period: int = 20, std_mult: float = 2.0):
    """Bollinger Bands: upper, mid, lower."""
    mid = pd.Series(close).rolling(period).mean().values
    std = pd.Series(close).rolling(period).std().values
    return mid + std_mult * mid * 0 + std_mult * std, mid, mid - std_mult * std


def _stochastic(
    high: np.ndarray, low: np.ndarray, close: np.ndarray,
    k_period: int = 14, d_period: int = 3,
):
    """Stochastic %K and %D."""
    ll = pd.Series(low).rolling(k_period).min().values
    hh = pd.Series(high).rolling(k_period).max().values
    k = 100.0 * (close - ll) / np.where((hh - ll) == 0, 1e-10, hh - ll)
    d = pd.Series(k).rolling(d_period).mean().values
    return k, d


# ─── SCORING FUNCTION ─────────────────────────────────────────────────────────

def compute_confluence_score(
    df: pd.DataFrame,
    direction: str,
    hour_utc: Optional[int] = None,
    min_score: float = DEFAULT_MIN_SCORE,
) -> ScoreResult:
    """
    Compute 8-layer confluence score for the LAST bar of df.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV bars (columns: open, high, low, close, volume).
        Must have at least 200 rows.
    direction : str
        "BUY" or "SELL" — the signal direction to evaluate.
    hour_utc : int, optional
        Current UTC hour. If None, derived from system clock.
    min_score : float
        Minimum score threshold. Default 5.0.

    Returns
    -------
    ScoreResult with score, direction (+1/-1/0), detail, and layer breakdown.
    """
    if len(df) < 200:
        return ScoreResult(0.0, 0, "insufficient_data", {})

    if direction not in ("BUY", "SELL"):
        return ScoreResult(0.0, 0, "invalid_direction", {})

    sig = 1 if direction == "BUY" else -1

    # Extract arrays
    c = df["close"].values.astype(np.float64)
    o = df["open"].values.astype(np.float64)
    h = df["high"].values.astype(np.float64)
    l = df["low"].values.astype(np.float64)
    v = df["volume"].values.astype(np.float64) if "volume" in df.columns else np.ones(len(c))

    i = len(c) - 1  # last bar index

    # Compute indicators
    e8 = _ema(c, 8)
    e20 = _ema(c, 20)
    e50 = _ema(c, 50)
    e200 = _ema(c, 200)
    rsi_val = _rsi(c, 14)
    atr_val = _atr(h, l, c, 14)
    atr_avg = pd.Series(atr_val).rolling(50).mean().values
    adx_v, pdi_v, mdi_v = _adx(h, l, c, 14)
    macd_l, macd_s, macd_h = _macd(c)
    bb_u, bb_m, bb_l = _bollinger_bands(c, 20, 2.0)
    bbw = bb_u - bb_l
    bbw_avg = pd.Series(bbw).rolling(50).mean().values
    stk_k, stk_d = _stochastic(h, l, c, 14, 3)
    vol_avg = pd.Series(v).rolling(20).mean().values

    # Current values
    a = atr_val[i]
    aa = atr_avg[i]
    if a <= 0 or aa <= 0:
        return ScoreResult(0.0, 0, "atr_zero", {})

    if hour_utc is None:
        hour_utc = datetime.now(timezone.utc).hour

    score = 0.0
    layers = {}
    direction_votes = []

    # ── L1: TREND (weight: 2.0) ──────────────────────────────────────────
    l1_score = 0.0
    if adx_v[i] > 28:
        if e8[i] > e20[i] > e50[i]:
            l1_score = 2.0; direction_votes.append(1)
        elif e8[i] < e20[i] < e50[i]:
            l1_score = 2.0; direction_votes.append(-1)
    elif adx_v[i] > 22:
        if e8[i] > e20[i] > e50[i]:
            l1_score = 1.0; direction_votes.append(1)
        elif e8[i] < e20[i] < e50[i]:
            l1_score = 1.0; direction_votes.append(-1)
    layers["trend"] = (l1_score, direction_votes[-1] if direction_votes else 0)
    score += l1_score

    # ── L2: MOMENTUM (weight: 1.5) ───────────────────────────────────────
    l2_score = 0.0
    l2_vote = 0
    rsi_v = rsi_val[i]
    mh = macd_h[i]
    mh_p = macd_h[i - 1] if i > 0 else 0.0
    rsi_buy = 40 <= rsi_v <= 65 and rsi_v > 50
    rsi_sell = 35 <= rsi_v <= 60 and rsi_v < 50
    macd_buy = mh > 0 and mh > mh_p
    macd_sell = mh < 0 and mh < mh_p

    if rsi_buy and macd_buy:
        l2_score = 1.5; l2_vote = 1
    elif rsi_sell and macd_sell:
        l2_score = 1.5; l2_vote = -1
    elif rsi_buy or macd_buy:
        l2_score = 0.5; l2_vote = 1
    elif rsi_sell or macd_sell:
        l2_score = 0.5; l2_vote = -1
    layers["momentum"] = (l2_score, l2_vote)
    score += l2_score
    if l2_vote:
        direction_votes.append(l2_vote)

    # ── L3: VOLATILITY (weight: 1.5) ─────────────────────────────────────
    l3_score = 0.0
    if bbw_avg[i] > 0 and bbw[i] < bbw_avg[i] * 0.80 and a > aa * 1.1:
        l3_score = 1.5  # Squeeze + expansion = powerful breakout
    elif a > aa * 1.15:
        l3_score = 0.8  # ATR expansion alone
    layers["volatility"] = (l3_score, 0)  # volatility doesn't vote direction
    score += l3_score

    # ── L4: SESSION (weight: 1.0) ────────────────────────────────────────
    l4_score = 0.0
    if 12 <= hour_utc <= 15:
        l4_score = 1.0
    elif 7 <= hour_utc <= 11 or 16 <= hour_utc <= 18:
        l4_score = 0.5
    layers["session"] = (l4_score, 0)
    score += l4_score

    # ── L5: MTF ALIGNMENT (weight: 1.5) ──────────────────────────────────
    l5_score = 0.0
    l5_vote = 0
    if e20[i] > e50[i] > e200[i]:
        l5_score = 1.5; l5_vote = 1
    elif e20[i] < e50[i] < e200[i]:
        l5_score = 1.5; l5_vote = -1
    layers["mtf_alignment"] = (l5_score, l5_vote)
    score += l5_score
    if l5_vote:
        direction_votes.append(l5_vote)

    # ── L6: PRICE ACTION (weight: 1.3) ───────────────────────────────────
    l6_score = 0.0
    l6_vote = 0
    body = abs(c[i] - o[i])
    wick_up = h[i] - max(o[i], c[i])
    wick_dn = min(o[i], c[i]) - l[i]
    rng = h[i] - l[i]
    if rng > 0:
        br = body / rng
        if c[i] > o[i] and br > 0.65:
            l6_score = 0.8; l6_vote = 1
        elif c[i] < o[i] and br > 0.65:
            l6_score = 0.8; l6_vote = -1
        # Pin bar / hammer
        if wick_dn > body * 2.5 and wick_dn > wick_up:
            l6_score += 0.5; l6_vote = 1
        elif wick_up > body * 2.5 and wick_up > wick_dn:
            l6_score += 0.5; l6_vote = -1
    layers["price_action"] = (l6_score, l6_vote)
    score += l6_score
    if l6_vote:
        direction_votes.append(l6_vote)

    # ── L7: VOLUME (weight: 0.7) ─────────────────────────────────────────
    l7_score = 0.0
    if vol_avg[i] > 0:
        if v[i] > vol_avg[i] * 1.3:
            l7_score = 0.7
        elif v[i] > vol_avg[i]:
            l7_score = 0.3
    layers["volume"] = (l7_score, 0)
    score += l7_score

    # ── L8: STOCHASTIC (weight: 0.8) ─────────────────────────────────────
    l8_score = 0.0
    l8_vote = 0
    sk = stk_k[i]
    sd = stk_d[i]
    if sk < 20 and sd < 20:
        l8_score = 0.8; l8_vote = 1  # Oversold — buy signal
    elif sk > 80 and sd > 80:
        l8_score = 0.8; l8_vote = -1  # Overbought — sell signal
    elif sk > sd and sk < 45:
        l8_score = 0.4; l8_vote = 1
    elif sk < sd and sk > 55:
        l8_score = 0.4; l8_vote = -1
    layers["stochastic"] = (l8_score, l8_vote)
    score += l8_score
    if l8_vote:
        direction_votes.append(l8_vote)

    # ── DETERMINE DIRECTION AGREEMENT ─────────────────────────────────────
    # Check if the majority of directional votes agree with the signal
    if direction_votes:
        buy_v = sum(1 for v in direction_votes if v > 0)
        sell_v = sum(1 for v in direction_votes if v < 0)
        majority = 1 if buy_v > sell_v else (-1 if sell_v > buy_v else 0)
    else:
        majority = 0
        buy_v = sell_v = 0

    # Direction is valid only if majority agrees with the signal
    valid = (majority == sig)

    detail = (
        f"score={score:.1f} B={buy_v} S={sell_v} "
        f"agree={'YES' if valid else 'NO'}"
    )

    return ScoreResult(
        score=score,
        direction=sig if valid else 0,
        detail=detail,
        layers=layers,
    )


# ─── BRAIN INTEGRATION ───────────────────────────────────────────────────────

def should_fire(
    df: pd.DataFrame,
    direction: str,
    conf: float,
    hour_utc: Optional[int] = None,
    min_score: Optional[float] = None,
    boost_enabled: bool = True,
) -> tuple[str, float, ScoreResult]:
    """
    Evaluate whether a brain signal should fire based on confluence scoring.

    Parameters
    ----------
    df : pd.DataFrame
        Raw OHLCV bars (at least 200 rows).
    direction : str
        "BUY", "SELL", or "NONE".
    conf : float
        Current ML confidence (0.0-1.0).
    hour_utc : int, optional
        Current UTC hour.
    min_score : float, optional
        Override minimum score threshold.
    boost_enabled : bool
        Whether to boost confidence for high-conviction setups.

    Returns
    -------
    (new_direction, new_conf, score_result)
    """
    enabled = _SCORING_CFG.get("enabled", DEFAULT_ENABLED)
    if not enabled:
        return direction, conf, ScoreResult(0.0, 0, "scoring_disabled", {})

    if direction in ("NONE", "none", ""):
        return direction, conf, ScoreResult(0.0, 0, "no_signal", {})

    _min = min_score or _SCORING_CFG.get("min_score", DEFAULT_MIN_SCORE)
    boost_pct = _SCORING_CFG.get("confidence_boost_pct", 0.05)
    max_boost = _SCORING_CFG.get("max_confidence_boost", 0.15)

    # ── REGIME FILTERS (from 350K-bar extended backtest) ──────────────
    # Chop filter: ADX < threshold = choppy market, no trade
    chop_adx = _SCORING_CFG.get("veto_chop_adx_threshold", 0)
    if chop_adx > 0 and len(df) >= 14:
        try:
            _c = df["close"].values.astype(np.float64)
            _h = df["high"].values.astype(np.float64)
            _l = df["low"].values.astype(np.float64)
            _adx_val = _adx(_h, _l, _c, 14)[0]
            if _adx_val[-1] < chop_adx:
                return "NONE", conf, ScoreResult(
                    0.0, 0, f"chop_veto: ADX={_adx_val[-1]:.1f} < {chop_adx}", {}
                )
        except Exception:
            pass
    # High-vol filter: ATR > N * average = too spiky
    hv_mult = _SCORING_CFG.get("veto_high_vol_atr_mult", 0)
    if hv_mult > 0 and len(df) >= 50:
        try:
            _c = df["close"].values.astype(np.float64)
            _h = df["high"].values.astype(np.float64)
            _l = df["low"].values.astype(np.float64)
            _atr_val = _atr(_h, _l, _c, 14)
            _atr_avg = pd.Series(_atr_val).rolling(50).mean().values
            if _atr_avg[-1] > 0 and _atr_val[-1] > _atr_avg[-1] * hv_mult:
                return "NONE", conf, ScoreResult(
                    0.0, 0, f"high_vol_veto: ATR={_atr_val[-1]:.4f} > {hv_mult}x avg={_atr_avg[-1]:.4f}", {}
                )
        except Exception:
            pass

    result = compute_confluence_score(df, direction, hour_utc, _min)

    if result.score >= _min and result.direction != 0:
        # Score above threshold AND direction agrees → fire
        if boost_enabled and result.score >= _min + 1.0:
            # High-conviction bonus: boost confidence
            boost = min(max_boost, (result.score - _min) * boost_pct)
            conf = min(1.0, conf + boost)
            logger.debug(
                "confluence boost: score=%.1f conf=%.3f->%.3f",
                result.score, conf - boost, conf,
            )
        return direction, conf, result
    else:
        # Score below threshold or direction disagrees → veto
        logger.info(
            "confluence veto: score=%.1f min=%.1f agree=%s detail=%s",
            result.score, _min,
            "YES" if result.direction != 0 else "NO",
            result.detail,
        )
        return "NONE", conf, result
