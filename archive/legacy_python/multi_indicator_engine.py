"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         MULTI-INDICATOR SIGNAL ENGINE  —  v2.0                             ║
║         5-Minute Timeframe  ·  15–30 min Signal Window                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  INDICATORS (from Sumit's TradingView chart):                               ║
║    1. MACD Overlay       fa=10, sa=21, sig=10, SMA=21                      ║
║    2. SuperBollingerTrend  prd=12, mult=2, ZigZag Median                   ║
║    3. ORB (LuxAlgo)      Opening Range 09:30–09:45 UTC-5, 50% targets      ║
║    4. Phoenix wSMD       k=12, d=3, dev=8, sens=0.5  (open-source replica) ║
║                                                                              ║
║  POSITION SIZING RULES (v2.0):                                              ║
║    • 0 or 1 indicator signal  →  NO TRADE                                   ║
║    • 2 indicators agree       →  1 trade  @ 0.01 lot  (TP1)                ║
║    • 3 indicators agree       →  2 trades @ 0.10 lot each  (TP1 + TP2)     ║
║    • 4 indicators agree       →  3 trades @ 0.01 lot each  (TP1+TP2+TP3)   ║
║                                                                              ║
║  POSITION STACKING (smart fill):                                            ║
║    If trades already open for symbol, open only the MISSING slots:          ║
║    e.g. 1 open + 3-signal → open 1 more (not 2)                            ║
║    e.g. 2 open + 4-signal → open 1 more (not 3)                            ║
║                                                                              ║
║  SIGNAL WINDOW:  15–30 bars on 5m TF  =  75–150 minutes                    ║
║  ALERTS:  Sound (Windows beep) + Telegram + MT5 execution                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import asyncio
import logging
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ── Project imports ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingview_indicators import (
    MACDOverlay,
    SuperBollingerTrend,
    OpeningRangeBreakout,
    PhoenixWsMD,
)

logger = logging.getLogger("MultiIndicatorEngine")

# ─────────────────────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IndicatorSignal:
    """Single indicator's verdict on a bar."""
    name: str           # "MACD" / "SBT" / "ORB" / "PHOENIX"
    direction: str      # "BUY" / "SELL" / "NEUTRAL"
    strength: str       # "HIGH" / "MEDIUM" / "LOW" / "NONE"
    reason: str         # Human-readable explanation
    bar_time: datetime  # Bar timestamp


@dataclass
class AggregatedSignal:
    """Combined result from all 4 indicators for one 5m bar."""
    bar_time: datetime
    symbol: str
    close_price: float
    signals: List[IndicatorSignal]
    buy_count: int = 0
    sell_count: int = 0
    direction: str = "NEUTRAL"     # final direction
    signal_count: int = 0          # how many indicators agree
    trade_decision: str = "NO_TRADE"  # NO_TRADE / NORMAL / DOUBLE / TRIPLE
    lot_size: float = 0.01         # lot size per trade
    total_trades: int = 0          # how many trades to open (max)
    trades_to_open: int = 0        # trades to open after accounting for open positions
    lot_multiplier: float = 1.0    # kept for backward compatibility
    reasons: List[str] = field(default_factory=list)


@dataclass
class SignalWindow:
    """Tracks signals in a rolling 15–30 bar window."""
    symbol: str
    window_bars: int = 20          # default: 20 bars × 5m = 100 minutes
    history: deque = field(default_factory=lambda: deque(maxlen=30))

    def add(self, sig: AggregatedSignal):
        self.history.append(sig)

    def recent_direction(self, n_bars: int = 6) -> str:
        """Majority direction of last n bars."""
        recent = list(self.history)[-n_bars:]
        buys  = sum(1 for s in recent if s.direction == "BUY")
        sells = sum(1 for s in recent if s.direction == "SELL")
        if buys > sells:
            return "BUY"
        elif sells > buys:
            return "SELL"
        return "NEUTRAL"

    def last_trade_bars_ago(self, direction: str) -> int:
        """How many bars ago was the last trade in this direction."""
        for i, s in enumerate(reversed(list(self.history))):
            if s.trade_decision in ("NORMAL", "DOUBLE", "TRIPLE") and s.direction == direction:
                return i
        return 999


# ─────────────────────────────────────────────────────────────────────────────
# SOUND ALERT (Windows + cross-platform fallback)
# ─────────────────────────────────────────────────────────────────────────────

def play_alert_sound(signal_count: int, direction: str):
    """
    Play alert sound based on signal strength.
    - 2 signals  → 2 short beeps
    - 3+ signals → 3 loud beeps (urgent)
    Works on Windows (winsound) and Linux/Mac (print bell fallback).
    """
    def _play():
        try:
            import winsound
            freq = 1200 if direction == "BUY" else 800
            if signal_count >= 3:
                # Triple loud beep for double trade
                for _ in range(3):
                    winsound.Beep(freq, 400)
                    time.sleep(0.1)
            else:
                # Double beep for normal trade
                for _ in range(2):
                    winsound.Beep(freq, 250)
                    time.sleep(0.15)
        except ImportError:
            # Linux/Mac fallback — print bell character
            beeps = 3 if signal_count >= 3 else 2
            print("\a" * beeps, flush=True)
        except Exception as e:
            logger.warning(f"Sound alert failed: {e}")

    threading.Thread(target=_play, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# TELEGRAM RICH ALERT
# ─────────────────────────────────────────────────────────────────────────────

async def send_telegram_signal_alert(
    notifier,
    agg,
    base_lot: float,
    sl_price: float,
    tp1_price: float,
    tp2_price: float,
    tp3_price: float,
    orb_info=None,
):
    """Send clean Telegram alert with all indicator details."""
    if notifier is None or not notifier.enabled:
        return

    d = agg.direction
    lot_per_trade = agg.lot_size
    n_trades_max  = agg.total_trades
    n_trades_open = agg.trades_to_open

    dir_arrow = "BUY  ^" if d == "BUY" else "SELL v"

    # Trade type label
    if agg.trade_decision == "TRIPLE":
        trade_type = f"4/4 TRIPLE  — {n_trades_open} trade(s) @ {lot_per_trade:.2f} lot  (TP1+TP2+TP3)"
    elif agg.trade_decision == "DOUBLE":
        trade_type = f"3/4 DOUBLE  — {n_trades_open} trade(s) @ {lot_per_trade:.2f} lot  (TP1+TP2)"
    else:
        trade_type = f"2/4 NORMAL  — {n_trades_open} trade @ {lot_per_trade:.2f} lot  (TP1)"

    if n_trades_open < n_trades_max:
        trade_type += f"  [already {n_trades_max - n_trades_open} open]"

    # Indicator breakdown lines
    ind_lines = ""
    for s in agg.signals:
        mark = "+" if s.direction == d else "-" if s.direction != "NEUTRAL" else "~"
        ind_lines += f"  [{mark}] {s.name}: {s.direction} ({s.strength}) - {s.reason}\n"

    # ORB targets
    orb_lines = ""
    if orb_info and orb_info.get("orh"):
        orb_lines = (
            f"\nORB LEVELS\n"
            f"  ORH: {orb_info['orh']:.2f}  ORL: {orb_info['orl']:.2f}\n"
        )
        tgts = orb_info.get("targets_above" if d == "BUY" else "targets_below", [])
        for i, t in enumerate(tgts[:3], 1):
            orb_lines += f"  T{i}: {t:.2f}\n"

    sym = agg.symbol
    text = (
        f"{sym} {dir_arrow}\n"
        f"{trade_type}\n"
        f"{'='*30}\n"
        f"Time  : {agg.bar_time.strftime('%d %b %Y  %H:%M')} UTC\n"
        f"Price : {agg.close_price:.2f}\n"
        f"Signals agreed: {agg.signal_count} / 4\n"
        f"Lot/trade : {lot_per_trade:.2f}  x{n_trades_open} = {lot_per_trade*n_trades_open:.2f}\n"
        f"{'='*30}\n"
        f"Indicator Summary:\n"
        f"{ind_lines}"
        f"{orb_lines}"
        f"{'='*30}\n"
        f"Stop Loss : {sl_price:.2f}\n"
        f"TP1       : {tp1_price:.2f}\n"
        f"TP2       : {tp2_price:.2f}\n"
        f"TP3       : {tp3_price:.2f}\n"
        f"\n#{sym} #AutoSignal"
    )

    try:
        # Send as plain text (no parse_mode) to avoid HTML errors
        if notifier.enabled:
            import aiohttp
            url = f"https://api.telegram.org/bot{notifier.bot_token}/sendMessage"
            payload = {"chat_id": notifier.chat_id, "text": text}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info("Telegram signal alert sent OK")
                    else:
                        body = await resp.text()
                        logger.warning(f"Telegram alert failed {resp.status}: {body[:100]}")
    except Exception as e:
        logger.warning(f"Telegram alert exception: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# INDIVIDUAL INDICATOR EVALUATORS
# ─────────────────────────────────────────────────────────────────────────────

class IndicatorEvaluator:
    """
    Evaluates all 4 TradingView indicators on a 5m DataFrame
    and returns individual IndicatorSignal objects.
    """

    def __init__(self):
        self.macd       = MACDOverlay(fast=10, slow=21, signal=10, sma_period=21)
        self.sbt        = SuperBollingerTrend(bb_period=12, bb_dev=2.0)
        self.orb        = OpeningRangeBreakout(target_pct=0.50, session_tz_offset=-5)
        self.phoenix    = PhoenixWsMD(stoch_k=12, stoch_d=3, smooth=1,
                                      dev=8.0, threshold=1.0, sensitivity=0.5)
        self._df_cache: Dict[str, pd.DataFrame] = {}

    def evaluate(self, df: pd.DataFrame, bar_time: datetime) -> List[IndicatorSignal]:
        """
        Run all 4 indicators on df (5m OHLCV) and return signals.
        df must have columns: open, high, low, close, volume
        df index should be DatetimeIndex (UTC).
        """
        signals: List[IndicatorSignal] = []
        if len(df) < 30:
            return signals

        # Pre-calculate
        df = df.copy()
        df = self.macd.calculate(df)
        df = self.sbt.calculate(df)
        df = self.phoenix.calculate(df)

        # ── 1. MACD Overlay (fa=12, sa=26, sig=9, SMA=89) ──
        macd_r = self.macd.analyze(df)
        sig_macd = macd_r["signal"]
        if sig_macd in ("STRONG_BUY", "BUY", "BULLISH_MOMENTUM"):
            direction = "BUY"
            strength  = "HIGH" if sig_macd == "STRONG_BUY" else "MEDIUM"
            reason    = (
                f"MACD cross ↑, fill green, "
                f"SMA89={'↑' if macd_r.get('sma89_rising') else '↓'}, "
                f"above SMA89={macd_r.get('above_sma89')}"
            )
        elif sig_macd in ("STRONG_SELL", "SELL", "BEARISH_MOMENTUM"):
            direction = "SELL"
            strength  = "HIGH" if sig_macd == "STRONG_SELL" else "MEDIUM"
            reason    = (
                f"MACD cross ↓, fill red, "
                f"SMA89={'↑' if macd_r.get('sma89_rising') else '↓'}, "
                f"above SMA89={macd_r.get('above_sma89')}"
            )
        else:
            direction = "NEUTRAL"
            strength  = "NONE"
            reason    = f"MACD neutral (hist={macd_r['histogram']:+.4f})"

        signals.append(IndicatorSignal("MACD", direction, strength, reason, bar_time))

        # ── 2. SuperBollingerTrend (prd=12, mult=2, ZigZag Median) ──
        sbt_r = self.sbt.analyze(df)
        verdict = sbt_r["verdict"]
        if verdict in ("STRONG_BULL", "BULLISH") or sbt_r.get("bull_flip"):
            direction = "BUY"
            strength  = "HIGH" if verdict == "STRONG_BULL" or sbt_r.get("bull_flip") else "MEDIUM"
            reason    = (
                f"SBT dir={'BULL'}, ZZmed={'↑' if sbt_r.get('above_zigzag_median') else '↓'}, "
                f"EMA align={sbt_r.get('ema_alignment')}/3"
                + (" [BULL FLIP!]" if sbt_r.get("bull_flip") else "")
            )
        elif verdict in ("STRONG_BEAR", "BEARISH") or sbt_r.get("bear_flip"):
            direction = "SELL"
            strength  = "HIGH" if verdict == "STRONG_BEAR" or sbt_r.get("bear_flip") else "MEDIUM"
            reason    = (
                f"SBT dir={'BEAR'}, ZZmed={'↓' if not sbt_r.get('above_zigzag_median') else '↑'}, "
                f"EMA bear={sbt_r.get('ema_bear_alignment')}/3"
                + (" [BEAR FLIP!]" if sbt_r.get("bear_flip") else "")
            )
        else:
            direction = "NEUTRAL"
            strength  = "NONE"
            reason    = f"SBT neutral (score={sbt_r.get('trend_score')}/3)"
            if sbt_r.get("bb_squeeze"):
                reason += " ⚡ BB SQUEEZE"

        signals.append(IndicatorSignal("SBT", direction, strength, reason, bar_time))

        # ── 3. ORB — LuxAlgo Opening Range Breakout ──
        orb_r = self.orb.analyze(df)
        orb_sig = orb_r.get("signal", "NEUTRAL")
        if orb_r.get("up_signal") or orb_sig in ("LONG",):
            direction = "BUY"
            strength  = "HIGH" if orb_r.get("up_signal") else "MEDIUM"
            reason    = (
                f"ORB breakout LONG! Close > ORH={orb_r.get('orh'):.2f}, "
                f"T1={orb_r['targets_above'][0]:.2f}" if orb_r.get("targets_above") else
                f"ORB above ORH={orb_r.get('orh')}"
            )
        elif orb_r.get("down_signal") or orb_sig in ("SHORT",):
            direction = "SELL"
            strength  = "HIGH" if orb_r.get("down_signal") else "MEDIUM"
            reason    = (
                f"ORB breakout SHORT! Close < ORL={orb_r.get('orl'):.2f}, "
                f"T1={orb_r['targets_below'][0]:.2f}" if orb_r.get("targets_below") else
                f"ORB below ORL={orb_r.get('orl')}"
            )
        elif orb_sig == "BULLISH_BIAS":
            direction = "BUY"
            strength  = "LOW"
            reason    = f"ORB: price above ORM={orb_r.get('orm'):.2f} (inside range)"
        elif orb_sig == "BEARISH_BIAS":
            direction = "SELL"
            strength  = "LOW"
            reason    = f"ORB: price below ORM={orb_r.get('orm'):.2f} (inside range)"
        else:
            direction = "NEUTRAL"
            strength  = "NONE"
            reason    = f"ORB: inside range (ORH={orb_r.get('orh')}, ORL={orb_r.get('orl')})"

        signals.append(IndicatorSignal("ORB", direction, strength, reason, bar_time))

        # ── 4. Phoenix wSMD (k=12, d=3, dev=8, sens=0.5) ──
        px_r = self.phoenix.analyze(df)
        px_sig = px_r.get("signal", "NEUTRAL")
        if px_sig in ("LONG", "LONG_WATCH"):
            direction = "BUY"
            strength  = px_r.get("strength", "MEDIUM")
            reason    = (
                f"Phoenix wSMD LONG: Stoch {px_r['stoch_k']:.0f} ({px_r['stoch_zone']})"
                + (" + bull divergence" if px_r.get("bullish_divergence") else "")
                + (" + wMom+" if px_r.get("weighted_momentum", 0) > 0 else "")
            )
        elif px_sig in ("SHORT", "SHORT_WATCH"):
            direction = "SELL"
            strength  = px_r.get("strength", "MEDIUM")
            reason    = (
                f"Phoenix wSMD SHORT: Stoch {px_r['stoch_k']:.0f} ({px_r['stoch_zone']})"
                + (" + bear divergence" if px_r.get("bearish_divergence") else "")
                + (" + wMom-" if px_r.get("weighted_momentum", 0) < 0 else "")
            )
        else:
            direction = "NEUTRAL"
            strength  = "NONE"
            reason    = (
                f"Phoenix: neutral Stoch {px_r['stoch_k']:.0f} ({px_r['stoch_zone']}), "
                f"wMom={px_r.get('weighted_momentum', 0):+.4f}"
            )

        signals.append(IndicatorSignal("PHOENIX", direction, strength, reason, bar_time))

        return signals

    def get_orb_info(self, df: pd.DataFrame) -> Dict:
        """Get ORB levels for Telegram/display."""
        return self.orb.analyze(df)


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL AGGREGATOR
# ─────────────────────────────────────────────────────────────────────────────

class SignalAggregator:
    """
    Counts how many indicators agree on direction.

    Position sizing rules (v2.0):
      signal_count 0 or 1  →  NO_TRADE
      signal_count == 2    →  NORMAL:  1 trade  @ 0.01 lot  (TP1 only)
      signal_count == 3    →  DOUBLE:  2 trades @ 0.10 lot each (TP1 + TP2)
      signal_count == 4    →  TRIPLE:  3 trades @ 0.01 lot each (TP1 + TP2 + TP3)

    A signal is counted only if strength >= min_strength.
    """

    # Lot sizes and trade counts per signal level
    SIGNAL_LOTS   = {2: 0.01, 3: 0.10, 4: 0.01}
    SIGNAL_TRADES = {2: 1,    3: 2,    4: 3}
    SIGNAL_NAMES  = {2: "NORMAL", 3: "DOUBLE", 4: "TRIPLE"}

    def __init__(self, min_strength: str = "LOW"):
        # Strength hierarchy: HIGH > MEDIUM > LOW > NONE
        self._strength_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}
        self.min_level = self._strength_order.get(min_strength, 1)

    def aggregate(self, symbol: str, close: float,
                  signals: List[IndicatorSignal], bar_time: datetime) -> AggregatedSignal:
        """Aggregate signals into a trade decision."""
        agg = AggregatedSignal(
            bar_time=bar_time,
            symbol=symbol,
            close_price=close,
            signals=signals,
        )

        buy_signals  = []
        sell_signals = []

        for s in signals:
            lvl = self._strength_order.get(s.strength, 0)
            if lvl < self.min_level:
                continue
            if s.direction == "BUY":
                buy_signals.append(s)
            elif s.direction == "SELL":
                sell_signals.append(s)

        agg.buy_count  = len(buy_signals)
        agg.sell_count = len(sell_signals)

        # Majority wins
        if agg.buy_count > agg.sell_count:
            agg.direction    = "BUY"
            agg.signal_count = agg.buy_count
            agg.reasons      = [s.reason for s in buy_signals]
        elif agg.sell_count > agg.buy_count:
            agg.direction    = "SELL"
            agg.signal_count = agg.sell_count
            agg.reasons      = [s.reason for s in sell_signals]
        else:
            agg.direction    = "NEUTRAL"
            agg.signal_count = 0
            agg.reasons      = ["No majority direction"]

        # Trade decision — v2.0 3-tier sizing
        if agg.signal_count <= 1:
            agg.trade_decision = "NO_TRADE"
            agg.lot_size       = 0.0
            agg.total_trades   = 0
            agg.trades_to_open = 0
            agg.lot_multiplier = 0.0
        else:
            cnt = min(agg.signal_count, 4)  # cap at 4
            agg.trade_decision = self.SIGNAL_NAMES[cnt]
            agg.lot_size       = self.SIGNAL_LOTS[cnt]
            agg.total_trades   = self.SIGNAL_TRADES[cnt]
            agg.trades_to_open = agg.total_trades  # may be reduced later by position stack check
            agg.lot_multiplier = agg.total_trades  # backward compat

        return agg


# ─────────────────────────────────────────────────────────────────────────────
# SL/TP CALCULATOR  (ATR-based, Gold-optimised)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_sl_tp(df: pd.DataFrame, direction: str,
                    atr_multiplier_sl: float = 1.5,
                    tp_ratios: Tuple[float, float, float] = (1.0, 2.0, 3.0)
                    ) -> Tuple[float, float, float, float]:
    """
    ATR-based SL and 3 TP levels.
    Returns (sl, tp1, tp2, tp3)
    """
    close  = float(df.iloc[-1]["close"])
    high   = df["high"] if "high" in df.columns else df["close"]
    low    = df["low"]  if "low"  in df.columns else df["close"]

    # ATR (14-bar)
    tr = pd.concat([
        high - low,
        (high - df["close"].shift(1)).abs(),
        (low  - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    if np.isnan(atr) or atr == 0:
        atr = close * 0.001  # fallback: 0.1%

    sl_dist  = atr * atr_multiplier_sl
    tp1_dist = atr * tp_ratios[0]
    tp2_dist = atr * tp_ratios[1]
    tp3_dist = atr * tp_ratios[2]

    if direction == "BUY":
        sl  = round(close - sl_dist,  2)
        tp1 = round(close + tp1_dist, 2)
        tp2 = round(close + tp2_dist, 2)
        tp3 = round(close + tp3_dist, 2)
    else:
        sl  = round(close + sl_dist,  2)
        tp1 = round(close - tp1_dist, 2)
        tp2 = round(close - tp2_dist, 2)
        tp3 = round(close - tp3_dist, 2)

    return sl, tp1, tp2, tp3


# ─────────────────────────────────────────────────────────────────────────────
# COOLDOWN TRACKER — prevents re-entry within N bars
# ─────────────────────────────────────────────────────────────────────────────

class CooldownTracker:
    """Prevent trading within cooldown_bars after last trade."""

    def __init__(self, cooldown_bars: int = 6):
        """cooldown_bars × 5m = 30-min default cooldown."""
        self.cooldown_bars = cooldown_bars
        self._last_trade: Dict[str, int] = {}   # symbol → bar_index of last trade
        self._bar_count:  Dict[str, int] = {}

    def tick(self, symbol: str):
        self._bar_count[symbol] = self._bar_count.get(symbol, 0) + 1

    def record_trade(self, symbol: str):
        self._last_trade[symbol] = self._bar_count.get(symbol, 0)

    def is_cooled(self, symbol: str) -> bool:
        last = self._last_trade.get(symbol, -999)
        current = self._bar_count.get(symbol, 0)
        return (current - last) >= self.cooldown_bars


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class MultiIndicatorEngine:
    """
    Main 5-minute multi-indicator signal engine.

    Usage:
        engine = MultiIndicatorEngine(
            symbol="XAUUSD",
            base_lot=0.01,
            notifier=telegram_notifier_instance,   # or None
            executor=order_executor_instance,      # or None for dry-run
        )
        await engine.run_once(df_5m)   # single-bar evaluation
        await engine.run_loop()        # continuous live loop (calls MT5)
    """

    SIGNAL_WINDOW_BARS = 20    # 20 × 5m = 100 min window for context

    def __init__(
        self,
        symbol:     str             = "XAUUSD",
        base_lot:   float           = 0.01,
        notifier    = None,         # TelegramNotifier instance
        executor    = None,         # OrderExecutor instance (src/order_executor.py)
        dry_run:    bool            = True,
        min_strength: str           = "LOW",   # minimum indicator strength to count
        cooldown_bars: int          = 6,        # bars between trades (6×5m=30min)
        atr_sl_mult: float          = 1.5,
    ):
        self.symbol       = symbol
        self.base_lot     = base_lot
        self.notifier     = notifier
        self.executor     = executor
        self.dry_run      = dry_run
        self.atr_sl_mult  = atr_sl_mult

        self.evaluator    = IndicatorEvaluator()
        self.aggregator   = SignalAggregator(min_strength=min_strength)
        self.cooldown     = CooldownTracker(cooldown_bars=cooldown_bars)
        self.window       = SignalWindow(symbol=symbol, window_bars=self.SIGNAL_WINDOW_BARS)

        self._last_signal: Optional[AggregatedSignal] = None
        self._trade_log:   List[Dict]                 = []
        # Dry-run position tracker: symbol → count of open positions
        self._dry_run_positions: Dict[str, int]       = {}

        logger.info(
            f"MultiIndicatorEngine ready | {symbol} | base_lot={base_lot} | "
            f"dry_run={dry_run} | cooldown={cooldown_bars} bars × 5m"
        )

    # ── Core evaluation ──────────────────────────────────────────────────────

    async def run_once(self, df: pd.DataFrame) -> Optional[AggregatedSignal]:
        """
        Evaluate one 5m bar. Call this every time a new 5m bar closes.

        df: OHLCV DataFrame, at least 60 rows, DatetimeIndex UTC.
        Returns AggregatedSignal (may have trade_decision == "NO_TRADE").
        """
        if len(df) < 30:
            logger.warning(f"[{self.symbol}] Not enough bars: {len(df)}")
            return None

        bar_time  = df.index[-1] if hasattr(df.index[-1], 'hour') else datetime.utcnow()
        close     = float(df.iloc[-1]["close"])

        # 1. Evaluate all 4 indicators
        self.cooldown.tick(self.symbol)
        signals   = self.evaluator.evaluate(df, bar_time)

        # 2. Aggregate → trade decision
        agg = self.aggregator.aggregate(self.symbol, close, signals, bar_time)
        self.window.add(agg)
        self._last_signal = agg

        # 3. Log summary
        self._log_bar(agg)

        # 4. If NO_TRADE, return early
        if agg.trade_decision == "NO_TRADE":
            return agg

        # 5. Cooldown check
        if not self.cooldown.is_cooled(self.symbol):
            logger.info(f"[{self.symbol}] Cooldown active — skipping trade")
            return agg

        # 6. Position stack check — count already-open trades for this symbol
        #    so we only open the MISSING slots (not re-open what's already there)
        already_open = self._count_open_positions(agg.symbol)
        need = agg.total_trades - already_open
        if need <= 0:
            logger.info(
                f"[{agg.symbol}] Signal {agg.signal_count}/4 but {already_open} trades "
                f"already open (max={agg.total_trades}) — no new trades needed"
            )
            return agg
        agg.trades_to_open = need
        logger.info(
            f"[{agg.symbol}] Signal {agg.signal_count}/4 → {agg.trade_decision}: "
            f"need {agg.total_trades} trades, {already_open} open → opening {need} more"
        )

        # 7. Calculate SL/TP
        sl, tp1, tp2, tp3 = calculate_sl_tp(
            df, agg.direction, self.atr_sl_mult, (1.0, 2.0, 3.0)
        )

        # 8. Sound alert
        play_alert_sound(agg.signal_count, agg.direction)

        # 9. Telegram alert
        orb_info = self.evaluator.get_orb_info(df)
        await send_telegram_signal_alert(
            self.notifier, agg, self.base_lot,
            sl, tp1, tp2, tp3, orb_info
        )

        # 10. Execute trades (or dry-run log)
        await self._execute(agg, sl, tp1, tp2, tp3)

        return agg

    # ── Position stack helper ─────────────────────────────────────────────────

    def _count_open_positions(self, symbol: str) -> int:
        """
        Return how many open positions exist for this symbol in the same direction.
        Uses MT5 positions_get() in live mode; in dry-run uses internal counter.
        Returns 0 if MT5 not available or dry-run with no logged trades.
        """
        if self.dry_run:
            # In dry-run: use internal tracker (reset when engine restarts)
            return self._dry_run_positions.get(symbol, 0)

        try:
            import MetaTrader5 as mt5
            if not mt5.initialize():
                return 0
            positions = mt5.positions_get(symbol=symbol)
            if positions is None:
                return 0
            return len(positions)
        except Exception as e:
            logger.warning(f"[{symbol}] _count_open_positions error: {e}")
            return 0

    # ── Trade execution ───────────────────────────────────────────────────────

    async def _execute(self, agg: AggregatedSignal,
                       sl: float, tp1: float, tp2: float, tp3: float):
        """
        Execute trades via MT5 (or dry-run log).

        Position sizing v2.0:
          2/4 → 1 trade @ 0.01 lot, TP = tp1
          3/4 → 2 trades @ 0.10 lot each, TPs = tp1, tp2
          4/4 → 3 trades @ 0.01 lot each, TPs = tp1, tp2, tp3

        trades_to_open may be < total_trades when positions already exist.
        The TP levels are assigned starting from the NEXT available slot:
          e.g. if 1 already open (tp1 used) and 3-signal arrives → open tp2 only
        """
        lot      = round(agg.lot_size, 2)
        n_open   = agg.total_trades - agg.trades_to_open   # already-open count
        # Which TPs to use for the new trades (skip already-used ones)
        all_tps  = [tp1, tp2, tp3]
        tps_used = all_tps[n_open: n_open + agg.trades_to_open]

        base_log = {
            "time":          agg.bar_time.isoformat(),
            "symbol":        agg.symbol,
            "direction":     agg.direction,
            "signal_count":  agg.signal_count,
            "decision":      agg.trade_decision,
            "lot_per_trade": lot,
            "trades_opened": agg.trades_to_open,
            "entry":         agg.close_price,
            "sl":            sl,
            "tp1": tp1, "tp2": tp2, "tp3": tp3,
            "reasons":       agg.reasons,
        }

        if self.dry_run or self.executor is None:
            for i, tp in enumerate(tps_used, start=n_open + 1):
                logger.info(
                    f"DRY-RUN [{agg.symbol}] {agg.direction} {agg.trade_decision} "
                    f"Trade#{i}  lot={lot}  entry={agg.close_price:.2f}  "
                    f"SL={sl:.2f}  TP={tp:.2f}"
                )
            # Update internal dry-run position counter
            self._dry_run_positions[agg.symbol] = (
                self._dry_run_positions.get(agg.symbol, 0) + agg.trades_to_open
            )
            self._trade_log.append({**base_log, "executed": False, "mode": "dry_run"})
            self.cooldown.record_trade(agg.symbol)
            return

        # ── Live execution ────────────────────────────────────────────────────
        tickets = []
        trade_placed = False
        for i, tp in enumerate(tps_used, start=n_open + 1):
            try:
                result = self.executor.execute_market_order(
                    symbol      = agg.symbol,
                    order_type  = agg.direction,
                    volume      = lot,
                    stop_loss   = sl,
                    take_profit = tp,
                    comment     = f"AI_{agg.signal_count}sig_T{i}",
                )
                if result.get("success"):
                    ticket = result.get("ticket")
                    tickets.append(ticket)
                    trade_placed = True
                    logger.info(
                        f"TRADE PLACED [{agg.symbol}] {agg.direction} "
                        f"Trade#{i}/{agg.total_trades}  lot={lot}  "
                        f"TP={tp:.2f}  ticket={ticket}"
                    )
                    # Notify Telegram for each trade
                    if self.notifier and self.notifier.enabled:
                        await self.notifier.send_trade_opened(
                            agg.symbol, agg.direction,
                            agg.close_price, sl, tp, lot
                        )
                else:
                    logger.error(
                        f"Trade#{i} failed [{agg.symbol}]: {result.get('error')}"
                    )
            except Exception as e:
                logger.error(f"Trade#{i} exception [{agg.symbol}]: {e}")

        if trade_placed:
            self.cooldown.record_trade(agg.symbol)

        self._trade_log.append({**base_log, "executed": trade_placed,
                                 "tickets": tickets})

    # ── Live MT5 loop ─────────────────────────────────────────────────────────

    async def run_loop(self, poll_seconds: int = 30):
        """
        Continuous live loop — fetches 5m bars from MT5 every poll_seconds
        and calls run_once() on each new closed bar.

        Requires MetaTrader5 package and active connection.
        """
        import MetaTrader5 as mt5

        logger.info(f"🚀 Starting live 5m loop for {self.symbol} (poll={poll_seconds}s)")
        last_bar_time = None

        while True:
            try:
                # Fetch last 100 5m bars from MT5
                # Initialize MT5 if not connected
                if not mt5.initialize():
                    logger.warning(f"[{self.symbol}] MT5 not ready: {mt5.last_error()} - retrying")
                    await asyncio.sleep(poll_seconds)
                    continue
                mt5.symbol_select(self.symbol, True)
                rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M5, 0, 100)
                if rates is None or len(rates) == 0:
                    logger.warning(f"[{self.symbol}] No MT5 data — retrying in {poll_seconds}s")
                    await asyncio.sleep(poll_seconds)
                    continue

                df = pd.DataFrame(rates)
                df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
                df = df.set_index("time")
                df = df.rename(columns={"tick_volume": "volume"})

                current_bar_time = df.index[-1]

                # Only process when a NEW bar closes
                if last_bar_time is None or current_bar_time > last_bar_time:
                    last_bar_time = current_bar_time
                    agg = await self.run_once(df)

                    if agg and agg.trade_decision != "NO_TRADE":
                        logger.info(
                            f"⚡ [{self.symbol}] {agg.direction} — "
                            f"{agg.signal_count} signals → {agg.trade_decision}"
                        )

            except Exception as e:
                logger.error(f"[{self.symbol}] Loop error: {e}")

            await asyncio.sleep(poll_seconds)

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log_bar(self, agg: AggregatedSignal):
        ind_summary = " | ".join(
            f"{s.name}={'↑' if s.direction=='BUY' else '↓' if s.direction=='SELL' else '─'}"
            for s in agg.signals
        )
        logger.info(
            f"[{agg.symbol}] {agg.bar_time.strftime('%H:%M')} "
            f"close={agg.close_price:.2f} | {ind_summary} "
            f"→ {agg.direction} ({agg.signal_count}/4) [{agg.trade_decision}]"
        )

    def get_trade_log(self) -> List[Dict]:
        return self._trade_log

    def get_status(self) -> Dict:
        last = self._last_signal
        return {
            "symbol":             self.symbol,
            "last_bar":           last.bar_time.isoformat() if last else None,
            "last_direction":     last.direction if last else None,
            "last_signal_count":  last.signal_count if last else 0,
            "last_decision":      last.trade_decision if last else "NO_TRADE",
            "last_lot_size":      last.lot_size if last else 0.0,
            "last_total_trades":  last.total_trades if last else 0,
            "last_trades_opened": last.trades_to_open if last else 0,
            "open_positions":     self._dry_run_positions.get(self.symbol, 0) if self.dry_run else None,
            "total_executed":     len([t for t in self._trade_log if t.get("executed")]),
            "dry_run":            self.dry_run,
        }


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-SYMBOL MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class MultiSymbolManager:
    """
    Runs MultiIndicatorEngine for multiple symbols concurrently.
    Each symbol gets its own engine with independent cooldown & signal window.
    """

    def __init__(
        self,
        symbols:    List[str]       = None,
        base_lot:   float           = 0.01,
        notifier    = None,
        executor    = None,
        dry_run:    bool            = True,
        cooldown_bars: int          = 6,
    ):
        symbols = symbols or ["XAUUSD"]
        self.engines: Dict[str, MultiIndicatorEngine] = {
            sym: MultiIndicatorEngine(
                symbol        = sym,
                base_lot      = base_lot,
                notifier      = notifier,
                executor      = executor,
                dry_run       = dry_run,
                cooldown_bars = cooldown_bars,
            )
            for sym in symbols
        }
        logger.info(f"MultiSymbolManager ready: {list(self.engines.keys())}")

    async def run_all_loops(self, poll_seconds: int = 30):
        """Run all symbol loops concurrently."""
        tasks = [
            engine.run_loop(poll_seconds)
            for engine in self.engines.values()
        ]
        await asyncio.gather(*tasks)

    async def run_once_all(self, data: Dict[str, pd.DataFrame]) -> Dict[str, AggregatedSignal]:
        """Run one evaluation for each symbol using provided DataFrames."""
        results = {}
        for sym, df in data.items():
            if sym in self.engines:
                agg = await self.engines[sym].run_once(df)
                if agg:
                    results[sym] = agg
        return results

    def get_all_status(self) -> Dict[str, Dict]:
        return {sym: eng.get_status() for sym, eng in self.engines.items()}


# ─────────────────────────────────────────────────────────────────────────────
# MT5 MQL5 INDICATOR STRING — paste this into MT5 terminal
# ─────────────────────────────────────────────────────────────────────────────

MT5_INDICATOR_GUIDE = """
╔══════════════════════════════════════════════════════════════════════╗
║   MT5 SETUP — How to show all 4 indicators on MetaTrader 5 chart   ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  1. MACD (12, 26, 9):                                                ║
║     Insert → Indicators → Oscillators → MACD                        ║
║     Fast=12, Slow=26, Signal=9, Apply to=Close                      ║
║     Add SMA(89): Insert → Indicators → Trend → Moving Average       ║
║     Period=89, Shift=0, Method=Simple, Apply to=Close               ║
║                                                                      ║
║  2. Bollinger Bands (SuperBollingerTrend approx):                   ║
║     Insert → Indicators → Trend → Bollinger Bands                   ║
║     Period=12, Deviation=2.0, Apply to=Close                        ║
║                                                                      ║
║  3. Stochastic Oscillator (Phoenix wSMD approx):                    ║
║     Insert → Indicators → Oscillators → Stochastic                  ║
║     %K=12, %D=3, Slowing=1, MA Method=Simple, Price=High/Low        ║
║     Levels: 20 (oversold), 80 (overbought)                          ║
║                                                                      ║
║  4. For ORB levels — use a custom indicator (AI_AMD_SMC_Indicator   ║
║     already in your project folder):                                 ║
║     File → Open Data Folder → MQL5 → Indicators                     ║
║     Copy: ai_trading_agents/AI_AMD_SMC_Indicator.mq5                ║
║     Then: Navigator → Indicators → Custom → AI_AMD_SMC_Indicator    ║
║                                                                      ║
║  5. For Python-driven alerts on MT5:                                 ║
║     The MultiIndicatorEngine sends push notifications via           ║
║     MetaTrader5 Python API — alerts appear in MT5 terminal log.     ║
║     For sound: set ALERT_SOUND=true in .env                         ║
╚══════════════════════════════════════════════════════════════════════╝
"""


# ─────────────────────────────────────────────────────────────────────────────
# QUICK-START HELPER (called from main.py or standalone)
# ─────────────────────────────────────────────────────────────────────────────

async def run_multi_indicator_gold(
    dry_run:     bool  = True,
    base_lot:    float = 0.01,
    telegram_token: str = None,
    telegram_chat:  str = None,
):
    """
    Multi-symbol engine — runs ALL pairs from config/settings.py concurrently.
    Each pair gets its own independent engine, cooldown, and signal window.
    Set dry_run=False to enable live MT5 execution.
    """
    # Load all trading pairs from settings
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from config.settings import TRADING_PAIRS
        symbols = TRADING_PAIRS
    except Exception as e:
        logger.warning(f"Could not load TRADING_PAIRS from settings: {e} — falling back to XAUUSD only")
        symbols = ["XAUUSD"]

    # Setup Telegram
    notifier = None
    try:
        from telegram_notifier import TelegramNotifier
        if telegram_token:
            os.environ["TELEGRAM_BOT_TOKEN"] = telegram_token
        if telegram_chat:
            os.environ["TELEGRAM_CHAT_ID"] = telegram_chat
        os.environ.setdefault("TELEGRAM_ENABLED", "true")
        notifier = TelegramNotifier()
    except ImportError:
        logger.warning("TelegramNotifier not available")

    # Setup MT5 executor (only for live mode)
    executor = None
    if not dry_run:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
            from order_executor import OrderExecutor
            executor = OrderExecutor()
        except Exception as e:
            logger.warning(f"OrderExecutor not available: {e} — running dry-run")
            dry_run = True

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print(f"[Multi-Indicator Engine v2.0] {len(symbols)} pairs | MACD+SBT+ORB+Phoenix | 2sig=1x0.01 3sig=2x0.1 4sig=3x0.01")
    print(f"[Pairs] {', '.join(symbols)}")
    logger.info(f"Multi-Indicator Engine starting — {len(symbols)} pairs: {symbols}")

    # Run all pairs concurrently via MultiSymbolManager
    manager = MultiSymbolManager(
        symbols       = symbols,
        base_lot      = base_lot,
        notifier      = notifier,
        executor      = executor,
        dry_run       = dry_run,
        cooldown_bars = 6,    # 30-min cooldown per pair
    )
    await manager.run_all_loops(poll_seconds=30)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    # Fix Windows console encoding
    if hasattr(sys.stdout, "reconfigure"):
        try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    logging.basicConfig(
        level   = logging.INFO,
        format  = "%(asctime)s [%(name)s] %(levelname)s — %(message)s",
        datefmt = "%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Multi-Indicator 5m Signal Engine")
    parser.add_argument("--symbol",   default="XAUUSD",  help="Trading symbol")
    parser.add_argument("--lot",      type=float, default=0.01, help="Base lot size")
    parser.add_argument("--live",     action="store_true",      help="Enable live MT5 execution")
    parser.add_argument("--token",    default=None,       help="Telegram bot token")
    parser.add_argument("--chat",     default=None,       help="Telegram chat ID")
    args = parser.parse_args()

    asyncio.run(run_multi_indicator_gold(
        dry_run        = not args.live,
        base_lot       = args.lot,
        telegram_token = args.token or os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat  = args.chat  or os.getenv("TELEGRAM_CHAT_ID"),
    ))
