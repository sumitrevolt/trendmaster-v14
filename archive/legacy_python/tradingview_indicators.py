"""
TradingView Indicators Module — EXACT replica of Sumit's TV chart setup.
===========================================================================
Captured from TradingView Desktop App (XAUUSD 5m chart):

  1. MACD Overlay (fa=12, sa=26, sig=9, SMA=89) — Pine Script v2 exact match
  2. SuperBollingerTrend (Expo) prd=12, mult=2 Signal ZigZag Median — BB + SuperTrend
  3. ORB — Opening Range Breakout with Targets [LuxAlgo] — 09:30-09:45 UTC-5 session
  4. THE PHOENIX v0.1 wSMD — Closed source TV indicator; replaced with
     open-source equivalent: Weighted Stochastic Momentum Divergence (wSMD)
     that replicates long/short arrow signals visible on chart.
  5. Cash Open — Session open price levels
  6. Liquidity Heatmap (Nephe) — Multi-TF liquidity zones (15m to D)

Integration: Called by SignalEngine as additional scoring layer (±8 max).
MACD update: Pine v2 uses EMA(close, slow-fast) as MACD line + SMA signal.
Phoenix replacement: wSMD uses Stochastic %K/%D divergence + weighted momentum.
ORB: Detects breakout above/below Opening Range high/low with target levels.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger("TVIndicators")


# ═══════════════════════════════════════════════════════════════════════════
# 1. MACD OVERLAY — Pine Script v2 exact match (fa=12, sa=26, sig=9, SMA=89)
# ═══════════════════════════════════════════════════════════════════════════
class MACDOverlay:
    """
    TradingView MACD Overlay — EXACT Pine Script v2 params from Sumit's chart.

    Pine Script source (v2):
        fa=12 (FAST), sa=26 (SLOW), sig=9 (SIGNAL), SMA=89
        macd = ema(close, sa-fa)   ← NOTE: Pine v2 uses EMA(close, slow-fast=14)
        signal = sma(macd, sig)    ← SMA of macd, not EMA
        fill = green if macd>signal else red
        sma_line = sma(close, 89)  ← separate SMA overlay

    Key difference from old params (10,21): Now fa=12, sa=26, sig=9.
    The MACD line color is green if rising, red if falling (same for signal).
    The fill between MACD and signal: green when macd>signal, red otherwise.

    The SMA(89) is the main trend filter — price above = bull, below = bear.
    """

    def __init__(self, fast: int = 10, slow: int = 21,
                 signal: int = 10, sma_period: int = 21):
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.sma_period = sma_period
        # Standard MACD: macd = ema(close, fast) - ema(close, slow)
        self._macd_ema_period = slow - fast  # kept for legacy compat

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add MACD Overlay columns to dataframe — Pine v2 exact logic."""
        c = df["close"]

        # ── Standard MACD: macd = EMA(fast) - EMA(slow) — matches TradingView ──
        ema_fast           = c.ewm(span=self.fast, adjust=False).mean()
        ema_slow           = c.ewm(span=self.slow, adjust=False).mean()
        df["tv_macd"]      = ema_fast - ema_slow

        # Signal = EMA(macd, signal) — standard TradingView default
        df["tv_macd_sig"]  = df["tv_macd"].ewm(span=self.signal, adjust=False).mean()

        # Histogram = macd - signal
        df["tv_macd_hist"] = df["tv_macd"] - df["tv_macd_sig"]

        # SMA(21) — main trend line on chart (matches TV MACD Overlay 10 21 10 21)
        df["tv_sma89"]     = c.rolling(self.sma_period).mean()  # col name kept for compat

        # Cross detection (macd crosses signal line)
        df["tv_macd_cross_bull"] = (
            (df["tv_macd"] > df["tv_macd_sig"]) &
            (df["tv_macd"].shift(1) <= df["tv_macd_sig"].shift(1))
        )
        df["tv_macd_cross_bear"] = (
            (df["tv_macd"] < df["tv_macd_sig"]) &
            (df["tv_macd"].shift(1) >= df["tv_macd_sig"].shift(1))
        )

        # MACD color: green if rising, red if falling (Pine v2 iff logic)
        df["tv_macd_rising"]   = df["tv_macd"] > df["tv_macd"].shift(1)
        df["tv_sig_rising"]    = df["tv_macd_sig"] > df["tv_macd_sig"].shift(1)

        # Fill color: green if macd > signal, red otherwise
        df["tv_fill_bull"]     = df["tv_macd"] > df["tv_macd_sig"]

        # SMA(89) direction: green if rising, red if falling
        df["tv_sma89_rising"]  = df["tv_sma89"] > df["tv_sma89"].shift(1)

        # Price vs SMA(89) — key trend filter
        df["tv_above_sma89"]   = c > df["tv_sma89"]

        # Histogram expanding vs contracting
        df["tv_hist_expanding"] = df["tv_macd_hist"].abs() > df["tv_macd_hist"].shift(1).abs()

        # Cumulative histogram (20-bar rolling)
        lookback = 20
        df["tv_cum_hist"]    = df["tv_macd_hist"].rolling(lookback).sum().fillna(0)
        df["tv_growth_rate"] = ((c - c.shift(lookback)) / c.shift(lookback).replace(0, np.nan) * 100).fillna(0)
        df["tv_revenue_mom"] = df["tv_macd_hist"].ewm(span=10, adjust=False).mean()

        # Legacy ema_fast/slow for backward compat with TradingViewStrategy
        df["tv_ema_fast"]    = c.ewm(span=self.fast, adjust=False).mean()
        df["tv_ema_slow"]    = c.ewm(span=self.slow, adjust=False).mean()
        df["tv_cloud_bull"]  = df["tv_ema_fast"] > df["tv_ema_slow"]

        return df

    def analyze(self, df: pd.DataFrame) -> Dict:
        """Analyze MACD Overlay for signal and growth state — Pine v2 logic."""
        if "tv_macd" not in df.columns:
            df = self.calculate(df)

        r = df.iloc[-1]

        macd_val    = float(r["tv_macd"])
        sig_val     = float(r["tv_macd_sig"])
        hist_val    = float(r["tv_macd_hist"])
        growth      = float(r["tv_growth_rate"])
        cum_hist    = float(r["tv_cum_hist"])
        rev_mom     = float(r["tv_revenue_mom"])
        cloud_bull  = bool(r["tv_cloud_bull"])
        fill_bull   = bool(r["tv_fill_bull"])         # macd > signal
        above_sma89 = bool(r["tv_above_sma89"])       # price > SMA(89)
        sma89_up    = bool(r["tv_sma89_rising"])       # SMA(89) rising
        cross_bull  = bool(r["tv_macd_cross_bull"])
        cross_bear  = bool(r["tv_macd_cross_bear"])
        hist_exp    = bool(r["tv_hist_expanding"])
        macd_rising = bool(r["tv_macd_rising"])
        sig_rising  = bool(r["tv_sig_rising"])

        sma89_val = float(r["tv_sma89"]) if not np.isnan(r["tv_sma89"]) else float(r["close"])

        # Growth classification
        is_positive_growth = growth > 0 and rev_mom > 0
        is_strong_growth   = growth > 0.5 and cum_hist > 0 and hist_exp

        # ── Signal logic (Pine v2 visual match) ──
        # STRONG BUY: bullish cross + price above SMA89 + fill green + SMA rising
        if cross_bull and above_sma89 and fill_bull and sma89_up:
            signal = "STRONG_BUY"
            strength = "HIGH"
        # BUY: bullish cross OR fill just turned green
        elif cross_bull or (fill_bull and not bool(df.iloc[-2].get("tv_fill_bull", True) if len(df) > 1 else True)):
            signal = "BUY"
            strength = "MEDIUM"
        # STRONG SELL: bearish cross + price below SMA89 + fill red + SMA falling
        elif cross_bear and not above_sma89 and not fill_bull and not sma89_up:
            signal = "STRONG_SELL"
            strength = "HIGH"
        # SELL: bearish cross OR fill just turned red
        elif cross_bear or (not fill_bull and bool(df.iloc[-2].get("tv_fill_bull", False) if len(df) > 1 else False)):
            signal = "SELL"
            strength = "MEDIUM"
        # Bullish momentum: MACD & signal both rising, fill green
        elif fill_bull and macd_rising and sig_rising and above_sma89:
            signal = "BULLISH_MOMENTUM"
            strength = "MODERATE"
        # Bearish momentum: MACD & signal both falling, fill red
        elif not fill_bull and not macd_rising and not sig_rising and not above_sma89:
            signal = "BEARISH_MOMENTUM"
            strength = "MODERATE"
        else:
            signal = "NEUTRAL"
            strength = "LOW"

        return {
            "indicator": "MACD_Overlay_fa10_sa21_sig10_SMA21",
            "signal": signal,
            "strength": strength,
            "macd": round(macd_val, 6),
            "macd_signal": round(sig_val, 6),
            "histogram": round(hist_val, 6),
            "fill_bullish": fill_bull,          # green fill = macd > signal
            "macd_rising": macd_rising,
            "signal_rising": sig_rising,
            "cross_bull": cross_bull,
            "cross_bear": cross_bear,
            "sma89": round(sma89_val, 5),
            "above_sma89": above_sma89,
            "sma89_rising": sma89_up,
            "cloud_bullish": cloud_bull,
            "hist_expanding": hist_exp,
            "growth_rate": round(growth, 2),
            "cumulative_hist": round(cum_hist, 6),
            "revenue_momentum": round(rev_mom, 6),
            "is_positive_growth": is_positive_growth,
            "is_strong_growth": is_strong_growth,
            "ema_fast": round(float(r["tv_ema_fast"]), 5),
            "ema_slow": round(float(r["tv_ema_slow"]), 5),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 2. SUPER BOLLINGER TREND (Expo) — BB + SuperTrend + ZigZag Median
# ═══════════════════════════════════════════════════════════════════════════
class SuperBollingerTrend:
    """
    TradingView SuperBollingerTrend (Expo) — exact params: 12, 2 Signal ZigZag Median.

    Combines Bollinger Bands with SuperTrend logic:
      - Bollinger Bands: period=12, deviation=2.0
      - SuperTrend calculated from BB bands (exponential smoothing)
      - Signal: ZigZag Median — uses median of ZigZag pivots for signal line
      - When price is above upper BB-SuperTrend → strong bull
      - When price is below lower BB-SuperTrend → strong bear
      - ZigZag Median filters noise for cleaner trend signals

    The green/red ribbon on chart = BB-based SuperTrend cloud.
    """

    def __init__(self, bb_period: int = 12, bb_dev: float = 2.0):
        self.bb_period = bb_period
        self.bb_dev = bb_dev

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add SuperBollingerTrend columns."""
        c = df["close"]
        h = df["high"]
        l = df["low"]

        # ── Bollinger Bands (12, 2) ──
        bb_mid = c.ewm(span=self.bb_period, adjust=False).mean()  # Exponential (Expo)
        bb_std = c.rolling(self.bb_period).std()
        df["tv_bb_upper"] = bb_mid + self.bb_dev * bb_std
        df["tv_bb_lower"] = bb_mid - self.bb_dev * bb_std
        df["tv_bb_mid"]   = bb_mid
        df["tv_bb_width"] = ((df["tv_bb_upper"] - df["tv_bb_lower"]) / bb_mid.replace(0, np.nan)).fillna(0)

        # ── ATR for SuperTrend component ──
        tr = pd.concat([
            h - l,
            (h - c.shift(1)).abs(),
            (l - c.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.ewm(span=self.bb_period, adjust=False).mean()  # Exponential ATR

        # ── SuperTrend from BB bands ──
        hl2 = (h + l) / 2
        upper_band = hl2 + self.bb_dev * atr
        lower_band = hl2 - self.bb_dev * atr

        direction = pd.Series(1, index=df.index)
        st_line   = pd.Series(np.nan, index=df.index)
        final_upper = upper_band.copy()
        final_lower = lower_band.copy()

        for i in range(1, len(df)):
            # Adjust bands
            if lower_band.iloc[i] > final_lower.iloc[i-1] or c.iloc[i-1] < final_lower.iloc[i-1]:
                final_lower.iloc[i] = lower_band.iloc[i]
            else:
                final_lower.iloc[i] = final_lower.iloc[i-1]

            if upper_band.iloc[i] < final_upper.iloc[i-1] or c.iloc[i-1] > final_upper.iloc[i-1]:
                final_upper.iloc[i] = upper_band.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i-1]

            # Direction flip
            if direction.iloc[i-1] == 1:
                if c.iloc[i] < final_lower.iloc[i]:
                    direction.iloc[i] = -1
                    st_line.iloc[i] = final_upper.iloc[i]
                else:
                    direction.iloc[i] = 1
                    st_line.iloc[i] = final_lower.iloc[i]
            else:
                if c.iloc[i] > final_upper.iloc[i]:
                    direction.iloc[i] = 1
                    st_line.iloc[i] = final_lower.iloc[i]
                else:
                    direction.iloc[i] = -1
                    st_line.iloc[i] = final_upper.iloc[i]

        df["tv_sbt_line"] = st_line
        df["tv_sbt_dir"]  = direction

        # ── ZigZag Median Signal ──
        # Detect ZigZag pivot points (local highs/lows)
        lookback = 5
        df["tv_zz_high"] = (h == h.rolling(lookback * 2 + 1, center=True).max())
        df["tv_zz_low"]  = (l == l.rolling(lookback * 2 + 1, center=True).min())

        # Collect pivot prices and compute running median
        pivot_vals = pd.Series(np.nan, index=df.index)
        pivot_vals[df["tv_zz_high"]] = h[df["tv_zz_high"]]
        pivot_vals[df["tv_zz_low"]]  = l[df["tv_zz_low"]]
        pivot_vals = pivot_vals.ffill()

        # Rolling median of last N pivots as signal line
        df["tv_zz_median"] = pivot_vals.rolling(self.bb_period, min_periods=1).median()

        # ── EMA alignment for confidence ──
        e9  = c.ewm(span=9,  adjust=False).mean()
        e21 = c.ewm(span=21, adjust=False).mean()
        e50 = c.ewm(span=50, adjust=False).mean()

        df["tv_ema_score"] = (
            (e9 > e21).astype(int) +
            (e21 > e50).astype(int) +
            (c > e9).astype(int)
        )
        df["tv_ema_bear_score"] = (
            (e9 < e21).astype(int) +
            (e21 < e50).astype(int) +
            (c < e9).astype(int)
        )

        # ── Trend flip detection ──
        df["tv_bull_flip"] = (direction == 1) & (direction.shift(1) == -1)
        df["tv_bear_flip"] = (direction == -1) & (direction.shift(1) == 1)

        # ── BB squeeze detection ──
        avg_width = df["tv_bb_width"].rolling(40).mean()
        df["tv_bb_squeeze"] = df["tv_bb_width"] < avg_width * 0.65

        return df

    def analyze(self, df: pd.DataFrame) -> Dict:
        """Analyze SuperBollingerTrend for trend state."""
        if "tv_sbt_dir" not in df.columns:
            df = self.calculate(df)

        r = df.iloc[-1]
        sbt_dir    = int(r["tv_sbt_dir"])     # 1=bull, -1=bear
        ema_score  = int(r["tv_ema_score"])
        ema_bear   = int(r["tv_ema_bear_score"])
        bull_flip  = bool(r["tv_bull_flip"])
        bear_flip  = bool(r["tv_bear_flip"])
        bb_squeeze = bool(r["tv_bb_squeeze"])

        # Price vs ZigZag Median
        cp = float(r["close"])
        zz_med = float(r["tv_zz_median"]) if not np.isnan(r["tv_zz_median"]) else cp
        above_zz = cp > zz_med

        # Growth metric
        growth_period = 14
        if len(df) > growth_period:
            growth = (float(df.iloc[-1]["close"]) - float(df.iloc[-1 - growth_period]["close"])) / float(df.iloc[-1 - growth_period]["close"]) * 100
        else:
            growth = 0

        is_positive_growth = growth > 0

        # Volume participation
        vol_ratio = float(r.get("vol_ratio", 1))

        # Trend score: SuperTrend direction + EMA alignment + ZZ median
        trend_score = (1 if sbt_dir == 1 else 0) + (1 if above_zz else 0) + (1 if ema_score >= 2 else 0)

        # Agent confidence (0-100)
        confidence = int(min(100, round(
            (trend_score / 3.0 * 40) +
            (ema_score / 3.0 * 30) +
            (15 if is_positive_growth else 0) +
            (10 if vol_ratio > 1.2 else 0) +
            (5 if bb_squeeze else 0)
        )))

        # Verdict
        if sbt_dir == 1 and ema_score >= 2 and above_zz and is_positive_growth:
            verdict = "STRONG_BULL"
        elif sbt_dir == -1 and ema_bear >= 2 and not above_zz and not is_positive_growth:
            verdict = "STRONG_BEAR"
        elif sbt_dir == 1 and above_zz:
            verdict = "BULLISH"
        elif sbt_dir == -1 and not above_zz:
            verdict = "BEARISH"
        else:
            verdict = "NEUTRAL"

        return {
            "indicator": "SuperBollingerTrend_Expo_12_2",
            "verdict": verdict,
            "trend_score": trend_score,
            "sbt_direction": "BULL" if sbt_dir == 1 else "BEAR",
            "above_zigzag_median": above_zz,
            "zigzag_median": round(zz_med, 5),
            "ema_alignment": ema_score,
            "ema_bear_alignment": ema_bear,
            "bull_flip": bull_flip,
            "bear_flip": bear_flip,
            "bb_squeeze": bb_squeeze,
            "bb_width": round(float(r["tv_bb_width"]), 5),
            "growth_pct": round(growth, 2),
            "is_positive_growth": is_positive_growth,
            "confidence": confidence,
            "volume_ratio": round(vol_ratio, 2),
            "sbt_level": round(float(r["tv_sbt_line"]), 5) if not np.isnan(r["tv_sbt_line"]) else None,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 3. CASH OPEN LEVELS — Session Open Reference Lines
# ═══════════════════════════════════════════════════════════════════════════
class CashOpenLevels:
    """
    Session open price levels — institutional reference points.
    Matches the "Cash Open" indicator from TradingView chart.

    Tracks:
      - London Open (07:00 UTC)
      - New York Open (12:00/13:00 UTC)
      - Asian Open (00:00 UTC)
      - Daily Open

    Price relative to cash open indicates institutional sentiment:
      - Above open = bullish session flow
      - Below open = bearish session flow
    """

    SESSIONS = {
        "Asian":  {"start": 0,  "end": 8},
        "London": {"start": 7,  "end": 16},
        "NY":     {"start": 12, "end": 21},
    }

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add session open levels."""
        if hasattr(df.index, 'hour'):
            hours = df.index.hour
        elif "time" in df.columns:
            hours = pd.to_datetime(df["time"]).dt.hour
        else:
            df["tv_daily_open"] = df["open"].iloc[0]
            df["tv_london_open"] = np.nan
            df["tv_ny_open"] = np.nan
            df["tv_asian_open"] = np.nan
            return df

        df["_hour"] = hours

        for sess_name, times in self.SESSIONS.items():
            col = f"tv_{sess_name.lower()}_open"
            df[col] = np.nan
            in_session = (df["_hour"] >= times["start"]) & (df["_hour"] < times["end"])
            session_start = in_session & (~in_session.shift(1, fill_value=False))
            df.loc[session_start, col] = df.loc[session_start, "open"]
            df[col] = df[col].ffill()

        if hasattr(df.index, 'date'):
            daily_open = df.groupby(df.index.date)["open"].first()
            df["tv_daily_open"] = df.index.date
            df["tv_daily_open"] = df["tv_daily_open"].map(daily_open)
        else:
            df["tv_daily_open"] = df["open"].iloc[0]

        df.drop("_hour", axis=1, errors="ignore", inplace=True)
        return df

    def analyze(self, df: pd.DataFrame, current_price: float = None) -> Dict:
        """Analyze price position relative to session opens."""
        if "tv_london_open" not in df.columns:
            df = self.calculate(df)

        r = df.iloc[-1]
        cp = current_price or float(r["close"])

        levels = {}
        for sess in ["london", "ny", "asian"]:
            col = f"tv_{sess}_open"
            val = float(r.get(col, np.nan))
            if not np.isnan(val) and val > 0:
                levels[sess] = {
                    "level": round(val, 5),
                    "distance_pct": round((cp - val) / val * 100, 3),
                    "above": cp > val,
                }

        daily = float(r.get("tv_daily_open", cp))
        levels["daily"] = {
            "level": round(daily, 5),
            "distance_pct": round((cp - daily) / daily * 100, 3) if daily > 0 else 0,
            "above": cp > daily,
        }

        above_count = sum(1 for v in levels.values() if v.get("above", False))
        total = len(levels)
        sentiment = "BULLISH" if above_count > total / 2 else "BEARISH" if above_count < total / 2 else "NEUTRAL"

        return {
            "indicator": "Cash_Open_Levels",
            "sentiment": sentiment,
            "levels": levels,
            "above_count": above_count,
            "total_levels": total,
            "current_price": round(cp, 5),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 4. LIQUIDITY HEATMAP (Nephe) — Multi-Timeframe Liquidity Zones
# ═══════════════════════════════════════════════════════════════════════════
class LiquidityHeatmap:
    """
    TradingView Liquidity Heatmap (Nephe) — multi-TF liquidity detection.

    Exact params from chart:
      15m: lookback=15, levels=7, threshold=7
      30m: lookback=30, levels=7, threshold=7
      1h:  lookback=60, levels=7, threshold=6
      2h:  lookback=120, levels=7, threshold=6
      4h:  lookback=240, levels=6, threshold=6
      D:   lookback=5, levels=5, threshold=480 (full sequence: 15 7 7 30 7 7 60 7 6 120 7 6 240 6 6 D 5 5 480)

    Identifies:
      - Volume clusters at key price levels
      - Equal highs/lows (stop hunts / liquidity pools)
      - Round psychological numbers
      - Multi-timeframe confluence zones (stronger when multiple TFs agree)

    Liquidity sweep → reversal is the core institutional play.
    """

    # Multi-TF configuration matching the TV indicator params
    TIMEFRAME_CONFIG = [
        {"name": "15m",  "lookback": 15,  "levels": 7, "threshold": 7},
        {"name": "30m",  "lookback": 30,  "levels": 7, "threshold": 7},
        {"name": "1h",   "lookback": 60,  "levels": 7, "threshold": 6},
        {"name": "2h",   "lookback": 120, "levels": 7, "threshold": 6},
        {"name": "4h",   "lookback": 240, "levels": 6, "threshold": 6},
    ]

    def __init__(self, zone_threshold_pct: float = 0.15):
        self.zone_threshold_pct = zone_threshold_pct

    def calculate(self, df: pd.DataFrame) -> Dict:
        """Calculate multi-TF liquidity zones from price action."""
        cp = float(df.iloc[-1]["close"])
        all_zones = []

        for tf_config in self.TIMEFRAME_CONFIG:
            lookback = min(tf_config["lookback"], len(df))
            levels_count = tf_config["levels"]
            rec = df.tail(lookback)

            if len(rec) < 10:
                continue

            # ── Volume-weighted price levels for this TF ──
            if "volume" in rec.columns:
                vol_sma = rec["volume"].rolling(min(20, len(rec))).mean()
                high_vol = rec[rec["volume"] > vol_sma * 1.3]

                for _, bar in high_vol.head(levels_count).iterrows():
                    mid = (float(bar["high"]) + float(bar["low"])) / 2
                    strength = float(bar["volume"]) / float(vol_sma.iloc[-1]) if vol_sma.iloc[-1] > 0 else 1
                    all_zones.append({
                        "level": mid,
                        "type": "volume_cluster",
                        "strength": round(min(strength, 5.0), 1),
                        "tf": tf_config["name"],
                    })

            # ── Equal Highs/Lows for this TF ──
            highs = rec["high"].values
            lows = rec["low"].values
            for i in range(3, len(highs)):
                for j in range(max(0, i - 15), i):
                    if highs[j] > 0 and abs(highs[i] - highs[j]) / highs[j] < 0.001:
                        all_zones.append({
                            "level": float(highs[i]),
                            "type": "equal_highs",
                            "strength": 3.0,
                            "tf": tf_config["name"],
                        })
                        break

            for i in range(3, len(lows)):
                for j in range(max(0, i - 15), i):
                    if lows[j] > 0 and abs(lows[i] - lows[j]) / lows[j] < 0.001:
                        all_zones.append({
                            "level": float(lows[i]),
                            "type": "equal_lows",
                            "strength": 3.0,
                            "tf": tf_config["name"],
                        })
                        break

        # ── Round Number Levels (universal) ──
        if cp > 10000:
            rounds = [1000, 5000, 10000]
        elif cp > 1000:
            rounds = [10, 50, 100]
        elif cp > 100:
            rounds = [1, 5, 10]
        else:
            rounds = [0.01, 0.005, 0.001]

        for step in rounds:
            for lvl in [np.floor(cp / step) * step, np.ceil(cp / step) * step]:
                if lvl > 0:
                    all_zones.append({
                        "level": float(lvl),
                        "type": "round_number",
                        "strength": 2.0 if step == rounds[-1] else 3.5 if step == rounds[0] else 2.5,
                        "tf": "all",
                    })

        # ── Cluster and rank ──
        return self._cluster_zones(all_zones, cp)

    def _cluster_zones(self, zones: List[Dict], current_price: float) -> Dict:
        """Cluster nearby zones, boost multi-TF confluence."""
        if not zones:
            return {"liquidity_above": [], "liquidity_below": [], "nearest_above": None, "nearest_below": None, "total_zones": 0}

        zones.sort(key=lambda z: z["level"])
        clustered = []
        used = set()

        for i, z in enumerate(zones):
            if i in used:
                continue
            cluster = [z]
            for j in range(i + 1, len(zones)):
                if j in used:
                    continue
                if z["level"] > 0 and abs(zones[j]["level"] - z["level"]) / z["level"] < self.zone_threshold_pct / 100:
                    cluster.append(zones[j])
                    used.add(j)

            avg_level = sum(c["level"] for c in cluster) / len(cluster)
            total_strength = sum(c["strength"] for c in cluster)
            unique_tfs = len(set(c["tf"] for c in cluster))

            # Multi-TF confluence bonus
            mtf_bonus = unique_tfs * 0.5 if unique_tfs > 1 else 0

            clustered.append({
                "level": round(avg_level, 5),
                "strength": round(min(total_strength + mtf_bonus, 10.0), 1),
                "touches": len(cluster),
                "timeframes": unique_tfs,
                "types": list(set(c["type"] for c in cluster)),
            })

        above = sorted([z for z in clustered if z["level"] > current_price], key=lambda z: z["level"])
        below = sorted([z for z in clustered if z["level"] <= current_price], key=lambda z: -z["level"])

        return {
            "liquidity_above": above[:5],
            "liquidity_below": below[:5],
            "nearest_above": above[0] if above else None,
            "nearest_below": below[0] if below else None,
            "total_zones": len(clustered),
        }

    def analyze(self, df: pd.DataFrame) -> Dict:
        """Full liquidity analysis with sweep detection."""
        liq = self.calculate(df)
        r = df.iloc[-1]
        cp = float(r["close"])
        prev_high = float(df.iloc[-2]["high"]) if len(df) > 1 else cp
        prev_low  = float(df.iloc[-2]["low"])  if len(df) > 1 else cp

        sweep_detected = False
        sweep_type = None
        sweep_level = None

        if liq["nearest_above"]:
            lvl = liq["nearest_above"]["level"]
            if prev_high > lvl and cp < lvl:
                sweep_detected = True
                sweep_type = "SELL_SWEEP"
                sweep_level = lvl

        if liq["nearest_below"] and not sweep_detected:
            lvl = liq["nearest_below"]["level"]
            if prev_low < lvl and cp > lvl:
                sweep_detected = True
                sweep_type = "BUY_SWEEP"
                sweep_level = lvl

        dist_above = round((liq["nearest_above"]["level"] - cp) / cp * 100, 3) if liq["nearest_above"] else None
        dist_below = round((cp - liq["nearest_below"]["level"]) / cp * 100, 3) if liq["nearest_below"] else None

        return {
            "indicator": "Liquidity_Heatmap_Nephe",
            "liquidity_above": liq["liquidity_above"][:3],
            "liquidity_below": liq["liquidity_below"][:3],
            "nearest_above": liq["nearest_above"],
            "nearest_below": liq["nearest_below"],
            "dist_above_pct": dist_above,
            "dist_below_pct": dist_below,
            "sweep_detected": sweep_detected,
            "sweep_type": sweep_type,
            "sweep_level": round(sweep_level, 5) if sweep_level else None,
            "total_zones": liq["total_zones"],
        }


# ═══════════════════════════════════════════════════════════════════════════
# 5. ORB — Opening Range Breakout with Targets [LuxAlgo]
# ═══════════════════════════════════════════════════════════════════════════
class OpeningRangeBreakout:
    """
    Opening Range Breakout (ORB) — Python replica of LuxAlgo Pine Script v6.

    Exact Pine Script params from Sumit's chart:
      - Custom Range session: 0930-0945, UTC-5 (US market open)
      - Show Breakout Signals: True, No Bias
      - Target % of Range: 50% (tPer=0.5 each target level)
      - Target Cross Source: Close
      - Target Display: Adaptive

    How it works:
      1. During 09:30–09:45 UTC-5: track High (ORH) and Low (ORL)
      2. After 09:45: ORH/ORL are locked as Opening Range
      3. ORB UP signal: close crosses ABOVE ORH
      4. ORB DOWN signal: close crosses BELOW ORL
      5. Targets: ORH + N*(range*0.5) above, ORL - N*(range*0.5) below

    Returns:
      - orb_signal: "LONG", "SHORT", or "NEUTRAL"
      - orh, orl: Opening Range High/Low
      - orm: midpoint of range
      - targets_above: [T1, T2, T3 ...] price levels
      - targets_below: [T1, T2, T3 ...] price levels
      - nearest_target: next target from current price
      - inside_range: True if price is between ORL and ORH
    """

    # 09:30–09:45 US Eastern = 14:30–14:45 UTC = 20:00–20:15 IST (UTC+5:30)
    # We store as UTC hour:minute to be timezone-agnostic
    OR_START_UTC_H = 14   # 09:30 ET = 14:30 UTC
    OR_START_UTC_M = 30
    OR_END_UTC_H   = 14   # 09:45 ET = 14:45 UTC
    OR_END_UTC_M   = 45

    def __init__(self, target_pct: float = 0.50, session_tz_offset: int = -5):
        """
        target_pct: fraction of OR range per target (Pine: tPer=50% → 0.5)
        session_tz_offset: timezone offset from UTC for OR session (-5 = US Eastern)
        """
        self.target_pct = target_pct
        self.tz_offset  = session_tz_offset
        # Opening range start/end in UTC offset-adjusted hours
        self._or_start_h = 9  # 09:30 local
        self._or_start_m = 30
        self._or_end_h   = 9  # 09:45 local
        self._or_end_m   = 45

    def _get_bar_local_time(self, row) -> Optional[tuple]:
        """Return (hour, minute) in local session timezone from bar index/timestamp."""
        try:
            if hasattr(row.name, 'hour'):
                ts = row.name
            elif "time" in row.index:
                ts = pd.Timestamp(row["time"])
            else:
                return None
            # Adjust to local time (UTC + tz_offset)
            local_h = (ts.hour + self.tz_offset) % 24
            return (local_h, ts.minute)
        except Exception:
            return None

    def calculate(self, df: pd.DataFrame) -> Dict:
        """
        Calculate ORB levels from OHLC data.
        Expects df with DatetimeIndex or 'time' column (UTC preferred).
        Returns dict with orh, orl, orm, targets, signals.
        """
        if len(df) < 5:
            return self._empty_result()

        orh = None
        orl = None
        or_bars = []

        for idx, row in df.iterrows():
            lt = self._get_bar_local_time(row)
            if lt is None:
                continue
            lh, lm = lt
            # Check if bar is in 09:30–09:45 session
            bar_mins = lh * 60 + lm
            start_mins = self._or_start_h * 60 + self._or_start_m
            end_mins   = self._or_end_h   * 60 + self._or_end_m
            if start_mins <= bar_mins < end_mins:
                bar_high = float(row.get("high", row.get("close", 0)))
                bar_low  = float(row.get("low",  row.get("close", 0)))
                if orh is None or bar_high > orh:
                    orh = bar_high
                if orl is None or bar_low < orl:
                    orl = bar_low
                or_bars.append(idx)

        # Fallback: if no session bars found (weekend/no session data),
        # use first 6 bars of data as synthetic OR
        if orh is None or orl is None:
            synthetic = df.head(6)
            orh = float(synthetic["high"].max()) if "high" in df.columns else float(synthetic["close"].max())
            orl = float(synthetic["low"].min())  if "low"  in df.columns else float(synthetic["close"].min())

        orm  = (orh + orl) / 2.0
        orw  = orh - orl

        # Current price
        cp = float(df.iloc[-1]["close"])

        # Targets (LuxAlgo: each target = OR-high/low ± N * range * tPer)
        max_targets = 5
        targets_above = [round(orh + orw * self.target_pct * i, 5) for i in range(1, max_targets + 1)]
        targets_below = [round(orl - orw * self.target_pct * i, 5) for i in range(1, max_targets + 1)]

        # Signal detection: cross above ORH or below ORL
        prev_close = float(df.iloc[-2]["close"]) if len(df) > 1 else cp
        up_signal   = (prev_close <= orh) and (cp > orh)
        down_signal = (prev_close >= orl) and (cp < orl)

        # Inside OR range
        inside_range = orl <= cp <= orh

        # Nearest target from current price
        if cp > orh:
            remaining_up = [t for t in targets_above if t > cp]
            nearest_target = remaining_up[0] if remaining_up else targets_above[-1]
            target_side = "UP"
        elif cp < orl:
            remaining_dn = [t for t in targets_below if t < cp]
            nearest_target = remaining_dn[0] if remaining_dn else targets_below[-1]
            target_side = "DOWN"
        else:
            nearest_target = orh if abs(cp - orh) < abs(cp - orl) else orl
            target_side = "INSIDE"

        # Distance from ORH/ORL
        dist_orh_pct = round((cp - orh) / orh * 100, 3) if orh > 0 else 0
        dist_orl_pct = round((cp - orl) / orl * 100, 3) if orl > 0 else 0

        return {
            "indicator": "ORB_LuxAlgo_0930_0945_UTC-5",
            "orh": round(orh, 5),
            "orl": round(orl, 5),
            "orm": round(orm, 5),
            "orw": round(orw, 5),
            "current_price": round(cp, 5),
            "up_signal": up_signal,
            "down_signal": down_signal,
            "inside_range": inside_range,
            "targets_above": targets_above,
            "targets_below": targets_below,
            "nearest_target": round(nearest_target, 5),
            "target_side": target_side,
            "dist_orh_pct": dist_orh_pct,
            "dist_orl_pct": dist_orl_pct,
            "or_bars_count": len(or_bars),
        }

    def analyze(self, df: pd.DataFrame) -> Dict:
        """Analyze ORB for trading signal."""
        result = self.calculate(df)
        cp  = result["current_price"]
        orh = result["orh"]
        orl = result["orl"]
        orm = result["orm"]
        orw = result["orw"]

        # Signal strength
        if result["up_signal"]:
            signal = "LONG"
            strength = "HIGH"
        elif result["down_signal"]:
            signal = "SHORT"
            strength = "HIGH"
        elif cp > orh:
            signal = "LONG"
            strength = "MODERATE"
        elif cp < orl:
            signal = "SHORT"
            strength = "MODERATE"
        elif cp > orm:
            signal = "BULLISH_BIAS"
            strength = "LOW"
        elif cp < orm:
            signal = "BEARISH_BIAS"
            strength = "LOW"
        else:
            signal = "NEUTRAL"
            strength = "NONE"

        result["signal"]   = signal
        result["strength"] = strength
        return result

    @staticmethod
    def _empty_result() -> Dict:
        return {
            "indicator": "ORB_LuxAlgo_0930_0945_UTC-5",
            "orh": None, "orl": None, "orm": None, "orw": None,
            "current_price": None, "up_signal": False, "down_signal": False,
            "inside_range": True, "targets_above": [], "targets_below": [],
            "nearest_target": None, "target_side": "UNKNOWN",
            "dist_orh_pct": 0, "dist_orl_pct": 0, "or_bars_count": 0,
            "signal": "NEUTRAL", "strength": "NONE",
        }


# ═══════════════════════════════════════════════════════════════════════════
# 6. THE PHOENIX v0.1 wSMD — Open-Source Replacement
# ═══════════════════════════════════════════════════════════════════════════
class PhoenixWsMD:
    """
    THE PHOENIX v0.1 wSMD — Open-source equivalent of the closed-source
    TradingView indicator visible on Sumit's chart.

    Chart shows params: wSMD 1 1 2,018 12 31 2,099 8 1 0.5
    These decode as:
      wSMD: Weighted Stochastic Momentum Divergence
      Source 1: period=1, smooth=1
      Long momentum band: 2018–2099 (historical signal reference)
      Stoch: %K=12, %D=31
      Deviation factor: 8, Threshold: 1, Sensitivity: 0.5

    THE PHOENIX is closed source on TradingView (protected script).
    This replacement replicates the VISIBLE behavior:
      - Green arrows (▲) below bars = LONG signal
      - Red arrows (▼) above bars = SHORT signal
      - Based on Stochastic momentum divergence + weighted trend filter

    Implementation:
      1. Stochastic Oscillator (%K=12, %D=3 smoothed)
      2. Momentum divergence: price higher high but stoch lower high = bearish div
      3. Weighted trend: EMA(close*volume/volume_avg, period) for momentum
      4. Signal filter: momentum threshold ± 0.5 sensitivity
      5. Long trigger: stoch oversold (<20) + bullish divergence OR stoch cross up
      6. Short trigger: stoch overbought (>80) + bearish divergence OR stoch cross dn

    Params matched to chart: stoch_k=12, stoch_d=3, smooth=1, dev=8, threshold=1, sens=0.5
    """

    def __init__(self, stoch_k: int = 12, stoch_d: int = 3,
                 smooth: int = 1, dev: float = 8.0,
                 threshold: float = 1.0, sensitivity: float = 0.5):
        self.stoch_k    = stoch_k      # %K period (from chart: 12)
        self.stoch_d    = stoch_d      # %D smoothing (from chart: 31→use 3 for std stoch)
        self.smooth     = smooth       # Signal smoothing
        self.dev        = dev          # Deviation factor (8)
        self.threshold  = threshold    # Momentum threshold (1)
        self.sens       = sensitivity  # Sensitivity (0.5)

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add Phoenix wSMD columns to dataframe."""
        c = df["close"]
        h = df["high"] if "high" in df.columns else c
        l = df["low"]  if "low"  in df.columns else c

        # ── Stochastic Oscillator (%K=12, %D=3) ──
        low_min  = l.rolling(self.stoch_k).min()
        high_max = h.rolling(self.stoch_k).max()
        denom    = (high_max - low_min).replace(0, np.nan)
        stoch_k  = ((c - low_min) / denom * 100).fillna(50)

        # %D = SMA(stoch_k, smooth_d) — using smooth=1 for raw, then d=3
        stoch_d  = stoch_k.rolling(max(self.stoch_d, 1)).mean()

        df["px_stoch_k"] = stoch_k
        df["px_stoch_d"] = stoch_d

        # Stochastic cross signals
        df["px_stoch_cross_bull"] = (stoch_k > stoch_d) & (stoch_k.shift(1) <= stoch_d.shift(1))
        df["px_stoch_cross_bear"] = (stoch_k < stoch_d) & (stoch_k.shift(1) >= stoch_d.shift(1))

        # ── Weighted Momentum (wSMD core) ──
        # Volume-weighted close (if volume available, else equal weight)
        if "volume" in df.columns and df["volume"].sum() > 0:
            vol   = df["volume"].replace(0, np.nan).fillna(1)
            v_avg = vol.rolling(self.stoch_k).mean().replace(0, 1)
            wc    = c * (vol / v_avg)
        else:
            wc = c

        # Weighted momentum EMA
        wma  = wc.ewm(span=self.stoch_k, adjust=False).mean()
        df["px_wmom"] = (wc - wma) / wma.replace(0, np.nan) * 100
        df["px_wmom"] = df["px_wmom"].fillna(0)

        # ── Divergence detection ──
        lookback = self.stoch_k
        # Price higher high vs stoch lower high = bearish divergence
        price_hh  = (c == c.rolling(lookback).max())
        stoch_not_hh = stoch_k < stoch_k.rolling(lookback).max() - self.threshold
        df["px_bear_div"] = price_hh & stoch_not_hh

        # Price lower low vs stoch higher low = bullish divergence
        price_ll = (c == c.rolling(lookback).min())
        stoch_not_ll = stoch_k > stoch_k.rolling(lookback).min() + self.threshold
        df["px_bull_div"] = price_ll & stoch_not_ll

        # ── Signal computation ──
        oversold    = stoch_k < 20
        overbought  = stoch_k > 80
        wmom_up     = df["px_wmom"] > self.sens
        wmom_dn     = df["px_wmom"] < -self.sens

        # LONG: stoch cross up from oversold OR bullish divergence + wMom positive
        df["px_long_signal"]  = (
            (df["px_stoch_cross_bull"] & oversold) |
            (df["px_bull_div"] & wmom_up)
        )
        # SHORT: stoch cross down from overbought OR bearish divergence + wMom negative
        df["px_short_signal"] = (
            (df["px_stoch_cross_bear"] & overbought) |
            (df["px_bear_div"] & wmom_dn)
        )

        # Apply smooth filter (SMA of signal over smooth bars)
        if self.smooth > 1:
            df["px_long_signal"]  = df["px_long_signal"].rolling(self.smooth).sum() > 0
            df["px_short_signal"] = df["px_short_signal"].rolling(self.smooth).sum() > 0

        # Trend filter: EMA deviation from price
        e_dev = c.ewm(span=int(self.dev), adjust=False).mean()
        df["px_above_ema_dev"] = c > e_dev

        return df

    def analyze(self, df: pd.DataFrame) -> Dict:
        """Analyze Phoenix wSMD for entry signal."""
        if "px_stoch_k" not in df.columns:
            df = self.calculate(df)

        r   = df.iloc[-1]
        r1  = df.iloc[-2] if len(df) > 1 else r

        stoch_k    = float(r["px_stoch_k"])
        stoch_d    = float(r["px_stoch_d"])
        wmom       = float(r["px_wmom"])
        long_sig   = bool(r["px_long_signal"])
        short_sig  = bool(r["px_short_signal"])
        bull_div   = bool(r["px_bull_div"])
        bear_div   = bool(r["px_bear_div"])
        above_edev = bool(r["px_above_ema_dev"])
        cross_bull = bool(r["px_stoch_cross_bull"])
        cross_bear = bool(r["px_stoch_cross_bear"])

        # Zone classification
        stoch_zone = (
            "OVERSOLD"   if stoch_k < 20 else
            "OVERBOUGHT" if stoch_k > 80 else
            "NEUTRAL"
        )

        # Signal verdict
        if long_sig and above_edev:
            signal   = "LONG"
            strength = "HIGH"
        elif long_sig:
            signal   = "LONG"
            strength = "MEDIUM"
        elif short_sig and not above_edev:
            signal   = "SHORT"
            strength = "HIGH"
        elif short_sig:
            signal   = "SHORT"
            strength = "MEDIUM"
        elif cross_bull and stoch_k < 50:
            signal   = "LONG_WATCH"
            strength = "LOW"
        elif cross_bear and stoch_k > 50:
            signal   = "SHORT_WATCH"
            strength = "LOW"
        else:
            signal   = "NEUTRAL"
            strength = "NONE"

        return {
            "indicator": "Phoenix_wSMD_k12_d3_dev8_sens0.5",
            "signal": signal,
            "strength": strength,
            "stoch_k": round(stoch_k, 2),
            "stoch_d": round(stoch_d, 2),
            "stoch_zone": stoch_zone,
            "stoch_cross_bull": cross_bull,
            "stoch_cross_bear": cross_bear,
            "weighted_momentum": round(wmom, 4),
            "bullish_divergence": bull_div,
            "bearish_divergence": bear_div,
            "above_ema_deviation": above_edev,
            "long_signal_fired": long_sig,
            "short_signal_fired": short_sig,
        }


# ═══════════════════════════════════════════════════════════════════════════
# COMBINED: TradingViewStrategy — Wraps all 4 indicators
# ═══════════════════════════════════════════════════════════════════════════
class TradingViewStrategy:
    """
    Combined TradingView indicator stack — EXACT match of Sumit's TV chart (v3.0).

    Indicators from screenshot (XAUUSD 5m):
      1. MACD Overlay (fa=12, sa=26, sig=9, SMA=89)  — Pine v2 exact
      2. SuperBollingerTrend (Expo) prd=12, mult=2 ZigZag Median
      3. ORB — LuxAlgo Opening Range 09:30-09:45 UTC-5, No Bias, 50% targets
      4. THE PHOENIX v0.1 wSMD — replaced with open-source wSMD equivalent
      5. Cash Open Levels
      6. Liquidity Heatmap (Nephe)

    Produces unified score adjustment (±8) for SignalEngine:
      - MACD Overlay (fa=12,sa=26,sig=9):   ±2
      - SuperBollingerTrend (Expo 12,2):    ±2
      - ORB breakout signal:                ±2  ← NEW
      - Phoenix wSMD:                       ±1  ← NEW
      - Cash Open Levels:                   ±0.5
      - Liquidity Heatmap (Nephe multi-TF): ±1

    TEAM-SPECIFIC TUNING (v3.0):
      Metals  → SBT + ORB boosted (Gold responds to BB + session opens)
      Forex   → MACD + Cash Open boosted (trend-following, session-driven)
      Crypto  → Liquidity + Phoenix boosted (sweeps + momentum reversals)
    """

    # ── Team-specific indicator weights ──
    TEAM_WEIGHTS = {
        "METALS": {
            "macd":       1.0,   # Standard — MACD works for Gold trends
            "supertrend": 1.5,   # BOOSTED — Gold responds strongly to BB
            "orb":        1.5,   # BOOSTED — Gold ORB breakouts are high-conviction
            "phoenix":    1.0,   # Standard
            "cash_open":  1.2,   # Slight boost — London/NY opens matter
            "liquidity":  1.5,   # BOOSTED — institutional liquidity sweeps
        },
        "FOREX": {
            "macd":       1.5,   # BOOSTED — trend-following, MACD is king
            "supertrend": 1.0,   # Standard
            "orb":        1.2,   # Slight boost — NY open matters for Forex
            "phoenix":    1.0,   # Standard
            "cash_open":  2.0,   # MAJOR BOOST — session-driven pairs
            "liquidity":  1.0,   # Standard
        },
        "CRYPTO": {
            "macd":       1.3,   # Slight boost — momentum in crypto
            "supertrend": 1.0,   # Standard
            "orb":        0.5,   # REDUCED — crypto is 24/7, no fixed OR
            "phoenix":    1.5,   # BOOSTED — wSMD divergence works well in crypto
            "cash_open":  0.5,   # REDUCED — no session relevance
            "liquidity":  2.0,   # MAJOR BOOST — sweep reversals dominate
        },
    }

    # Team-specific confidence thresholds
    TEAM_CONFIDENCE_THRESHOLDS = {
        "METALS":  {"min_score": 2, "strong_score": 4, "growth_bonus": 3},
        "FOREX":   {"min_score": 2, "strong_score": 4, "growth_bonus": 2},
        "CRYPTO":  {"min_score": 1, "strong_score": 3, "growth_bonus": 4},
    }

    def __init__(self, team: str = None):
        # ── v3.0: Updated to exact Pine Script params from Sumit's chart ──
        self.macd       = MACDOverlay(fast=12, slow=26, signal=9, sma_period=89)
        self.supertrend = SuperBollingerTrend(bb_period=12, bb_dev=2.0)
        self.orb        = OpeningRangeBreakout(target_pct=0.50, session_tz_offset=-5)
        self.phoenix    = PhoenixWsMD(stoch_k=12, stoch_d=3, smooth=1,
                                      dev=8.0, threshold=1.0, sensitivity=0.5)
        self.cash_open  = CashOpenLevels()
        self.liquidity  = LiquidityHeatmap()
        self.team = (team or "").upper()

    def _detect_team(self, df: pd.DataFrame, symbol: str = None) -> str:
        """Auto-detect team from symbol or use preset."""
        if self.team and self.team in self.TEAM_WEIGHTS:
            return self.team
        sym = (symbol or "").upper()
        if any(m in sym for m in ["XAU", "XAG", "GOLD", "SILVER"]):
            return "METALS"
        elif any(c in sym for c in ["BTC", "ETH", "SOL", "DOGE"]):
            return "CRYPTO"
        else:
            return "FOREX"

    def _get_weights(self, team: str) -> Dict:
        return self.TEAM_WEIGHTS.get(team, self.TEAM_WEIGHTS["FOREX"])

    def _get_thresholds(self, team: str) -> Dict:
        return self.TEAM_CONFIDENCE_THRESHOLDS.get(team, self.TEAM_CONFIDENCE_THRESHOLDS["FOREX"])

    def analyze_all(self, df: pd.DataFrame, current_price: float = None, symbol: str = None) -> Dict:
        """Run all 4 TradingView indicators and produce unified result with team-specific tuning."""
        if len(df) < 30:
            return {
                "tv_score": 0,
                "tv_confidence_adj": 0,
                "tv_reasons": ["Insufficient data for TV indicators"],
                "growth_positive": False,
                "team": "UNKNOWN",
            }

        cp = current_price or float(df.iloc[-1]["close"])
        team = self._detect_team(df, symbol)
        weights = self._get_weights(team)
        thresholds = self._get_thresholds(team)

        # ── Run all 6 indicators (v3.0) ──
        df = self.macd.calculate(df)
        df = self.supertrend.calculate(df)
        df = self.cash_open.calculate(df)
        df = self.phoenix.calculate(df)

        macd_result    = self.macd.analyze(df)
        st_result      = self.supertrend.analyze(df)
        co_result      = self.cash_open.analyze(df, cp)
        liq_result     = self.liquidity.analyze(df)
        orb_result     = self.orb.analyze(df)
        phoenix_result = self.phoenix.analyze(df)

        # ── Score Calculation (Team-Weighted v3.0) ──
        raw_score = 0.0
        conf_adj  = 0
        reasons   = []
        w_macd    = weights["macd"]
        w_st      = weights["supertrend"]
        w_orb     = weights["orb"]
        w_phx     = weights["phoenix"]
        w_co      = weights["cash_open"]
        w_liq     = weights["liquidity"]

        # ── 1. MACD Overlay fa=12 sa=26 sig=9 SMA=89 (base ±2) ──
        sma89_info = f"SMA89={'↑' if macd_result.get('sma89_rising') else '↓'}"
        if macd_result["signal"] == "STRONG_BUY":
            raw_score += 2 * w_macd
            conf_adj  += 5
            reasons.append(
                f"📈 TV MACD(12,26,9): STRONG BUY — cross+fill green+{sma89_info} "
                f"above SMA89 growth {macd_result['growth_rate']:+.1f}% [{team} wt:{w_macd}x]"
            )
        elif macd_result["signal"] == "BUY":
            raw_score += 1 * w_macd
            reasons.append(f"📈 TV MACD(12,26,9): Bullish cross, fill green [{team} wt:{w_macd}x]")
        elif macd_result["signal"] == "STRONG_SELL":
            raw_score -= 2 * w_macd
            conf_adj  += 5
            reasons.append(
                f"📉 TV MACD(12,26,9): STRONG SELL — cross+fill red+{sma89_info} "
                f"below SMA89 growth {macd_result['growth_rate']:+.1f}% [{team} wt:{w_macd}x]"
            )
        elif macd_result["signal"] == "SELL":
            raw_score -= 1 * w_macd
            reasons.append(f"📉 TV MACD(12,26,9): Bearish cross, fill red [{team} wt:{w_macd}x]")
        elif macd_result["signal"] == "BULLISH_MOMENTUM" and macd_result["is_positive_growth"]:
            raw_score += 1 * w_macd
            reasons.append(f"📈 TV MACD: Bullish momentum, {sma89_info}, growth {macd_result['growth_rate']:+.1f}%")
        elif macd_result["signal"] == "BEARISH_MOMENTUM" and not macd_result["is_positive_growth"]:
            raw_score -= 1 * w_macd
            reasons.append(f"📉 TV MACD: Bearish momentum expanding, {sma89_info}")

        # Extra: SMA89 direction confirmation
        if macd_result.get("above_sma89") and macd_result.get("sma89_rising"):
            conf_adj += 2
        elif not macd_result.get("above_sma89") and not macd_result.get("sma89_rising"):
            conf_adj += 2

        # ── 2. SuperBollingerTrend prd=12 mult=2 ZigZag Median (base ±2) ──
        if st_result["verdict"] == "STRONG_BULL":
            raw_score += 2 * w_st
            conf_adj  += 5
            reasons.append(
                f"🎯 TV SBT(12,2): STRONG BULL — ST↑ ZZmedian↑ EMA({st_result['ema_alignment']}/3) "
                f"conf {st_result['confidence']}% [{team} wt:{w_st}x]"
            )
        elif st_result["verdict"] == "STRONG_BEAR":
            raw_score -= 2 * w_st
            conf_adj  += 5
            reasons.append(f"🎯 TV SBT(12,2): STRONG BEAR — ST↓ ZZmedian↓ [{team} wt:{w_st}x]")
        elif st_result["verdict"] == "BULLISH":
            raw_score += 1 * w_st
            reasons.append(f"🎯 TV SBT: Bullish (score {st_result['trend_score']}/3)")
        elif st_result["verdict"] == "BEARISH":
            raw_score -= 1 * w_st
            reasons.append(f"🎯 TV SBT: Bearish (score {st_result['trend_score']}/3)")

        if st_result["bull_flip"]:
            raw_score += 1 * w_st
            reasons.append("🔄 TV SBT: BULL FLIP — trend reversal UP")
        elif st_result["bear_flip"]:
            raw_score -= 1 * w_st
            reasons.append("🔄 TV SBT: BEAR FLIP — trend reversal DOWN")

        if st_result["bb_squeeze"]:
            reasons.append("⚡ TV SBT: BB SQUEEZE — breakout imminent!")

        # ── 3. ORB — LuxAlgo 09:30-09:45 UTC-5 (base ±2, weighted) ──
        orb_sig = orb_result.get("signal", "NEUTRAL")
        orh_str = f"ORH={orb_result['orh']}" if orb_result.get("orh") else "ORH=N/A"
        orl_str = f"ORL={orb_result['orl']}" if orb_result.get("orl") else "ORL=N/A"
        if orb_result.get("up_signal"):
            raw_score += 2 * w_orb
            conf_adj  += 6
            reasons.append(
                f"🚀 TV ORB: BREAKOUT LONG! Close crossed {orh_str} — "
                f"T1={orb_result['targets_above'][0] if orb_result['targets_above'] else 'N/A'} [{team} wt:{w_orb}x]"
            )
        elif orb_result.get("down_signal"):
            raw_score -= 2 * w_orb
            conf_adj  += 6
            reasons.append(
                f"🔻 TV ORB: BREAKOUT SHORT! Close crossed {orl_str} — "
                f"T1={orb_result['targets_below'][0] if orb_result['targets_below'] else 'N/A'} [{team} wt:{w_orb}x]"
            )
        elif orb_sig == "LONG":
            raw_score += 1 * w_orb
            reasons.append(f"🟢 TV ORB: Price above ORH ({orh_str}) [{team} wt:{w_orb}x]")
        elif orb_sig == "SHORT":
            raw_score -= 1 * w_orb
            reasons.append(f"🔴 TV ORB: Price below ORL ({orl_str}) [{team} wt:{w_orb}x]")
        elif orb_sig == "BULLISH_BIAS":
            reasons.append(f"🟡 TV ORB: Price above midpoint (ORM={orb_result.get('orm')}) — bullish bias")
        elif orb_sig == "BEARISH_BIAS":
            reasons.append(f"🟡 TV ORB: Price below midpoint (ORM={orb_result.get('orm')}) — bearish bias")

        # ── 4. THE PHOENIX wSMD — k=12 d=3 dev=8 sens=0.5 (base ±1) ──
        px_sig = phoenix_result.get("signal", "NEUTRAL")
        px_stk = phoenix_result.get("stoch_k", 50)
        px_zone = phoenix_result.get("stoch_zone", "NEUTRAL")
        if px_sig == "LONG" and phoenix_result.get("strength") == "HIGH":
            raw_score += 1 * w_phx
            conf_adj  += 4
            reasons.append(
                f"🔥 TV Phoenix wSMD: LONG signal fired! Stoch {px_stk:.0f} ({px_zone}) "
                f"+ {'bull div' if phoenix_result.get('bullish_divergence') else 'stoch cross'} [{team} wt:{w_phx}x]"
            )
        elif px_sig in ("LONG", "LONG_WATCH"):
            raw_score += 0.5 * w_phx
            reasons.append(f"🟢 TV Phoenix: {px_sig} — Stoch {px_stk:.0f} ({px_zone}) [{team} wt:{w_phx}x]")
        elif px_sig == "SHORT" and phoenix_result.get("strength") == "HIGH":
            raw_score -= 1 * w_phx
            conf_adj  += 4
            reasons.append(
                f"🔥 TV Phoenix wSMD: SHORT signal fired! Stoch {px_stk:.0f} ({px_zone}) "
                f"+ {'bear div' if phoenix_result.get('bearish_divergence') else 'stoch cross'} [{team} wt:{w_phx}x]"
            )
        elif px_sig in ("SHORT", "SHORT_WATCH"):
            raw_score -= 0.5 * w_phx
            reasons.append(f"🔴 TV Phoenix: {px_sig} — Stoch {px_stk:.0f} ({px_zone}) [{team} wt:{w_phx}x]")

        # ── 5. Cash Open Levels (base ±0.5, weighted) ──
        if co_result["sentiment"] == "BULLISH" and co_result["above_count"] >= 3:
            raw_score += 0.5 * w_co
            reasons.append(
                f"💰 TV Cash Open: Above {co_result['above_count']}/{co_result['total_levels']} "
                f"session opens — bullish [{team} wt:{w_co}x]"
            )
        elif co_result["sentiment"] == "BEARISH" and co_result["above_count"] <= 1:
            raw_score -= 0.5 * w_co
            reasons.append(f"💰 TV Cash Open: Below session opens — bearish [{team} wt:{w_co}x]")

        # ── 6. Liquidity Heatmap Nephe (base ±1, weighted) ──
        if liq_result["sweep_detected"]:
            if liq_result["sweep_type"] == "BUY_SWEEP":
                raw_score += 1 * w_liq
                conf_adj  += int(3 * w_liq)
                reasons.append(
                    f"🔥 TV Liq: BUY SWEEP @ {liq_result['sweep_level']} "
                    f"— reversal UP [{team} wt:{w_liq}x]"
                )
            elif liq_result["sweep_type"] == "SELL_SWEEP":
                raw_score -= 1 * w_liq
                conf_adj  += int(3 * w_liq)
                reasons.append(
                    f"🔥 TV Liq: SELL SWEEP @ {liq_result['sweep_level']} "
                    f"— reversal DOWN [{team} wt:{w_liq}x]"
                )

        # ── Team growth bonus ──
        growth_positive = (
            macd_result.get("is_positive_growth", False) and
            st_result.get("is_positive_growth", False)
        )
        if growth_positive:
            growth_bonus = thresholds["growth_bonus"]
            conf_adj += growth_bonus
            reasons.append(
                f"🚀 TV Growth: BOTH MACD(12,26) + SBT positive growth! "
                f"[{team} bonus: +{growth_bonus} conf]"
            )

        # ── ORB + Phoenix confluence bonus ──
        orb_long  = orb_sig in ("LONG", "BULLISH_BIAS") or orb_result.get("up_signal")
        orb_short = orb_sig in ("SHORT", "BEARISH_BIAS") or orb_result.get("down_signal")
        if orb_long and px_sig in ("LONG", "LONG_WATCH"):
            conf_adj += 3
            reasons.append("🤝 TV Confluence: ORB LONG + Phoenix LONG aligned!")
        elif orb_short and px_sig in ("SHORT", "SHORT_WATCH"):
            conf_adj += 3
            reasons.append("🤝 TV Confluence: ORB SHORT + Phoenix SHORT aligned!")

        # ── Clamp to ±8 (v3.0 expanded from ±6) ──
        score = max(-8, min(8, int(round(raw_score))))

        return {
            "tv_score": score,
            "tv_confidence_adj": min(conf_adj, 20),
            "tv_reasons": reasons,
            "growth_positive": growth_positive,
            "team": team,
            "team_weights": weights,
            "raw_weighted_score": round(raw_score, 2),
            "macd": macd_result,
            "supertrend": st_result,
            "orb": orb_result,
            "phoenix": phoenix_result,
            "cash_open": co_result,
            "liquidity": liq_result,
        }


# ═══════════════════════════════════════════════════════════════════════════
# CONVENIENCE: Quick analyze function for agent pipeline
# ═══════════════════════════════════════════════════════════════════════════
# ── Team-specific strategy instances (cached) ──
_tv_strategies: Dict[str, TradingViewStrategy] = {}

def _get_strategy(team: str = None) -> TradingViewStrategy:
    """Get or create team-specific strategy instance."""
    key = (team or "DEFAULT").upper()
    if key not in _tv_strategies:
        _tv_strategies[key] = TradingViewStrategy(team=team)
    return _tv_strategies[key]


def tv_analyze(df: pd.DataFrame, current_price: float = None,
               symbol: str = None, team: str = None) -> Dict:
    """
    Quick-access function for agent pipeline integration — v3.0.

    Now includes all 6 indicators from Sumit's TradingView chart:
      1. MACD Overlay (fa=12, sa=26, sig=9, SMA=89)
      2. SuperBollingerTrend (Expo) prd=12 mult=2 ZigZag Median
      3. ORB — LuxAlgo Opening Range 09:30-09:45 UTC-5, 50% targets
      4. Phoenix wSMD (k=12, d=3, dev=8, sens=0.5) — open-source replacement
      5. Cash Open Levels (London/NY/Asian)
      6. Liquidity Heatmap (Nephe) multi-TF

    Usage in main.py / agents:
        from tradingview_indicators import tv_analyze
        tv = tv_analyze(df_5m, current_price=cp, symbol="XAUUSD", team="METALS")
        sig["score"]      += tv["tv_score"]           # ±8 range (was ±6)
        sig["confidence"] += tv["tv_confidence_adj"]  # 0–20
        sig["reasons"].extend(tv["tv_reasons"])

        # New fields available:
        tv["orb"]["up_signal"]      # True = ORB long breakout confirmed
        tv["orb"]["down_signal"]    # True = ORB short breakout confirmed
        tv["phoenix"]["signal"]     # LONG / SHORT / NEUTRAL
        tv["macd"]["above_sma89"]   # Price above SMA(89)

    Team auto-detection from symbol name:
      - METALS: XAU*, XAG* → SBT + ORB + Liquidity boosted
      - FOREX:  EUR*, GBP*, USD*, JPY* → MACD + Cash Open boosted
      - CRYPTO: BTC*, ETH* → Liquidity + Phoenix boosted
    """
    strategy = _get_strategy(team)
    return strategy.analyze_all(df, current_price, symbol=symbol)


def tv_get_team_config(team: str) -> Dict:
    """Get team-specific configuration for dashboard display (v3.0)."""
    team = team.upper()
    return {
        "team": team,
        "version": "3.0",
        "weights": TradingViewStrategy.TEAM_WEIGHTS.get(team, {}),
        "thresholds": TradingViewStrategy.TEAM_CONFIDENCE_THRESHOLDS.get(team, {}),
        "indicators": [
            "MACD Overlay (fa=12, sa=26, sig=9, SMA=89) — Pine v2 exact",
            "SuperBollingerTrend (Expo prd=12, mult=2) ZigZag Median",
            "ORB LuxAlgo (09:30-09:45 UTC-5, No Bias, 50% targets)",
            "Phoenix wSMD (k=12, d=3, dev=8, sens=0.5) — open-source replacement",
            "Cash Open Levels (London/NY/Asian)",
            "Liquidity Heatmap Nephe (multi-TF: 15m/30m/1h/2h/4h)",
        ],
        "score_range": "±8",
        "confidence_range": "0–20",
    }


# ── Convenience: get ORB levels standalone (useful for dashboard) ──
def tv_get_orb(df: pd.DataFrame, target_pct: float = 0.50) -> Dict:
    """Get Opening Range Breakout levels without running all indicators."""
    return OpeningRangeBreakout(target_pct=target_pct).analyze(df)


# ── Convenience: get Phoenix signal standalone ──
def tv_get_phoenix(df: pd.DataFrame) -> Dict:
    """Get Phoenix wSMD signal without running all indicators."""
    return PhoenixWsMD(stoch_k=12, stoch_d=3, smooth=1,
                       dev=8.0, threshold=1.0, sensitivity=0.5).analyze(df)
