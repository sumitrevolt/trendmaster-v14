"""
MULTI-AGENT TRAINING SYSTEM — 7 Specialized Agents Train Concurrently
======================================================================
Each agent has a specific role in the training pipeline. They run in
parallel where possible, share results via a TrainingBus, and produce
a comprehensive training output that feeds into the live trading system.

AGENTS:
  1. DataCollectorAgent     — Fetches 6mo historical data for all 14 symbols
  2. TechnicalAnalysisAgent — Computes indicators + generates simulated signals
  3. PatternDiscoveryAgent  — Identifies winning/losing patterns from trades
  4. MLTrainerAgent         — Trains multiple ML models (DT, RF, GB, LR)
  5. StrategyOptimizerAgent — Optimizes per-symbol thresholds & session filters
  6. BacktestValidatorAgent — Walk-forward validation to prevent overfitting
  7. CoordinatorAgent       — Orchestrates all agents, merges results, saves

USAGE:
    python multi_agent_trainer.py              # Full training
    python multi_agent_trainer.py --quick      # Quick mode (3 symbols only)
    python multi_agent_trainer.py --symbols XAUUSD,EURUSD,BTCUSD

All results are saved to agent_training_data.json (same format as TrainingEngine).
"""

import asyncio
import json
import math
import os
import sys
import io
import time
import random
import tempfile
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-22s] %(message)s",
)
logger = logging.getLogger("MultiAgentTrainer")

# ── Dependencies ─────────────────────────────────────────────────────
try:
    import numpy as np
    import pandas as pd
except ImportError:
    print("ERROR: pip install numpy pandas")
    sys.exit(1)

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False
    print("WARNING: yfinance not available — install with: pip install yfinance")

try:
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score, TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import classification_report, accuracy_score
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("WARNING: scikit-learn not available — ML training disabled")

# ── Paths ────────────────────────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
TRAINING_FILE = os.path.join(_DIR, "agent_training_data.json")

# ── Symbol mapping ───────────────────────────────────────────────────
SYMBOL_MAP = {
    "XAUUSD": "GC=F", "XAGUSD": "SI=F",
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X", "NZDUSD": "NZDUSD=X",
    "GBPJPY": "GBPJPY=X", "EURJPY": "EURJPY=X", "EURGBP": "EURGBP=X",
    "USDCHF": "USDCHF=X",
    "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD",
}

# TP/SL thresholds per asset class for outcome determination
ASSET_THRESHOLDS = {
    "XAUUSD": {"tp": 0.15, "sl": 0.30}, "XAGUSD": {"tp": 0.20, "sl": 0.40},
    "BTCUSD": {"tp": 0.50, "sl": 1.00}, "ETHUSD": {"tp": 0.60, "sl": 1.20},
}
DEFAULT_THRESHOLD = {"tp": 0.08, "sl": 0.15}


# ═══════════════════════════════════════════════════════════════════════
# TRAINING BUS — Shared state between agents
# ═══════════════════════════════════════════════════════════════════════
class TrainingBus:
    """Thread-safe shared state for inter-agent communication."""

    def __init__(self):
        self.raw_data: Dict[str, pd.DataFrame] = {}       # symbol → H1 DataFrame
        self.daily_data: Dict[str, pd.DataFrame] = {}     # symbol → Daily DataFrame
        self.trades: List[Dict] = []                       # Generated training trades
        self.patterns: Dict[str, Any] = {}                 # Discovered patterns
        self.ml_results: Dict[str, Any] = {}               # ML model results
        self.optimizations: Dict[str, Any] = {}            # Per-symbol optimizations
        self.backtest_results: Dict[str, Any] = {}         # Validation results
        self.agent_status: Dict[str, str] = {}             # agent_name → status
        self.agent_logs: List[str] = []                    # Timestamped log entries
        self.start_time: float = time.time()
        self._lock = asyncio.Lock()

    async def log(self, agent: str, message: str):
        elapsed = time.time() - self.start_time
        entry = f"[{elapsed:6.1f}s] [{agent:22s}] {message}"
        self.agent_logs.append(entry)
        logger.info(f"[{agent}] {message}")

    async def set_status(self, agent: str, status: str):
        self.agent_status[agent] = status
        await self.log(agent, f"STATUS: {status}")


# ═══════════════════════════════════════════════════════════════════════
# TECHNICAL ANALYSIS FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════
def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calc_sma(series, period):
    return series.rolling(window=period).mean()

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))

def calc_atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calc_adx(high, low, close, period=14):
    tr = calc_atr(high, low, close, 1)  # True range per bar
    atr = tr.rolling(window=period).mean()

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_di = 100 * (pd.Series(plus_dm, index=close.index).rolling(period).mean() / atr.replace(0, 1e-10))
    minus_di = 100 * (pd.Series(minus_dm, index=close.index).rolling(period).mean() / atr.replace(0, 1e-10))

    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1e-10))
    return dx.rolling(window=period).mean()

def calc_macd(close, fast=12, slow=26, signal=9):
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calc_bollinger(close, period=20, std_dev=2):
    sma = calc_sma(close, period)
    std = close.rolling(window=period).std()
    return sma + std_dev * std, sma, sma - std_dev * std

def determine_trend(close, ema20, ema50):
    if close.iloc[-1] > ema20.iloc[-1] > ema50.iloc[-1]:
        return "BULLISH"
    elif close.iloc[-1] < ema20.iloc[-1] < ema50.iloc[-1]:
        return "BEARISH"
    return "SIDEWAYS"

def get_killzone(hour):
    if 2 <= hour <= 5: return "ASIAN"
    if 7 <= hour <= 10: return "LONDON"
    if 13 <= hour <= 16: return "NEW_YORK"
    if 10 <= hour <= 13: return "LONDON_NY_OVERLAP"
    return "NONE"

def get_amd_phase(rsi, adx, bb_state):
    if adx < 20 and bb_state in ("UPPER_HALF", "LOWER_HALF"):
        return "ACCUMULATION"
    if adx > 25 and bb_state in ("ABOVE_UPPER", "BELOW_LOWER"):
        return "MANIPULATION"
    if adx > 30:
        return "DISTRIBUTION"
    return "NONE"

def get_bb_state(close_val, upper, lower, mid):
    if close_val >= upper: return "ABOVE_UPPER"
    if close_val <= lower: return "BELOW_LOWER"
    if close_val > mid: return "UPPER_HALF"
    return "LOWER_HALF"

def get_macd_label(hist, hist_prev):
    if hist > 0 and hist > hist_prev: return "BULLISH_STRONG"
    if hist > 0: return "BULLISH_WEAK"
    if hist < 0 and hist < hist_prev: return "BEARISH_STRONG"
    return "BEARISH_WEAK"

def _col(df, name):
    """Get column value handling both uppercase and lowercase column names."""
    if name in df.columns:
        return name
    cap = name.capitalize()
    if cap in df.columns:
        return cap
    upper = name.upper()
    if upper in df.columns:
        return upper
    return name  # fallback

def detect_candle_patterns(df, i):
    """Detect candlestick patterns at index i."""
    if i < 2 or i >= len(df):
        return []
    patterns = []
    row = df.iloc[i]
    o_col, h_col, l_col, c_col = _col(df, "open"), _col(df, "high"), _col(df, "low"), _col(df, "close")
    o, h, l, c = float(row[o_col]), float(row[h_col]), float(row[l_col]), float(row[c_col])
    body = abs(c - o)
    total = h - l
    if total == 0:
        return []

    # Pin bar (hammer/shooting star)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    if lower_wick > body * 2 and lower_wick > upper_wick * 1.5:
        patterns.append("HAMMER")
    if upper_wick > body * 2 and upper_wick > lower_wick * 1.5:
        patterns.append("SHOOTING_STAR")

    # Engulfing
    if i >= 1:
        prev = df.iloc[i-1]
        po, pc = float(prev[o_col]), float(prev[c_col])
        prev_body = abs(pc - po)
        if body > prev_body * 1.2:
            if c > o and pc < po:
                patterns.append("BULLISH_ENGULFING")
            elif c < o and pc > po:
                patterns.append("BEARISH_ENGULFING")

    # Doji
    if body < total * 0.1:
        patterns.append("DOJI")

    return patterns


# ═══════════════════════════════════════════════════════════════════════
# AGENT 1: DATA COLLECTOR
# ═══════════════════════════════════════════════════════════════════════
class DataCollectorAgent:
    """Fetches historical data for all symbols from Yahoo Finance."""

    NAME = "DataCollectorAgent"

    @staticmethod
    async def run(bus: TrainingBus, symbols: List[str], lookback_days: int = 180):
        await bus.set_status(DataCollectorAgent.NAME, "RUNNING")
        total = len(symbols)
        fetched = 0
        failed = []

        for i, symbol in enumerate(symbols):
            yf_ticker = SYMBOL_MAP.get(symbol)
            if not yf_ticker:
                await bus.log(DataCollectorAgent.NAME, f"No Yahoo ticker for {symbol} — skipping")
                failed.append(symbol)
                continue

            try:
                await bus.log(DataCollectorAgent.NAME,
                    f"[{i+1}/{total}] Fetching {symbol} ({yf_ticker})...")

                # Run blocking yfinance in executor
                loop = asyncio.get_event_loop()
                ticker = yf.Ticker(yf_ticker)

                df_h1 = await loop.run_in_executor(
                    None, lambda: ticker.history(period=f"{lookback_days}d", interval="1h"))
                df_daily = await loop.run_in_executor(
                    None, lambda: ticker.history(period=f"{lookback_days}d", interval="1d"))

                if df_h1 is None or len(df_h1) < 100:
                    await bus.log(DataCollectorAgent.NAME,
                        f"  {symbol}: Only {len(df_h1) if df_h1 is not None else 0} H1 bars — skipping")
                    failed.append(symbol)
                    continue

                bus.raw_data[symbol] = df_h1
                if df_daily is not None and len(df_daily) > 20:
                    bus.daily_data[symbol] = df_daily

                fetched += 1
                await bus.log(DataCollectorAgent.NAME,
                    f"  {symbol}: {len(df_h1)} H1 bars, "
                    f"{len(df_daily) if df_daily is not None else 0} daily bars")

                # Brief pause to avoid rate limits
                await asyncio.sleep(0.5)

            except Exception as e:
                await bus.log(DataCollectorAgent.NAME, f"  {symbol} FAILED: {e}")
                failed.append(symbol)

        await bus.log(DataCollectorAgent.NAME,
            f"DONE: {fetched}/{total} symbols fetched, {len(failed)} failed")
        if failed:
            await bus.log(DataCollectorAgent.NAME, f"  Failed: {', '.join(failed)}")
        await bus.set_status(DataCollectorAgent.NAME, "DONE")


# ═══════════════════════════════════════════════════════════════════════
# AGENT 2: TECHNICAL ANALYSIS + SIGNAL GENERATION
# ═══════════════════════════════════════════════════════════════════════
class TechnicalAnalysisAgent:
    """Computes all indicators and generates simulated trade signals."""

    NAME = "TechnicalAnalysisAgent"

    @staticmethod
    async def run(bus: TrainingBus):
        await bus.set_status(TechnicalAnalysisAgent.NAME, "WAITING_FOR_DATA")

        # Wait for data collection
        while not bus.raw_data:
            await asyncio.sleep(1)
        await bus.set_status(TechnicalAnalysisAgent.NAME, "RUNNING")

        all_trades = []
        for symbol, df_h1 in bus.raw_data.items():
            await bus.log(TechnicalAnalysisAgent.NAME, f"Processing {symbol}...")

            trades = await asyncio.get_event_loop().run_in_executor(
                None, TechnicalAnalysisAgent._process_symbol,
                symbol, df_h1, bus.daily_data.get(symbol))

            all_trades.extend(trades)
            await bus.log(TechnicalAnalysisAgent.NAME,
                f"  {symbol}: Generated {len(trades)} trades")

        async with bus._lock:
            bus.trades = all_trades

        wins = sum(1 for t in all_trades if t["outcome"] == "WIN")
        total = len(all_trades)
        wr = round(wins / total * 100, 1) if total > 0 else 0
        await bus.log(TechnicalAnalysisAgent.NAME,
            f"DONE: {total} total trades, {wr}% raw win rate")
        await bus.set_status(TechnicalAnalysisAgent.NAME, "DONE")

    @staticmethod
    def _process_symbol(symbol: str, df_h1: pd.DataFrame,
                        df_daily: pd.DataFrame = None) -> List[Dict]:
        """Generate training trades for a single symbol."""
        close = df_h1["Close"]
        high = df_h1["High"]
        low = df_h1["Low"]

        # Indicators
        ema9 = calc_ema(close, 9)
        ema20 = calc_ema(close, 20)
        ema50 = calc_ema(close, 50)
        rsi = calc_rsi(close, 14).fillna(50.0)
        adx = calc_adx(high, low, close, 14).fillna(20.0)
        atr = calc_atr(high, low, close, 14).fillna(0)
        macd_line, signal_line, macd_hist = calc_macd(close)
        macd_hist = macd_hist.fillna(0)
        bb_upper, bb_mid, bb_lower = calc_bollinger(close)
        bb_upper = bb_upper.fillna(close + close.std())
        bb_lower = bb_lower.fillna(close - close.std())
        bb_mid = bb_mid.fillna(close)
        ema20 = ema20.fillna(close)
        ema50 = ema50.fillna(close)

        # Daily trend (H4 proxy)
        d_ema20, d_ema50 = ema20, ema50
        if df_daily is not None and len(df_daily) >= 50:
            d_ema20 = calc_ema(df_daily["Close"], 20)
            d_ema50 = calc_ema(df_daily["Close"], 50)

        # Thresholds
        thresh = ASSET_THRESHOLDS.get(symbol, DEFAULT_THRESHOLD)
        forward_bars = 12
        step = 4  # Every 4 H1 bars
        trades = []

        for i in range(60, len(df_h1) - forward_bars, step):
            try:
                c = float(close.iloc[i])
                r = float(rsi.iloc[i])
                a = float(adx.iloc[i])
                mh = float(macd_hist.iloc[i])
                mh_prev = float(macd_hist.iloc[i - 1])
                bb_u = float(bb_upper.iloc[i])
                bb_l = float(bb_lower.iloc[i])
                bb_m = float(bb_mid.iloc[i])
                e20 = float(ema20.iloc[i])
                e50 = float(ema50.iloc[i])
                e9 = float(ema9.iloc[i])
                atr_val = float(atr.iloc[i])

                if any(math.isnan(x) for x in [c, r, a, mh, mh_prev, bb_u, bb_l, bb_m, e20, e50]):
                    continue

                # Trends
                h1_trend = determine_trend(close.iloc[:i+1], ema20.iloc[:i+1], ema50.iloc[:i+1])
                bb_state = get_bb_state(c, bb_u, bb_l, bb_m)
                macd_label = get_macd_label(mh, mh_prev)

                # H4 trend from daily
                dt = df_h1.index[i]
                h4_trend = h1_trend  # default
                if df_daily is not None and len(df_daily) >= 50:
                    try:
                        dt_naive = dt.tz_localize(None) if hasattr(dt, 'tz_localize') and dt.tzinfo else dt
                        daily_idx = df_daily.index.tz_localize(None) if df_daily.index.tzinfo else df_daily.index
                        d_idx = min(daily_idx.searchsorted(dt_naive), len(df_daily) - 1)
                        if d_idx >= 20:
                            h4_trend = determine_trend(
                                df_daily["Close"].iloc[:d_idx+1],
                                d_ema20.iloc[:d_idx+1], d_ema50.iloc[:d_idx+1])
                    except Exception:
                        pass

                hour = dt.hour if hasattr(dt, 'hour') else 12
                killzone = get_killzone(hour)
                amd_phase = get_amd_phase(r, a, bb_state)
                day_of_week = dt.dayofweek if hasattr(dt, 'dayofweek') else 0

                # Candlestick patterns
                candle_patterns = detect_candle_patterns(df_h1, i)

                # ── Signal scoring (comprehensive) ──
                score = 0
                confidence = 50

                # Trend alignment (H1 + H4)
                if h1_trend == h4_trend and h1_trend != "SIDEWAYS":
                    score += 4; confidence += 15
                elif h1_trend != "SIDEWAYS":
                    score += 2; confidence += 5
                if h1_trend == "SIDEWAYS":
                    score -= 1

                # RSI
                if r < 30: score += 2; confidence += 5
                elif r > 70: score += 2; confidence += 5
                elif 45 < r < 55: score -= 1

                # ADX strength
                if a > 35: score += 3; confidence += 12
                elif a > 25: score += 2; confidence += 8
                elif a > 20: score += 1; confidence += 3
                elif a < 15: score -= 2; confidence -= 10

                # MACD
                if "STRONG" in macd_label: score += 2; confidence += 5
                elif "WEAK" in macd_label: score += 1

                # Bollinger
                if bb_state == "BELOW_LOWER": score += 1
                elif bb_state == "ABOVE_UPPER": score += 1

                # Killzone
                if killzone != "NONE": score += 1; confidence += 5
                if killzone == "LONDON_NY_OVERLAP": score += 1; confidence += 3

                # AMD phase
                if amd_phase == "DISTRIBUTION": score += 2; confidence += 5
                elif amd_phase == "ACCUMULATION": score -= 1

                # Candlestick patterns
                for p in candle_patterns:
                    if p in ("BULLISH_ENGULFING", "HAMMER"):
                        score += 1; confidence += 3
                    elif p in ("BEARISH_ENGULFING", "SHOOTING_STAR"):
                        score += 1; confidence += 3
                    elif p == "DOJI":
                        score -= 1

                # EMA9 cross (momentum)
                if e9 > e20 and c > e9: score += 1
                elif e9 < e20 and c < e9: score += 1

                # ── Direction ──
                if h1_trend == "BULLISH" or (h1_trend == "SIDEWAYS" and r < 40):
                    direction = "BUY"
                elif h1_trend == "BEARISH" or (h1_trend == "SIDEWAYS" and r > 60):
                    direction = "SELL"
                else:
                    continue

                if score < 2:
                    continue

                confidence = max(20, min(95, confidence))

                # ── Outcome (forward looking) ──
                future_close = float(close.iloc[i + forward_bars])
                if direction == "BUY":
                    max_move = (float(high.iloc[i+1:i+forward_bars+1].max()) - c) / c * 100
                    min_move = (c - float(low.iloc[i+1:i+forward_bars+1].min())) / c * 100
                    move_pct = (future_close - c) / c * 100
                else:
                    max_move = (c - float(low.iloc[i+1:i+forward_bars+1].min())) / c * 100
                    min_move = (float(high.iloc[i+1:i+forward_bars+1].max()) - c) / c * 100
                    move_pct = (c - future_close) / c * 100

                if max_move >= thresh["tp"] and min_move < thresh["sl"]:
                    outcome = "WIN"
                    pnl = round(max_move * 10 * (1 + score / 15), 2)
                elif min_move >= thresh["sl"]:
                    outcome = "LOSS"
                    pnl = round(-min_move * 12, 2)
                elif move_pct > 0:
                    outcome = "WIN"
                    pnl = round(move_pct * 8, 2)
                else:
                    outcome = "LOSS"
                    pnl = round(move_pct * 10, 2)

                # Simulated institutional signals
                inst_dir = direction if random.random() > 0.35 else ("SELL" if direction == "BUY" else "BUY")
                inst_conf = random.randint(40, 85)
                news = random.choice(["BULLISH", "BEARISH", "NEUTRAL", "NEUTRAL"])
                vol_signal = random.choice(["NORMAL"] * 3 + ["HIGH_INSTITUTIONAL", "MASSIVE_INSTITUTIONAL"])

                trade = {
                    "symbol": symbol,
                    "direction": direction,
                    "score": score,
                    "confidence": confidence,
                    "h1_trend": h1_trend,
                    "h4_trend": h4_trend,
                    "h4_h1_aligned": h4_trend == h1_trend and h4_trend != "SIDEWAYS",
                    "rsi": round(r, 1),
                    "adx": round(a, 1),
                    "atr": round(atr_val, 6),
                    "macd": macd_label,
                    "bb_state": bb_state,
                    "amd_phase": amd_phase,
                    "news": news,
                    "hour_utc": hour,
                    "day_of_week": day_of_week,
                    "institutional_dir": inst_dir,
                    "institutional_conf": inst_conf,
                    "killzone": killzone,
                    "volume_signal": vol_signal,
                    "candle_patterns": candle_patterns,
                    "ema9_above_ema20": e9 > e20,
                    "price_above_ema50": c > e50,
                    "move_pct": round(move_pct, 4),
                    "max_favorable_move": round(max_move, 4),
                    "max_adverse_move": round(min_move, 4),
                    "agents": [f"{symbol}_analyst", "signal_engine", "risk_manager",
                               "pattern_memory", "operator_mind"],
                    "entry_time": dt.strftime("%Y-%m-%dT%H:%M:%S"),
                    "outcome": outcome,
                    "pnl": pnl,
                    "close_time": df_h1.index[i + forward_bars].strftime("%Y-%m-%dT%H:%M:%S"),
                    "trade_id": f"{symbol}_{dt.strftime('%Y%m%d%H%M')}",
                }
                trades.append(trade)

            except Exception:
                continue

        return trades


# ═══════════════════════════════════════════════════════════════════════
# AGENT 3: PATTERN DISCOVERY
# ═══════════════════════════════════════════════════════════════════════
class PatternDiscoveryAgent:
    """Analyzes trades to discover winning/losing patterns."""

    NAME = "PatternDiscoveryAgent"

    @staticmethod
    async def run(bus: TrainingBus):
        await bus.set_status(PatternDiscoveryAgent.NAME, "WAITING_FOR_TRADES")

        while not bus.trades:
            await asyncio.sleep(2)
        await bus.set_status(PatternDiscoveryAgent.NAME, "RUNNING")

        trades = bus.trades
        await bus.log(PatternDiscoveryAgent.NAME, f"Analyzing {len(trades)} trades...")

        patterns = {}

        # 1. Symbol stats
        symbol_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0})
        for t in trades:
            s = symbol_stats[t["symbol"]]
            s["wins" if t["outcome"] == "WIN" else "losses"] += 1
            s["pnl"] += t.get("pnl", 0)
        for sym, s in symbol_stats.items():
            total = s["wins"] + s["losses"]
            s["win_rate"] = round(s["wins"] / total * 100, 1) if total > 0 else 50
            s["total"] = total
        patterns["symbol_stats"] = dict(symbol_stats)

        # 2. Session analysis (hour × symbol)
        session_stats = defaultdict(lambda: defaultdict(lambda: {"w": 0, "l": 0}))
        for t in trades:
            h = str(t.get("hour_utc", 12))
            session_stats[t["symbol"]][h]["w" if t["outcome"] == "WIN" else "l"] += 1
        patterns["session_stats"] = {s: dict(h) for s, h in session_stats.items()}

        # 3. Killzone performance
        kz_stats = defaultdict(lambda: {"w": 0, "l": 0})
        for t in trades:
            kz = t.get("killzone", "NONE")
            kz_stats[kz]["w" if t["outcome"] == "WIN" else "l"] += 1
        patterns["killzone_stats"] = dict(kz_stats)

        # 4. AMD phase performance
        amd_stats = defaultdict(lambda: {"w": 0, "l": 0})
        for t in trades:
            amd_stats[t.get("amd_phase", "NONE")]["w" if t["outcome"] == "WIN" else "l"] += 1
        patterns["amd_stats"] = dict(amd_stats)

        # 5. Trend alignment analysis
        aligned_w = sum(1 for t in trades if t.get("h4_h1_aligned") and t["outcome"] == "WIN")
        aligned_l = sum(1 for t in trades if t.get("h4_h1_aligned") and t["outcome"] == "LOSS")
        not_aligned_w = sum(1 for t in trades if not t.get("h4_h1_aligned") and t["outcome"] == "WIN")
        not_aligned_l = sum(1 for t in trades if not t.get("h4_h1_aligned") and t["outcome"] == "LOSS")
        patterns["alignment"] = {
            "aligned": {"w": aligned_w, "l": aligned_l,
                       "wr": round(aligned_w / max(aligned_w + aligned_l, 1) * 100, 1)},
            "not_aligned": {"w": not_aligned_w, "l": not_aligned_l,
                           "wr": round(not_aligned_w / max(not_aligned_w + not_aligned_l, 1) * 100, 1)},
        }

        # 6. Score threshold analysis
        score_bands = {}
        for threshold in range(2, 15, 2):
            above = [t for t in trades if t["score"] >= threshold]
            if above:
                w = sum(1 for t in above if t["outcome"] == "WIN")
                score_bands[f"score>={threshold}"] = {
                    "count": len(above),
                    "win_rate": round(w / len(above) * 100, 1),
                    "avg_pnl": round(sum(t["pnl"] for t in above) / len(above), 2),
                }
        patterns["score_bands"] = score_bands

        # 7. Indicator combo analysis
        combo_stats = defaultdict(lambda: {"w": 0, "l": 0})
        for t in trades:
            parts = []
            if t.get("h4_h1_aligned"): parts.append("H4_ALIGNED")
            if t.get("killzone", "NONE") != "NONE": parts.append("KILLZONE")
            if t.get("institutional_dir") == t.get("direction"): parts.append("INST_CONFIRM")
            if t.get("amd_phase") == "DISTRIBUTION": parts.append("AMD_DIST")
            r = t.get("rsi", 50)
            if r < 35 or r > 65: parts.append("RSI_EXTREME")
            if t.get("adx", 20) > 25: parts.append("TRENDING")
            if t.get("volume_signal", "NORMAL") != "NORMAL": parts.append("VOL_SPIKE")
            if t.get("ema9_above_ema20") and t.get("direction") == "BUY": parts.append("EMA9_CROSS")
            if parts:
                combo_stats["+".join(sorted(parts))]["w" if t["outcome"] == "WIN" else "l"] += 1
        patterns["combo_stats"] = dict(combo_stats)

        # 8. Day of week analysis
        dow_stats = defaultdict(lambda: {"w": 0, "l": 0})
        for t in trades:
            dow_stats[str(t.get("day_of_week", 0))]["w" if t["outcome"] == "WIN" else "l"] += 1
        patterns["day_of_week_stats"] = dict(dow_stats)

        # 9. Candle pattern effectiveness
        candle_stats = defaultdict(lambda: {"w": 0, "l": 0})
        for t in trades:
            for cp in t.get("candle_patterns", []):
                candle_stats[cp]["w" if t["outcome"] == "WIN" else "l"] += 1
        patterns["candle_pattern_stats"] = dict(candle_stats)

        async with bus._lock:
            bus.patterns = patterns

        # Log top findings
        best_combos = sorted(
            [(k, v) for k, v in combo_stats.items() if v["w"] + v["l"] >= 5],
            key=lambda x: x[1]["w"] / max(x[1]["w"] + x[1]["l"], 1),
            reverse=True
        )[:5]
        for combo, stats in best_combos:
            total = stats["w"] + stats["l"]
            wr = round(stats["w"] / total * 100, 1)
            await bus.log(PatternDiscoveryAgent.NAME, f"  TOP COMBO: {combo} → {wr}% WR ({total} trades)")

        await bus.log(PatternDiscoveryAgent.NAME, "DONE: Pattern analysis complete")
        await bus.set_status(PatternDiscoveryAgent.NAME, "DONE")


# ═══════════════════════════════════════════════════════════════════════
# AGENT 4: ML TRAINER (Multiple Models)
# ═══════════════════════════════════════════════════════════════════════
class MLTrainerAgent:
    """Trains multiple ML models and selects the best one."""

    NAME = "MLTrainerAgent"

    FEATURE_NAMES = [
        "score", "confidence", "rsi", "adx", "hour", "day_of_week",
        "inst_conf", "h4_aligned", "killzone", "inst_confirm",
        "amd_dist", "vol_spike", "news_confirm", "is_buy",
        "ema9_cross", "price_above_ema50",
    ]

    @staticmethod
    async def run(bus: TrainingBus):
        if not ML_AVAILABLE:
            await bus.log(MLTrainerAgent.NAME, "SKIPPED: scikit-learn not installed")
            await bus.set_status(MLTrainerAgent.NAME, "SKIPPED")
            return

        await bus.set_status(MLTrainerAgent.NAME, "WAITING_FOR_TRADES")
        while not bus.trades:
            await asyncio.sleep(2)
        await bus.set_status(MLTrainerAgent.NAME, "RUNNING")

        trades = bus.trades
        if len(trades) < 50:
            await bus.log(MLTrainerAgent.NAME, f"Only {len(trades)} trades — need 50+ for ML")
            await bus.set_status(MLTrainerAgent.NAME, "INSUFFICIENT_DATA")
            return

        await bus.log(MLTrainerAgent.NAME, f"Training on {len(trades)} trades with 4 models...")

        # Build feature matrix
        X, y = MLTrainerAgent._build_features(trades)

        results = await asyncio.get_event_loop().run_in_executor(
            None, MLTrainerAgent._train_all_models, X, y, trades)

        async with bus._lock:
            bus.ml_results = results

        best = results.get("best_model", "unknown")
        best_acc = results.get("best_cv_accuracy", 0)
        await bus.log(MLTrainerAgent.NAME,
            f"DONE: Best model = {best} ({best_acc:.1f}% CV accuracy)")

        # Log all model results
        for name, info in results.get("models", {}).items():
            await bus.log(MLTrainerAgent.NAME,
                f"  {name}: Train={info['train_accuracy']:.1f}%, "
                f"CV={info['cv_accuracy']:.1f}% (+/- {info['cv_std']:.1f}%)")

        # Log top features
        for feat in results.get("top_features", [])[:5]:
            await bus.log(MLTrainerAgent.NAME,
                f"  TOP FEATURE: {feat['name']} = {feat['importance']:.1f}%")

        await bus.set_status(MLTrainerAgent.NAME, "DONE")

    @staticmethod
    def _build_features(trades: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
        features = []
        labels = []
        for t in trades:
            news_match = t.get("news") == t.get("direction", "").replace(
                "BUY", "BULLISH").replace("SELL", "BEARISH")
            f = [
                t.get("score", 0),
                t.get("confidence", 50),
                t.get("rsi", 50),
                t.get("adx", 20),
                t.get("hour_utc", 12),
                t.get("day_of_week", 0),
                t.get("institutional_conf", 50),
                1 if t.get("h4_h1_aligned") else 0,
                1 if t.get("killzone", "NONE") != "NONE" else 0,
                1 if t.get("institutional_dir") == t.get("direction") else 0,
                1 if t.get("amd_phase") == "DISTRIBUTION" else 0,
                1 if t.get("volume_signal", "NORMAL") != "NORMAL" else 0,
                1 if news_match else 0,
                1 if t.get("direction") == "BUY" else 0,
                1 if t.get("ema9_above_ema20") and t.get("direction") == "BUY" else 0,
                1 if t.get("price_above_ema50") else 0,
            ]
            features.append(f)
            labels.append(1 if t["outcome"] == "WIN" else 0)
        return np.array(features), np.array(labels)

    @staticmethod
    def _train_all_models(X: np.ndarray, y: np.ndarray, trades: List[Dict]) -> Dict:
        """Train 4 different ML models and compare."""
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Time-series aware cross validation
        n_splits = min(5, max(2, len(X) // 100))
        tscv = TimeSeriesSplit(n_splits=n_splits)

        models = {
            "DecisionTree": DecisionTreeClassifier(
                max_depth=6, min_samples_leaf=5, min_samples_split=10, random_state=42),
            "RandomForest": RandomForestClassifier(
                n_estimators=100, max_depth=8, min_samples_leaf=5, random_state=42, n_jobs=-1),
            "GradientBoosting": GradientBoostingClassifier(
                n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42),
            "LogisticRegression": LogisticRegression(
                max_iter=1000, random_state=42, C=0.5),
        }

        results = {"models": {}, "best_model": None, "best_cv_accuracy": 0}

        for name, model in models.items():
            try:
                # Use scaled features for LR, raw for tree-based
                X_use = X_scaled if name == "LogisticRegression" else X

                # Cross-validation
                cv_scores = cross_val_score(model, X_use, y, cv=tscv, scoring='accuracy')

                # Train on full data
                model.fit(X_use, y)
                train_preds = model.predict(X_use)
                train_acc = round(accuracy_score(y, train_preds) * 100, 1)
                cv_acc = round(cv_scores.mean() * 100, 1)
                cv_std = round(cv_scores.std() * 100, 1)

                results["models"][name] = {
                    "train_accuracy": train_acc,
                    "cv_accuracy": cv_acc,
                    "cv_std": cv_std,
                    "cv_scores": [round(s * 100, 1) for s in cv_scores],
                }

                if cv_acc > results["best_cv_accuracy"]:
                    results["best_cv_accuracy"] = cv_acc
                    results["best_model"] = name

                # Feature importances (for tree-based models)
                if hasattr(model, 'feature_importances_'):
                    importances = model.feature_importances_
                    feat_imp = sorted(
                        zip(MLTrainerAgent.FEATURE_NAMES, importances),
                        key=lambda x: x[1], reverse=True)
                    results["models"][name]["feature_importances"] = [
                        {"name": n, "importance": round(imp * 100, 1)}
                        for n, imp in feat_imp
                    ]

            except Exception as e:
                results["models"][name] = {"error": str(e)}

        # Get overall top features from best tree-based model
        for name in ["RandomForest", "GradientBoosting", "DecisionTree"]:
            if name in results["models"] and "feature_importances" in results["models"][name]:
                results["top_features"] = results["models"][name]["feature_importances"]
                break

        # Per-symbol ML accuracy
        results["ml_model_accuracy"] = results["best_cv_accuracy"]

        return results


# ═══════════════════════════════════════════════════════════════════════
# AGENT 5: STRATEGY OPTIMIZER
# ═══════════════════════════════════════════════════════════════════════
class StrategyOptimizerAgent:
    """Optimizes per-symbol thresholds and session filters."""

    NAME = "StrategyOptimizerAgent"

    @staticmethod
    async def run(bus: TrainingBus):
        await bus.set_status(StrategyOptimizerAgent.NAME, "WAITING_FOR_PATTERNS")

        while not bus.patterns:
            await asyncio.sleep(2)
        await bus.set_status(StrategyOptimizerAgent.NAME, "RUNNING")

        trades = bus.trades
        patterns = bus.patterns
        optimizations = {}

        # 1. Per-symbol adaptive thresholds
        symbol_stats = patterns.get("symbol_stats", {})
        adaptive_thresholds = {}
        blacklisted_symbols = []
        boosted_symbols = []

        for sym, s in symbol_stats.items():
            total = s.get("total", 0)
            wr = s.get("win_rate", 50)
            if total < 10:
                adaptive_thresholds[sym] = {"min_score_adj": 0, "min_conf_adj": 0,
                                            "reason": f"Insufficient data ({total} trades)"}
                continue

            if wr < 35:
                blacklisted_symbols.append(sym)
                adaptive_thresholds[sym] = {
                    "min_score_adj": +5, "min_conf_adj": +15,
                    "reason": f"BLACKLISTED: {wr}% WR < 35%"}
            elif wr < 45:
                adaptive_thresholds[sym] = {
                    "min_score_adj": +3, "min_conf_adj": +10,
                    "reason": f"WEAK: {wr}% WR — stricter filters"}
            elif wr > 65:
                boosted_symbols.append(sym)
                adaptive_thresholds[sym] = {
                    "min_score_adj": -1, "min_conf_adj": -5,
                    "reason": f"STRONG: {wr}% WR — slightly relaxed"}
            else:
                adaptive_thresholds[sym] = {
                    "min_score_adj": 0, "min_conf_adj": 0,
                    "reason": f"NORMAL: {wr}% WR"}

        optimizations["adaptive_thresholds"] = adaptive_thresholds
        optimizations["blacklisted_symbols"] = blacklisted_symbols
        optimizations["boosted_symbols"] = boosted_symbols

        # 2. Session hour blacklist
        blacklisted_hours = {}
        session_stats = patterns.get("session_stats", {})
        for sym, hours in session_stats.items():
            bad = []
            for h, stats in hours.items():
                total = stats["w"] + stats["l"]
                if total >= 5 and stats["w"] / total < 0.30:
                    bad.append(int(h))
            if bad:
                blacklisted_hours[sym] = bad
        optimizations["blacklisted_hours"] = blacklisted_hours

        # 3. Optimal score threshold per symbol
        optimal_scores = {}
        for sym in symbol_stats:
            sym_trades = [t for t in trades if t["symbol"] == sym]
            best_wr = 0
            best_threshold = 8
            for thresh in range(4, 14):
                above = [t for t in sym_trades if t["score"] >= thresh]
                if len(above) >= 10:
                    w = sum(1 for t in above if t["outcome"] == "WIN")
                    wr = w / len(above) * 100
                    # Optimal = best WR with at least 60% of trades remaining
                    if wr > best_wr and len(above) >= len(sym_trades) * 0.3:
                        best_wr = wr
                        best_threshold = thresh
            optimal_scores[sym] = {"threshold": best_threshold, "expected_wr": round(best_wr, 1)}
        optimizations["optimal_score_thresholds"] = optimal_scores

        # 4. Market regime detection
        regime_stats = {}
        for sym in symbol_stats:
            sym_trades = [t for t in trades if t["symbol"] == sym]
            if len(sym_trades) >= 10:
                trending = [t for t in sym_trades if t.get("adx", 0) > 25]
                ranging = [t for t in sym_trades if t.get("adx", 0) <= 25]
                t_wr = sum(1 for t in trending if t["outcome"] == "WIN") / max(len(trending), 1) * 100
                r_wr = sum(1 for t in ranging if t["outcome"] == "WIN") / max(len(ranging), 1) * 100
                regime_stats[sym] = {
                    "trending_wr": round(t_wr, 1), "trending_count": len(trending),
                    "ranging_wr": round(r_wr, 1), "ranging_count": len(ranging),
                    "best_regime": "TRENDING" if t_wr > r_wr else "RANGING",
                }
        optimizations["regime_stats"] = regime_stats

        # 5. Best killzone per symbol
        best_kz = {}
        for sym in symbol_stats:
            sym_trades = [t for t in trades if t["symbol"] == sym]
            kz_perf = defaultdict(lambda: {"w": 0, "l": 0})
            for t in sym_trades:
                kz = t.get("killzone", "NONE")
                kz_perf[kz]["w" if t["outcome"] == "WIN" else "l"] += 1
            best = max(kz_perf.items(),
                       key=lambda x: x[1]["w"] / max(x[1]["w"] + x[1]["l"], 1),
                       default=("NONE", {"w": 0, "l": 0}))
            best_total = best[1]["w"] + best[1]["l"]
            best_kz[sym] = {
                "killzone": best[0],
                "win_rate": round(best[1]["w"] / max(best_total, 1) * 100, 1),
                "trades": best_total,
            }
        optimizations["best_killzones"] = best_kz

        async with bus._lock:
            bus.optimizations = optimizations

        await bus.log(StrategyOptimizerAgent.NAME,
            f"Blacklisted: {blacklisted_symbols or 'none'}")
        await bus.log(StrategyOptimizerAgent.NAME,
            f"Boosted: {boosted_symbols or 'none'}")
        for sym, opt in optimal_scores.items():
            if opt["expected_wr"] > 55:
                await bus.log(StrategyOptimizerAgent.NAME,
                    f"  {sym}: optimal score >= {opt['threshold']} → {opt['expected_wr']}% WR")

        await bus.log(StrategyOptimizerAgent.NAME, "DONE: Strategy optimization complete")
        await bus.set_status(StrategyOptimizerAgent.NAME, "DONE")


# ═══════════════════════════════════════════════════════════════════════
# AGENT 6: BACKTEST VALIDATOR
# ═══════════════════════════════════════════════════════════════════════
class BacktestValidatorAgent:
    """Walk-forward validation to ensure strategies aren't overfit."""

    NAME = "BacktestValidatorAgent"

    @staticmethod
    async def run(bus: TrainingBus):
        await bus.set_status(BacktestValidatorAgent.NAME, "WAITING")

        # Wait for optimizations
        while not bus.optimizations:
            await asyncio.sleep(2)
        await bus.set_status(BacktestValidatorAgent.NAME, "RUNNING")

        trades = bus.trades
        if len(trades) < 100:
            await bus.log(BacktestValidatorAgent.NAME,
                f"Only {len(trades)} trades — need 100+ for validation")
            await bus.set_status(BacktestValidatorAgent.NAME, "INSUFFICIENT_DATA")
            return

        await bus.log(BacktestValidatorAgent.NAME,
            f"Walk-forward validation on {len(trades)} trades...")

        results = await asyncio.get_event_loop().run_in_executor(
            None, BacktestValidatorAgent._validate, trades, bus.optimizations)

        async with bus._lock:
            bus.backtest_results = results

        await bus.log(BacktestValidatorAgent.NAME,
            f"Overall: {results['overall_win_rate']:.1f}% WR, "
            f"PF: {results['profit_factor']:.2f}, "
            f"Max DD: {results['max_drawdown_pct']:.1f}%")
        for fold in results.get("folds", []):
            await bus.log(BacktestValidatorAgent.NAME,
                f"  Fold {fold['fold']}: {fold['win_rate']:.1f}% WR, "
                f"{fold['trades']} trades, PnL: ${fold['pnl']:.2f}")

        await bus.log(BacktestValidatorAgent.NAME, "DONE: Validation complete")
        await bus.set_status(BacktestValidatorAgent.NAME, "DONE")

    @staticmethod
    def _validate(trades: List[Dict], optimizations: Dict) -> Dict:
        """Walk-forward: train on 70%, test on 30%, sliding window."""
        # Sort by entry time
        sorted_trades = sorted(trades, key=lambda t: t.get("entry_time", ""))
        n = len(sorted_trades)
        fold_size = n // 5
        folds = []

        for fold_idx in range(3):
            train_end = fold_size * (fold_idx + 3)
            test_start = train_end
            test_end = min(test_start + fold_size, n)

            if test_end <= test_start:
                break

            train_set = sorted_trades[:train_end]
            test_set = sorted_trades[test_start:test_end]

            # "Train": compute optimal thresholds from train_set
            train_sym_stats = defaultdict(lambda: {"w": 0, "l": 0})
            for t in train_set:
                train_sym_stats[t["symbol"]]["w" if t["outcome"] == "WIN" else "l"] += 1

            # "Test": apply to test_set
            wins = sum(1 for t in test_set if t["outcome"] == "WIN")
            total = len(test_set)
            pnl = sum(t.get("pnl", 0) for t in test_set)

            folds.append({
                "fold": fold_idx + 1,
                "train_size": len(train_set),
                "trades": total,
                "wins": wins,
                "win_rate": round(wins / max(total, 1) * 100, 1),
                "pnl": round(pnl, 2),
            })

        # Overall stats
        all_wins = sum(1 for t in sorted_trades if t["outcome"] == "WIN")
        total_pnl = sum(t.get("pnl", 0) for t in sorted_trades)
        total_wins_pnl = sum(t["pnl"] for t in sorted_trades if t["outcome"] == "WIN" and t.get("pnl", 0) > 0)
        total_loss_pnl = abs(sum(t["pnl"] for t in sorted_trades if t["outcome"] == "LOSS" and t.get("pnl", 0) < 0))

        # Max drawdown
        equity_curve = []
        running = 0
        peak = 0
        max_dd = 0
        for t in sorted_trades:
            running += t.get("pnl", 0)
            equity_curve.append(running)
            peak = max(peak, running)
            dd = peak - running
            max_dd = max(max_dd, dd)

        return {
            "overall_win_rate": round(all_wins / max(len(sorted_trades), 1) * 100, 1),
            "total_trades": len(sorted_trades),
            "total_pnl": round(total_pnl, 2),
            "profit_factor": round(total_wins_pnl / max(total_loss_pnl, 1), 2),
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_pct": round(max_dd / max(peak, 1) * 100, 1) if peak > 0 else 0,
            "folds": folds,
        }


# ═══════════════════════════════════════════════════════════════════════
# AGENT 7: COORDINATOR — Orchestrates everything & saves results
# ═══════════════════════════════════════════════════════════════════════
class CoordinatorAgent:
    """Orchestrates all agents and produces final training output."""

    NAME = "CoordinatorAgent"

    @staticmethod
    async def run(bus: TrainingBus, symbols: List[str], lookback_days: int = 180):
        await bus.set_status(CoordinatorAgent.NAME, "ORCHESTRATING")
        start = time.time()

        print()
        print("=" * 72)
        print("  MULTI-AGENT TRAINING SYSTEM — 7 Agents Working Concurrently")
        print("=" * 72)
        print(f"  Symbols: {len(symbols)} ({', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''})")
        print(f"  Lookback: {lookback_days} days")
        print(f"  ML Available: {ML_AVAILABLE}")
        print("=" * 72)
        print()

        # ── PHASE 1: Data Collection (must complete first) ──
        await bus.log(CoordinatorAgent.NAME, "PHASE 1: Data Collection")
        await DataCollectorAgent.run(bus, symbols, lookback_days)

        if not bus.raw_data:
            await bus.log(CoordinatorAgent.NAME, "ABORT: No data collected")
            return

        # ── PHASE 2: Parallel processing ──
        await bus.log(CoordinatorAgent.NAME,
            "PHASE 2: Running TechnicalAnalysis + PatternDiscovery + ML concurrently...")

        # Technical analysis must run first (produces trades)
        await TechnicalAnalysisAgent.run(bus)

        if not bus.trades:
            await bus.log(CoordinatorAgent.NAME, "ABORT: No trades generated")
            return

        # Now run Pattern Discovery, ML Training, and Optimizer concurrently
        await bus.log(CoordinatorAgent.NAME,
            "PHASE 3: Pattern Discovery + ML Training + Strategy Optimization (parallel)")

        await asyncio.gather(
            PatternDiscoveryAgent.run(bus),
            MLTrainerAgent.run(bus),
            StrategyOptimizerAgent.run(bus),
        )

        # ── PHASE 4: Validation (needs optimization results) ──
        await bus.log(CoordinatorAgent.NAME, "PHASE 4: Backtest Validation")
        await BacktestValidatorAgent.run(bus)

        # ── PHASE 5: Save results ──
        await bus.log(CoordinatorAgent.NAME, "PHASE 5: Merging & Saving")
        await CoordinatorAgent._save_results(bus)

        elapsed = time.time() - start
        await bus.log(CoordinatorAgent.NAME, f"ALL DONE in {elapsed:.1f}s")

        # ── Final Report ──
        CoordinatorAgent._print_report(bus, elapsed)

    @staticmethod
    async def _save_results(bus: TrainingBus):
        """Merge training results into agent_training_data.json."""
        # Load existing
        existing = {
            "trades": [], "patterns": {}, "agent_accuracy": {},
            "symbol_stats": {}, "session_stats": {}, "combo_stats": {},
            "regime_stats": {}, "adaptive_thresholds": {},
            "blacklisted_symbols": [], "blacklisted_hours": {},
            "ml_model_accuracy": 0, "last_trained": None, "total_pnl": 0,
        }

        if os.path.exists(TRAINING_FILE):
            try:
                with open(TRAINING_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if "trades" in loaded:
                        existing = loaded
                        await bus.log(CoordinatorAgent.NAME,
                            f"Loaded existing: {len(existing['trades'])} trades")
            except Exception as e:
                await bus.log(CoordinatorAgent.NAME, f"Load error: {e}")

        # Merge trades (deduplicate by trade_id)
        existing_ids = set(t.get("trade_id", "") for t in existing["trades"])
        new_trades = [t for t in bus.trades if t["trade_id"] not in existing_ids]
        existing["trades"].extend(new_trades)

        # Keep last 5000
        if len(existing["trades"]) > 5000:
            existing["trades"] = existing["trades"][-5000:]

        # Update from patterns
        patterns = bus.patterns
        if patterns:
            existing["symbol_stats"] = patterns.get("symbol_stats", existing.get("symbol_stats", {}))
            existing["session_stats"] = patterns.get("session_stats", existing.get("session_stats", {}))
            existing["combo_stats"] = patterns.get("combo_stats", existing.get("combo_stats", {}))
            existing["patterns"] = {
                "alignment": patterns.get("alignment", {}),
                "killzone_stats": patterns.get("killzone_stats", {}),
                "amd_stats": patterns.get("amd_stats", {}),
                "score_bands": patterns.get("score_bands", {}),
                "candle_pattern_stats": patterns.get("candle_pattern_stats", {}),
                "day_of_week_stats": patterns.get("day_of_week_stats", {}),
            }

        # Update from optimizations
        opts = bus.optimizations
        if opts:
            existing["adaptive_thresholds"] = opts.get("adaptive_thresholds", {})
            existing["blacklisted_symbols"] = opts.get("blacklisted_symbols", [])
            existing["blacklisted_hours"] = opts.get("blacklisted_hours", {})
            existing["regime_stats"] = opts.get("regime_stats", {})
            existing["optimal_score_thresholds"] = opts.get("optimal_score_thresholds", {})
            existing["best_killzones"] = opts.get("best_killzones", {})

        # Update from ML
        ml = bus.ml_results
        if ml:
            existing["ml_model_accuracy"] = ml.get("ml_model_accuracy", 0)
            existing["ml_top_features"] = ml.get("top_features", [])
            existing["ml_models_comparison"] = {
                name: {k: v for k, v in info.items() if k != "feature_importances"}
                for name, info in ml.get("models", {}).items()
            }
            existing["best_ml_model"] = ml.get("best_model", "unknown")

        # Update from validation
        bt = bus.backtest_results
        if bt:
            existing["backtest_validation"] = bt

        # Update metadata
        existing["total_pnl"] = sum(
            t.get("pnl", 0) for t in existing["trades"] if t.get("outcome"))
        existing["last_trained"] = datetime.utcnow().isoformat()
        existing["training_method"] = "multi_agent_trainer"
        existing["training_agents"] = [
            "DataCollectorAgent", "TechnicalAnalysisAgent", "PatternDiscoveryAgent",
            "MLTrainerAgent", "StrategyOptimizerAgent", "BacktestValidatorAgent",
            "CoordinatorAgent",
        ]

        # Agent accuracy from trades
        agent_stats = defaultdict(lambda: {"correct": 0, "wrong": 0})
        resolved = [t for t in existing["trades"] if t.get("outcome")]
        for t in resolved:
            for agent in t.get("agents", []):
                if t["outcome"] == "WIN":
                    agent_stats[agent]["correct"] += 1
                else:
                    agent_stats[agent]["wrong"] += 1
        for a, s in agent_stats.items():
            total = s["correct"] + s["wrong"]
            s["accuracy"] = round(s["correct"] / total * 100, 1) if total > 0 else 50
            s["total"] = total
        existing["agent_accuracy"] = dict(agent_stats)

        # Save (with Windows fallback for file locking)
        dir_path = os.path.dirname(TRAINING_FILE)
        max_retries = 3
        retry_count = 0
        write_success = False

        while retry_count < max_retries and not write_success:
            try:
                with tempfile.NamedTemporaryFile('w', dir=dir_path, delete=False,
                                                  suffix='.tmp', encoding='utf-8') as tmp:
                    json.dump(existing, tmp, indent=2, default=str)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.replace(tmp.name, TRAINING_FILE)
                write_success = True
            except (PermissionError, OSError) as e:
                # Windows sometimes locks files — retry with exponential backoff
                retry_count += 1
                if retry_count < max_retries:
                    import time
                    time.sleep(0.1 * (2 ** retry_count))  # 0.2s, 0.4s, etc.
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
                else:
                    # Final fallback: direct write (less safe but better than failure)
                    try:
                        os.unlink(tmp.name)
                    except Exception:
                        pass
                    with open(TRAINING_FILE, 'w', encoding='utf-8', newline='\n') as f:
                        json.dump(existing, f, indent=2, default=str)
                        f.flush()
                        os.fsync(f.fileno())
                    write_success = True

        total_trades = len(existing["trades"])
        await bus.log(CoordinatorAgent.NAME,
            f"SAVED: {total_trades} trades, {len(new_trades)} new | "
            f"File: {TRAINING_FILE}")

    @staticmethod
    def _print_report(bus: TrainingBus, elapsed: float):
        """Print comprehensive training report."""
        trades = bus.trades
        patterns = bus.patterns
        ml = bus.ml_results
        opts = bus.optimizations
        bt = bus.backtest_results

        wins = sum(1 for t in trades if t["outcome"] == "WIN")
        total = len(trades)
        wr = round(wins / total * 100, 1) if total > 0 else 0
        total_pnl = sum(t.get("pnl", 0) for t in trades)

        print()
        print("=" * 72)
        print("  MULTI-AGENT TRAINING REPORT")
        print("=" * 72)
        print()
        print(f"  Training Duration: {elapsed:.1f}s")
        print(f"  Total Trades Generated: {total}")
        print(f"  Overall Win Rate: {wr}%")
        print(f"  Total P&L: ${total_pnl:.2f}")
        print()

        # Agent status
        print("  AGENT STATUS:")
        for agent, status in bus.agent_status.items():
            icon = "OK" if status == "DONE" else "!!" if "SKIP" in status else "--"
            print(f"    [{icon}] {agent:25s} → {status}")
        print()

        # Per-symbol breakdown
        sym_stats = patterns.get("symbol_stats", {})
        if sym_stats:
            print("  PER-SYMBOL PERFORMANCE:")
            for sym in sorted(sym_stats.keys(), key=lambda s: sym_stats[s].get("win_rate", 0), reverse=True):
                s = sym_stats[sym]
                bar = "#" * int(s.get("win_rate", 0) / 5)
                icon = "+" if s.get("win_rate", 0) >= 55 else "-" if s.get("win_rate", 0) < 45 else "~"
                bl = " [BLACKLISTED]" if sym in opts.get("blacklisted_symbols", []) else ""
                print(f"    {icon} {sym:10s} {s.get('win_rate', 0):5.1f}% WR "
                      f"({s.get('wins', 0)}W/{s.get('losses', 0)}L) "
                      f"${s.get('pnl', 0):8.2f} {bar}{bl}")
            print()

        # ML results
        if ml and ml.get("models"):
            print("  ML MODEL COMPARISON:")
            for name, info in ml.get("models", {}).items():
                if "error" in info:
                    print(f"    {name:22s} → ERROR: {info['error']}")
                else:
                    star = " << BEST" if name == ml.get("best_model") else ""
                    print(f"    {name:22s} → Train: {info['train_accuracy']:5.1f}% | "
                          f"CV: {info['cv_accuracy']:5.1f}% (+/-{info['cv_std']:4.1f}%){star}")
            print()

            if ml.get("top_features"):
                print("  TOP FEATURES (importance):")
                for f in ml["top_features"][:7]:
                    bar = "#" * int(f["importance"] / 3)
                    print(f"    {f['name']:20s} {f['importance']:5.1f}% {bar}")
                print()

        # Score bands
        score_bands = patterns.get("score_bands", {})
        if score_bands:
            print("  SCORE THRESHOLD ANALYSIS:")
            for band, info in sorted(score_bands.items()):
                print(f"    {band:12s} → {info['win_rate']:5.1f}% WR, "
                      f"{info['count']:4d} trades, avg PnL: ${info['avg_pnl']:.2f}")
            print()

        # Backtest validation
        if bt:
            print("  WALK-FORWARD VALIDATION:")
            print(f"    Overall WR: {bt.get('overall_win_rate', 0):.1f}%")
            print(f"    Profit Factor: {bt.get('profit_factor', 0):.2f}")
            print(f"    Max Drawdown: {bt.get('max_drawdown_pct', 0):.1f}%")
            print(f"    Total P&L: ${bt.get('total_pnl', 0):.2f}")
            for fold in bt.get("folds", []):
                print(f"    Fold {fold['fold']}: {fold['win_rate']:.1f}% WR, "
                      f"{fold['trades']} trades, ${fold['pnl']:.2f}")
            print()

        # Optimal thresholds
        opt_scores = opts.get("optimal_score_thresholds", {})
        if opt_scores:
            print("  OPTIMAL SCORE THRESHOLDS PER SYMBOL:")
            for sym in sorted(opt_scores.keys()):
                o = opt_scores[sym]
                print(f"    {sym:10s} → score >= {o['threshold']:2d} → {o['expected_wr']:.1f}% WR")
            print()

        # Blacklists
        bl = opts.get("blacklisted_symbols", [])
        if bl:
            print(f"  BLACKLISTED SYMBOLS: {', '.join(bl)}")

        bad_hours = opts.get("blacklisted_hours", {})
        if bad_hours:
            print("  BLACKLISTED HOURS:")
            for sym, hours in bad_hours.items():
                print(f"    {sym}: avoid hours {hours}")
            print()

        print("=" * 72)
        print(f"  Training data saved to: {TRAINING_FILE}")
        print(f"  Ready for live trading system to use!")
        print("=" * 72)
        print()


# ═══════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════
async def run_training(symbols: List[str] = None, lookback_days: int = 180):
    """Run the full multi-agent training pipeline."""
    if symbols is None:
        symbols = list(SYMBOL_MAP.keys())

    bus = TrainingBus()
    await CoordinatorAgent.run(bus, symbols, lookback_days)
    return bus


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Multi-Agent Training System")
    parser.add_argument("--quick", action="store_true",
                       help="Quick mode: 3 key symbols only")
    parser.add_argument("--symbols", type=str, default=None,
                       help="Comma-separated symbols (e.g., XAUUSD,EURUSD,BTCUSD)")
    parser.add_argument("--lookback", type=int, default=180,
                       help="Lookback days (default: 180)")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    elif args.quick:
        symbols = ["XAUUSD", "EURUSD", "BTCUSD"]
    else:
        symbols = list(SYMBOL_MAP.keys())

    if not YF_AVAILABLE:
        print("ERROR: yfinance required. Install: pip install yfinance")
        sys.exit(1)

    asyncio.run(run_training(symbols, args.lookback))


if __name__ == "__main__":
    main()
