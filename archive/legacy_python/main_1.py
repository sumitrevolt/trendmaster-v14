"""
╔══════════════════════════════════════════════════════════════════════╗
║          AI TRADING AGENTS TEAM SYSTEM — ADMIN COMMAND CENTER       ║
║          Powered by MetaTrader 5 + AMD/SMC + News Analysis          ║
╠══════════════════════════════════════════════════════════════════════╣
║  TEAMS:                                                              ║
║    🥇 METALS  — XAUUSD (Gold), XAGUSD (Silver)                     ║
║    💱 FOREX   — EURUSD, GBPUSD, USDJPY                              ║
║    🪙 CRYPTO  — BTCUSD, ETHUSD                                      ║
║                                                                      ║
║  AGENTS PER TEAM (9):                                               ║
║    1. DataFetcher      → Real-time MT5 OHLCV data (REAL ONLY)       ║
║    2. MarketAnalyst    → RSI, MACD, BB, EMAs, ADX, S/R              ║
║    3. SmartMoney       → AMD Phase + SMC (FVG, BOS, Sweeps)         ║
║    4. NewsAnalyst      → Yahoo Finance RSS + Sentiment scoring       ║
║    5. SignalGenerator  → BUY/SELL/HOLD + News-adjusted score        ║
║    6. RiskManager      → SL / TP / Position sizing / R:R            ║
║    7. PatternMemory    → Historical setup learning + session bias    ║
║    8. OperatorMind     → Institutional logic / trap detection        ║
║    9. Coordinator      → Confidence-gated summary → Admin           ║
║                                                                      ║
║  ADMIN AGENT:                                                        ║
║    • Cross-team correlation & bias                                   ║
║    • High-confidence alerts + loud sound in browser                 ║
║    • Operator-level market narrative                                 ║
║    • Agent learning accuracy report                                  ║
║                                                                      ║
║  DASHBOARD: http://localhost:8000                                    ║
║  API STATE:  http://localhost:8000/api/state                        ║
╚══════════════════════════════════════════════════════════════════════╝

Usage:
    python main.py    # Live MT5 mode only (no simulation fallback)
"""

import os
import sys
import asyncio
import json
import logging
import tempfile
import threading
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────
# FASTAPI / UVICORN
# ─────────────────────────────────────────────────────────────────────
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

# ─────────────────────────────────────────────────────────────────────
# INSTITUTIONAL AGENTS — Follow the Big Players
# ─────────────────────────────────────────────────────────────────────
try:
    from institutional_agents import (
        run_institutional_analysis,
        AgentCommunicationBus,
        AgentRewardSystem,
        InstitutionalFlowAgent,
        WebResearchAgent,
        CrossMarketAgent,
        EconomicCalendarAgent,
    )
    INSTITUTIONAL_AGENTS_AVAILABLE = True
except ImportError as e:
    INSTITUTIONAL_AGENTS_AVAILABLE = False
    logging.getLogger(__name__).warning(f"⚠️ Institutional agents not available: {e}")

# ─────────────────────────────────────────────────────────────────────
# ADVANCED AGENTS — Correlation, OrderFlow, MarketRegime, DrawdownRecovery
# ─────────────────────────────────────────────────────────────────────
try:
    from advanced_agents import (
        CorrelationAgent,
        OrderFlowAgent,
        MarketRegimeAgent,
        DrawdownRecoveryAgent,
    )
    ADVANCED_AGENTS_AVAILABLE = True
except ImportError as e:
    ADVANCED_AGENTS_AVAILABLE = False
    logging.getLogger(__name__).warning(f"⚠️ Advanced agents not available: {e}")

# ─────────────────────────────────────────────────────────────────────
# GOLD SWING STRATEGY — loaded after sys.path setup (see below ~line 190)
# ─────────────────────────────────────────────────────────────────────
GOLD_SWING_AVAILABLE = False
gold_swing_strategy = None

# ─────────────────────────────────────────────────────────────────────
# AGENT TRAINING SYSTEM — Self-learning feedback loop
# ─────────────────────────────────────────────────────────────────────
try:
    from agent_training import TrainingEngine, TradeSnapshot
    TRAINING_AVAILABLE = True
    TrainingEngine.load()
except ImportError as e:
    TRAINING_AVAILABLE = False
    logging.getLogger(__name__).warning(f"⚠️ Training system not available: {e}")

# ─────────────────────────────────────────────────────────────────────
# SMART RECOVERY & SENTIMENT — Active position management
# ─────────────────────────────────────────────────────────────────────
try:
    from smart_recovery import (
        run_smart_recovery,
        update_sentiment,
        get_sentiment_report,
        SentimentTracker,
        SmartRecoveryManager,
    )
    SMART_RECOVERY_AVAILABLE = True
except ImportError as e:
    SMART_RECOVERY_AVAILABLE = False
    logging.getLogger(__name__).warning(f"⚠️ Smart recovery not available: {e}")

# ─────────────────────────────────────────────────────────────────────
# GEOPOLITICAL RISK — War/Conflict Tracking & Auto-Adjustment
# ─────────────────────────────────────────────────────────────────────
try:
    from geopolitical_agent import GeopoliticalRiskAgent
    GEO_AVAILABLE = True
except ImportError as e:
    GEO_AVAILABLE = False
    logging.getLogger(__name__).warning(f"⚠️ Geopolitical agent not available: {e}")

# ─────────────────────────────────────────────────────────────────────
# INSTITUTIONAL COPY — Follow big player trades from COT/Banks/CBs
# ─────────────────────────────────────────────────────────────────────
try:
    from institutional_copy import run_institutional_copy, InstitutionalCopyAgent
    INST_COPY_AVAILABLE = True
except ImportError as e:
    INST_COPY_AVAILABLE = False
    logging.getLogger(__name__).warning(f"⚠️ Institutional copy not available: {e}")

# ─────────────────────────────────────────────────────────────────────
# TRADINGVIEW INDICATORS — MACD Overlay, SuperTrend, Cash Open, Liquidity
# ─────────────────────────────────────────────────────────────────────
try:
    from tradingview_indicators import tv_analyze, TradingViewStrategy, tv_get_team_config
    TV_INDICATORS_AVAILABLE = True
except ImportError as e:
    TV_INDICATORS_AVAILABLE = False
    logging.getLogger(__name__).warning(f"⚠️ TradingView indicators not available: {e}")

# ─────────────────────────────────────────────────────────────────────
# METATRADER 5
# ─────────────────────────────────────────────────────────────────────
MT5_AVAILABLE = False
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    pass  # Graceful fallback to simulation mode

# ─────────────────────────────────────────────────────────────────────
# ORDER EXECUTOR  (reuses existing src/order_executor.py)
# Initialized after logger is ready — see _init_order_executor() below
# ─────────────────────────────────────────────────────────────────────
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

order_executor = None  # Initialized in _init_order_executor() after logger setup

# ─────────────────────────────────────────────────────────────────────
# LIQUIDITY ENGINE — H1/H4 Major Liquidity Zone Detection + 55/45 Rule
# ─────────────────────────────────────────────────────────────────────
try:
    from src.liquidity_engine import LiquidityEngine, liquidity_engine
    from src.indicators import HTFLiquidityIndicators
    LIQUIDITY_ENGINE_AVAILABLE = True
except ImportError as e:
    LIQUIDITY_ENGINE_AVAILABLE = False
    liquidity_engine = None
    logging.getLogger(__name__).warning(f"⚠️ Liquidity Engine not available: {e}")

# ─────────────────────────────────────────────────────────────────────
# GOLD SWING STRATEGY — H4/Daily swing trading for XAUUSD
# ─────────────────────────────────────────────────────────────────────
try:
    from config.settings import GOLD_SWING_MODE
    if GOLD_SWING_MODE:
        from src.strategy import GoldSwingStrategy
        gold_swing_strategy = GoldSwingStrategy()
        GOLD_SWING_AVAILABLE = True
        logging.getLogger(__name__).info("✅ Gold Swing Strategy loaded (H4/Daily mode for XAUUSD)")
except Exception as e:
    logging.getLogger(__name__).warning(f"⚠️ Gold Swing Strategy not available: {e}")

# ─────────────────────────────────────────────────────────────────────
# LOGGING WITH ROTATION
# ─────────────────────────────────────────────────────────────────────

def _rotate_stderr_log(log_path="agent_err.txt", max_size_mb=50):
    """Rotate stderr log if it exceeds max_size_mb (compress old ones)."""
    try:
        if os.path.exists(log_path):
            file_size_mb = os.path.getsize(log_path) / (1024 * 1024)
            if file_size_mb > max_size_mb:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{log_path}.{timestamp}.bak"
                # Compress and backup
                import shutil
                try:
                    import gzip
                    with open(log_path, 'rb') as f_in:
                        with gzip.open(f"{backup_path}.gz", 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    logger.info(f"📋 Rotated stderr log: {log_path} → {backup_path}.gz ({file_size_mb:.1f}MB)")
                    # Clear the log file
                    with open(log_path, 'w', encoding='utf-8') as f:
                        f.write(f"[LOG ROTATED] {datetime.now().isoformat()}\n")
                except Exception as gz_err:
                    # Fallback: just backup without compression
                    shutil.copy2(log_path, backup_path)
                    logger.info(f"📋 Rotated stderr log: {log_path} → {backup_path} ({file_size_mb:.1f}MB)")
                    with open(log_path, 'w', encoding='utf-8') as f:
                        f.write(f"[LOG ROTATED] {datetime.now().isoformat()}\n")
    except Exception as e:
        logger.warning(f"⚠️ Log rotation failed: {e}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("AgentSystem")

# Rotate stderr logs on startup
_rotate_stderr_log("agent_err.txt", max_size_mb=50)

# ─────────────────────────────────────────────────────────────────────
# AI BRAIN — Claude AI powered agent intelligence
# ─────────────────────────────────────────────────────────────────────
try:
    from ai_brain import (
        ask_agent, get_all_agent_responses, search_market_news,
        save_learning, get_learnings, get_agent_history,
        AGENT_SYSTEM_PROMPTS,
        auto_training_loop, run_full_training, train_agent_on_sector,
        get_training_status, get_sector_knowledge,
        get_knowledge_for_sector,
        ai_validate_signal,
    )
    AI_BRAIN_AVAILABLE = True
    logger.info("🧠 AI Brain module loaded — Claude AI intelligence ACTIVE")
except Exception as _ai_err:
    AI_BRAIN_AVAILABLE = False
    logger.warning(f"⚠️ AI Brain not available: {_ai_err} — using fallback responses")


def _init_order_executor():
    """Initialize OrderExecutor after logger is ready."""
    global order_executor
    if MT5_AVAILABLE:
        try:
            from src.order_executor import OrderExecutor as _OE
            order_executor = _OE()
            logger.info("✅ OrderExecutor loaded — MT5 live trade execution enabled")
        except Exception as _oe_err:
            logger.warning(f"⚠️ OrderExecutor unavailable: {_oe_err}")


# ─────────────────────────────────────────────────────────────────────
# LIVE EXECUTION PARAMETERS
# ─────────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════
# MULTI-MARKET ROTATION PARAMETERS
# Philosophy: Trade 20+ times/day across 10 different markets
# Each market gets max 3 trades/day, then rotate to next
# Small risk per trade (0.5%) but volume creates edge
# ═══════════════════════════════════════════════════════════════════
# FIX 2026-04-14: Score threshold lowered 10→6. Was 10 — too high, no trades ever fired.
# Research: 6+ score with 4+ confluences = high quality setup. 10 was A+++ only (never happens).
_MIN_SCORE_TO_TRADE       = 6     # FIXED: was 10 — lowered to allow quality setups through
_FIXED_LOT_SIZE           = 0.01  # FIXED 0.01 lot — always trade with 0.01 lot only
_MAX_RISK_PCT             = 0.5   # 0.5% risk per trade (small per trade, many trades = edge)
# FIX 2026-04-14: Cooldowns relaxed — 30min was too aggressive, GBPJPY needs faster rotation
_SYMBOL_COOLDOWN_MINUTES  = 20    # FIXED: was 30 — 20 min between same-symbol trades
_GLOBAL_COOLDOWN_MINUTES  = 5     # FIXED: was 10 — 5 min between ANY trade
_MAX_TRADES_PER_TEAM_PER_PAIR = 2  # Max 2 trades per symbol per team (TIGHTENED from 3)
_MAX_OPEN_TRADES_TOTAL    = 3     # Max 3 trades open simultaneously (TIGHTENED from 4 — capital safety)
_MAX_TRADES_PER_DAY_TOTAL = 15    # Max 15 trades/day (TIGHTENED from 30 — quality over quantity)
_NEWS_MUST_CONFIRM        = False # News adjusts score but does NOT block trades
_USE_TP1_FOR_EXECUTION    = True  # Use TP1 for faster profit-taking (volume strategy = lock profits fast)
_GOLD_AGGRESSIVE_MODE     = True  # ENABLED — Gold is our #1 money maker, optimize aggressively

# ── $10 PER TRADE TARGET CALCULATOR ──────────────────────────────────
# For each pair, calculate the lot size needed to make $10 per trade
# XAUUSD: 0.03 lot × 33 pips = $9.90 (~$10). EURUSD: 0.03 lot × 33 pips = $9.90.
# The bot will dynamically select lot size to target $10 profit.
# ── FIXED DOLLAR-BASED SL/TP SYSTEM ─────────────────────────────────
# Sumit's rules: $40 SL, $110 TP, at $30 profit → lock $10 by moving SL
_FIXED_SL_USD  = 40.0    # Max loss per trade = $40
_FIXED_TP_USD  = 110.0   # Take profit target = $110
_LOCK_PROFIT_TRIGGER_USD = 30.0   # When profit reaches $30...
_LOCK_PROFIT_SL_USD      = 10.0   # ...move SL to lock $10 profit
_TARGET_PROFIT_USD = 10.0  # Target profit per trade (partial TP)
_PIP_VALUES = {
    # METALS
    "XAUUSD": 0.10,   # $0.10 per pip per 0.01 lot (gold)
    "XAGUSD": 0.05,   # $0.05 per pip per 0.01 lot (silver)
    # FOREX MAJORS
    "EURUSD": 0.10,
    "GBPUSD": 0.10,
    "USDJPY": 0.09,
    "USDCHF": 0.10,
    "AUDUSD": 0.10,
    "USDCAD": 0.07,
    "NZDUSD": 0.10,
    # FOREX CROSSES
    "GBPJPY": 0.07,
    "EURJPY": 0.07,
    "EURGBP": 0.13,
    "AUDJPY": 0.07,
    "CADJPY": 0.07,
    # CRYPTO
    "BTCUSD": 0.01,   # per $1 move per 0.01 lot
    "ETHUSD": 0.01,
    # COMMODITIES (NEW)
    "USOIL":  0.10,   # $0.10 per pip per 0.01 lot (crude oil)
    "UKOIL":  0.10,   # $0.10 per pip per 0.01 lot (brent)
    "XNGUSD": 0.10,   # $0.10 per pip per 0.01 lot (natural gas)
    "CORN":   0.05,   # $0.05 per pip per 0.01 lot (grain)
    "WHEAT":  0.05,   # $0.05 per pip per 0.01 lot (grain)
}

def calculate_scalp_lot(symbol: str, tp_pips: float) -> float:
    """Calculate optimal lot size to hit $10 target profit."""
    pip_val = _PIP_VALUES.get(symbol, 0.10)
    if tp_pips <= 0 or pip_val <= 0:
        return _FIXED_LOT_SIZE
    # lots_needed = target_profit / (tp_pips * pip_value_per_0.01_lot)
    lots = _TARGET_PROFIT_USD / (tp_pips * pip_val)
    # Round to 0.01 step and clamp
    lots = round(lots / 0.01) * 0.01
    lots = max(0.01, min(lots, 0.05))  # Min 0.01, Max 0.05 (capital safety)
    return lots

# ── ELITE PAIR PRIORITY (focus on highest win rate pairs) ────────────
# ── ELITE PAIRS - highest proven accuracy, get priority execution ─────
# Updated 2026-04-14: Full 4-team roster, all blacklists removed
_ELITE_PAIRS = {
    "GBPJPY",   # 97.7% prediction accuracy - STAR #1
    "USDCAD",   # 87.0% prediction accuracy - STAR #2
    "XAUUSD",   # Swing mode - gold is fundamental money-maker
    "XAGUSD",   # Correlated with gold, good volatility
    "USDCHF",   # Tight spreads, consistent performer
    "EURUSD",   # Most liquid pair - reliable signals
    # COMMODITIES elites
    "USOIL",    # High volatility = high profit potential
    "UKOIL",    # Brent crude - correlated opportunities
}

# ── ALL PAIRS USE DEFAULT GATE - No blacklists ────────────────────────
# 2026-04-14: Removed all blacklisted pairs. Every pair gets a fair chance.
# New pairs (commodities) start at standard gate.
# Dynamic gate system will adjust per-pair based on live performance.
_WEAK_PAIRS = {
    # Only truly consistent losers with NO hope - none right now.
    # All pairs re-enabled. Dynamic tracker will auto-adjust poor performers.
    # Commodities start slightly higher gate (new, needs calibration):
    "CORN":   68,   # New pair - needs calibration, slightly higher gate
    "WHEAT":  68,   # New pair - needs calibration
    "XNGUSD": 65,   # Natural gas - volatile, slightly higher gate
    "NZDUSD": 63,   # Lower liquidity, moderate gate
    "EURGBP": 63,   # Range-bound, needs strong signal
    "CADJPY": 63,   # Less liquid cross
    "AUDJPY": 63,   # Less liquid cross
}
# All unlisted pairs use default gate of 60
_DEFAULT_CONF_GATE = 60
# Require at least 2 confirmation signals for trade execution
_MIN_CONFIRMATION_SIGNALS = 2

# === ENHANCEMENT (2026-03-31): Dynamic accuracy tracker ===
# Tracks recent trade outcomes per symbol and auto-adjusts gates.
# If a symbol drops below 30% win rate over last 20 trades, gate rises to 100 (disabled).
# If a symbol rises above 60% win rate over last 20 trades, gate loosens by 5%.
_DYNAMIC_TRADE_TRACKER = {}  # {symbol: [True/False, ...]} — last 20 results
_DYNAMIC_GATE_ADJUSTMENTS = {}  # {symbol: int} — gate delta

def _update_dynamic_gate(symbol: str, won: bool):
    """Track trade outcome and adjust gate dynamically."""
    global _DYNAMIC_TRADE_TRACKER, _DYNAMIC_GATE_ADJUSTMENTS
    if symbol not in _DYNAMIC_TRADE_TRACKER:
        _DYNAMIC_TRADE_TRACKER[symbol] = []
    _DYNAMIC_TRADE_TRACKER[symbol].append(won)
    # Keep only last 20
    if len(_DYNAMIC_TRADE_TRACKER[symbol]) > 20:
        _DYNAMIC_TRADE_TRACKER[symbol] = _DYNAMIC_TRADE_TRACKER[symbol][-20:]

    results = _DYNAMIC_TRADE_TRACKER[symbol]
    if len(results) >= 10:
        win_rate = sum(results) / len(results)
        if win_rate < 0.30:
            # Terrible performance — effectively disable
            _DYNAMIC_GATE_ADJUSTMENTS[symbol] = 30  # +30 to gate
            logging.getLogger("DynamicGate").warning(
                f"GATE UP: {symbol} win rate {win_rate*100:.0f}% over {len(results)} trades — "
                f"raising confidence gate by +30"
            )
        elif win_rate < 0.45:
            _DYNAMIC_GATE_ADJUSTMENTS[symbol] = 10  # +10 to gate
        elif win_rate > 0.65:
            # Excellent performance — reward with slightly lower gate
            _DYNAMIC_GATE_ADJUSTMENTS[symbol] = -5
            logging.getLogger("DynamicGate").info(
                f"GATE DOWN: {symbol} win rate {win_rate*100:.0f}% over {len(results)} trades — "
                f"lowering confidence gate by -5"
            )
        else:
            _DYNAMIC_GATE_ADJUSTMENTS[symbol] = 0

def _get_effective_gate(symbol: str) -> int:
    """Get the effective confidence gate for a symbol, including dynamic adjustments."""
    base_gate = _WEAK_PAIRS.get(symbol, _DEFAULT_CONF_GATE)
    dynamic_adj = _DYNAMIC_GATE_ADJUSTMENTS.get(symbol, 0)
    return min(100, max(50, base_gate + dynamic_adj))

# ── SESSION-AWARE TRADING (Billionaire Edge) ────────────────────────
# Gold trades ONLY during London (7-16 UTC) and NY (12-21 UTC) sessions.
# Crypto trades 24/7 (it never sleeps). Forex during London+NY.
# Asian session (0-7 UTC) = accumulation/manipulation — NO ENTRIES.
_SESSION_FILTER_ENABLED   = True  # Enable session-based trade filtering
# MULTI-MARKET SESSIONS — each market has its own active window
_GOLD_SESSIONS_UTC        = [(7, 20)]   # London open to NY active
_FOREX_SESSIONS_UTC       = [(0, 21)]   # Almost 24h (Tokyo→London→NY) — forex is truly global
_CRYPTO_SESSIONS_UTC      = [(0, 24)]   # 24/7 — crypto never sleeps, but lower size at thin hours
# Per-pair overrides (loaded from settings.PAIR_SESSION_FILTERS at runtime)
# High-quality trading sessions (overlap periods with better liquidity and lower spreads)
_LONDON_OVERLAP_UTC       = (13, 17)    # London-European overlap: 13:00-17:00 UTC (highest quality)
_NY_SESSION_UTC           = (13, 21)    # NY session: 13:00-21:00 UTC (good liquidity)
_TRADING_QUALITY_FILTER   = True        # Require trading during quality sessions for tighter entries

# ── DAILY DRAWDOWN PROTECTION ───────────────────────────────────────
# Billionaire Rule: "Live to trade another day. Never blow up."
# If daily drawdown exceeds limit, STOP ALL TRADING for the day.
_DAILY_DRAWDOWN_LIMIT_PCT = 4.0   # 4% daily drawdown limit (allows room for 20+ trades)
_DAILY_STARTING_BALANCE   = 0.0   # Set at first cycle of the day
_TRADING_HALTED_TODAY     = False  # Flag to halt all new trades

# ── SMART PYRAMIDING ────────────────────────────────────────────────
# When existing position is in profit (> 30% toward TP), allow adding
# more positions in same direction with REDUCED cooldown.
# This is how the user wants to stack 5 XAUUSD BUY trades.
_PYRAMID_PROFIT_THRESHOLD = 0.65  # Existing position must be 65%+ toward TP before pyramiding (TIGHTENED from 50%)
_PYRAMID_COOLDOWN_MINUTES = 25    # 25 min cooldown for pyramid entries (TIGHTENED from 15 — stack only proven winners)

# ── CORRELATION FILTER ─────────────────────────────────────────────
# Prevent conflicting trades on highly correlated pairs.
# E.g., don't BUY EURUSD and BUY USDCHF simultaneously (inverse correlation).
# Also boost confidence when correlated pairs agree.
_CORRELATION_GROUPS = {
    # Group 1: USD-based majors (EUR, GBP move ~together vs USD)
    "USD_BULL": ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"],   # USD weakens = these go UP
    "USD_BEAR": ["USDCHF", "USDCAD", "USDJPY"],              # USD strengthens = these go UP
    # Group 2: JPY crosses (correlated via risk appetite)
    "JPY_CROSS": ["GBPJPY", "EURJPY", "USDJPY", "AUDJPY", "CADJPY"],
    # Group 3: EUR crosses
    "EUR_CROSS": ["EURUSD", "EURJPY", "EURGBP"],
    # Group 4: Metals (move together)
    "METALS": ["XAUUSD", "XAGUSD"],
    # Group 5: COMMODITIES (NEW)
    "OIL": ["USOIL", "UKOIL", "CADJPY"],    # Oil & CAD correlated
    "GRAINS": ["CORN", "WHEAT"],             # Agricultural commodities
    # Group 6: Commodity currencies (AUD/NZD/CAD linked to commodities)
    "COMM_FX": ["AUDUSD", "NZDUSD", "USDCAD", "AUDJPY", "CADJPY"],
    # Group 7: CRYPTO (move together)
    "CRYPTO": ["BTCUSD", "ETHUSD"],
}

# Inverse correlations: if one group is BUY, the other should be SELL
_INVERSE_CORRELATIONS = {
    "USD_BULL": "USD_BEAR",   # EUR up = USD down = USDCHF should fall
    "USD_BEAR": "USD_BULL",
    # Oil up = CAD stronger = USDCAD down (oil/CAD inverse)
    # No strict inverse for commodities — they trade independently
}

def check_correlation_conflict(symbol: str, direction: str) -> dict:
    """
    Check if a new trade conflicts with existing open trades on correlated pairs.
    Returns: {"conflict": bool, "boost": bool, "reason": str, "conf_adj": int}
    """
    active = system_state.get("active_trades", {})
    if not active:
        return {"conflict": False, "boost": False, "reason": "", "conf_adj": 0}

    # Find which correlation groups this symbol belongs to
    my_groups = [g for g, syms in _CORRELATION_GROUPS.items() if symbol in syms]
    if not my_groups:
        return {"conflict": False, "boost": False, "reason": "", "conf_adj": 0}

    conflicts = []
    confirmations = []

    for ticket, trade in active.items():
        t_sym = trade.get("symbol", "")
        t_dir = trade.get("direction", "")
        if t_sym == symbol or not t_dir:
            continue

        for grp in my_groups:
            group_syms = _CORRELATION_GROUPS.get(grp, [])
            inv_grp = _INVERSE_CORRELATIONS.get(grp)

            # Same group: should trade same direction
            if t_sym in group_syms:
                if t_dir != direction:
                    conflicts.append(f"{t_sym} is {t_dir} (same group {grp}, should be {direction})")
                else:
                    confirmations.append(f"{t_sym} confirms {direction} ({grp})")

            # Inverse group: should trade opposite direction
            if inv_grp and t_sym in _CORRELATION_GROUPS.get(inv_grp, []):
                expected_inv = "SELL" if direction == "BUY" else "BUY"
                if t_dir != expected_inv:
                    conflicts.append(f"{t_sym} is {t_dir} (inverse {inv_grp}, expected {expected_inv})")
                else:
                    confirmations.append(f"{t_sym} inverse confirms ({inv_grp})")

    if conflicts:
        return {
            "conflict": True,
            "boost": False,
            "reason": f"CORR CONFLICT: {conflicts[0]}",
            "conf_adj": -15,
        }
    elif len(confirmations) >= 2:
        return {
            "conflict": False,
            "boost": True,
            "reason": f"CORR BOOST: {len(confirmations)} pairs confirm {direction}",
            "conf_adj": +5,
        }
    elif confirmations:
        return {
            "conflict": False,
            "boost": True,
            "reason": f"CORR: {confirmations[0]}",
            "conf_adj": +2,
        }
    return {"conflict": False, "boost": False, "reason": "", "conf_adj": 0}

# Trade guards — persist across cycles
_open_trade_counts: dict        = {}      # team → {symbol → open trade count}
_symbol_last_trade:  dict       = {}      # symbol → datetime of last trade
_symbol_last_direction: dict    = {}      # symbol → last trade direction ("BUY"/"SELL")
_symbol_same_dir_count: dict    = {}      # symbol → consecutive same-direction trades count
_MAX_SAME_DIR_TRADES   = 1               # Max 1 consecutive trade in same direction per symbol (TIGHTENED from 2 — no stacking same-dir)
_daily_trade_counts: dict       = {"date": "", "count": 0}
_cycle_candidates:   dict       = {}      # team → [{score, symbol, direction, risk, sig}, ...]

# ── ANTI-MARTINGALE LOSS STREAK TRACKER ────────────────────────────
# Billionaire Rule: "After losses, get SMALLER not bigger."
# Reduces position size after consecutive losses and pauses after 5.
_consecutive_losses: int        = 0       # Reset to 0 after a win
_loss_streak_paused: bool       = False   # True if 5+ consecutive losses
_loss_streak_pause_until: float = 0.0     # Timestamp when pause ends

def get_loss_streak_multiplier() -> float:
    """Multi-market anti-martingale:
    0 losses = 1.0x (full size)
    1-2 losses = 0.75x (slightly reduced — normal in volume trading)
    3-4 losses = 0.5x (half size — getting concerning)
    5+ losses = PAUSED 1 hour (take a breather, reassess)
    """
    global _loss_streak_paused, _loss_streak_pause_until
    import time
    if _loss_streak_paused:
        if time.time() >= _loss_streak_pause_until:
            _loss_streak_paused = False
            logger.info("🔄 Anti-Martingale: Loss streak pause ended — resuming at 0.5x size")
            return 0.5  # Resume at half size
        return 0.0  # Still paused
    if _consecutive_losses >= 5:
        _loss_streak_paused = True
        _loss_streak_pause_until = time.time() + 3600  # 1 hour pause after 5 losses
        logger.warning(f"⛔ Anti-Martingale: {_consecutive_losses} consecutive losses — PAUSING 1 HOUR")
        return 0.0
    if _consecutive_losses >= 3:
        return 0.5  # Half size
    if _consecutive_losses >= 1:
        return 0.75  # Slightly reduced
    return 1.0

def record_trade_result(is_win: bool, symbol: str = "", direction: str = ""):
    """Call after a trade closes to update loss streak tracker + reward agents."""
    global _consecutive_losses
    if is_win:
        if _consecutive_losses > 0:
            logger.info(f"✅ Anti-Martingale: Win after {_consecutive_losses} losses — streak reset")
        _consecutive_losses = 0
    else:
        _consecutive_losses += 1
        logger.warning(f"📉 Anti-Martingale: Loss #{_consecutive_losses} — size multiplier: {get_loss_streak_multiplier():.2f}x")

    # Reward institutional agents for their contribution
    if INSTITUTIONAL_AGENTS_AVAILABLE:
        try:
            agents_involved = ["InstitutionalFlow", "WebResearch", "CrossMarket", "EconomicCalendar"]
            AgentRewardSystem.record_trade_result(
                symbol=symbol, direction=direction,
                is_profit=is_win, agents_involved=agents_involved
            )
            if is_win:
                logger.info(f"🏆 REWARDS: All agents earned +10 pts for profitable {direction} {symbol}")
            else:
                logger.info(f"📉 PENALTY: All agents lost -8 pts for losing {direction} {symbol}")
        except Exception as e:
            logger.debug(f"Reward system error: {e}")

# ═════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═════════════════════════════════════════════════════════════════════
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "false").lower() == "true"
ANALYSIS_TIMEFRAME = "H1"     # Main analysis timeframe
BARS_TO_FETCH = 200           # Number of bars per symbol
ANALYSIS_INTERVAL = 30        # 30 seconds between cycles (fast for multi-market rotation)
TEAM_STAGGER = ANALYSIS_INTERVAL // 3  # 10s between teams

TEAMS: Dict[str, Dict] = {
    # ── TEAM 1: METALS ─────────────────────────────────────────────────────
    "METALS": {
        "symbols": ["XAUUSD", "XAGUSD"],
        "color": "#FFD700",
        "icon": "🥇",
        "fallback": {"XAUUSD": 3200.0, "XAGUSD": 32.0},
    },
    # ── TEAM 2: FOREX ──────────────────────────────────────────────────────
    "FOREX": {
        "symbols": [
            "GBPJPY",                                    # STAR - 97.7% accuracy
            "USDCAD",                                    # 87% accuracy
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF",   # Majors
            "AUDUSD", "NZDUSD",                          # Commodity currencies
            "EURJPY", "EURGBP", "AUDJPY", "CADJPY",    # Crosses
        ],
        "color": "#00BFFF",
        "icon": "💱",
        "fallback": {
            "EURUSD": 1.0840, "GBPUSD": 1.2640, "USDJPY": 151.5,
            "USDCHF": 0.8950, "AUDUSD": 0.6380, "USDCAD": 1.3850,
            "NZDUSD": 0.5800, "GBPJPY": 193.5, "EURJPY": 164.0,
            "EURGBP": 0.8580, "AUDJPY": 97.0, "CADJPY": 109.5,
        },
    },
    # ── TEAM 3: CRYPTO ─────────────────────────────────────────────────────
    "CRYPTO": {
        "symbols": ["BTCUSD", "ETHUSD"],
        "color": "#A855F7",
        "icon": "🪙",
        "fallback": {"BTCUSD": 82000.0, "ETHUSD": 1600.0},
    },
    # ── TEAM 4: COMMODITIES (NEW) ──────────────────────────────────────────
    "COMMODITIES": {
        "symbols": ["USOIL", "UKOIL", "XNGUSD", "CORN", "WHEAT"],
        "color": "#F97316",
        "icon": "🛢️",
        "fallback": {
            "USOIL": 62.0,    # WTI Crude Oil (USD/barrel)
            "UKOIL": 66.0,    # Brent Crude Oil (USD/barrel)
            "XNGUSD": 3.50,   # Natural Gas (USD/MMBtu)
            "CORN": 480.0,    # Corn futures (USd/bushel)
            "WHEAT": 560.0,   # Wheat futures (USd/bushel)
        },
    },
}

# ─────────────────────────────────────────────────────────────────────
# NUMPY → PYTHON TYPE CONVERTER  (fixes JSON serialization errors)
# ─────────────────────────────────────────────────────────────────────
def to_native(obj):
    """Recursively convert numpy scalars / arrays to native Python types."""
    if isinstance(obj, dict):
        return {k: to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_native(v) for v in obj]
    if hasattr(obj, "item"):          # numpy scalar → Python scalar
        return obj.item()
    if hasattr(obj, "tolist"):        # numpy array → Python list
        return obj.tolist()
    return obj

AGENT_ICONS = {
    "DataFetcher":     "📡",
    "MarketAnalyst":   "📊",
    "SmartMoney":      "🔍",
    "NewsAnalyst":     "📰",
    "SignalGenerator": "⚡",
    "RiskManager":     "🛡️",
    "PatternMemory":   "🧠",
    "OperatorMind":    "🎯",
    "Coordinator":     "📋",
    "AdminAgent":      "👁️",
    "ML_Engine":       "🤖",
    "AI_Brain":        "🧠",
    "InstitutionalAgents": "🏦",
    "InstitutionalCopy":   "🏛️",
    "LiquidityAgent":      "💧",
    # Team icons
    "METALS":          "🥇",
    "FOREX":           "💱",
    "CRYPTO":          "🪙",
    "COMMODITIES":     "🛢️",   # NEW
}

TYPE_COLORS = {
    "data":        "#6B7280",
    "warning":     "#F59E0B",
    "error":       "#EF4444",
    "analysis":    "#3B82F6",
    "smart_money": "#8B5CF6",
    "news":        "#14B8A6",
    "signal":      "#10B981",
    "risk":        "#F97316",
    "report":      "#06B6D4",
    "admin":       "#EC4899",
    "alert":       "#EF4444",
    "liquidity":   "#06D6A0",
}

# ═════════════════════════════════════════════════════════════════════
# SHARED GLOBAL STATE
# ═════════════════════════════════════════════════════════════════════
executor = ThreadPoolExecutor(max_workers=4)


# ═════════════════════════════════════════════════════════════════════
# CONTINUOUS TRAINING LOOP — Re-analyzes all trades every 15 min
# ═════════════════════════════════════════════════════════════════════
async def _continuous_training_loop():
    """
    Background loop that:
      1. Every 15 min: Re-runs TrainingEngine.run_continuous_learning()
         - Statistical re-analysis of all trades
         - ML model retraining
         - Regime detection updates
         - Stale blacklist pruning
      2. Every cycle: Logs results to system_state for dashboard
    """
    logger.info("🔄 Continuous ML training: Starting in 120s...")
    await asyncio.sleep(120)  # Wait for first trades to come in

    while True:
        try:
            if TRAINING_AVAILABLE:
                result = TrainingEngine.run_continuous_learning()
                system_state["continuous_training"] = {
                    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "result": result,
                }
                if result.get("status") == "success":
                    logger.info(
                        f"🔄 Continuous training: {result['trades']} trades, "
                        f"{result['win_rate']}% WR, ML: {'✅' if result['ml_active'] else '❌'}"
                    )
        except Exception as e:
            logger.warning(f"🔄 Continuous training error: {e}")

        await asyncio.sleep(900)  # 15 minutes


@asynccontextmanager
async def lifespan(app: "FastAPI"):
    """FastAPI lifespan — replaces deprecated @app.on_event('startup')."""
    global message_queue
    message_queue = asyncio.Queue(maxsize=6000)

    system_state["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # MT5 init (blocking → run in executor)
    loop   = asyncio.get_event_loop()
    mt5_ok = await loop.run_in_executor(executor, _sync_init_mt5)
    system_state["mt5_connected"] = mt5_ok
    system_state["mode"]          = "LIVE MT5" if mt5_ok else "SIMULATION"

    # Initialize OrderExecutor for live trade placement
    _init_order_executor()

    # ── STARTUP: Detect existing MT5 positions → populate _open_trade_counts ──
    # Prevents duplicate trades after restart (e.g., 2× XAUUSD BUY)
    if mt5_ok:
        try:
            _existing = await loop.run_in_executor(executor, mt5.positions_get)
            if _existing:
                # Build reverse map: symbol → team name
                _sym_to_team = {}
                for _tn, _td in TEAMS.items():
                    for _s in _td["symbols"]:
                        _sym_to_team[_s] = _tn
                _loaded = 0
                for _pos in _existing:
                    if _pos.comment in ("AI_SWARM_AGENT", "AI_PARTIAL_TP1"):
                        _ps = _pos.symbol
                        _pt = _sym_to_team.get(_ps)
                        if _pt:
                            if _pt not in _open_trade_counts:
                                _open_trade_counts[_pt] = {}
                            _open_trade_counts[_pt][_ps] = _open_trade_counts[_pt].get(_ps, 0) + 1
                            _loaded += 1
                if _loaded:
                    logger.info(f"📊 Loaded {_loaded} existing positions into trade counter: {dict(_open_trade_counts)}")
        except Exception as _e:
            logger.warning(f"⚠️ Failed to load existing positions: {_e}")

    logger.info(f"🚀 Mode: {system_state['mode']} | MT5: {'✅' if mt5_ok else '❌ (simulation)'}")

    # Launch agents (staggered to avoid MT5 burst)
    asyncio.create_task(run_team("METALS", stagger=0))
    asyncio.create_task(run_team("FOREX",  stagger=TEAM_STAGGER))
    asyncio.create_task(run_team("CRYPTO", stagger=TEAM_STAGGER * 2))
    asyncio.create_task(run_admin())
    asyncio.create_task(broadcaster())

    # 🎓 Launch auto-training loop (agents learn from internet every 30 min)
    if AI_BRAIN_AVAILABLE:
        asyncio.create_task(auto_training_loop(emit_fn=emit))
        logger.info("🎓 Auto-training loop launched — agents will learn from internet every 30 min")

    # 🔄 Launch continuous ML training loop (re-analyzes trades every 15 min)
    if TRAINING_AVAILABLE:
        asyncio.create_task(_continuous_training_loop())
        logger.info("🔄 Continuous ML training loop launched — re-learns every 15 min")

    logger.info("✅ All agent teams launched — dashboard at http://localhost:8000")
    yield   # ← application runs here
    # (graceful shutdown can go after yield if needed)

app = FastAPI(title="AI Trading Agents Command Center", lifespan=lifespan)
message_queue: asyncio.Queue = None

system_state: Dict[str, Any] = {
    "mt5_connected": False,
    "mode": "SIMULATION",
    "started_at": "",
    "teams": {
        "METALS": {"prices": {}, "signals": {}, "trends": {}, "bias": "NEUTRAL", "status": "STARTING"},
        "FOREX":  {"prices": {}, "signals": {}, "trends": {}, "bias": "NEUTRAL", "status": "STARTING"},
        "CRYPTO": {"prices": {}, "signals": {}, "trends": {}, "bias": "NEUTRAL", "status": "STARTING"},
    },
    "admin": {
        "market_bias": "NEUTRAL",
        "signal_count": {"BUY": 0, "SELL": 0, "HOLD": 0},
        "alerts": [],
        "correlation": "",
    },
    "daily_stats": {
        "date": "",
        "signal_count": 0,
        "approved_signals": 0,
        "rejected_signals": 0,
    },
    "active_trades": {},    # ticket_str → trade info dict
    "execution_stats": {
        "total_executed": 0,
        "successful":     0,
        "failed":         0,
        "daily_count":    0,
    },
}

# ═════════════════════════════════════════════════════════════════════
# WEBSOCKET MANAGER
# ═════════════════════════════════════════════════════════════════════
class WSManager:
    def __init__(self):
        self._conns: set = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._conns.add(ws)
        logger.info(f"Dashboard connected ({len(self._conns)} active)")

    def disconnect(self, ws: WebSocket):
        self._conns.discard(ws)

    async def broadcast(self, data: dict):
        dead = set()
        for ws in self._conns.copy():
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        self._conns -= dead

    @property
    def count(self):
        return len(self._conns)

ws_manager = WSManager()

# ═════════════════════════════════════════════════════════════════════
# MESSAGE FACTORY
# ═════════════════════════════════════════════════════════════════════
_msg_counter = 0
_msg_lock = threading.Lock()

def make_msg(team: str, agent: str, msg_type: str, content: str, data: dict = None) -> dict:
    global _msg_counter
    with _msg_lock:
        _msg_counter += 1
        _mid = _msg_counter
    return {
        "id": _mid,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "team": team,
        "team_icon": TEAMS.get(team, {}).get("icon", "🤖"),
        "team_color": TEAMS.get(team, {}).get("color", "#FFFFFF"),
        "agent": agent,
        "agent_icon": AGENT_ICONS.get(agent, "🤖"),
        "type": msg_type,
        "type_color": TYPE_COLORS.get(msg_type, "#FFFFFF"),
        "content": str(content),
        "data": to_native(data or {}),   # ← strip all numpy types
    }

async def emit(team: str, agent: str, msg_type: str, content: str, data: dict = None):
    """Queue a message for broadcast to dashboard clients."""
    m = make_msg(team, agent, msg_type, content, data)
    if message_queue:
        try:
            message_queue.put_nowait(m)
        except asyncio.QueueFull:
            pass  # Drop message if queue is full (non-critical)

# ═════════════════════════════════════════════════════════════════════
# MT5 DATA LAYER  (synchronous wrappers run in thread executor)
# ═════════════════════════════════════════════════════════════════════
_TF_MAP = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 16385, "H4": 16388, "D1": 16408,
}

def _sync_get_rates(symbol: str, tf_str: str, bars: int) -> Optional[pd.DataFrame]:
    if not MT5_AVAILABLE or SIMULATION_MODE:
        return None
    try:
        tf = getattr(mt5, f"TIMEFRAME_{tf_str}", mt5.TIMEFRAME_H1)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df[["time", "open", "high", "low", "close", "volume"]].copy()
    except Exception as e:
        logger.debug(f"MT5 rates error [{symbol}]: {e}")
        return None

def _sync_get_tick(symbol: str) -> Optional[dict]:
    if not MT5_AVAILABLE or SIMULATION_MODE:
        return None
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {
            "bid": round(tick.bid, 5),
            "ask": round(tick.ask, 5),
            "spread": round(tick.ask - tick.bid, 5),
            "time": datetime.fromtimestamp(tick.time).strftime("%H:%M:%S"),
        }
    except Exception:
        return None

def _sync_init_mt5() -> bool:
    if not MT5_AVAILABLE or SIMULATION_MODE:
        return False
    try:
        if not mt5.initialize():
            return False
        acct = mt5.account_info()
        if acct:
            logger.info(f"MT5 OK → Account: {acct.login} | Server: {acct.server} | Balance: {acct.balance:.2f}")
        return True
    except Exception as e:
        logger.error(f"MT5 init error: {e}")
        return False

async def mt5_get_rates(symbol: str, tf: str = "H1", bars: int = 100) -> Optional[pd.DataFrame]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _sync_get_rates, symbol, tf, bars)

async def mt5_get_tick(symbol: str) -> Optional[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _sync_get_tick, symbol)

# ═════════════════════════════════════════════════════════════════════
# AGENT MEMORY & LEARNING SYSTEM
# ═════════════════════════════════════════════════════════════════════
class AgentMemory:
    """
    Persistent learning system — every BUY/SELL signal is recorded.
    On the next cycle, the price is compared to see if the prediction
    was correct.  Accuracy is tracked per-symbol and used to adjust
    future signal confidence (good track record → boost, bad → penalty).

    Data is saved to  agent_memory.json  in the same folder as main.py.
    """

    MEMORY_FILE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "prediction_memory.json"
    )
    # Per-asset minimum move to declare prediction outcome (avoids noise)
    MIN_MOVE_PCT_DEFAULT = 0.15   # 0.15% default (metals/forex)
    MIN_MOVE_CRYPTO      = 0.30   # 0.30% crypto (higher volatility)

    def __init__(self):
        self.memory: Dict[str, Any] = self._load()

    def _load(self) -> dict:
        try:
            if os.path.exists(self.MEMORY_FILE):
                with open(self.MEMORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"AgentMemory load error: {e}")
        return {}

    _save_counter: int = 0

    def _save(self):
        """Batch saves — ATOMIC writes to disk every 10 calls to prevent corruption."""
        AgentMemory._save_counter = getattr(AgentMemory, '_save_counter', 0) + 1
        if AgentMemory._save_counter % 10 != 0:
            return
        try:
            # Pre-serialize to validate JSON before writing to disk
            json_str = json.dumps(self.memory, indent=2)
            # Atomic write: temp file + os.replace() prevents corruption on crash
            dir_path = os.path.dirname(self.MEMORY_FILE)
            with tempfile.NamedTemporaryFile('w', dir=dir_path, delete=False,
                                              suffix='.tmp', encoding='utf-8') as tmp:
                tmp.write(json_str)
                tmp.flush()
                os.fsync(tmp.fileno())
            try:
                os.replace(tmp.name, self.MEMORY_FILE)
            except (OSError, PermissionError) as rename_err:
                logger.debug(f"Atomic rename failed for {self.MEMORY_FILE}, fallback: {rename_err}")
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
                with open(self.MEMORY_FILE, 'w', encoding='utf-8') as f:
                    f.write(json_str)
                    f.flush()
                    os.fsync(f.fileno())
            # Also update backup after successful write
            bak_file = self.MEMORY_FILE + ".bak"
            try:
                with tempfile.NamedTemporaryFile('w', dir=dir_path, delete=False,
                                                  suffix='.tmp', encoding='utf-8') as tmp_bak:
                    json.dump(self.memory, tmp_bak, indent=2)
                    tmp_bak.flush()
                    os.fsync(tmp_bak.fileno())
                os.replace(tmp_bak.name, bak_file)
            except Exception:
                pass  # Backup write failure is non-critical
        except Exception as e:
            logger.warning(f"AgentMemory save error: {e}")
            try:
                if os.path.exists(tmp.name):
                    os.unlink(tmp.name)
            except Exception:
                pass

    # ── Record a new prediction ────────────────────────────────────────
    def record(self, symbol: str, signal: str, price: float, confidence: int):
        """Store a BUY/SELL prediction for later outcome evaluation."""
        if signal == "HOLD":
            return
        if symbol not in self.memory:
            self.memory[symbol] = {
                "predictions": [],
                "total": 0,
                "correct": 0,
                "accuracy": 0.5,
            }
        self.memory[symbol]["predictions"].append({
            "signal":     signal,
            "price":      price,
            "confidence": confidence,
            "timestamp":  datetime.now().isoformat(),
            "evaluated":  False,
            "correct":    None,
        })
        # Keep only the last 500 predictions per symbol (memory safety limit)
        self.memory[symbol]["predictions"] = self.memory[symbol]["predictions"][-500:]
        self._save()

    # ── Evaluate pending predictions against current price ─────────────
    def evaluate(self, symbol: str, current_price: float) -> List[dict]:
        """
        Compare current_price against all un-evaluated predictions.
        Returns a list of lesson-dicts to show on the dashboard.
        """
        if symbol not in self.memory:
            return []

        lessons = []
        changed = False

        for pred in self.memory[symbol]["predictions"]:
            if pred.get("evaluated"):
                continue

            old_price = pred["price"]
            signal    = pred["signal"]
            pct       = (current_price - old_price) / old_price * 100

            # Need minimum move to call a verdict
            min_move = self.MIN_MOVE_CRYPTO if symbol in ("BTCUSD","ETHUSD") else self.MIN_MOVE_PCT_DEFAULT
            if abs(pct) < min_move:
                continue

            correct = (signal == "BUY" and pct > 0) or (signal == "SELL" and pct < 0)
            # Track weighted accuracy (larger moves count more)
            move_weight = min(abs(pct) / 1.0, 3.0)  # Cap weight at 3.0
            pred["move_pct"]    = round(pct, 3)
            pred["move_weight"] = round(move_weight, 3)

            if correct:
                icon    = "✅"
                outcome = f"{icon} {signal} @ {old_price:.5f} → Now {current_price:.5f} ({pct:+.2f}%) — CORRECT"
            else:
                icon    = "❌"
                outcome = f"{icon} {signal} @ {old_price:.5f} → Now {current_price:.5f} ({pct:+.2f}%) — WRONG"

            pred["evaluated"] = True
            pred["correct"]   = correct
            changed = True

            # Update running accuracy
            m = self.memory[symbol]
            m["total"]   += 1
            m["correct"] += int(correct)
            # Weighted accuracy: correct moves count proportionally to their size
            weighted_correct = sum(
                p.get("move_weight", 1.0) for p in self.memory[symbol]["predictions"]
                if p.get("evaluated") and p.get("correct")
            )
            weighted_total = sum(
                p.get("move_weight", 1.0) for p in self.memory[symbol]["predictions"]
                if p.get("evaluated")
            )
            m["accuracy"] = (weighted_correct / weighted_total) if weighted_total > 0 else 0.5

            lessons.append({
                "outcome":  outcome,
                "symbol":   symbol,
                "signal":   signal,
                "correct":  correct,
                "pct":      round(pct, 2),
                "accuracy": round(m["accuracy"] * 100, 1),
                "correct_count": m["correct"],
                "total":    m["total"],
            })

            # ── AUTO-FEED: Send evaluated predictions to TrainingEngine ──
            # This is how the system learns WITHOUT needing actual MT5 trades!
            # Every evaluated prediction becomes training data for ML.
            if TRAINING_AVAILABLE:
                try:
                    _syn_pnl = round(abs(pct) * 0.5 if correct else -(abs(pct) * 0.5), 2)
                    _pred_trade = {
                        "symbol": symbol,
                        "direction": signal,
                        "score": 8 if signal == "BUY" else -8,
                        "confidence": pred.get("confidence", 50),
                        "rsi": 50, "adx": 25,
                        "hour_utc": datetime.utcnow().hour,
                        "h1_trend": signal.replace("BUY","BULLISH").replace("SELL","BEARISH"),
                        "h4_trend": "SIDEWAYS",
                        "h4_h1_aligned": False,
                        "killzone": "NONE",
                        "institutional_dir": "NEUTRAL",
                        "institutional_conf": 50,
                        "amd_phase": "", "volume_signal": "NORMAL", "news": "NEUTRAL",
                        "entry_time": pred.get("timestamp", datetime.utcnow().isoformat()),
                        "outcome": "WIN" if correct else "LOSS",
                        "pnl": _syn_pnl,
                        "close_time": datetime.utcnow().isoformat(),
                        "source": "prediction_eval",
                    }
                    TrainingEngine.load()
                    TrainingEngine._data.setdefault("trades", []).append(_pred_trade)
                    # Only save every 10th to reduce I/O
                    if len(TrainingEngine._data["trades"]) % 10 == 0:
                        TrainingEngine.save()
                except Exception:
                    pass  # Don't let training errors break prediction flow

        if changed:
            self._save()
        return lessons

    # ── Confidence multiplier based on historical accuracy ─────────────
    def multiplier(self, symbol: str) -> float:
        """
        Continuous linear multiplier based on historical accuracy.
        Scales smoothly: 40% acc → 0.75×,  55% → 1.00×,  70% → 1.25×
        Below 5 evaluated predictions → neutral 1.0×
        """
        m = self.memory.get(symbol)
        if not m or not isinstance(m, dict) or m.get("total", 0) < 5:
            return 1.0
        acc = m["accuracy"]  # 0.0 – 1.0
        # Linear interpolation: clamp to [0.75, 1.25]
        mult = 0.75 + (acc - 0.40) * (1.25 - 0.75) / (0.70 - 0.40)
        return round(max(0.75, min(1.25, mult)), 3)

    # ── Stats summary for a symbol ─────────────────────────────────────
    def stats(self, symbol: str) -> dict:
        m = self.memory.get(symbol)
        if not m or not isinstance(m, dict) or m.get("total", 0) == 0:
            return {"accuracy": 50.0, "total": 0, "correct": 0, "multiplier": 1.0}
        return {
            "accuracy":   round(m["accuracy"] * 100, 1),
            "total":      m["total"],
            "correct":    m["correct"],
            "multiplier": self.multiplier(symbol),
        }

    # ── Full memory report for Admin display ──────────────────────────
    def report(self) -> str:
        lines = []
        for sym, m in self.memory.items():
            if not isinstance(m, dict) or m.get("total", 0) == 0:
                continue
            acc = round(m["accuracy"] * 100, 1)
            grade = "🟢" if acc >= 65 else "🟡" if acc >= 50 else "🔴"
            lines.append(
                f"{grade} {sym}: {acc}% ({m['correct']}/{m['total']}) "
                f"× mult {self.multiplier(sym):.2f}"
            )
        return " | ".join(lines) if lines else "No evaluated predictions yet"


# Singleton — shared across all team agents
agent_memory = AgentMemory()


# ═════════════════════════════════════════════════════════════════════
# NEWS ENGINE  — Yahoo Finance RSS (no API key required)
# ═════════════════════════════════════════════════════════════════════
# Yahoo Finance RSS symbol map
NEWS_FEEDS: Dict[str, str] = {
    # METALS
    "XAUUSD": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC%3DF&region=US&lang=en-US",
    "XAGUSD": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SI%3DF&region=US&lang=en-US",
    # FOREX MAJORS
    "EURUSD": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=EURUSD%3DX&region=US&lang=en-US",
    "GBPUSD": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GBPUSD%3DX&region=US&lang=en-US",
    "USDJPY": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=JPY%3DX&region=US&lang=en-US",
    "USDCHF": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=CHF%3DX&region=US&lang=en-US",
    "AUDUSD": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AUDUSD%3DX&region=US&lang=en-US",
    "USDCAD": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=CAD%3DX&region=US&lang=en-US",
    "NZDUSD": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=NZDUSD%3DX&region=US&lang=en-US",
    # FOREX CROSSES
    "GBPJPY": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GBPJPY%3DX&region=US&lang=en-US",
    "EURJPY": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=EURJPY%3DX&region=US&lang=en-US",
    "EURGBP": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=EURGBP%3DX&region=US&lang=en-US",
    "AUDJPY": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AUDJPY%3DX&region=US&lang=en-US",
    "CADJPY": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=CADJPY%3DX&region=US&lang=en-US",
    # CRYPTO
    "BTCUSD": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=BTC-USD&region=US&lang=en-US",
    "ETHUSD": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ETH-USD&region=US&lang=en-US",
    # COMMODITIES (NEW) - Yahoo Finance commodity tickers
    "USOIL":  "https://feeds.finance.yahoo.com/rss/2.0/headline?s=CL%3DF&region=US&lang=en-US",
    "UKOIL":  "https://feeds.finance.yahoo.com/rss/2.0/headline?s=BZ%3DF&region=US&lang=en-US",
    "XNGUSD": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=NG%3DF&region=US&lang=en-US",
    "CORN":   "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ZC%3DF&region=US&lang=en-US",
    "WHEAT":  "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ZW%3DF&region=US&lang=en-US",
}

# General macro / forex news fallback (BBC Business RSS — no key needed)
MACRO_FEED = "https://feeds.bbci.co.uk/news/business/rss.xml"

class NewsEngine:
    """
    Fetches latest news headlines via Yahoo Finance RSS feed per symbol.
    Runs basic keyword-sentiment analysis (no NLP library needed).
    Returns a sentiment score + top headlines for the NewsAnalyst agent.
    News score ±2 feeds directly into the SignalEngine score.
    """

    BULLISH = {
        # Price action
        "surges","surge","rises","rise","gains","gain","rally","rallies","bullish",
        "breakout","strong","positive","growth","up","high","record","buy","buying",
        "increase","boost","jump","soar","soaring","climbs","advance","recover",
        "recovery","optimistic","upside","outperform","upgrade","beats","exceeds",
        "inflow","demand","interest","support","accumulation","hawkish","inflation",
        "boosts","lifted","powered","leads","tops","peaks","higher",
        # Geopolitical → GOLD/safe-haven BULLISH
        "war","conflict","invasion","attack","missile","strike","troops","military",
        "tension","escalation","crisis","sanctions","nato","threat","nuclear",
        "ceasefire fails","offensive","bombardment","airstrike","warfare","hostilities",
        "emergency","geopolitical","instability","turmoil","unrest",
    }
    BEARISH = {
        # Price action
        "falls","fall","drops","drop","declines","decline","bearish","crash","crashes",
        "weak","weakness","negative","loss","plunges","plunge","down","low","sell",
        "selling","decrease","slump","tumbles","sinks","retreat","fear","concern",
        "warning","risk","cut","cuts","miss","misses","below","disappoints","downturn",
        "outflow","supply","dovish","slowdown","recession","drop",
        "pressure","dragged","weighs","weigh","losses","deficit","uncertainty","ban",
        # Geopolitical → risk-OFF / USD-strength BEARISH for other assets
        "ceasefire","peace","deal","truce","resolution","de-escalation","withdrawal",
        "diplomacy","agreement","accord","negotiations","settled","calm",
    }

    # Cache: symbol → (timestamp, result) so we don't hammer RSS every 30 s
    _cache: Dict[str, tuple] = {}
    CACHE_TTL = 300   # seconds before re-fetching (5 min — matches typical news cycle)

    @classmethod
    async def fetch(cls, symbol: str) -> dict:
        """Return news sentiment dict for the given symbol."""
        now = datetime.now().timestamp()
        cached = cls._cache.get(symbol)
        if cached and now - cached[0] < cls.CACHE_TTL:
            return cached[1]

        url = NEWS_FEEDS.get(symbol, MACRO_FEED)
        result = await cls._fetch_rss(url, symbol)
        cls._cache[symbol] = (now, result)
        return result

    @classmethod
    async def _fetch_rss(cls, url: str, symbol: str) -> dict:
        empty = {"score": 0, "sentiment": "NEUTRAL", "headlines": [],
                 "bull_hits": 0, "bear_hits": 0, "count": 0}
        try:
            import aiohttp
            headers = {"User-Agent": "Mozilla/5.0 (compatible; TradingBot/1.0)"}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=6), headers=headers
                ) as resp:
                    if resp.status != 200:
                        return empty
                    text = await resp.text()

            # Parse RSS XML
            root = ET.fromstring(text)
            headlines = []
            for item in root.iter("item"):
                title = item.find("title")
                if title is not None and title.text:
                    headlines.append(title.text.strip())
                if len(headlines) >= 6:
                    break

            if not headlines:
                return empty

            # Keyword sentiment scoring
            bull = 0
            bear = 0
            for h in headlines:
                words = set(w.strip(".,!?;:\"'()[]").lower() for w in h.split())
                bull += len(words & cls.BULLISH)
                bear += len(words & cls.BEARISH)

            score = bull - bear
            if   score >= 2:  sentiment = "BULLISH"
            elif score <= -2: sentiment = "BEARISH"
            else:             sentiment = "NEUTRAL"

            return {
                "score":     score,
                "sentiment": sentiment,
                "headlines": headlines[:3],
                "bull_hits": bull,
                "bear_hits": bear,
                "count":     len(headlines),
            }

        except asyncio.TimeoutError:
            logger.debug(f"News timeout [{symbol}]")
            return empty
        except Exception as e:
            logger.debug(f"News fetch error [{symbol}]: {e}")
            return empty


# ═════════════════════════════════════════════════════════════════════
# SESSION FILTER  — Only trade during high-liquidity windows
# ═════════════════════════════════════════════════════════════════════
class SessionFilter:
    """
    ALL TEAMS RUN 24/7 — no market is ever blocked.
    Instead, a session-quality label is returned with each cycle.

      METALS (XAUUSD / XAGUSD):
        Peak       07:00–21:00 UTC (London + NY)
        Thin       21:00–07:00 UTC (Asian dead zone — wider spreads)

      FOREX:
        True 24/5 market.
        Tokyo     00:00–07:00 UTC  (JPY pairs most active)
        London    07:00–13:00 UTC
        Overlap   13:00–16:00 UTC  (PEAK)
        New York  16:00–21:00 UTC
        Late NY   21:00–24:00 UTC  (spreads widening)

      CRYPTO:
        Always active — note thin zone 22:00–05:00 UTC.

    Agent always proceeds with analysis; liquidity quality adjusts
    confidence scoring internally.
    """

    @classmethod
    def check(cls, team: str) -> tuple:
        """
        Returns (is_active=True always, session_quality_note: str).
        All teams run 24/7 — session note informs agents about
        current liquidity quality so they can calibrate confidence.
        """
        now_h = datetime.utcnow().hour

        if team == "CRYPTO":
            thin = (now_h >= 22) or (now_h < 5)
            if thin:
                return True, (
                    f"⚠️ Crypto thin zone ({now_h:02d}:xx UTC) — "
                    "wider spreads, confidence auto-reduced"
                )
            return True, f"✅ Crypto active ({now_h:02d}:xx UTC)"

        if team == "METALS":
            if 13 <= now_h < 16:
                return True, f"🔥 METALS PEAK: London/NY Overlap ({now_h:02d}:xx UTC) — highest liquidity"
            elif 7 <= now_h < 13:
                return True, f"🇬🇧 METALS: London session ({now_h:02d}:xx UTC) — high liquidity"
            elif 16 <= now_h < 21:
                return True, f"🇺🇸 METALS: New York session ({now_h:02d}:xx UTC) — good liquidity"
            else:
                return True, (
                    f"🌙 METALS: Asian thin zone ({now_h:02d}:xx UTC) — "
                    "lower liquidity, signals require higher confidence threshold"
                )

        # FOREX — true 24/5 market
        if team == "FOREX":
            if 13 <= now_h < 16:
                return True, f"🔥 FOREX PEAK: London/NY Overlap ({now_h:02d}:xx UTC) — PEAK LIQUIDITY"
            elif 7 <= now_h < 13:
                return True, f"🇬🇧 FOREX: London session ({now_h:02d}:xx UTC) — EUR/GBP most active"
            elif 16 <= now_h < 21:
                return True, f"🇺🇸 FOREX: New York session ({now_h:02d}:xx UTC) — USD pairs most active"
            elif 0 <= now_h < 7:
                return True, f"🌏 FOREX: Tokyo session ({now_h:02d}:xx UTC) — JPY/AUD pairs most active"
            else:
                return True, (
                    f"🌙 FOREX: Late NY/transition ({now_h:02d}:xx UTC) — "
                    "thinner liquidity, widen SL slightly"
                )

        # Fallback: always active
        return True, f"✅ {team} active ({now_h:02d}:xx UTC)"

    @classmethod
    def liquidity_quality(cls, team: str) -> str:
        """Returns PEAK / HIGH / MEDIUM / LOW for internal confidence adjustment."""
        now_h = datetime.utcnow().hour
        if team == "CRYPTO":
            # Crypto is 24/7; only genuine thin zone is extreme late night
            return "MEDIUM" if (now_h >= 23 or now_h < 4) else "HIGH"
        if team in ("METALS", "FOREX"):
            if 13 <= now_h < 16:
                return "PEAK"
            elif 7 <= now_h < 21:
                return "HIGH"
            else:
                return "MEDIUM"
        return "HIGH"


# ═════════════════════════════════════════════════════════════════════
# CANDLESTICK PATTERN DETECTOR
# ═════════════════════════════════════════════════════════════════════
class CandlePatterns:
    """
    Detects high-probability reversal and continuation candle patterns.
    Each confirmed pattern contributes a score:
      +2  Bullish Engulfing / Green Hammer / Bullish Momentum
      -2  Bearish Engulfing / Red Shooting Star
      +1  Regular Hammer / Bullish Pin Bar
      -1  Bearish Pin Bar
       0  Doji (indecision — flags caution)
    Total score capped at ±4.
    """

    @staticmethod
    def detect(df: pd.DataFrame) -> dict:
        if len(df) < 4:
            return {"patterns": [], "score": 0}

        patterns = []
        score    = 0

        r0 = df.iloc[-1]   # Current candle
        r1 = df.iloc[-2]   # Previous candle

        o0, h0, l0, c0 = float(r0["open"]), float(r0["high"]), float(r0["low"]), float(r0["close"])
        o1, h1, l1, c1 = float(r1["open"]), float(r1["high"]), float(r1["low"]), float(r1["close"])

        body0 = abs(c0 - o0)
        body1 = abs(c1 - o1)
        rng0  = h0 - l0
        rng1  = h1 - l1

        if rng0 < 1e-10:
            return {"patterns": [], "score": 0}

        lower_wick = min(o0, c0) - l0
        upper_wick = h0 - max(o0, c0)

        # ── Bullish Engulfing ────────────────────────────────────────
        if (c1 < o1 and c0 > o0 and c0 >= o1 and o0 <= c1 and body0 > body1 * 1.1):
            patterns.append("🕯️ BULLISH ENGULFING — Strong reversal signal")
            score += 2

        # ── Bearish Engulfing ────────────────────────────────────────
        elif (c1 > o1 and c0 < o0 and c0 <= o1 and o0 >= c1 and body0 > body1 * 1.1):
            patterns.append("🕯️ BEARISH ENGULFING — Strong reversal signal")
            score -= 2

        # ── Hammer (Bullish reversal at lows) ────────────────────────
        if (body0 > 0 and lower_wick >= body0 * 2.0 and upper_wick <= body0 * 0.5):
            if c0 > o0:
                patterns.append("🔨 GREEN HAMMER — High-probability bullish reversal")
                score += 2
            else:
                patterns.append("🔨 HAMMER — Potential bullish reversal")
                score += 1

        # ── Shooting Star (Bearish reversal at highs) ─────────────────
        elif (body0 > 0 and upper_wick >= body0 * 2.0 and lower_wick <= body0 * 0.5):
            if c0 < o0:
                patterns.append("⭐ RED SHOOTING STAR — High-probability bearish reversal")
                score -= 2
            else:
                patterns.append("⭐ SHOOTING STAR — Potential bearish reversal")
                score -= 1

        # ── Pin Bar (Rejection wick ≥ 70% of range) ──────────────────
        wick_ratio = max(lower_wick, upper_wick) / rng0
        if wick_ratio >= 0.70 and body0 / rng0 < 0.20:
            if lower_wick > upper_wick:
                patterns.append("📌 BULLISH PIN BAR — Aggressive rejection of lower prices")
                score += 1
            else:
                patterns.append("📌 BEARISH PIN BAR — Aggressive rejection of higher prices")
                score -= 1

        # ── Doji (Indecision — caution) ───────────────────────────────
        if body0 / rng0 < 0.12:
            patterns.append("➕ DOJI — Indecision; wait for next candle confirmation")

        # ── Momentum Candle (body ≥ 75% of range, ≥ 2× avg body) ─────
        avg_body = df["close"].sub(df["open"]).abs().tail(20).mean()
        if body0 > avg_body * 2.0 and body0 / rng0 >= 0.75:
            if c0 > o0:
                patterns.append("⚡ BULL MOMENTUM CANDLE — Strong buying pressure")
                score += 1
            else:
                patterns.append("⚡ BEAR MOMENTUM CANDLE — Strong selling pressure")
                score -= 1

        return {
            "patterns": patterns[:4],
            "score":    max(-4, min(4, score)),
        }


# ═════════════════════════════════════════════════════════════════════
# RSI DIVERGENCE DETECTOR  (leading indicator — high accuracy)
# ═════════════════════════════════════════════════════════════════════
class DivergenceDetector:
    """
    Detects RSI divergence with correct index handling and tighter thresholds.
    Requires RSI near extremes (< 35 oversold / > 65 overbought) for valid signal.
    """

    @staticmethod
    def detect(df: pd.DataFrame) -> dict:
        empty = {"type": "NONE", "score": 0, "detail": "No divergence"}
        n = len(df)
        if n < 20:
            return empty

        closes = df["close"].values
        rsis   = df["rsi"].values

        # ── Bullish divergence: price lower low, RSI higher low ──────
        # Scan last 15 bars for recent low, bars 5-15 ago for earlier low
        try:
            recent_range  = range(max(0, n-5), n)
            earlier_range = range(max(0, n-15), max(0, n-5))

            recent_lo  = min(recent_range,  key=lambda i: closes[i])
            earlier_lo = min(earlier_range, key=lambda i: closes[i])

            if (closes[recent_lo] < closes[earlier_lo]   # Price: lower low
                    and rsis[recent_lo] > rsis[earlier_lo]   # RSI: higher low
                    and rsis[recent_lo] < 35                 # RSI in oversold zone
                    and rsis[earlier_lo] < 45):              # Earlier RSI also low
                return {
                    "type":  "BULLISH",
                    "score": 2,
                    "detail": (
                        f"📈 RSI BULLISH DIVERGENCE — Price LL "
                        f"({closes[earlier_lo]:.5f}→{closes[recent_lo]:.5f}) "
                        f"vs RSI HL ({rsis[earlier_lo]:.1f}→{rsis[recent_lo]:.1f}) "
                        "— Momentum reversing UP from oversold"
                    ),
                }

            # ── Bearish divergence: price higher high, RSI lower high ──
            recent_hi  = max(recent_range,  key=lambda i: closes[i])
            earlier_hi = max(earlier_range, key=lambda i: closes[i])

            if (closes[recent_hi] > closes[earlier_hi]   # Price: higher high
                    and rsis[recent_hi] < rsis[earlier_hi]  # RSI: lower high
                    and rsis[recent_hi] > 65               # RSI in overbought zone
                    and rsis[earlier_hi] > 55):             # Earlier RSI also high
                return {
                    "type":  "BEARISH",
                    "score": -2,
                    "detail": (
                        f"📉 RSI BEARISH DIVERGENCE — Price HH "
                        f"({closes[earlier_hi]:.5f}→{closes[recent_hi]:.5f}) "
                        f"vs RSI LH ({rsis[earlier_hi]:.1f}→{rsis[recent_hi]:.1f}) "
                        "— Momentum reversing DOWN from overbought"
                    ),
                }
        except (ValueError, IndexError):
            return empty

        return empty


# ═════════════════════════════════════════════════════════════════════
# TECHNICAL ANALYSIS ENGINE
# ═════════════════════════════════════════════════════════════════════
class TechAnalysis:
    """Full indicator suite — pure pandas/numpy, no external TA lib needed."""

    @staticmethod
    def add_all(df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < 26:
            return df
        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]

        # ── EMAs ──
        df["ema9"]  = c.ewm(span=9,  adjust=False).mean()
        df["ema21"] = c.ewm(span=21, adjust=False).mean()
        df["ema50"] = c.ewm(span=50, adjust=False).mean()

        # ── RSI(14) ──
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs   = gain / loss.replace(0, np.nan)
        df["rsi"] = (100 - 100 / (1 + rs)).fillna(50)

        # ── MACD(12,26,9) ──
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        df["macd"]        = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"]   = df["macd"] - df["macd_signal"]
        df["macd_cross_bull"] = (df["macd_hist"] > 0) & (df["macd_hist"].shift(1) <= 0)
        df["macd_cross_bear"] = (df["macd_hist"] < 0) & (df["macd_hist"].shift(1) >= 0)

        # ── Bollinger Bands(20,2) ──
        bm = c.rolling(20).mean()
        bs = c.rolling(20).std()
        df["bb_upper"]  = bm + bs * 2
        df["bb_middle"] = bm
        df["bb_lower"]  = bm - bs * 2
        df["bb_width"]  = ((df["bb_upper"] - df["bb_lower"]) / bm).fillna(0)
        brange = (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
        df["bb_pct"] = ((c - df["bb_lower"]) / brange).fillna(0.5)

        # ── ATR(14) ──
        tr = pd.concat([
            h - l,
            (h - c.shift(1)).abs(),
            (l - c.shift(1)).abs(),
        ], axis=1).max(axis=1)
        raw_atr = tr.rolling(14).mean()
        # Spike filter: if single TR > 3× rolling ATR, cap it (gap open protection)
        atr_mean_prev = raw_atr.shift(1)
        tr_capped = tr.where(tr <= atr_mean_prev * 3, atr_mean_prev * 3)
        df["atr"] = tr_capped.rolling(14).mean().bfill()

        # ── ADX(14) ──
        dm_p = h.diff().clip(lower=0)
        dm_n = (-l.diff()).clip(lower=0)
        dm_p = dm_p.where(dm_p > (-l.diff()).clip(lower=0), 0)
        dm_n = dm_n.where(dm_n > h.diff().clip(lower=0), 0)
        atr14 = tr.rolling(14).mean().replace(0, np.nan)
        di_p  = 100 * dm_p.rolling(14).mean() / atr14
        di_n  = 100 * dm_n.rolling(14).mean() / atr14
        dx    = 100 * (di_p - di_n).abs() / (di_p + di_n).replace(0, np.nan)
        df["adx"]      = dx.rolling(14).mean().fillna(0)
        df["di_plus"]  = di_p.fillna(0)
        df["di_minus"] = di_n.fillna(0)

        # ── Volume ──
        df["vol_sma"]   = v.rolling(20).mean()
        df["vol_ratio"] = (v / df["vol_sma"].replace(0, np.nan)).fillna(1)

        return df.bfill().fillna(0)

    # ── Trend ──────────────────────────────────────────────────────────
    @staticmethod
    def trend(df: pd.DataFrame) -> dict:
        r = df.iloc[-1]
        bullish = r["ema9"] > r["ema21"] > r["ema50"]
        bearish = r["ema9"] < r["ema21"] < r["ema50"]
        adx = r["adx"]
        str_label = (
            "VERY STRONG" if adx > 40 else "STRONG" if adx > 30
            else "MODERATE" if adx > 20 else "WEAK"
        )
        direction = "BULLISH" if bullish else "BEARISH" if bearish else "SIDEWAYS"
        # DI spread confirmation: direction only valid if DI spread > 5
        di_spread = abs(r.get("di_plus", 0) - r.get("di_minus", 0))
        di_confirmed = di_spread >= 5
        if not di_confirmed and direction != "SIDEWAYS":
            direction = "SIDEWAYS"   # Weak DI spread → treat as ranging
        # Include RSI + MACD for exhaustion/reversal detection
        rsi_val = float(r.get("rsi", 50))
        macd_h = float(r.get("macd_hist", 0))
        macd_h_prev = float(df.iloc[-2].get("macd_hist", 0)) if len(df) > 1 else 0

        return {
            "direction": direction,
            "adx": round(adx, 1),
            "strength_label": str_label,
            "ema9":  round(r["ema9"],  5),
            "ema21": round(r["ema21"], 5),
            "ema50": round(r["ema50"], 5),
            "di_plus":  round(r["di_plus"],  1),
            "di_minus": round(r["di_minus"], 1),
            "rsi": round(rsi_val, 1),
            "macd_hist": round(macd_h, 6),
            "macd_hist_prev": round(macd_h_prev, 6),
        }

    # ── Momentum ────────────────────────────────────────────────────────
    @staticmethod
    def momentum(df: pd.DataFrame) -> dict:
        r = df.iloc[-1]
        rsi = r["rsi"]
        hist = r["macd_hist"]
        rsi_label = (
            "EXTREME OVERSOLD"  if rsi < 20 else
            "OVERSOLD"          if rsi < 30 else
            "BULLISH ZONE"      if rsi < 45 else
            "NEUTRAL"           if rsi < 55 else
            "BEARISH ZONE"      if rsi < 70 else
            "OVERBOUGHT"        if rsi < 80 else
            "EXTREME OVERBOUGHT"
        )
        # True cross = histogram changed sign this bar
        cross_bull = bool(df["macd_cross_bull"].iloc[-1]) if "macd_cross_bull" in df.columns else False
        cross_bear = bool(df["macd_cross_bear"].iloc[-1]) if "macd_cross_bear" in df.columns else False
        if cross_bull:
            macd_label = "BULLISH CROSS ✅"
        elif cross_bear:
            macd_label = "BEARISH CROSS ✅"
        elif hist > 0:
            macd_label = "BULLISH (above zero)"
        else:
            macd_label = "BEARISH (below zero)"
        return {
            "rsi":        round(rsi, 1),
            "rsi_label":  rsi_label,
            "macd_hist":  round(hist, 6),
            "macd_label": macd_label,
        }

    # ── Support / Resistance ─────────────────────────────────────────────
    @staticmethod
    def support_resistance(df: pd.DataFrame, lookback: int = 50) -> dict:
        """
        Improved S/R with zone clustering.
        Uses 3-bar pivot logic and merges levels within 0.2% of each other.
        Ranks zones by number of touches.
        """
        rec = df.tail(lookback)
        cp  = float(df.iloc[-1]["close"])
        highs, lows = [], []

        for i in range(3, len(rec) - 3):
            row  = rec.iloc[i]
            # Require 3 bars on each side for stronger pivots
            left_h  = rec.iloc[i-3:i]["high"].max()
            right_h = rec.iloc[i+1:i+4]["high"].max()
            left_l  = rec.iloc[i-3:i]["low"].min()
            right_l = rec.iloc[i+1:i+4]["low"].min()

            if row["high"] > left_h and row["high"] > right_h:
                highs.append(row["high"])
            if row["low"] < left_l and row["low"] < right_l:
                lows.append(row["low"])

        def cluster_levels(levels: list, threshold_pct: float = 0.002) -> list:
            """Merge levels within threshold_pct of each other into zones."""
            if not levels:
                return []
            sorted_levels = sorted(levels)
            clusters = [[sorted_levels[0]]]
            for lvl in sorted_levels[1:]:
                if clusters[-1][-1] != 0 and abs(lvl - clusters[-1][-1]) / clusters[-1][-1] <= threshold_pct:
                    clusters[-1].append(lvl)
                else:
                    clusters.append([lvl])
            # Return cluster midpoint weighted by number of touches
            return [(sum(c) / len(c), len(c)) for c in clusters]

        res_zones = cluster_levels([x for x in highs if x > cp])
        sup_zones = cluster_levels([x for x in lows  if x < cp])

        # Sort by touches (descending) then pick nearest
        res_zones.sort(key=lambda x: (-x[1], x[0]))
        sup_zones.sort(key=lambda x: (-x[1], -x[0]))

        best_res = min(res_zones, key=lambda x: x[0])[0] if res_zones else rec["high"].max()
        best_sup = max(sup_zones, key=lambda x: x[0])[0] if sup_zones else rec["low"].min()
        res_touches = max((z[1] for z in res_zones), default=1)
        sup_touches = max((z[1] for z in sup_zones), default=1)

        return {
            "support":     round(best_sup, 5),
            "resistance":  round(best_res, 5),
            "sup_touches": sup_touches,
            "res_touches": res_touches,
            "sup_zones":   [(round(z[0],5), z[1]) for z in sup_zones[:3]],
            "res_zones":   [(round(z[0],5), z[1]) for z in res_zones[:3]],
        }

    # ── Bollinger Analysis ───────────────────────────────────────────────
    @staticmethod
    def bb_analysis(df: pd.DataFrame) -> dict:
        r   = df.iloc[-1]
        pct = r["bb_pct"]
        bw  = r["bb_width"]
        avg_bw = df["bb_width"].tail(40).mean()
        squeeze = bw < avg_bw * 0.65
        state = (
            "ABOVE UPPER BAND" if pct > 1.0 else
            "NEAR UPPER BAND"  if pct > 0.8 else
            "UPPER HALF"       if pct > 0.5 else
            "LOWER HALF"       if pct > 0.2 else
            "NEAR LOWER BAND"  if pct > 0   else
            "BELOW LOWER BAND"
        )
        return {
            "bb_pct":   round(pct, 3),
            "bb_width": round(bw,  5),
            "state":    state,
            "squeeze":  squeeze,
            "squeeze_note": "⚡ BB SQUEEZE — Breakout imminent!" if squeeze else "Normal range",
        }

# ═════════════════════════════════════════════════════════════════════
# SMART MONEY CONCEPTS ENGINE  (AMD + SMC)
# ═════════════════════════════════════════════════════════════════════
class SmartMoneyEngine:
    """
    Accumulation / Manipulation / Distribution  +
    Fair Value Gaps / Order Blocks / BOS / Liquidity Sweeps
    """

    @staticmethod
    def amd_phase(df: pd.DataFrame) -> dict:
        if len(df) < 30:
            return {"phase": "UNKNOWN", "confidence": 0, "detail": "Insufficient data"}
        r   = df.iloc[-1]
        r5  = df.tail(5)
        adx = r["adx"]
        vol = r["vol_ratio"]
        bw  = r["bb_width"]
        avg_bw = df["bb_width"].tail(50).mean()

        body  = abs(r["close"] - r["open"])
        rng   = r["high"] - r["low"]
        wick  = (rng - body) / rng if rng > 0 else 0
        pc5   = (r5["close"].iloc[-1] - r5["close"].iloc[0]) / r5["close"].iloc[0] * 100

        # Phase logic
        if vol > 1.3 and wick > 0.55 and adx < 30:
            phase = "MANIPULATION"
            conf  = min(95, int(vol * 40 + wick * 35))
            detail = (
                f"STOP HUNT ACTIVE — Vol {vol:.1f}x surge, wick ratio {wick:.0%}. "
                "Operators clearing retail stop-losses before real directional move."
            )
        elif adx > 22 and vol > 1.1 and abs(pc5) > 0.25:
            phase = "DISTRIBUTION"
            direction = "UPWARD" if pc5 > 0 else "DOWNWARD"
            conf  = min(92, int(adx * 1.8 + vol * 12))
            detail = (
                f"REAL MOVE {direction} — ADX {adx:.0f}, Vol {vol:.1f}x. "
                "Smart money distributing/executing positions. Follow the flow."
            )
        elif adx < 20 and bw < avg_bw * 0.72:
            phase = "ACCUMULATION"
            conf  = min(88, int((1 - bw / max(avg_bw, 1e-9)) * 55 + (20 - min(adx, 20)) * 1.5))
            detail = (
                f"STEALTH ACCUMULATION — ADX {adx:.0f} (no trend), BB squeeze "
                f"({bw:.4f} vs avg {avg_bw:.4f}). Institutions loading in quiet market."
            )
        else:
            phase = "TRANSITION"
            conf  = 50
            detail = (
                f"Phase unclear — ADX:{adx:.0f}, Vol:{vol:.1f}x, BB_w:{bw:.4f}. "
                "Waiting for clearer institutional footprint."
            )

        return {
            "phase": phase,
            "confidence": conf,
            "detail": detail,
            "adx":  round(adx, 1),
            "vol":  round(vol, 2),
            "wick": round(wick, 2),
        }

    @staticmethod
    def smc_levels(df: pd.DataFrame) -> dict:
        if len(df) < 10:
            return {}
        out = {"fvg_bull": [], "fvg_bear": [], "bos": None, "sweep": None}

        # Fair Value Gaps (last 12 candles)
        for i in range(2, min(12, len(df))):
            c0, c2 = df.iloc[-(i + 1)], df.iloc[-(i - 1)]
            if c2["low"] > c0["high"]:
                out["fvg_bull"].append({"top": round(c2["low"], 5), "bot": round(c0["high"], 5), "ago": i})
            if c2["high"] < c0["low"]:
                out["fvg_bear"].append({"top": round(c0["low"], 5), "bot": round(c2["high"], 5), "ago": i})

        # Break of Structure
        recent = df.tail(20)
        cp = df.iloc[-1]["close"]
        prev_hi = recent["high"].iloc[:-1].max()
        prev_lo = recent["low"].iloc[:-1].min()
        if cp > prev_hi:
            out["bos"] = {"type": "BULLISH BOS", "level": round(prev_hi, 5)}
        elif cp < prev_lo:
            out["bos"] = {"type": "BEARISH BOS", "level": round(prev_lo, 5)}

        # Liquidity Sweep (last 2 candles vs prior 5 swing)
        if len(df) >= 6:
            lc = df.iloc[-1]
            prior_hi = df.iloc[-6:-1]["high"].max()
            prior_lo = df.iloc[-6:-1]["low"].min()
            if lc["high"] > prior_hi and lc["close"] < prior_hi:
                out["sweep"] = {
                    "type":   "BEARISH SWEEP (Bull Trap)",
                    "level":  round(prior_hi, 5),
                    "detail": "Swept above resistance, then rejected — longs trapped",
                }
            elif lc["low"] < prior_lo and lc["close"] > prior_lo:
                out["sweep"] = {
                    "type":   "BULLISH SWEEP (Bear Trap)",
                    "level":  round(prior_lo, 5),
                    "detail": "Swept below support, then recovered — shorts squeezed",
                }
        return out

    @staticmethod
    def operator_narrative(amd: dict, smc: dict, trend: dict) -> str:
        parts = []
        sweep = smc.get("sweep")
        bos   = smc.get("bos")
        fgb   = smc.get("fvg_bull", [])
        fgr   = smc.get("fvg_bear", [])

        if sweep:
            parts.append(f"🎯 {sweep['type']} @ {sweep['level']} — {sweep['detail']}")

        phase_notes = {
            "ACCUMULATION": "📦 Operators in stealth loading phase — retail sees chop, institutions see opportunity",
            "MANIPULATION": "⚡ Operators running liquidity raid — brace for real directional move after sweep",
            "DISTRIBUTION": "🚀 Operators executing position — align with institutional flow",
            "TRANSITION":   "🔄 Phase changing — monitor for AMD footprint crystallisation",
        }
        if amd.get("phase") in phase_notes:
            parts.append(phase_notes[amd["phase"]])

        if bos:
            parts.append(f"📐 {bos['type']} at {bos['level']} — structure shifted, expect continuation/retest")
        if fgb:
            parts.append(f"⬜ Bullish FVG {fgb[0]['bot']}–{fgb[0]['top']} (price likely returns to fill imbalance)")
        if fgr:
            parts.append(f"⬛ Bearish FVG {fgr[0]['bot']}–{fgr[0]['top']} (price likely returns to fill imbalance)")

        return " | ".join(parts) if parts else "No clear operator footprint — market in equilibrium"


# ═════════════════════════════════════════════════════════════════════
# SIGNAL ENGINE
# ═════════════════════════════════════════════════════════════════════
class SignalEngine:
    MAX_SCORE = 20   # Expanded: base 14 + candle ±4 + divergence ±2 + H4 ±2 (news ±2 added after)

    @staticmethod
    def generate(
        trend: dict, mom: dict, bb: dict, amd: dict, smc: dict,
        candle: dict = None, divergence: dict = None, h4_trend: dict = None,
        sr: dict = None, h4_sr: dict = None, current_price: float = 0,
        adx_filter: bool = True,
    ) -> dict:
        """
        Generates trading signal from all available analysis inputs.

        New inputs vs previous version:
          candle     — CandlePatterns.detect() result       (±4)
          divergence — DivergenceDetector.detect() result   (±2)
          h4_trend   — TechAnalysis.trend() on H4 data      (±2)
          adx_filter — If True, HOLD when ADX < 15 and no BB squeeze
        """
        score = 0
        reasons = []

        # ── ADX Quality Filter ────────────────────────────────────────
        # Flat/ranging markets produce far more false signals.
        # Gold uses lower threshold (15) because it often trends with lower ADX.
        # Other pairs use 20. Skip filter if BB squeeze is active.
        adx_val = trend.get("adx", 0)
        adx_threshold = 18  # 18 for multi-market (some forex pairs trend softer)
        if adx_filter and adx_val < adx_threshold and not bb.get("squeeze", False):
            return {
                "signal":     "HOLD",
                "strength":   "NEUTRAL",
                "score":      0,
                "confidence": 15,
                "reasons":    [f"ADX {adx_val:.0f} < {adx_threshold} — ranging/consolidating, no directional edge (skip)"],
                "filtered":   True,
            }

        # ── Trend (±3) ────────────────────────────────────────────────
        d = trend["direction"]
        if d == "BULLISH":
            score += 3;  reasons.append(f"EMA stack UP (ADX {adx_val:.0f})")
        elif d == "BEARISH":
            score -= 3;  reasons.append(f"EMA stack DOWN (ADX {adx_val:.0f})")

        # ── RSI (±2) ──────────────────────────────────────────────────
        rsi = mom["rsi"]
        if rsi < 35:
            score += 2;  reasons.append(f"RSI oversold ({rsi:.0f})")
        elif rsi > 65:
            score -= 2;  reasons.append(f"RSI overbought ({rsi:.0f})")

        # ── MACD (±2, cross=±3) ───────────────────────────────────────
        if "CROSS ✅" in mom["macd_label"] and "BULLISH" in mom["macd_label"]:
            score += 3;  reasons.append("MACD FRESH BULLISH CROSS (high confidence)")
        elif "CROSS ✅" in mom["macd_label"] and "BEARISH" in mom["macd_label"]:
            score -= 3;  reasons.append("MACD FRESH BEARISH CROSS (high confidence)")
        elif "BULLISH" in mom["macd_label"]:
            score += 2;  reasons.append("MACD bullish (above zero)")
        else:
            score -= 2;  reasons.append("MACD bearish (below zero)")

        # ── Bollinger Bands (±1) ──────────────────────────────────────
        bp = bb["bb_pct"]
        if bp < 0.2:
            score += 1;  reasons.append("Near BB lower band")
        elif bp > 0.8:
            score -= 1;  reasons.append("Near BB upper band")
        if bb.get("squeeze"):
            reasons.append("BB squeeze — high-probability breakout zone")

        # ── AMD Phase (±3) ────────────────────────────────────────────
        phase = amd["phase"]
        if phase == "DISTRIBUTION":
            if d == "BULLISH":
                score += 3;  reasons.append("AMD Distribution UP")
            elif d == "BEARISH":
                score -= 3;  reasons.append("AMD Distribution DOWN")
        elif phase == "MANIPULATION":
            sweep = smc.get("sweep", {}).get("type", "")
            if "Bear Trap" in sweep:
                score += 2;  reasons.append("SMC Bear Trap → reversal UP")
            elif "Bull Trap" in sweep:
                score -= 2;  reasons.append("SMC Bull Trap → reversal DOWN")

        # ── BOS (±2) ──────────────────────────────────────────────────
        bos = smc.get("bos")
        if bos:
            if "BULLISH" in bos["type"]:
                score += 2;  reasons.append(f"Bullish BOS @ {bos['level']}")
            else:
                score -= 2;  reasons.append(f"Bearish BOS @ {bos['level']}")

        # ── S/R Zone strength bonus (multi-touch = stronger level) ────
        sr = sr or {}
        sup_touches = sr.get("sup_touches", 1)
        res_touches = sr.get("res_touches", 1)
        if d == "BULLISH" and sup_touches >= 3:
            score += 1;  reasons.append(f"Strong support zone ({sup_touches} touches) — bounce area")
        elif d == "BEARISH" and res_touches >= 3:
            score -= 1;  reasons.append(f"Strong resistance zone ({res_touches} touches) — rejection area")

        # ── Candlestick Patterns (±4) ─────────────────────────────────
        if candle and candle.get("patterns"):
            cp_score = candle.get("score", 0)
            if cp_score != 0:
                score += cp_score
            for p in candle["patterns"][:2]:
                reasons.append(p[:60])

        # ── RSI Divergence (±2) ───────────────────────────────────────
        if divergence and divergence.get("type") != "NONE":
            score += divergence["score"]
            reasons.append(divergence["detail"][:70])

        # ═══════════════════════════════════════════════════════════════
        # H4 EXHAUSTION / REVERSAL DETECTION — Catch TOPS and DIPS
        # Rule: If H4 trend is bullish BUT exhausting → prepare for SELL
        #       If H4 trend is bearish BUT exhausting → prepare for BUY
        # Exhaustion signals: RSI overbought/oversold + MACD weakening
        # ═══════════════════════════════════════════════════════════════
        h4_exhausted = False
        h4_reversal_dir = None  # The direction of the expected reversal

        if h4_trend:
            h4_rsi = h4_trend.get("rsi", 50)
            h4_macd_hist = h4_trend.get("macd_hist", 0)
            h4_macd_prev = h4_trend.get("macd_hist_prev", 0)
            h4_dir_raw = h4_trend.get("direction", "SIDEWAYS")
            h4_adx_raw = h4_trend.get("adx", 0)

            # DETECT H4 TOP: Bullish trend + RSI > 65 + MACD histogram shrinking
            if h4_dir_raw == "BULLISH" and h4_rsi > 65:
                if h4_macd_hist < h4_macd_prev or h4_rsi > 75:
                    h4_exhausted = True
                    h4_reversal_dir = "SELL"
                    score -= 7  # STRONG reversal — must overpower alignment bonus (+4)
                    reasons.append(
                        f"🔻 H4 TOP DETECTED: RSI {h4_rsi:.0f} overbought + "
                        f"MACD weakening → REVERSAL DOWN expected. SELL bias. (score -7)"
                    )
                elif h4_rsi > 60:
                    # Near-exhaustion: not fully triggered but risky for new BUY
                    score -= 3
                    reasons.append(f"⚠️ H4 NEAR TOP: RSI {h4_rsi:.0f} — risky for BUY")

            # DETECT H4 DIP: Bearish trend + RSI < 35 + MACD histogram recovering
            elif h4_dir_raw == "BEARISH" and h4_rsi < 35:
                if h4_macd_hist > h4_macd_prev or h4_rsi < 25:
                    h4_exhausted = True
                    h4_reversal_dir = "BUY"
                    score += 7  # STRONG reversal — must overpower alignment bonus (-4)
                    reasons.append(
                        f"🔺 H4 DIP DETECTED: RSI {h4_rsi:.0f} oversold + "
                        f"MACD recovering → REVERSAL UP expected. BUY bias. (score +7)"
                    )
                elif h4_rsi < 40:
                    # Near-exhaustion at bottom
                    score += 3
                    reasons.append(f"⚠️ H4 NEAR DIP: RSI {h4_rsi:.0f} — risky for SELL")

        # ═══════════════════════════════════════════════════════════════
        # H4 + H1 TREND ALIGNMENT — ** MANDATORY ** (CORE RULE)
        # UPDATED: Respects exhaustion/reversal detection
        # If H4 exhausted at TOP → allow SELL even if H4 still technically bullish
        # If H4 exhausted at DIP → allow BUY even if H4 still technically bearish
        # ═══════════════════════════════════════════════════════════════
        if h4_trend:
            h4_dir = h4_trend.get("direction", "SIDEWAYS")
            h4_adx = h4_trend.get("adx", 0)

            # If H4 is exhausted, use the REVERSAL direction instead
            if h4_exhausted and h4_reversal_dir:
                effective_h4_dir = h4_reversal_dir  # Override: top→SELL, dip→BUY
                reasons.append(
                    f"🔄 H4 EXHAUSTION OVERRIDE: Technical {h4_dir} but exhausted → "
                    f"using reversal direction {h4_reversal_dir}"
                )
            else:
                effective_h4_dir = h4_dir

            if effective_h4_dir == d and effective_h4_dir == "BULLISH":
                # H4 + H1 both BULLISH → GREEN LIGHT for BUY
                score += 4
                reasons.append(f"✅ H4+H1 ALIGNED BULLISH (H4 ADX:{h4_adx}) — FULL MTF BUY CONFIRMED")
            elif effective_h4_dir == d and effective_h4_dir == "BEARISH":
                # H4 + H1 both BEARISH → GREEN LIGHT for SELL
                score -= 4
                reasons.append(f"✅ H4+H1 ALIGNED BEARISH (H4 ADX:{h4_adx}) — FULL MTF SELL CONFIRMED")
            elif h4_dir != "SIDEWAYS" and d != "SIDEWAYS" and h4_dir != d:
                # ⛔ H4 DIRECTLY CONFLICTS H1 — BLOCK THE TRADE
                # Only block when BOTH have clear direction AND they're OPPOSITE
                # (e.g. H4=BULLISH vs H1=BEARISH, or H4=BEARISH vs H1=BULLISH)
                # H1=SIDEWAYS is NOT a conflict — just means no H1 trend yet
                sig, strength = "HOLD", "NEUTRAL"
                score = 0  # Reset score to zero — do NOT trade
                reasons.append(
                    f"⛔ H4 ({h4_dir}) CONFLICTS H1 ({d}) — BLOCKED. "
                    f"Only scalp in H4 direction. Wait for alignment."
                )
                return {
                    "signal": "HOLD", "strength": "NEUTRAL", "score": 0,
                    "confidence": 10,
                    "reasons": reasons,
                    "filtered": True,
                    "h4_block": True,  # Flag for dashboard
                }
            elif h4_dir != "SIDEWAYS" and d == "SIDEWAYS":
                # H1 is SIDEWAYS while H4 has direction — reduced conviction, NOT a block
                # H4 direction gets priority, but we don't block: allow with penalty
                score -= 2  # Small penalty for missing H1 confirmation
                reasons.append(
                    f"⚠️ H1 SIDEWAYS while H4 {h4_dir} (ADX:{h4_adx}) — "
                    f"H4 leads, reduced conviction (score -2). Watching for H1 alignment."
                )
            else:
                # H4 is SIDEWAYS — allow but with reduced conviction
                score += 0  # No bonus
                reasons.append(
                    f"🔄 H4 sideways (ADX:{h4_adx}) — no HTF trend confirmation. "
                    f"H1 ({d}) leads, reduced conviction."
                )
        else:
            # No H4 data available — BLOCK TRADE (trend is everything, no H4 = no trade)
            reasons.append("⛔ H4 data unavailable — CANNOT confirm trend direction. BLOCKED.")
            return {
                "signal": "HOLD", "strength": "NEUTRAL", "score": 0,
                "confidence": 5,
                "reasons": reasons,
                "filtered": True,
                "h4_block": True,
            }

        # ═══════════════════════════════════════════════════════════════
        # 🛑 H4 RESISTANCE/SUPPORT PRICE CHECK — BLOCK BUY AT H4 TOP
        # If current price is near H4 resistance AND H4 RSI overbought → NO BUY
        # If current price is near H4 support AND H4 RSI oversold → NO SELL
        # This is the #1 fix for GBPUSD BUY signals at H4 tops
        # ═══════════════════════════════════════════════════════════════
        if h4_sr and current_price > 0:
            h4_res = h4_sr.get("resistance", 0)
            h4_sup = h4_sr.get("support", 0)
            h4_rsi_now = h4_trend.get("rsi", 50) if h4_trend else 50

            # Calculate distance to H4 resistance/support
            if h4_res > 0:
                dist_to_res_pct = abs(current_price - h4_res) / current_price * 100
                # If price is within 0.25% of H4 resistance → dangerous for BUY
                if dist_to_res_pct < 0.25 and score > 0:
                    if h4_rsi_now > 60:
                        # AT H4 RESISTANCE + OVERBOUGHT → BLOCK BUY
                        reasons.append(
                            f"🛑 H4 RESISTANCE BLOCK: Price {current_price:.5f} is {dist_to_res_pct:.2f}% "
                            f"from H4 resistance {h4_res:.5f} + RSI {h4_rsi_now:.0f} overbought → BUY BLOCKED"
                        )
                        return {
                            "signal": "HOLD", "strength": "NEUTRAL", "score": 0,
                            "confidence": 15,
                            "reasons": reasons,
                            "filtered": True,
                            "h4_block": True,
                        }
                    else:
                        # Near resistance but RSI not extreme — heavy penalty
                        score -= 5
                        reasons.append(
                            f"⚠️ NEAR H4 RESISTANCE: {dist_to_res_pct:.2f}% away — BUY risky (score -5)"
                        )
                elif dist_to_res_pct < 0.50 and score > 0 and h4_rsi_now > 65:
                    score -= 3
                    reasons.append(
                        f"⚠️ Approaching H4 resistance ({dist_to_res_pct:.2f}%) + RSI {h4_rsi_now:.0f} — caution (score -3)"
                    )

            if h4_sup > 0:
                dist_to_sup_pct = abs(current_price - h4_sup) / current_price * 100
                # If price is within 0.25% of H4 support → dangerous for SELL
                if dist_to_sup_pct < 0.25 and score < 0:
                    if h4_rsi_now < 40:
                        # AT H4 SUPPORT + OVERSOLD → BLOCK SELL
                        reasons.append(
                            f"🛑 H4 SUPPORT BLOCK: Price {current_price:.5f} is {dist_to_sup_pct:.2f}% "
                            f"from H4 support {h4_sup:.5f} + RSI {h4_rsi_now:.0f} oversold → SELL BLOCKED"
                        )
                        return {
                            "signal": "HOLD", "strength": "NEUTRAL", "score": 0,
                            "confidence": 15,
                            "reasons": reasons,
                            "filtered": True,
                            "h4_block": True,
                        }
                    else:
                        score += 5
                        reasons.append(
                            f"⚠️ NEAR H4 SUPPORT: {dist_to_sup_pct:.2f}% away — SELL risky (score +5)"
                        )
                elif dist_to_sup_pct < 0.50 and score < 0 and h4_rsi_now < 35:
                    score += 3
                    reasons.append(
                        f"⚠️ Approaching H4 support ({dist_to_sup_pct:.2f}%) + RSI {h4_rsi_now:.0f} — caution (score +3)"
                    )

        # ── Minimum confluence guard — need ≥ 2 aligned reasons ─────
        # Prevents single-indicator fake signals (e.g. MACD alone firing).
        bullish_count = sum(1 for r in reasons if any(w in r.lower() for w in
            ["up", "bull", "oversold", "bos", "accumulation", "confirms", "hammer",
             "engulfing", "divergence", "ema stack up", "macd bull"]))
        bearish_count = sum(1 for r in reasons if any(w in r.lower() for w in
            ["down", "bear", "overbought", "distribution", "bos", "trap",
             "shooting", "divergence", "ema stack down", "macd bear"]))

        # Need ≥2 confluent reasons (balanced for multi-market volume)
        if score > 0 and bullish_count < 2:
            sig, strength = "HOLD", "NEUTRAL"
            reasons.append(f"⚠️ Only {bullish_count} bullish reason(s) — need ≥2 confluence (skip)")
            score = min(score, 2)
        elif score < 0 and bearish_count < 2:
            sig, strength = "HOLD", "NEUTRAL"
            reasons.append(f"⚠️ Only {bearish_count} bearish reason(s) — need ≥2 confluence (skip)")
            score = max(score, -2)
        else:
            # Signal determination (82% win rate — strict thresholds)
            if   score >= 10: sig, strength = "BUY",  "STRONG"
            elif score >= 7:  sig, strength = "BUY",  "MODERATE"
            elif score <= -10: sig, strength = "SELL", "STRONG"
            elif score <= -7: sig, strength = "SELL", "MODERATE"
            else:             sig, strength = "HOLD", "NEUTRAL"

        # ── Confidence formula (scaled to produce 55-90% for strong signals) ──
        # Base: signal strength (0-40%) + AMD confidence (0-30%) + base 25%
        # Strong signal (score ±12+) → ~75-90% confidence
        # Moderate signal (score ±6-11) → ~55-75% confidence
        # Weak signals (score ±1-5) → ~30-50% confidence (won't pass 55% gate anyway)
        _signal_pct = abs(score) / SignalEngine.MAX_SCORE * 40       # 0-40%
        _amd_pct    = amd.get("confidence", 50) / 100 * 30           # 0-30%
        _base_pct   = 25                                              # base 25%
        conf = min(95, max(20, int(_signal_pct + _amd_pct + _base_pct)))

        # ── Admin instruction influence (±2 score adjustment) ──────
        # Check if admin has given specific instructions for this signal
        try:
            admin_instrs = get_active_instructions()
            for inst in admin_instrs:
                inst_text = inst.get("text", "").lower()
                # If admin said "buy" for a symbol → boost buy score
                if "buy" in inst_text and score > 0:
                    score += 2
                    reasons.append(f"📌 Admin instruction boost: \"{inst['text'][:40]}\"")
                    break
                elif "sell" in inst_text and score < 0:
                    score += -2  # make score more negative = stronger sell
                    reasons.append(f"📌 Admin instruction boost: \"{inst['text'][:40]}\"")
                    break
                elif ("avoid" in inst_text or "band" in inst_text or
                      "stop" in inst_text or "mat" in inst_text):
                    # Admin wants to avoid trading → reduce score toward 0
                    score = int(score * 0.5)
                    reasons.append(f"📌 Admin caution: \"{inst['text'][:40]}\"")
                    break
        except Exception:
            pass  # Don't let instruction parsing break signal generation

        return {
            "signal":    sig,
            "strength":  strength,
            "score":     score,
            "confidence": conf,
            "reasons":   reasons[:6],
            "filtered":  False,
        }

    @staticmethod
    def entry_zone(df: pd.DataFrame, signal: str) -> dict:
        r = df.iloc[-1]
        p = r["close"]
        atr = r.get("atr", p * 0.001)
        if signal == "BUY":
            zone = f"{round(p - atr*0.3, 5)} – {round(p + atr*0.15, 5)}"
        elif signal == "SELL":
            zone = f"{round(p - atr*0.15, 5)} – {round(p + atr*0.3, 5)}"
        else:
            zone = "NO ENTRY"
        return {"current": round(p, 5), "zone": zone}


# ═════════════════════════════════════════════════════════════════════
# RISK MANAGEMENT ENGINE
# ═════════════════════════════════════════════════════════════════════
class RiskEngine:
    # Max spread as fraction of ATR, per asset class
    SPREAD_LIMITS = {
        "XAU": 0.0015,  # Gold: max 1.5 pips relative
        "XAG": 0.0020,
        "EUR": 0.0008,  "GBP": 0.0010,  "USD": 0.0008,
        "JPY": 0.0008,  "AUD": 0.0010,
        "BTC": 0.0050,  "ETH": 0.0050,
    }

    @staticmethod
    def calculate(df: pd.DataFrame, sig: dict, balance: float = 600.0,
                  risk_pct: float = 2.0, symbol: str = "") -> dict:
        if sig["signal"] == "HOLD":
            return {"verdict": "NO TRADE", "reason": "Signal HOLD — no position"}
        if sig.get("filtered"):
            return {"verdict": "NO TRADE", "reason": "ADX filter — ranging market, no edge"}

        r   = df.iloc[-1]
        cp  = float(r["close"])
        atr = max(float(r.get("atr", cp * 0.001)), cp * 0.0001)
        spread = float(r.get("spread", 0)) if "spread" in r.index else 0.0

        # Determine max spread for this asset
        asset_key = next((k for k in RiskEngine.SPREAD_LIMITS if symbol.startswith(k)), None)
        max_spread_frac = RiskEngine.SPREAD_LIMITS.get(asset_key, 0.0015)
        max_spread_abs  = cp * max_spread_frac

        spread_warning = ""
        if spread > max_spread_abs and spread > 0:
            spread_warning = f" | ⚠️ Wide spread ({spread:.5f} > max {max_spread_abs:.5f})"

        is_strong = sig.get("strength") == "STRONG"
        is_gold = symbol.upper().startswith("XAU")

        # ── Gold $10 SCALP optimizations ──────────────────────────────────
        # Gold (XAUUSD) responds well to tighter SL/TP with faster profit-taking.
        # Target: $10 per trade. 0.03 lot × 33 pips = $9.90 ($10).
        if is_gold and _GOLD_AGGRESSIVE_MODE:
            sl_mult   = 0.7 if is_strong else 0.9   # Very tight SL (82% WR = small SL OK)
            spread_buffer = spread * 2 if spread > 0 else atr * 0.03
            sl_d  = atr * sl_mult + spread_buffer
            tp1_d = atr * 1.5   # TP1 = 1.5×ATR  ($10 target — quick cash)
            tp2_d = atr * 2.5   # TP2 = 2.5×ATR  (bonus if runner continues)
            tp3_d = atr * 4.0   # TP3 = full runner (let it fly)
        else:
            sl_mult   = 1.0 if is_strong else 1.2   # Tight SL → smaller loss per trade
            # Spread-adjusted SL: add spread buffer so SL isn't hit by spread alone
            spread_buffer = spread * 2 if spread > 0 else atr * 0.05
            sl_d  = atr * sl_mult + spread_buffer
            tp1_d = atr * 2.5   # TP1 = 2.5×ATR  (R:R ~2.5:1)
            tp2_d = atr * 4.0   # TP2 = 4.0×ATR
            tp3_d = atr * 6.0   # TP3 for full runners

        if sig["signal"] == "BUY":
            sl, tp1, tp2, tp3 = cp - sl_d, cp + tp1_d, cp + tp2_d, cp + tp3_d
        else:
            sl, tp1, tp2, tp3 = cp + sl_d, cp - tp1_d, cp - tp2_d, cp - tp3_d

        rr1 = round(tp1_d / sl_d, 2)
        rr2 = round(tp2_d / sl_d, 2)

        # Reject if R:R at TP1 is below minimum (Gold = 1.5, others = 1.8)
        min_rr = 1.5 if is_gold else 1.8
        if rr1 < min_rr:
            return {
                "verdict": "NO TRADE",
                "reason": f"R:R {rr1} < {min_rr} minimum — profit too small vs risk (wide spread or tight ATR)",
            }

        conf_factor = sig["confidence"] / 100
        str_factor  = 1.2 if is_strong else 0.8
        kelly_mult  = sig.get("_kelly_multiplier", 1.0)  # ML Kelly boost (1.0-1.25×)
        pos_sz = round(min(5.0, max(0.3, risk_pct * conf_factor * str_factor * kelly_mult)), 1)
        risk_  = round(balance * risk_pct / 100, 2)

        level = (
            "VERY LOW"  if sig["confidence"] > 85 else
            "LOW"       if sig["confidence"] > 70 else
            "MEDIUM"    if sig["confidence"] > 55 else
            "HIGH"
        )

        return {
            "verdict":    "TRADE APPROVED",
            "stop_loss":  round(sl,  5),
            "tp1":        round(tp1, 5),
            "tp2":        round(tp2, 5),
            "tp3":        round(tp3, 5),
            "rr1":        f"1:{rr1}",
            "rr2":        f"1:{rr2}",
            "rr":         f"1:{rr1}",
            "pos_size":   f"{pos_sz}%",
            "risk_usd":   risk_,
            "atr":        round(atr, 5),
            "risk_level": level,
            "spread_note": spread_warning,
            "management": (
                f"🎯 At TP1 ({round(tp1,5)}): Move SL to breakeven | "
                f"At TP2 ({round(tp2,5)}): Trail SL by 1×ATR ({round(atr,5)}) | "
                f"TP3 ({round(tp3,5)}) = full runner target{spread_warning}"
            ),
        }


# ═════════════════════════════════════════════════════════════════════
# AGENT 8 — PATTERN MEMORY  (historical setup learning)
# ═════════════════════════════════════════════════════════════════════
class PatternMemoryAgent:
    """
    Learns from past bar data and previous prediction outcomes to:
    - Identify which session/time-of-day historically yields best results
    - Detect whether current setup is structurally similar to past winners
    - Flag over-extended moves (price too far from mean = reversal risk)
    - Measure volatility regime: expanding ATR vs contracting ATR
    - Provide a pattern confidence score (boosts or reduces signal confidence)
    """

    @staticmethod
    def analyze(
        symbol: str,
        df: pd.DataFrame,
        memory: "AgentMemory",
        tr: dict,
        amd: dict,
        liquidity: str,
    ) -> dict:
        now      = datetime.utcnow()
        hour_utc = now.hour
        dow      = now.strftime("%A")   # Monday … Sunday

        notes   = []
        p_score = 0   # Pattern confidence adjustment (–10 to +10)

        # ── 1. Session timing quality ─────────────────────────────────
        session_quality_map = {
            "PEAK":   ("🔥 PEAK session — operators most active, highest signal fidelity", +5),
            "HIGH":   ("✅ HIGH-liquidity session — good setup conditions",                +3),
            "MEDIUM": ("⚠️ MEDIUM liquidity — valid setups possible, raise SL buffer",     0),
            "LOW":    ("🌙 LOW liquidity — widen confirmation threshold, reduce size",     -5),
        }
        sq_note, sq_adj = session_quality_map.get(liquidity, ("", 0))
        p_score += sq_adj
        if sq_note:
            notes.append(sq_note)

        # ── 2. Price extension from mean (overextended = danger) ──────
        if len(df) >= 50:
            close   = df["close"].values
            mean50  = float(np.mean(close[-50:]))
            std50   = float(np.std(close[-50:]))
            cp      = close[-1]
            z_score = (cp - mean50) / std50 if std50 > 0 else 0
            if abs(z_score) > 2.0:
                direction = "above" if z_score > 0 else "below"
                notes.append(
                    f"⚠️ Price Z-score {z_score:+.1f} — {abs(z_score):.1f}σ {direction} 50-bar mean "
                    f"({mean50:.5f}) — OVEREXTENDED, reversion risk is elevated"
                )
                p_score -= 4
            elif abs(z_score) < 0.5:
                notes.append(
                    f"✅ Price near 50-bar mean (Z={z_score:+.2f}) — fair value entry zone, "
                    "low reversion risk"
                )
                p_score += 3

        # ── 3. ATR volatility regime ──────────────────────────────────
        if "atr" in df.columns and len(df) >= 20:
            atr_now  = float(df["atr"].iloc[-1])
            atr_mean = float(df["atr"].tail(20).mean())
            if atr_now > atr_mean * 1.5:
                notes.append(
                    f"📈 ATR EXPANDING ({atr_now:.5f} vs avg {atr_mean:.5f}) — "
                    "high volatility, breakout/momentum setups favoured"
                )
                p_score += 2
            elif atr_now < atr_mean * 0.6:
                notes.append(
                    f"📉 ATR CONTRACTING ({atr_now:.5f} vs avg {atr_mean:.5f}) — "
                    "low volatility, squeeze near → avoid chasing, wait for breakout"
                )
                p_score -= 2

        # ── 4. Volume profile ─────────────────────────────────────────
        if "vol_ratio" in df.columns:
            vol_r = float(df["vol_ratio"].iloc[-1])
            if vol_r > 1.8:
                notes.append(
                    f"🔊 Volume spike: {vol_r:.1f}× average — institutional activity detected, "
                    "confirms directional move"
                )
                p_score += 3
            elif vol_r < 0.5:
                notes.append(
                    f"🔇 Volume dry-up: {vol_r:.1f}× average — low conviction, "
                    "potential false move"
                )
                p_score -= 2

        # ── 5. Historical accuracy feedback ──────────────────────────
        stats = memory.stats(symbol)
        if stats["total"] >= 5:
            acc = stats["accuracy"]
            if acc >= 70:
                notes.append(
                    f"📚 Pattern memory: {acc}% win rate on {stats['total']} signals — "
                    f"STRONG historical edge on this symbol (×{stats['multiplier']:.2f} boost)"
                )
                p_score += 4
            elif acc >= 55:
                notes.append(
                    f"📚 Pattern memory: {acc}% accuracy — above-average edge "
                    f"({stats['correct']}/{stats['total']} correct)"
                )
                p_score += 2
            elif acc < 45:
                notes.append(
                    f"📚 Pattern memory: {acc}% accuracy ({stats['correct']}/{stats['total']}) — "
                    "BELOW 50%: agents applying caution penalty to confidence"
                )
                p_score -= 4

        # ── 6. AMD phase historical alignment ────────────────────────
        phase = amd.get("phase", "")
        phase_notes = {
            "ACCUMULATION": "📦 AMD: Accumulation phase — operators quietly building. Best entry for smart money longs.",
            "MANIPULATION": "⚡ AMD: Manipulation phase — liquidity sweep in progress. Wait for sweep confirmation before entry.",
            "DISTRIBUTION":  "🚀 AMD: Distribution phase — operators executing. Align with direction for highest-probability ride.",
            "TRANSITION":    "🔄 AMD: Transition phase — phase change in progress. Reduce size; setup not fully formed.",
        }
        if phase in phase_notes:
            notes.append(phase_notes[phase])
            if phase == "DISTRIBUTION":
                p_score += 3
            elif phase == "MANIPULATION":
                p_score += 1   # Good but risky — need confirmation
            elif phase == "TRANSITION":
                p_score -= 2

        # ── 7. Day-of-week bias ───────────────────────────────────────
        if dow == "Monday":
            notes.append("📅 Monday: Gap fills and false breakouts common — demand extra confirmation")
            p_score -= 1
        elif dow == "Friday":
            notes.append("📅 Friday: NY close risk — positions often squared, avoid late-day entries")
            p_score -= 2
        elif dow in ("Tuesday", "Wednesday", "Thursday"):
            notes.append(f"📅 {dow}: Mid-week — highest directional reliability historically")
            p_score += 1

        p_score = max(-10, min(10, p_score))   # Cap to ±10

        return {
            "pattern_score": p_score,
            "notes":         notes,
            "session_dow":   f"{dow} {hour_utc:02d}:xx UTC",
            "liquidity":     liquidity,
        }


# ═════════════════════════════════════════════════════════════════════
# AGENT 9 — OPERATOR MIND  (institutional-grade final validator)
# ═════════════════════════════════════════════════════════════════════
class OperatorMindAgent:
    """
    Simulates the thinking of a professional institutional operator.
    Reviews every signal through 6 institutional lenses:

    1. Premium/Discount: Is entry at fair value or chasing?
    2. Multi-timeframe alignment: H1 + H4 telling the same story?
    3. AMD phase → signal direction: Are operators backing this move?
    4. Spread / execution quality: Can we enter cleanly?
    5. Liquidity trap check: Is this a retail stop hunt, not a real move?
    6. Final verdict: APPROVE / CAUTION / REJECT + confidence adjustment
    """

    @staticmethod
    def evaluate(
        symbol:        str,
        sig:           dict,
        amd:           dict,
        smc:           dict,
        tr:            dict,
        h4_trend:      dict,
        spread:        float,
        sr:            dict,
        cp:            float,
        pattern:       dict,
        df:            pd.DataFrame,
        liquidity:     str,
    ) -> dict:
        signal    = sig.get("signal", "HOLD")
        score     = sig.get("score", 0)
        conf      = sig.get("confidence", 0)
        atr       = float(df["atr"].iloc[-1]) if "atr" in df.columns else cp * 0.001
        verdict   = "APPROVE"
        reasons   = []
        conf_adj  = 0     # Final confidence adjustment

        if signal == "HOLD":
            return {
                "verdict":    "NO TRADE",
                "reasons":    ["Signal is HOLD — operator has nothing to validate"],
                "conf_adj":   0,
                "final_conf": conf,
            }

        # ── 1. Premium / Discount analysis ────────────────────────────
        # A premium entry (buying at top of range) is poor operator practice.
        if len(df) >= 20:
            hi20 = float(df["high"].tail(20).max())
            lo20 = float(df["low"].tail(20).min())
            rng  = hi20 - lo20
            if rng > 0:
                pct_in_range = (cp - lo20) / rng
                if signal == "BUY" and pct_in_range > 0.75:
                    reasons.append(
                        f"⚠️ PREMIUM entry risk: price at {pct_in_range*100:.0f}% of 20-bar range "
                        f"({lo20:.5f}–{hi20:.5f}) — buying at top, operators prefer discount"
                    )
                    conf_adj -= 8
                    verdict   = "CAUTION"
                elif signal == "SELL" and pct_in_range < 0.25:
                    reasons.append(
                        f"⚠️ PREMIUM entry risk: price at {pct_in_range*100:.0f}% of 20-bar range "
                        f"— selling at bottom, operators prefer premium"
                    )
                    conf_adj -= 8
                    verdict   = "CAUTION"
                elif signal == "BUY" and pct_in_range < 0.35:
                    reasons.append(
                        f"✅ DISCOUNT entry: price at {pct_in_range*100:.0f}% of range "
                        "— buying at institutional discount zone"
                    )
                    conf_adj += 6
                elif signal == "SELL" and pct_in_range > 0.65:
                    reasons.append(
                        f"✅ PREMIUM sell: price at {pct_in_range*100:.0f}% of range "
                        "— selling at institutional premium zone"
                    )
                    conf_adj += 6

        # ── 2. Multi-timeframe confluence — MANDATORY H4+H1 ALIGNMENT ─
        h4_dir = (h4_trend or {}).get("direction", "SIDEWAYS")
        h1_dir = tr.get("direction", "SIDEWAYS")
        if h4_dir != "SIDEWAYS" and h4_dir == h1_dir:
            # ALIGNED — Big confidence boost (both timeframes agree)
            reasons.append(
                f"✅ H4+H1 ALIGNED ({h4_dir}) — institutional thesis confirmed, scalp WITH trend"
            )
            conf_adj += 10  # Boosted from 7 to 10 (alignment is the most important factor)
        elif h4_dir != "SIDEWAYS" and h4_dir != h1_dir:
            # CONFLICTING — REJECT (was just CAUTION — THIS was causing losses!)
            reasons.append(
                f"⛔ H4 ({h4_dir}) CONFLICTS H1 ({h1_dir}) — REJECTED. "
                f"Never scalp against H4 trend direction."
            )
            conf_adj -= 20  # Devastating penalty — kills the signal
            verdict = "REJECT"  # Hard REJECT, not soft CAUTION
        else:
            # H4 SIDEWAYS — allow but reduce conviction
            reasons.append(
                f"🔄 H4 sideways — no HTF bias. H1 ({h1_dir}) leads, lower conviction."
            )
            conf_adj -= 5  # Increased penalty (was -3)

        # ── 3. AMD direction alignment ────────────────────────────────
        phase = amd.get("phase", "")
        if phase == "DISTRIBUTION":
            amd_ok = (h1_dir == "BULLISH" and signal == "BUY") or \
                     (h1_dir == "BEARISH" and signal == "SELL")
            if amd_ok:
                reasons.append(
                    f"✅ AMD DISTRIBUTION aligned with signal ({signal}) — operators executing, join flow"
                )
                conf_adj += 8
            else:
                reasons.append(
                    f"⛔ AMD DISTRIBUTION conflicts signal: operators going {h1_dir} but signal is {signal}"
                )
                conf_adj  -= 12
                verdict    = "REJECT" if verdict != "REJECT" else verdict
        elif phase == "MANIPULATION":
            sweep = smc.get("sweep", {}).get("type", "")
            if sweep:
                reasons.append(
                    f"⚡ Manipulation sweep detected ({sweep}) — wait for sweep completion + "
                    "reversal candle before entry"
                )
                conf_adj -= 5
                if verdict == "APPROVE":
                    verdict = "CAUTION"
            else:
                reasons.append("⚡ Manipulation phase but no sweep confirmed — elevated false-signal risk")
                conf_adj -= 3
        elif phase == "ACCUMULATION":
            reasons.append(
                "📦 Accumulation phase — operators building. BUY entries have institutional backing; "
                "SELL entries are counter-institutional (higher risk)"
            )
            if signal == "BUY":
                conf_adj += 4
            else:
                conf_adj -= 5

        # ── 4. Spread quality check ───────────────────────────────────
        max_spread = atr * 0.25   # Max acceptable spread = 25% of ATR
        if spread > 0 and spread > max_spread:
            reasons.append(
                f"⚠️ Wide spread ({spread:.5f}) exceeds 25% ATR ({max_spread:.5f}) — "
                "execution cost erodes R:R, size down"
            )
            conf_adj -= 5
        elif spread > 0:
            reasons.append(f"✅ Spread OK ({spread:.5f}) — tight, clean execution possible")

        # ── 5. Liquidity trap detector ────────────────────────────────
        # If we just swept S/R and the signal is WITH the sweep direction,
        # it could be a retail trap (operators sweep liquidity then reverse)
        sweep = smc.get("sweep", {})
        if sweep:
            sweep_type = sweep.get("type", "")
            if "Bear Trap" in sweep_type and signal == "SELL":
                reasons.append(
                    "🪤 TRAP WARNING: Bear Trap sweep detected but signal is SELL — "
                    "this is the retail trap direction. Operators are likely reversing UP."
                )
                conf_adj -= 15
                verdict   = "REJECT"
            elif "Bull Trap" in sweep_type and signal == "BUY":
                reasons.append(
                    "🪤 TRAP WARNING: Bull Trap sweep detected but signal is BUY — "
                    "this is the retail trap direction. Operators are likely reversing DOWN."
                )
                conf_adj -= 15
                verdict   = "REJECT"
            elif "Bear Trap" in sweep_type and signal == "BUY":
                reasons.append(
                    "✅ Bear Trap confirmed and signal is BUY — aligning with operator reversal move"
                )
                conf_adj += 8
            elif "Bull Trap" in sweep_type and signal == "SELL":
                reasons.append(
                    "✅ Bull Trap confirmed and signal is SELL — aligning with operator reversal move"
                )
                conf_adj += 8

        # ── 6. Pattern memory quality adjustment ─────────────────────
        p_score = pattern.get("pattern_score", 0)
        conf_adj += int(p_score * 0.8)  # 80% weight of pattern score into final confidence
        if p_score >= 5:
            reasons.append(f"🧠 Pattern Memory: STRONG historical edge (score +{p_score}) — full confidence")
        elif p_score <= -5:
            reasons.append(f"🧠 Pattern Memory: WEAK setup history (score {p_score}) — operator reducing confidence")
            if verdict == "APPROVE":
                verdict = "CAUTION"

        # ── 7. Liquidity-based confidence adjustment ──────────────────
        if liquidity == "LOW":
            reasons.append(
                "🌙 Low liquidity session — operator reducing position size, widening SL buffer"
            )
            conf_adj -= 8
        elif liquidity == "PEAK":
            reasons.append("🔥 Peak liquidity — operators most active, highest execution quality")
            conf_adj += 5

        # ── Final confidence cap ──────────────────────────────────────
        final_conf = max(5, min(95, conf + conf_adj))

        # Operator REJECTS below confidence threshold (per-pair adaptive)
        _pair_gate = _get_effective_gate(symbol)
        if final_conf < _pair_gate and verdict != "REJECT":
            verdict = "REJECT"
            reasons.append(
                f"⛔ Final confidence {final_conf}% < {_pair_gate}% threshold for {symbol} — "
                "operator vetoes signal: insufficient conviction"
            )

        return {
            "verdict":    verdict,
            "conf_adj":   conf_adj,
            "final_conf": final_conf,
            "reasons":    reasons[:7],
        }


# ═════════════════════════════════════════════════════════════════════
# ─────────────────────  TEAM AGENT LOOP  ────────────────────────────
# ═════════════════════════════════════════════════════════════════════
# ═════════════════════════════════════════════════════════════════════
# SESSION FILTER + DRAWDOWN GUARD — BILLIONAIRE EDGE
# "Trade only when the HOUSE has the edge. Rest when it doesn't."
# ═════════════════════════════════════════════════════════════════════

def is_trading_session(symbol: str) -> tuple:
    """
    Check if current UTC hour is within the optimal trading session for this symbol.
    Returns (allowed: bool, session_name: str, reason: str)
    """
    if not _SESSION_FILTER_ENABLED:
        return True, "ALL", "Session filter disabled"

    from datetime import datetime
    hour = datetime.utcnow().hour

    sym_upper = symbol.upper()

    # Gold/Silver = London + NY only (7-21 UTC)
    if sym_upper.startswith(("XAU", "XAG")):
        sessions = _GOLD_SESSIONS_UTC
        name = "LONDON+NY"
    # Crypto = 24/7
    elif sym_upper.startswith(("BTC", "ETH")):
        sessions = _CRYPTO_SESSIONS_UTC
        name = "24/7"
    # Forex = London + NY
    else:
        sessions = _FOREX_SESSIONS_UTC
        name = "LONDON+NY"

    for start_h, end_h in sessions:
        if start_h <= hour < end_h:
            return True, name, f"Session active ({name}: {start_h}:00-{end_h}:00 UTC)"

    return False, name, f"Outside session ({name}) — current hour: {hour}:00 UTC"


def check_daily_drawdown() -> tuple:
    """
    Check if daily drawdown limit has been hit.
    Returns (trading_allowed: bool, drawdown_pct: float, message: str)

    Billionaire Rule: "Capital preservation > profit. Live to trade tomorrow."
    """
    global _DAILY_STARTING_BALANCE, _TRADING_HALTED_TODAY

    if not MT5_AVAILABLE:
        return True, 0.0, "MT5 not available — no drawdown check"

    try:
        account = mt5.account_info()
        if account is None:
            return True, 0.0, "No account info"

        current_balance = account.balance
        current_equity  = account.equity
        today_str = datetime.utcnow().strftime("%Y-%m-%d")

        # Reset at start of new day
        if _daily_trade_counts.get("date") != today_str:
            _DAILY_STARTING_BALANCE = current_balance
            _TRADING_HALTED_TODAY = False
            _daily_trade_counts["date"] = today_str
            _daily_trade_counts["count"] = 0
            logger.info(f"📅 New trading day — starting balance: ${current_balance:.2f}")

        # First cycle of the day
        if _DAILY_STARTING_BALANCE <= 0:
            _DAILY_STARTING_BALANCE = current_balance

        # Calculate drawdown from daily start
        drawdown = _DAILY_STARTING_BALANCE - min(current_balance, current_equity)
        drawdown_pct = (drawdown / _DAILY_STARTING_BALANCE * 100) if _DAILY_STARTING_BALANCE > 0 else 0

        if drawdown_pct >= _DAILY_DRAWDOWN_LIMIT_PCT:
            _TRADING_HALTED_TODAY = True
            return False, drawdown_pct, (
                f"⛔ DAILY DRAWDOWN LIMIT HIT: {drawdown_pct:.1f}% "
                f"(limit: {_DAILY_DRAWDOWN_LIMIT_PCT}%) — "
                f"Started: ${_DAILY_STARTING_BALANCE:.2f} → Now: ${current_equity:.2f} — "
                f"ALL TRADING HALTED until tomorrow"
            )

        return True, drawdown_pct, f"Drawdown: {drawdown_pct:.1f}% (limit: {_DAILY_DRAWDOWN_LIMIT_PCT}%)"

    except Exception as e:
        logger.warning(f"Drawdown check error: {e}")
        return True, 0.0, f"Error: {e}"


def check_pyramid_allowed(symbol: str, direction: str) -> tuple:
    """
    Check if pyramiding (adding to winning position) is allowed.
    Returns (allowed: bool, reason: str)

    Billionaire Strategy: "Add to winners, cut losers."
    Only pyramid if existing position is already profitable (> 30% toward TP).
    """
    if not MT5_AVAILABLE:
        return False, "MT5 not available"

    try:
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            return True, "No existing position — fresh entry allowed"

        # Check if any existing position in SAME direction is in profit
        profitable_count = 0
        for pos in positions:
            if pos.comment != "AI_SWARM_AGENT":
                continue

            is_buy = pos.type == 0
            pos_dir = "BUY" if is_buy else "SELL"

            # Only pyramid in same direction
            if pos_dir != direction.upper():
                continue

            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                continue

            current = tick.bid if is_buy else tick.ask
            entry = pos.price_open
            tp = pos.tp

            if tp == 0:
                continue

            # Calculate progress toward TP
            if is_buy:
                total = tp - entry
                progress = (current - entry) / total if total > 0 else 0
            else:
                total = entry - tp
                progress = (entry - current) / total if total > 0 else 0

            if progress >= _PYRAMID_PROFIT_THRESHOLD:
                profitable_count += 1

        if profitable_count > 0:
            return True, f"✅ Pyramid OK — {profitable_count} position(s) in profit (>{_PYRAMID_PROFIT_THRESHOLD:.0%} toward TP)"
        else:
            # Existing positions not yet profitable enough — use normal cooldown
            return False, "Existing positions not yet profitable enough for pyramid"

    except Exception as e:
        logger.warning(f"⚠️ Pyramid check error: {e} — BLOCKING entry for safety")
        return False, f"Pyramid check error: {e} — blocking entry for safety"


# ═════════════════════════════════════════════════════════════════════
# MT5 LIVE TRADE EXECUTION LAYER
# Fires when Operator Mind approves a signal at >= _MIN_EXECUTION_CONFIDENCE
# ═════════════════════════════════════════════════════════════════════

def _sync_execute_mt5_trade(symbol: str, direction: str,
                             stop_loss: float, take_profit: float,
                             risk_pos_size: float = 0.0) -> dict:
    """
    Place a real MT5 market order directly via mt5.order_send().
    Uses DYNAMIC lot sizing based on RiskEngine's confidence-adjusted position size.
    Falls back to _FIXED_LOT_SIZE (0.01) if risk_pos_size not provided.

    risk_pos_size: % of balance to risk (e.g., 1.2 means 1.2%)

    Returns {success, ticket, price, volume} on success
            {success=False, error} on failure.
    """
    if not MT5_AVAILABLE:
        return {"success": False, "error": "MetaTrader5 package not installed"}

    try:
        # ── Symbol info ──────────────────────────────────────────────
        sym_info = mt5.symbol_info(symbol)
        if sym_info is None:
            err = mt5.last_error()
            return {"success": False, "error": f"Symbol {symbol} not found — MT5 error: {err}"}

        if not sym_info.visible:
            mt5.symbol_select(symbol, True)

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            err = mt5.last_error()
            return {"success": False, "error": f"No tick data for {symbol} — {err}"}

        # ── Price + DYNAMIC lot sizing ──────────────────────────────
        direction_up = direction.upper()
        price  = tick.ask if direction_up == "BUY" else tick.bid

        # Dynamic lot calculation based on RiskEngine's recommended position size
        min_lot  = float(sym_info.volume_min)
        max_lot  = float(sym_info.volume_max)
        lot_step = float(sym_info.volume_step)

        if risk_pos_size > 0 and stop_loss > 0:
            # Calculate lots from risk %: risk_amount / (SL distance in account currency)
            try:
                account = mt5.account_info()
                if account:
                    risk_amount = account.balance * (risk_pos_size / 100)
                    sl_dist_price = abs(price - stop_loss)
                    if sl_dist_price > 0:
                        # For forex: 1 standard lot = 100,000 units
                        # pip_value ≈ trade_tick_value / trade_tick_size * lot_step
                        tick_val  = float(sym_info.trade_tick_value)
                        tick_size = float(sym_info.trade_tick_size)
                        if tick_val > 0 and tick_size > 0:
                            value_per_lot_per_point = tick_val / tick_size
                            raw_lots = risk_amount / (sl_dist_price * value_per_lot_per_point)
                            # Round DOWN to nearest lot_step
                            lots = max(min_lot, min(max_lot, round(raw_lots / lot_step) * lot_step))
                            lots = round(lots, 2)
                            logger.info(f"📐 Dynamic lot: risk={risk_pos_size:.1f}% → ${risk_amount:.2f} risk → {lots} lots (SL dist={sl_dist_price:.5f})")
                        else:
                            lots = _FIXED_LOT_SIZE
                            logger.warning(f"⚠️ tick_val/tick_size invalid, using fixed lot {lots}")
                    else:
                        lots = _FIXED_LOT_SIZE
                else:
                    lots = _FIXED_LOT_SIZE
            except Exception as e:
                lots = _FIXED_LOT_SIZE
                logger.warning(f"⚠️ Dynamic lot calc error: {e}, using fixed {lots}")
        else:
            lots = _FIXED_LOT_SIZE  # Fallback to fixed 0.01

        if lots < min_lot:
            lots = min_lot

        # FIXED: Hard cap lot size at 0.01 — ALWAYS trade 0.01 lot only
        lots = 0.01

        # ── Filling mode (broker-safe) ───────────────────────────────
        fm = sym_info.filling_mode
        if fm & 1:
            filling = mt5.ORDER_FILLING_FOK
        elif fm & 2:
            filling = mt5.ORDER_FILLING_IOC
        else:
            filling = mt5.ORDER_FILLING_RETURN

        # ── Order type ───────────────────────────────────────────────
        digits   = sym_info.digits
        mt5_type = mt5.ORDER_TYPE_BUY if direction_up == "BUY" else mt5.ORDER_TYPE_SELL

        # ── Validate stops level (fix retcode 10016 "Invalid stops") ──
        # Broker requires minimum distance between price and SL/TP
        stops_level = float(sym_info.trade_stops_level)  # In points
        point = float(sym_info.point)
        min_dist = stops_level * point
        if min_dist <= 0:
            min_dist = point * 50  # Safe default: 50 points

        # Ensure SL is far enough from price
        sl_dist = abs(price - stop_loss)
        if sl_dist < min_dist:
            # Push SL further out to meet minimum distance
            if direction_up == "BUY":
                stop_loss = price - min_dist - (point * 10)  # Extra buffer
            else:
                stop_loss = price + min_dist + (point * 10)
            logger.warning(f"⚠️ {symbol}: SL too close ({sl_dist:.5f} < {min_dist:.5f}) — adjusted to {stop_loss:.{digits}f}")

        # Ensure TP is far enough from price
        tp_dist = abs(price - take_profit)
        if tp_dist < min_dist:
            if direction_up == "BUY":
                take_profit = price + min_dist + (point * 10)
            else:
                take_profit = price - min_dist - (point * 10)
            logger.warning(f"⚠️ {symbol}: TP too close ({tp_dist:.5f} < {min_dist:.5f}) — adjusted to {take_profit:.{digits}f}")

        # ── Spread check at execution time ──
        exec_tick = mt5.symbol_info_tick(symbol)
        if exec_tick:
            exec_spread = exec_tick.ask - exec_tick.bid
            sl_dist = abs(price - stop_loss)
            # Spread must not exceed 20% of SL distance (balanced for multi-market)
            if sl_dist > 0 and exec_spread > sl_dist * 0.20:
                return {
                    "success": False,
                    "error": (
                        f"SPREAD TOO WIDE at execution: {exec_spread:.{digits}f} > "
                        f"25% of SL distance ({sl_dist * 0.25:.{digits}f}) — "
                        f"R:R destroyed, skipping"
                    ),
                }

        request = {
            "action":      mt5.TRADE_ACTION_DEAL,
            "symbol":      symbol,
            "volume":      lots,
            "type":        mt5_type,
            "price":       round(price,       digits),
            "sl":          round(stop_loss,   digits),
            "tp":          round(take_profit, digits),
            "deviation":   20,
            "magic":       234001,
            "comment":     "AI_SWARM_AGENT",
            "type_time":   mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        result = mt5.order_send(request)

        if result is None:
            err = mt5.last_error()
            return {"success": False, "error": f"order_send returned None — MT5: {err}"}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {
                "success": False,
                "error":   f"retcode {result.retcode} — {result.comment}",
                "retcode": result.retcode,
            }

        logger.info(
            f"✅ LIVE TRADE: {direction_up} {lots}L {symbol} "
            f"@ {result.price} | SL:{stop_loss} TP:{take_profit} "
            f"| Ticket #{result.order}"
        )
        return {
            "success": True,
            "ticket":  result.order,
            "price":   result.price,
            "volume":  result.volume,
            "symbol":  symbol,
            "type":    direction_up,
            "sl":      stop_loss,
            "tp":      take_profit,
        }

    except Exception as exc:
        logger.error(f"MT5 execution exception [{symbol}]: {exc}", exc_info=True)
        return {"success": False, "error": str(exc)}


def _sync_get_open_positions() -> dict:
    """Return {ticket: symbol} for all currently open MT5 positions."""
    if not MT5_AVAILABLE:
        return {}
    try:
        positions = mt5.positions_get()
        if not positions:
            return {}
        return {str(p.ticket): p.symbol for p in positions}
    except Exception:
        return {}


def _calculate_dollar_based_sl_tp(symbol: str, direction: str, entry_price: float,
                                    sl_usd: float, tp_usd: float, lots: float) -> tuple:
    """
    Calculate SL and TP prices based on FIXED DOLLAR amounts.
    Returns (stop_loss_price, take_profit_price).

    Uses MT5 tick_value to convert $ → price distance.
    Formula: price_distance = dollar_amount / (lots * tick_value / tick_size)
    """
    try:
        sym_info = mt5.symbol_info(symbol)
        if not sym_info:
            return None, None

        tick_val  = float(sym_info.trade_tick_value)   # Value of 1 tick in account currency
        tick_size = float(sym_info.trade_tick_size)     # Smallest price change
        digits    = sym_info.digits

        if tick_val <= 0 or tick_size <= 0 or lots <= 0:
            return None, None

        # Price distance per $1 = tick_size / (tick_value * lots)
        # So for $X: distance = X * tick_size / (tick_value * lots)
        value_per_point = tick_val / tick_size  # Dollar value per 1.0 price unit per 1 lot
        sl_distance = sl_usd / (value_per_point * lots)
        tp_distance = tp_usd / (value_per_point * lots)

        if direction.upper() == "BUY":
            sl_price = round(entry_price - sl_distance, digits)
            tp_price = round(entry_price + tp_distance, digits)
        else:
            sl_price = round(entry_price + sl_distance, digits)
            tp_price = round(entry_price - tp_distance, digits)

        logger.info(
            f"💰 DOLLAR-BASED SL/TP: {symbol} {direction} @ {entry_price:.{digits}f} | "
            f"SL=${sl_usd} → {sl_distance:.{digits}f} distance → {sl_price:.{digits}f} | "
            f"TP=${tp_usd} → {tp_distance:.{digits}f} distance → {tp_price:.{digits}f} | "
            f"Lots: {lots}"
        )
        return sl_price, tp_price

    except Exception as e:
        logger.error(f"Dollar-based SL/TP calc error: {e}")
        return None, None


async def mt5_execute_trade(team: str, symbol: str, sig: dict, risk: dict) -> dict:
    """Async wrapper — runs blocking MT5 call in thread-pool executor.
    Uses FIXED DOLLAR-BASED SL/TP: $40 SL, $110 TP."""
    # ── Anti-Martingale check ──────────────────────────────────────
    loss_mult = get_loss_streak_multiplier()
    if loss_mult <= 0.0:
        return {"success": False, "error": f"Anti-Martingale: trading paused after {_consecutive_losses} consecutive losses"}

    loop = asyncio.get_event_loop()

    # ── DOLLAR-BASED OVERRIDE ──────────────────────────────────────
    # Calculate SL/TP based on $40 loss / $110 profit targets
    # First get the entry price to calculate dollar-based levels
    def _execute_with_dollar_sl_tp():
        if not MT5_AVAILABLE:
            return {"success": False, "error": "MT5 not available"}

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return {"success": False, "error": f"No tick data for {symbol}"}

        direction = sig["signal"]
        entry_price = tick.ask if direction.upper() == "BUY" else tick.bid
        lots = 0.01  # ALWAYS 0.01 lot — no exceptions

        # Calculate dollar-based SL and TP
        sl_price, tp_price = _calculate_dollar_based_sl_tp(
            symbol, direction, entry_price,
            sl_usd=_FIXED_SL_USD,   # $40 stop loss
            tp_usd=_FIXED_TP_USD,   # $110 take profit
            lots=lots
        )

        if sl_price is None or tp_price is None:
            # Fallback to RiskEngine values if dollar calc fails
            logger.warning(f"⚠️ Dollar-based SL/TP failed for {symbol}, using RiskEngine values")
            sl_price = risk.get("stop_loss", 0)
            tp_key = "tp1" if _USE_TP1_FOR_EXECUTION else "tp2"
            tp_price = risk.get(tp_key, risk.get("tp2", risk.get("tp1", 0)))

        return _sync_execute_mt5_trade(
            symbol, direction, sl_price, tp_price,
            risk_pos_size=0  # Use fixed lot, not dynamic
        )

    return await loop.run_in_executor(executor, _execute_with_dollar_sl_tp)


async def mt5_sync_open_positions():
    """Async wrapper to refresh which symbols are still open in MT5."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _sync_get_open_positions)


# ═════════════════════════════════════════════════════════════════════
# TRAILING STOP MANAGER — Move SL to breakeven when in profit
# Protects profits on open trades by trailing the stop-loss
# ═════════════════════════════════════════════════════════════════════

def _sync_manage_trailing_stops():
    """
    DOLLAR-BASED TRAILING STOP MANAGER:
    Rule 1: At $30 profit → move SL to lock $10 profit
    Rule 2: At $60 profit → move SL to lock $30 profit
    Rule 3: At $90 profit → move SL to lock $60 profit
    TP stays at $110.
    Returns list of modified tickets.
    """
    if not MT5_AVAILABLE:
        return []

    modified = []
    try:
        positions = mt5.positions_get()
        if not positions:
            return []

        for pos in positions:
            if pos.comment != "AI_SWARM_AGENT":
                continue  # Only manage our AI trades

            ticket = pos.ticket
            symbol = pos.symbol
            entry  = pos.price_open
            sl     = pos.sl
            tp     = pos.tp
            volume = pos.volume
            profit = pos.profit  # Current unrealized P&L in account currency ($)
            is_buy = pos.type == 0  # 0 = BUY, 1 = SELL

            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                continue

            sym_info = mt5.symbol_info(symbol)
            if not sym_info:
                continue

            digits    = sym_info.digits
            tick_val  = float(sym_info.trade_tick_value)
            tick_size = float(sym_info.trade_tick_size)

            if tick_val <= 0 or tick_size <= 0 or volume <= 0:
                continue

            # Calculate price distance for a given dollar amount
            value_per_point = tick_val / tick_size
            def dollar_to_distance(usd_amount):
                return usd_amount / (value_per_point * volume)

            # ── DOLLAR-BASED TRAILING RULES ────────────────────────────
            # Determine new SL based on current profit level
            new_sl = None
            trail_reason = ""

            if profit >= 90.0:
                # Lock $60 profit
                lock_dist = dollar_to_distance(60.0)
                if is_buy:
                    new_sl = round(entry + lock_dist, digits)
                else:
                    new_sl = round(entry - lock_dist, digits)
                trail_reason = f"$90+ profit → locking $60 (SL at +$60)"

            elif profit >= 60.0:
                # Lock $30 profit
                lock_dist = dollar_to_distance(30.0)
                if is_buy:
                    new_sl = round(entry + lock_dist, digits)
                else:
                    new_sl = round(entry - lock_dist, digits)
                trail_reason = f"$60+ profit → locking $30 (SL at +$30)"

            elif profit >= _LOCK_PROFIT_TRIGGER_USD:  # $30
                # Lock $10 profit (Sumit's core rule)
                lock_dist = dollar_to_distance(_LOCK_PROFIT_SL_USD)  # $10
                if is_buy:
                    new_sl = round(entry + lock_dist, digits)
                else:
                    new_sl = round(entry - lock_dist, digits)
                trail_reason = f"${profit:.0f} profit → locking ${_LOCK_PROFIT_SL_USD:.0f} (SL at +${_LOCK_PROFIT_SL_USD:.0f})"

            if new_sl is None:
                continue

            # Check if new SL is better than current
            if is_buy:
                if sl >= new_sl:
                    continue  # SL already at or above new level
            else:
                if sl != 0 and sl <= new_sl:
                    continue  # SL already tighter

            # Modify the position
            request = {
                "action":    mt5.TRADE_ACTION_SLTP,
                "position":  ticket,
                "symbol":    symbol,
                "sl":        new_sl,
                "tp":        tp,  # Keep TP unchanged at $110
            }
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                modified.append({
                    "ticket": ticket,
                    "symbol": symbol,
                    "old_sl": sl,
                    "new_sl": new_sl,
                    "progress": trail_reason,
                    "current_profit": f"${profit:.2f}",
                })
                logger.info(
                    f"🔒 DOLLAR TRAIL: {symbol} #{ticket} — "
                    f"{trail_reason} | SL: {sl} → {new_sl} | Profit: ${profit:.2f}"
                )

    except Exception as e:
        logger.warning(f"Trailing stop manager error: {e}")

    return modified


async def manage_trailing_stops():
    """Async wrapper for trailing stop management."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _sync_manage_trailing_stops)


# ═════════════════════════════════════════════════════════════════════
# PARTIAL TAKE PROFIT MANAGER — Close 50% at TP1, let rest run to TP2
# Billionaire Rule: "Lock profits at TP1, let runners ride to TP2/TP3"
# ═════════════════════════════════════════════════════════════════════
_partial_tp_done: set = set()  # Track tickets that already had partial close


def _sync_manage_partial_tp() -> list:
    """
    When price reaches TP1 zone (within 5% of TP), close 50% of position.
    Then update the TP on remaining volume to TP2 (stored in comment or system state).

    Returns list of partial closes executed.
    """
    if not MT5_AVAILABLE:
        return []

    partials = []
    try:
        positions = mt5.positions_get()
        if not positions:
            return []

        for pos in positions:
            if pos.comment != "AI_SWARM_AGENT":
                continue
            if pos.ticket in _partial_tp_done:
                continue  # Already partial-closed

            ticket = pos.ticket
            symbol = pos.symbol
            entry  = pos.price_open
            tp     = pos.tp
            volume = pos.volume
            is_buy = pos.type == 0

            if tp == 0.0 or volume <= 0.01:
                continue  # No TP or too small to split

            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                continue

            current = tick.bid if is_buy else tick.ask
            sym_info = mt5.symbol_info(symbol)
            if not sym_info:
                continue

            digits  = sym_info.digits
            min_lot = float(sym_info.volume_min)
            lot_step = float(sym_info.volume_step)

            # Calculate progress toward TP
            if is_buy:
                total_dist = tp - entry
                current_dist = current - entry
            else:
                total_dist = entry - tp
                current_dist = entry - current

            if total_dist <= 0:
                continue

            progress = current_dist / total_dist

            # TP1 zone reached (>= 90% toward TP — because TP is already set to TP1)
            if progress >= 0.90 and volume >= min_lot * 2:
                # Close 50% of the position
                close_vol = round((volume * 0.5) / lot_step) * lot_step
                close_vol = max(min_lot, close_vol)
                remain_vol = round((volume - close_vol) / lot_step) * lot_step

                if close_vol < min_lot or remain_vol < min_lot:
                    continue  # Can't split meaningfully

                # Determine filling mode
                fm = sym_info.filling_mode
                if fm & 1:
                    filling = mt5.ORDER_FILLING_FOK
                elif fm & 2:
                    filling = mt5.ORDER_FILLING_IOC
                else:
                    filling = mt5.ORDER_FILLING_RETURN

                # Partial close order
                close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
                close_price = tick.bid if is_buy else tick.ask

                close_req = {
                    "action":      mt5.TRADE_ACTION_DEAL,
                    "symbol":      symbol,
                    "volume":      close_vol,
                    "type":        close_type,
                    "position":    ticket,
                    "price":       round(close_price, digits),
                    "deviation":   20,
                    "magic":       234001,
                    "comment":     "AI_PARTIAL_TP1",
                    "type_filling": filling,
                }

                result = mt5.order_send(close_req)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    _partial_tp_done.add(ticket)
                    # NOTE: Do NOT record_trade_result here — TP1 is partial profit.
                    # The final close (remaining lots at TP2 or SL) will be the real outcome.
                    # Recording partial as WIN + final as LOSS = conflicting data that poisons ML.
                    _tp_dir = "BUY" if is_buy else "SELL"
                    logger.info(f"📊 Partial TP1 profit — NOT recording as trade result (wait for final close)")
                    partials.append({
                        "ticket": ticket,
                        "symbol": symbol,
                        "closed_vol": close_vol,
                        "remain_vol": remain_vol,
                        "close_price": close_price,
                        "progress": f"{progress:.0%}",
                    })
                    logger.info(
                        f"💰 PARTIAL TP1: {symbol} #{ticket} — closed {close_vol} lots "
                        f"at {close_price} ({progress:.0%} to TP), remaining {remain_vol} lots running"
                    )

    except Exception as e:
        logger.warning(f"Partial TP manager error: {e}")

    return partials


async def manage_partial_tp():
    """Async wrapper for partial take profit management."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _sync_manage_partial_tp)


# ═════════════════════════════════════════════════════════════════════
# CLOSED TRADE MONITOR — Track wins/losses for anti-martingale
# ═════════════════════════════════════════════════════════════════════
_last_checked_deals_time: float = 0.0
_processed_deal_tickets: set = set()  # Dedup: track already-processed deal tickets


def _sync_check_closed_trades():
    """Check recently closed trades and update anti-martingale tracker."""
    global _last_checked_deals_time
    if not MT5_AVAILABLE:
        return

    try:
        import time
        now = time.time()
        # Check every 60 seconds
        if now - _last_checked_deals_time < 60:
            return
        _last_checked_deals_time = now

        # Get deals from last 10 minutes (widened from 2min to prevent missed closures)
        from_time = datetime.utcnow() - timedelta(minutes=10)
        deals = mt5.history_deals_get(from_time, datetime.utcnow())
        if not deals:
            return

        for deal in deals:
            if deal.comment and "AI_SWARM_AGENT" in deal.comment:
                if deal.entry == 1:  # Exit deal (close)
                    # Dedup: skip if already processed this deal ticket
                    if deal.ticket in _processed_deal_tickets:
                        continue
                    _processed_deal_tickets.add(deal.ticket)
                    # Keep set bounded (max 500 entries)
                    if len(_processed_deal_tickets) > 500:
                        _processed_deal_tickets.clear()

                    is_win = deal.profit > 0
                    _deal_dir = "BUY" if deal.type == 0 else "SELL"
                    _deal_sym = deal.symbol
                    record_trade_result(is_win, symbol=_deal_sym, direction=_deal_dir)

                    # TRAINING: Record outcome for self-learning
                    if TRAINING_AVAILABLE:
                        try:
                            TrainingEngine.record_outcome(
                                symbol=_deal_sym, direction=_deal_dir,
                                is_win=is_win, pnl=deal.profit
                            )
                            logger.info(f"🎓 Training outcome recorded: {_deal_dir} {_deal_sym} → {'WIN' if is_win else 'LOSS'} ${deal.profit:.2f}")
                        except Exception as _te:
                            logger.debug(f"Training outcome error: {_te}")

                    logger.info(
                        f"{'✅' if is_win else '❌'} Closed {_deal_dir} {_deal_sym} #{deal.order}: "
                        f"P&L: ${deal.profit:.2f} — agents {'rewarded' if is_win else 'penalized'} + training updated"
                    )
    except Exception as e:
        logger.warning(f"Closed trade monitor error: {e}")


async def check_closed_trades():
    """Async wrapper."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _sync_check_closed_trades)


# ═════════════════════════════════════════════════════════════════════
# ADMIN CHAT SYSTEM  — 2-way communication between Admin ↔ AI Agents
# ═════════════════════════════════════════════════════════════════════
ADMIN_INSTRUCTIONS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "admin_instructions.json"
)

# In-memory store of admin instructions (persisted to JSON file)
_admin_instructions: List[dict] = []

def _load_admin_instructions():
    """Load admin instructions from disk on startup."""
    global _admin_instructions
    try:
        if os.path.exists(ADMIN_INSTRUCTIONS_FILE):
            with open(ADMIN_INSTRUCTIONS_FILE, "r", encoding="utf-8") as f:
                _admin_instructions = json.load(f)
            logger.info(f"📋 Loaded {len(_admin_instructions)} admin instructions from disk")
    except Exception as e:
        logger.warning(f"Admin instructions load error: {e}")
        _admin_instructions = []

def _save_admin_instructions():
    """Persist admin instructions to disk using atomic writes."""
    try:
        # Atomic write: temp file + os.replace() prevents corruption on crash
        json_str = json.dumps(_admin_instructions[-200:], indent=2)
        dir_path = os.path.dirname(ADMIN_INSTRUCTIONS_FILE)
        with tempfile.NamedTemporaryFile('w', dir=dir_path, delete=False,
                                          suffix='.tmp', encoding='utf-8') as tmp:
            tmp.write(json_str)
            tmp.flush()
            os.fsync(tmp.fileno())
        try:
            os.replace(tmp.name, ADMIN_INSTRUCTIONS_FILE)
        except (OSError, PermissionError):
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
            with open(ADMIN_INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
                f.write(json_str)
                f.flush()
                os.fsync(f.fileno())
    except Exception as e:
        logger.warning(f"Admin instructions save error: {e}")
        try:
            if 'tmp' in locals() and os.path.exists(tmp.name):
                os.unlink(tmp.name)
        except Exception:
            pass

def get_active_instructions(team: str = None, symbol: str = None) -> List[dict]:
    """Get active (non-expired) instructions, optionally filtered by team/symbol."""
    active = [i for i in _admin_instructions if i.get("active", True)]
    if team:
        active = [i for i in active
                  if i.get("target_team") in (team, "ALL", None)]
    if symbol:
        active = [i for i in active
                  if i.get("target_symbol") is None or
                     i.get("target_symbol", "").upper() == symbol.upper()]
    return active


async def _handle_admin_chat(msg: dict):
    """
    🧠 CLAUDE AI-POWERED chat handler — each agent THINKS using Claude AI.
    Agents have memory, learn from conversations, and search the internet for market data.
    Falls back to hardcoded responses if AI Brain is unavailable.
    """
    try:
        text   = msg.get("text", "").strip()
        target = msg.get("target", "ALL").upper()
        if not text:
            return

        logger.info(f"💬 Processing admin chat: '{text}' → {target}")
        text_lower = text.lower()

        # ── Show admin's message in feed ──────────────────────────────────
        await emit("ADMIN", "You (Admin)", "admin",
            f"💬 ADMIN → {target}: {text}",
            {"chat": True, "target": target, "text": text})

        # ── Detect mentioned symbols ──────────────────────────────────────
        mentioned_syms = []
        for tcfg in TEAMS.values():
            for sym in tcfg["symbols"]:
                if sym.lower() in text_lower or sym.lower().replace("usd","") in text_lower:
                    mentioned_syms.append(sym)
        name_map = {"gold": "XAUUSD", "silver": "XAGUSD", "bitcoin": "BTCUSD",
                     "btc": "BTCUSD", "eth": "ETHUSD", "ethereum": "ETHUSD",
                     "euro": "EURUSD", "pound": "GBPUSD", "yen": "USDJPY",
                     "swiss": "USDCHF", "chf": "USDCHF", "franc": "USDCHF",
                     "aussie": "AUDUSD", "aud": "AUDUSD", "cad": "USDCAD",
                     "kiwi": "NZDUSD", "nzd": "NZDUSD",
                     "beast": "GBPJPY", "eurjpy": "EURJPY", "eurgbp": "EURGBP",
                     "sona": "XAUUSD", "chandi": "XAGUSD"}
        for name, sym in name_map.items():
            if name in text_lower and sym not in mentioned_syms:
                mentioned_syms.append(sym)

        # ── Determine teams to respond ────────────────────────────────────
        teams_to_reply = [target] if target in TEAMS else list(TEAMS.keys())

        # ── COMMAND: train agents ─────────────────────────────────────────
        if any(kw in text_lower for kw in ["train", "training", "learn", "sikh",
                                             "seekh", "improve", "upgrade", "update knowledge"]):
            if AI_BRAIN_AVAILABLE:
                await emit("ADMIN", "AdminAgent", "admin",
                    "🎓 Training command received! Sabhi agents ko internet se train kar raha hoon...",
                    {"chat_reply": True})
                # Run training in background so chat doesn't block
                if target in TEAMS:
                    asyncio.create_task(train_agent_on_sector(target, emit_fn=emit))
                else:
                    asyncio.create_task(run_full_training(emit_fn=emit))
            else:
                await emit("ADMIN", "AdminAgent", "error",
                    "⚠️ AI Brain not available — training requires Gemini API.",
                    {"chat_reply": True})
            return

        # ── COMMAND: training status ──────────────────────────────────────
        if any(kw in text_lower for kw in ["training status", "kya seekha", "knowledge",
                                             "kya jaante", "trained", "training report"]):
            if AI_BRAIN_AVAILABLE:
                status = get_training_status()
                insights = status.get("latest_insights", {})
                sessions = status.get("training_sessions", {})
                await emit("ADMIN", "AdminAgent", "admin",
                    f"🎓 TRAINING STATUS:\n"
                    f"  Running: {'✅ Haan' if status['is_running'] else '❌ Nahi'}\n"
                    f"  Last training: {status['last_training'] or 'Not yet'}\n"
                    f"  Total learnings: {status['total_learnings']}\n"
                    f"  Sessions — METALS: {sessions.get('METALS', 0)} | "
                    f"FOREX: {sessions.get('FOREX', 0)} | CRYPTO: {sessions.get('CRYPTO', 0)}\n\n"
                    f"📊 Latest Insights:\n"
                    f"  🥇 METALS: {insights.get('METALS', 'No data')[:150]}\n"
                    f"  💱 FOREX: {insights.get('FOREX', 'No data')[:150]}\n"
                    f"  🪙 CRYPTO: {insights.get('CRYPTO', 'No data')[:150]}",
                    {"chat_reply": True})
            else:
                await emit("ADMIN", "AdminAgent", "error",
                    "⚠️ AI Brain not available.", {"chat_reply": True})
            return

        # ── COMMAND: clear / reset ────────────────────────────────────────
        if any(kw in text_lower for kw in ["clear instruction", "reset instruction",
                                             "sab hatao", "instructions delete"]):
            count = len(_admin_instructions)
            _admin_instructions.clear()
            _save_admin_instructions()
            await emit("ADMIN", "OperatorMind", "signal",
                f"🗑️ Done! {count} instructions cleared. Agents ab default behaviour pe hain.",
                {"chat_reply": True})
            return

        # ── INSTRUCTION: save as a rule for agents ────────────────────────
        instr_words = ["sikhao", "sikho", "instruction", "remember", "yaad",
                       "rule", "hamesha", "always", "never", "kabhi mat",
                       "avoid", "prefer", "only", "sirf", "mat karo",
                       "band karo", "nahi karna"]
        if any(kw in text_lower for kw in instr_words):
            instr = {
                "id":            len(_admin_instructions) + 1,
                "text":          text,
                "target_team":   target if target != "ALL" else None,
                "target_symbol": mentioned_syms[0] if mentioned_syms else None,
                "created_at":    datetime.now().isoformat(),
                "active":        True,
            }
            _admin_instructions.append(instr)
            _save_admin_instructions()

            sym_note = instr["target_symbol"] or "ALL symbols"
            team_note = target if target != "ALL" else "ALL teams"

            # Save as learning too
            if AI_BRAIN_AVAILABLE:
                # Save to team-specific learning file if target is a specific team
                target_team = target if target != "ALL" else None
                save_learning(
                    topic=sym_note,
                    lesson=text,
                    source="admin_instruction",
                    team=target_team
                )

            await emit("ADMIN", "OperatorMind", "signal",
                f"🧠 INSTRUCTION #{instr['id']} SAVED!\n"
                f"  Rule: \"{text}\"\n"
                f"  Applies to: {team_note} → {sym_note}\n"
                f"  Status: ACTIVE — agents will follow this in every analysis cycle.",
                {"instruction": instr, "chat_reply": True})

            # AI-powered acknowledgment from each relevant agent
            if AI_BRAIN_AVAILABLE:
                for t in teams_to_reply:
                    try:
                        ai_resp = await ask_agent(
                            agent_name="SignalGenerator",
                            user_message=f"Admin ne ye instruction diya hai: \"{text}\". "
                                         f"Isko acknowledge karo aur batao kaise ye tumhari signal generation ko affect karega.",
                            live_data={"team": t, "instruction": text, "symbols": TEAMS[t]["symbols"]},
                            team=t,
                        )
                        await emit(t, "SignalGenerator", "signal",
                            f"📌 {TEAMS[t]['icon']} {t} SignalGenerator: {ai_resp}",
                            {"chat_reply": True})
                    except Exception:
                        await emit(t, "SignalGenerator", "signal",
                            f"📌 {TEAMS[t]['icon']} {t} SignalGenerator: Understood! "
                            f"I will factor \"{text[:60]}\" into my signal scoring.",
                            {"chat_reply": True})
                    await asyncio.sleep(0.3)
            else:
                for t in teams_to_reply:
                    await emit(t, "SignalGenerator", "signal",
                        f"📌 {TEAMS[t]['icon']} {t} SignalGenerator: Understood! "
                        f"I will factor \"{text[:60]}\" into my signal scoring from now on.",
                        {"chat_reply": True})
                    await asyncio.sleep(0.3)
            return

        # ══════════════════════════════════════════════════════════════════
        # 🧠 CLAUDE AI-POWERED INTELLIGENT RESPONSE
        # Each agent THINKS using Claude AI with real-time data + memory
        # ══════════════════════════════════════════════════════════════════

        if AI_BRAIN_AVAILABLE:
            # --- Claude AI mode: Real intelligence ---
            logger.info(f"🧠 Using Claude AI Brain for chat response...")

            # Check if user is asking about market/news → enable web search
            web_keywords = ["news", "khabar", "market", "kya hora", "kya ho raha",
                           "forecast", "prediction", "analysis", "outlook",
                           "internet", "web", "search", "latest", "update"]
            wants_web = any(kw in text_lower for kw in web_keywords)

            for t in teams_to_reply:
                t_icon = TEAMS[t]["icon"]
                t_symbols = TEAMS[t]["symbols"]

                # Determine which agents should respond based on message content
                # For general questions, only 2-3 most relevant agents respond
                agents_to_ask = _pick_relevant_agents(text_lower)

                for agent_name in agents_to_ask:
                    try:
                        ai_resp = await ask_agent(
                            agent_name=agent_name,
                            user_message=text,
                            live_data={
                                "team": t,
                                "symbols": t_symbols,
                                "prices": system_state.get("teams", {}).get(t, {}).get("prices", {}),
                                "signals": system_state.get("teams", {}).get(t, {}).get("signals", {}),
                                "trends": system_state.get("teams", {}).get(t, {}).get("trends", {}),
                                "bias": system_state.get("teams", {}).get(t, {}).get("bias", "NEUTRAL"),
                                "open_trades": {k: v for k, v in system_state.get("active_trades", {}).items()
                                               if v.get("team") == t},
                                "execution_stats": system_state.get("execution_stats", {}),
                                "active_instructions": [i["text"] for i in get_active_instructions(team=t)],
                                "market_bias": system_state.get("admin", {}).get("market_bias", "NEUTRAL"),
                                "training_knowledge": get_sector_knowledge(t) if AI_BRAIN_AVAILABLE else "",
                            },
                            team=t,
                            include_web_search=wants_web,
                            symbols=mentioned_syms or t_symbols,
                        )

                        agent_icons = {
                            "DataFetcher": "📡", "MarketAnalyst": "📊",
                            "SmartMoney": "🔍", "NewsAnalyst": "📰",
                            "SignalGenerator": "⚡", "RiskManager": "🛡️",
                            "PatternMemory": "🧠", "OperatorMind": "🎯",
                            "Coordinator": "📋", "AdminAgent": "👁️",
                            "TVIndicators": "📺",
                        }
                        agent_types = {
                            "DataFetcher": "data", "MarketAnalyst": "analysis",
                            "SmartMoney": "smart_money", "NewsAnalyst": "news",
                            "SignalGenerator": "signal", "RiskManager": "risk",
                            "PatternMemory": "analysis", "OperatorMind": "analysis",
                            "Coordinator": "report", "AdminAgent": "admin",
                            "TVIndicators": "analysis",
                        }

                        await emit(t, agent_name, agent_types.get(agent_name, "signal"),
                            f"{agent_icons.get(agent_name, '🤖')} {t_icon} {t} {agent_name}:\n{ai_resp}",
                            {"chat_reply": True})
                        await asyncio.sleep(0.5)  # Brief pause between agents

                    except Exception as agent_err:
                        logger.error(f"❌ AI agent {agent_name} error: {agent_err}")
                        await emit(t, agent_name, "error",
                            f"⚠️ {t_icon} {t} {agent_name}: Temporarily unavailable.",
                            {"chat_reply": True})

            # Save the conversation as a learning moment to relevant teams
            try:
                for t in teams_to_reply:
                    save_learning(
                        topic="admin_chat",
                        lesson=f"Admin asked: {text[:200]}",
                        source="chat",
                        team=t
                    )
            except Exception:
                pass

        else:
            # --- FALLBACK: Hardcoded responses when AI Brain is not available ---
            ex = system_state.get("execution_stats", {})
            active_trades = system_state.get("active_trades", {})
            market_bias = system_state.get("admin", {}).get("market_bias", "NEUTRAL")

            for t in teams_to_reply:
                tdata   = system_state["teams"].get(t, {})
                signals = tdata.get("signals", {})
                prices  = tdata.get("prices", {})
                bias    = tdata.get("bias", "NEUTRAL")
                t_icon  = TEAMS[t]["icon"]
                t_trades = {tk: tv for tk, tv in active_trades.items() if tv.get("team") == t}
                t_instrs = get_active_instructions(team=t)

                price_lines = []
                for sym, pdata in prices.items():
                    p = pdata.get("price", "?")
                    spread = pdata.get("spread", 0)
                    price_lines.append(f"  {sym}: {p} (spread: {spread})")
                if price_lines:
                    await emit(t, "DataFetcher", "data",
                        f"📡 {t_icon} {t} DataFetcher:\n" + "\n".join(price_lines),
                        {"chat_reply": True})
                    await asyncio.sleep(0.3)

                sig_lines = []
                for sym, s in signals.items():
                    sig_lines.append(f"  {sym}: {s.get('signal','?')} | Score: {s.get('score',0):+d}/20")
                if sig_lines:
                    await emit(t, "SignalGenerator", "signal",
                        f"⚡ {t_icon} {t} SignalGenerator:\n" + "\n".join(sig_lines),
                        {"chat_reply": True})
                await asyncio.sleep(0.3)

                await emit(t, "OperatorMind", "analysis",
                    f"🎯 {t_icon} {t} OperatorMind: Bias={bias} | Trades={len(t_trades)} | Instructions={len(t_instrs)}",
                    {"chat_reply": True})
                await asyncio.sleep(0.3)

            total_open = len(active_trades)
            await emit("ADMIN", "AdminAgent", "admin",
                f"👁️ SUMMARY: {total_open} open trades | "
                f"Today: {ex.get('total_executed',0)} executed | "
                f"Mode: {'LIVE MT5' if system_state['mt5_connected'] else 'SIM'}\n"
                f"⚠️ AI Brain offline — showing basic data only. Check API key.",
                {"chat_reply": True})

    except Exception as chat_exc:
        logger.error(f"❌ Admin chat handler error: {chat_exc}", exc_info=True)
        try:
            await emit("ADMIN", "AdminAgent", "error",
                f"❌ Chat error: {str(chat_exc)[:100]}",
                {"chat_reply": True})
        except Exception:
            pass


def _pick_relevant_agents(text_lower: str) -> list:
    """
    Intelligently pick which agents should respond based on message content.
    ALL 10 agents are now AI-powered with expert system prompts.
    Not all agents need to reply to every message — keeps chat clean.
    """
    agents = []

    # Price / data questions → DataFetcher
    if any(kw in text_lower for kw in ["price", "data", "spread", "connection",
           "rate", "kimat", "kya chal", "kitna", "current", "tick",
           "session", "correlation", "dxy", "vix"]):
        agents.append("DataFetcher")

    # Technical chart analysis → MarketAnalyst (NEW)
    if any(kw in text_lower for kw in ["chart", "technical", "rsi", "macd", "bb",
           "bollinger", "ema", "indicator", "support", "resistance", "adx",
           "momentum", "volume", "candle", "pattern", "divergence",
           "trend analysis", "stochastic", "atr"]):
        if "MarketAnalyst" not in agents:
            agents.append("MarketAnalyst")

    # Smart money / institutional → SmartMoney (NEW)
    if any(kw in text_lower for kw in ["smart money", "fvg", "order block", "ob",
           "liquidity", "sweep", "bos", "choch", "amd", "accumulation",
           "manipulation", "distribution", "institutional", "ict",
           "premium", "discount", "imbalance", "mitigation"]):
        if "SmartMoney" not in agents:
            agents.append("SmartMoney")

    # News / macro / events → NewsAnalyst (NEW)
    if any(kw in text_lower for kw in ["news", "nfp", "cpi", "fomc", "fed",
           "event", "calendar", "macro", "khabar", "release",
           "fundamental", "inflation", "interest rate", "gdp",
           "geopolitical", "war", "economic"]):
        if "NewsAnalyst" not in agents:
            agents.append("NewsAnalyst")

    # Signal / buy / sell questions → SignalGenerator
    if any(kw in text_lower for kw in ["signal", "buy", "sell", "score",
           "kab", "when", "entry", "exit", "kharido", "becho",
           "bullish", "bearish", "strong", "weak"]):
        if "SignalGenerator" not in agents:
            agents.append("SignalGenerator")

    # Risk / SL / TP / trade management → RiskManager
    if any(kw in text_lower for kw in ["risk", "sl", "tp", "stop", "profit",
           "loss", "lot", "trade", "position", "margin", "nuksaan", "faida",
           "drawdown", "circuit", "breakeven"]):
        if "RiskManager" not in agents:
            agents.append("RiskManager")

    # Historical patterns / win rate / memory → PatternMemory (NEW)
    if any(kw in text_lower for kw in ["history", "pattern", "win rate", "accuracy",
           "memory", "past", "learning", "statistics", "purana",
           "kitne percent", "success rate", "backtest", "performance"]):
        if "PatternMemory" not in agents:
            agents.append("PatternMemory")

    # Strategy / bias / overall → OperatorMind
    if any(kw in text_lower for kw in ["strategy", "bias", "plan", "market",
           "overall", "kya kare", "decision", "approve", "reject",
           "cooldown", "approach", "regime"]):
        if "OperatorMind" not in agents:
            agents.append("OperatorMind")

    # Summary / consensus / final report → Coordinator (NEW)
    if any(kw in text_lower for kw in ["summary", "report", "consensus", "final",
           "coordinator", "combine", "all teams", "sabhi", "poora",
           "complete", "overview"]):
        if "Coordinator" not in agents:
            agents.append("Coordinator")

    # Default: AdminAgent + OperatorMind for general questions
    if not agents or any(kw in text_lower for kw in ["status",
           "how", "kaise", "total", "help", "hello",
           "hi", "kya", "batao", "samjhao", "explain", "trained",
           "learn", "sikh", "smart"]):
        if "AdminAgent" not in agents:
            agents.append("AdminAgent")
        if "OperatorMind" not in agents:
            agents.append("OperatorMind")

    # Cap at max 5 agents — enough for comprehensive answers without spam
    return agents[:5]

# Load admin instructions on import
_load_admin_instructions()


async def run_team(team_name: str, stagger: float = 0.0):
    """Full 9-agent cycle for one team.  Runs 24/7, every ANALYSIS_INTERVAL seconds."""
    if stagger > 0:
        await asyncio.sleep(stagger)

    symbols = TEAMS[team_name]["symbols"]
    t_icon  = TEAMS[team_name]["icon"]

    await emit(team_name, "DataFetcher", "data",
               f"{t_icon} {team_name} TEAM INITIALISING (9-agent mode) — symbols: {', '.join(symbols)}")

    while True:
        try:
            system_state["teams"][team_name]["status"] = "ACTIVE"

            # ── Session quality note (ALL teams run 24/7 — no blocking) ──────
            _, sess_note = SessionFilter.check(team_name)
            liquidity    = SessionFilter.liquidity_quality(team_name)
            await emit(team_name, "DataFetcher", "data",
                f"🕐 SESSION [{team_name}]: {sess_note} | Liquidity: {liquidity}")

            for symbol in symbols:

                # ══ AGENT 1 : DATA FETCHER ══════════════════════════════════
                await emit(team_name, "DataFetcher", "data",
                    f"📡 Fetching {symbol} [M15 + H1 + H4] from MT5...")
                await asyncio.sleep(0.4)

                # Fetch M15 (entry precision) + H1 (main) + H4 (confluence) concurrently
                df_m15, df_h1, df_h4, tick = await asyncio.gather(
                    mt5_get_rates(symbol, "M15", 96),   # 24h of M15 bars
                    mt5_get_rates(symbol, "H1",  BARS_TO_FETCH),
                    mt5_get_rates(symbol, "H4",  60),
                    mt5_get_tick(symbol),
                )

                # ── REAL DATA ONLY — skip if H1 unavailable ─────────────────
                if df_h1 is None or len(df_h1) < 30:
                    await emit(team_name, "DataFetcher", "warning",
                        f"⚠️ {symbol} — MT5 H1 data unavailable "
                        f"({len(df_h1) if df_h1 is not None else 0} bars), skipping")
                    logger.warning(f"[{team_name}] {symbol}: MT5 H1 data unavailable — skipped")
                    continue

                df_h1 = TechAnalysis.add_all(df_h1)
                cp    = round(float(df_h1.iloc[-1]["close"]), 5)
                tick  = tick or {}

                # ── H4 trend for multi-timeframe confluence ──────────────────
                h4_trend = None
                if df_h4 is not None and len(df_h4) >= 26:
                    df_h4    = TechAnalysis.add_all(df_h4)
                    h4_trend = TechAnalysis.trend(df_h4)

                # ── M15 entry precision (micro-trend + RSI for exact entry) ──
                m15_trend = None
                m15_rsi = 50
                if df_m15 is not None and len(df_m15) >= 26:
                    df_m15 = TechAnalysis.add_all(df_m15)
                    m15_trend = TechAnalysis.trend(df_m15)
                    m15_mom = TechAnalysis.momentum(df_m15)
                    m15_rsi = m15_mom.get("rsi", 50)

                # ── LEARNING: Evaluate previous predictions ──────────────────
                lessons   = agent_memory.evaluate(symbol, float(cp))
                mem_stats = agent_memory.stats(symbol)
                for lesson in lessons:
                    await emit(team_name, "DataFetcher", "analysis",
                        f"🧠 LESSON [{symbol}] {lesson['outcome']} | "
                        f"Running accuracy: {lesson['accuracy']}% "
                        f"({lesson['correct_count']}/{lesson['total']} correct)",
                        {"symbol": symbol, "lesson": lesson})
                    await asyncio.sleep(0.3)

                system_state["teams"][team_name]["prices"][symbol] = {
                    "price":  float(cp),
                    "bid":    float(tick.get("bid",    cp)),
                    "ask":    float(tick.get("ask",    cp)),
                    "spread": float(tick.get("spread", 0)),
                }

                h4_note   = f" | H4: {h4_trend['direction']} (ADX {h4_trend['adx']})" if h4_trend else ""
                acc_note  = (f" | 🧠 {mem_stats['accuracy']}% acc ({mem_stats['total']} sigs)"
                             if mem_stats["total"] > 0 else "")
                await emit(team_name, "DataFetcher", "data",
                    f"✅ {symbol} — Price: {cp} | Bid: {tick.get('bid',cp)} | "
                    f"Ask: {tick.get('ask',cp)} | Spread: {tick.get('spread',0)} | "
                    f"H1 bars: {len(df_h1)}{h4_note}{acc_note}",
                    {"symbol": symbol, "price": cp, "tick": tick})
                await asyncio.sleep(0.8)

                # ══ AGENT 2 : MARKET ANALYST ════════════════════════════════
                tr  = TechAnalysis.trend(df_h1)
                mom = TechAnalysis.momentum(df_h1)
                sr  = TechAnalysis.support_resistance(df_h1)
                bb  = TechAnalysis.bb_analysis(df_h1)
                # ── H4 Support/Resistance (CRITICAL: was missing — caused BUY at H4 tops) ──
                h4_sr = TechAnalysis.support_resistance(df_h4) if df_h4 is not None and len(df_h4) > 10 else None
                r   = df_h1.iloc[-1]

                # ── Store H1/H4 trends in system_state for recovery system ──
                system_state["teams"][team_name]["trends"][symbol] = {
                    "h1": tr.get("direction", "SIDEWAYS"),
                    "h4": h4_trend.get("direction", "SIDEWAYS") if h4_trend else "SIDEWAYS",
                    "h1_adx": tr.get("adx", 0),
                    "h4_adx": h4_trend.get("adx", 0) if h4_trend else 0,
                }

                # ── Candlestick patterns ─────────────────────────────────────
                candle = CandlePatterns.detect(df_h1)
                candle_note = ""
                if candle["patterns"]:
                    candle_note = " | 🕯️ Patterns: " + " | ".join(candle["patterns"][:2])

                # ── RSI Divergence ────────────────────────────────────────────
                divergence = DivergenceDetector.detect(df_h1)
                div_note   = f" | {divergence['detail']}" if divergence["type"] != "NONE" else ""

                # H4 note for display
                h4_disp = (f" | 📈 H4 Trend: {h4_trend['direction']} ADX:{h4_trend['adx']}"
                           if h4_trend else " | H4: data unavailable")

                await emit(team_name, "MarketAnalyst", "analysis",
                    f"📊 {symbol} H1 — Trend: {tr['direction']} ({tr['strength_label']}, ADX:{tr['adx']}) | "
                    f"RSI: {mom['rsi']} [{mom['rsi_label']}] | MACD: {mom['macd_label']} | "
                    f"BB: {bb['state']} | {bb['squeeze_note']} | ATR: {round(float(r.get('atr',0)),5)} | "
                    f"S: {sr.get('support','?')} R: {sr.get('resistance','?')}"
                    f"{h4_disp}{candle_note}{div_note}",
                    {"symbol": symbol, "trend": tr, "momentum": mom, "sr": sr, "bb": bb,
                     "candle": candle, "divergence": divergence, "h4_trend": h4_trend})
                await asyncio.sleep(1.2)

                # ══ AGENT 3 : SMART MONEY ════════════════════════════════════
                amd   = SmartMoneyEngine.amd_phase(df_h1)
                smc   = SmartMoneyEngine.smc_levels(df_h1)
                narr  = SmartMoneyEngine.operator_narrative(amd, smc, tr)
                emoji = {"ACCUMULATION":"📦","MANIPULATION":"⚡","DISTRIBUTION":"🚀","TRANSITION":"🔄"}.get(amd["phase"],"🔍")

                await emit(team_name, "SmartMoney", "smart_money",
                    f"{emoji} {symbol} AMD: [{amd['phase']}] Confidence: {amd['confidence']}% | "
                    f"{amd['detail']} | {narr}",
                    {"symbol": symbol, "amd": amd, "smc": smc})
                await asyncio.sleep(1.2)

                # ══ AGENT 3a : LIQUIDITY AGENT (55/45 Rule) ════════════════
                # H1+H4 Liquidity Zone Detection, Sweep Detection, 55/45 Rule
                # This agent runs on ALL teams — METALS, FOREX, CRYPTO
                liq_analysis = None
                if LIQUIDITY_ENGINE_AVAILABLE:
                    try:
                        # Get ATR values for zone calculation
                        _h1_atr = float(df_h1.iloc[-1].get('atr', 0)) if 'atr' in df_h1.columns else 0
                        _h4_atr = float(df_h4.iloc[-1].get('atr', 0)) if df_h4 is not None and 'atr' in df_h4.columns else 0

                        # Run full liquidity analysis on H1 + H4
                        liq_analysis = liquidity_engine.analyze(
                            symbol=symbol,
                            df_h1=df_h1,
                            df_h4=df_h4 if df_h4 is not None else pd.DataFrame(),
                            current_price=float(cp),
                            atr_h1=_h1_atr,
                            atr_h4=_h4_atr,
                        )

                        # Store in system state for dashboard
                        if 'liquidity' not in system_state["teams"][team_name]:
                            system_state["teams"][team_name]["liquidity"] = {}
                        system_state["teams"][team_name]["liquidity"][symbol] = {
                            "h1_buy_zones": len(liq_analysis.get('h1_zones', {}).get('buy_side', [])),
                            "h1_sell_zones": len(liq_analysis.get('h1_zones', {}).get('sell_side', [])),
                            "h4_buy_zones": len(liq_analysis.get('h4_zones', {}).get('buy_side', [])),
                            "h4_sell_zones": len(liq_analysis.get('h4_zones', {}).get('sell_side', [])),
                            "active_sweeps": len(liq_analysis.get('active_sweeps', [])),
                            "signal": liq_analysis.get('liquidity_signal', 'NEUTRAL'),
                            "sweep_55_passed": liq_analysis.get('sweep_55_rule_passed', False),
                            "fake_blocked": liq_analysis.get('fake_signal_blocked', False),
                            "confidence": liq_analysis.get('liquidity_confidence', 0),
                            "profit_target": liq_analysis.get('profit_target', 0),
                            "zones": liq_analysis.get('h1_zones', {}),
                            "h4_zones_data": liq_analysis.get('h4_zones', {}),
                            "nearest_buy_side": liq_analysis.get('nearest_buy_side'),
                            "nearest_sell_side": liq_analysis.get('nearest_sell_side'),
                            "filters_passed": liq_analysis.get('filters_passed', 0),
                            "total_filters": liq_analysis.get('total_filters', 6),
                        }

                        # Emit liquidity status
                        _liq_sig = liq_analysis.get('liquidity_signal', 'NEUTRAL')
                        _liq_sweeps = len(liq_analysis.get('active_sweeps', []))
                        _55_pass = liq_analysis.get('sweep_55_rule_passed', False)
                        _fake_block = liq_analysis.get('fake_signal_blocked', False)
                        _zone_count = liq_analysis.get('zone_count', 0)
                        _liq_reasons = liq_analysis.get('reasons', [])
                        _filters = liq_analysis.get('filters_passed', 0)
                        _total_f = liq_analysis.get('total_filters', 6)

                        _liq_icon = "💧"
                        if _55_pass:
                            _liq_icon = "✅"
                        elif _fake_block:
                            _liq_icon = "🚫"
                        elif _liq_sweeps > 0:
                            _liq_icon = "⚡"

                        _nearest_bs = liq_analysis.get('nearest_buy_side')
                        _nearest_ss = liq_analysis.get('nearest_sell_side')
                        _nearest_note = ""
                        if _nearest_bs:
                            _nearest_note += f" | Buy-side: {_nearest_bs['level']:.5f} (str:{_nearest_bs['strength']})"
                        if _nearest_ss:
                            _nearest_note += f" | Sell-side: {_nearest_ss['level']:.5f} (str:{_nearest_ss['strength']})"

                        await emit(team_name, "LiquidityAgent", "liquidity",
                            f"{_liq_icon} {symbol} LIQUIDITY [{team_name}]: "
                            f"Signal: {_liq_sig} | "
                            f"Zones: {_zone_count} (H1+H4) | "
                            f"Sweeps: {_liq_sweeps} | "
                            f"55% Rule: {'✅ PASS' if _55_pass else '❌ FAIL'} | "
                            f"Filters: {_filters}/{_total_f} | "
                            f"Fake Block: {'🚫 YES' if _fake_block else '✅ NO'}"
                            f"{_nearest_note} | "
                            f"{_liq_reasons[0] if _liq_reasons else 'Monitoring zones...'}",
                            {"symbol": symbol, "liquidity": liq_analysis})
                        await asyncio.sleep(0.8)

                    except Exception as _liq_err:
                        logger.warning(f"Liquidity Engine error [{symbol}]: {_liq_err}")
                        await emit(team_name, "LiquidityAgent", "warning",
                            f"⚠️ {symbol}: Liquidity analysis error — {str(_liq_err)[:80]}",
                            {"symbol": symbol})

                # ══ AGENT 3b : NEWS ANALYST ══════════════════════════════════
                try:
                    news = await asyncio.wait_for(NewsEngine.fetch(symbol), timeout=3.0)
                except Exception:
                    news = {"score": 0, "sentiment": "NEUTRAL", "headlines": [],
                            "bull_hits": 0, "bear_hits": 0, "count": 0}
                sent_icon = (
                    "📈" if news["sentiment"] == "BULLISH" else
                    "📉" if news["sentiment"] == "BEARISH" else "📰"
                )
                if news["count"] > 0:
                    top_lines = " | ".join(news["headlines"][:2])
                    await emit(team_name, "NewsAnalyst", "news",
                        f"{sent_icon} {symbol} NEWS SENTIMENT: {news['sentiment']} "
                        f"(score {news['score']:+d} | 🟢{news['bull_hits']} bullish 🔴{news['bear_hits']} bearish) | "
                        f"Headlines: {top_lines}",
                        {"symbol": symbol, "news": news})
                else:
                    await emit(team_name, "NewsAnalyst", "news",
                        f"📰 {symbol} NEWS: No headlines — skipping news sentiment",
                        {"symbol": symbol, "news": news})
                await asyncio.sleep(0.8)

                # ══ INSTITUTIONAL AGENTS (3c/3d/3e/3f) ═════════════════════
                # Run ALL institutional agents concurrently: COT, Web Research,
                # Cross-Market (DXY/VIX), Economic Calendar
                inst_analysis = None
                if INSTITUTIONAL_AGENTS_AVAILABLE:
                    try:
                        # Get volume data for institutional detection
                        _tick_vol = float(df_h1.iloc[-1].get("volume", 0)) if len(df_h1) > 0 else 0
                        _avg_vol = float(df_h1["volume"].tail(20).mean()) if "volume" in df_h1.columns else 0

                        inst_analysis = await asyncio.wait_for(
                            run_institutional_analysis(
                                symbol, df_h1, _tick_vol, _avg_vol
                            ),
                            timeout=12.0,  # 12 sec max for all 4 agents combined
                        )

                        # Display institutional results
                        _inst_dir = inst_analysis.get("institutional_direction", "NEUTRAL")
                        _inst_score = inst_analysis.get("institutional_score", 0)
                        _agents_agree = inst_analysis.get("agents_agree", 0)
                        _safe = inst_analysis.get("safe_to_trade", True)
                        _inst_reasons = inst_analysis.get("reasons", [])

                        _inst_ico = "🏦" if _inst_dir == "BUY" else "🏦" if _inst_dir == "SELL" else "🏛️"
                        _safe_ico = "✅" if _safe else "⛔"

                        await emit(team_name, "InstitutionalAgents", "smart_money",
                            f"{_inst_ico} {symbol} INSTITUTIONAL CONSENSUS: {_inst_dir} "
                            f"(score: {_inst_score}, {_agents_agree} agents agree) | "
                            f"{_safe_ico} Safe to trade: {'YES' if _safe else 'NO — EVENT BLOCK'} | "
                            f"{' | '.join(_inst_reasons[:3])}",
                            {"symbol": symbol, "institutional": inst_analysis})
                        await asyncio.sleep(0.5)

                        # If calendar blocks trading → skip this symbol entirely
                        if not _safe:
                            await emit(team_name, "InstitutionalAgents", "warning",
                                f"⛔ {symbol}: BLOCKED by institutional agents — "
                                f"high-impact event approaching. Skipping.",
                                {"symbol": symbol})
                            continue  # Skip to next symbol

                    except asyncio.TimeoutError:
                        await emit(team_name, "InstitutionalAgents", "warning",
                            f"⚠️ {symbol}: Institutional analysis timeout (12s) — proceeding without",
                            {"symbol": symbol})
                    except Exception as _inst_err:
                        logger.warning(f"Institutional agents error [{symbol}]: {_inst_err}")

                # ══ ADVANCED AGENTS (Correlation + OrderFlow + MarketRegime) ══
                _regime_data = None
                _orderflow_data = None
                _correlation_data = None
                _drawdown_adj = None

                if ADVANCED_AGENTS_AVAILABLE:
                    try:
                        # ── MARKET REGIME AGENT ──
                        _regime_data = MarketRegimeAgent.analyze(symbol, df_h1)
                        if _regime_data:
                            _regime = _regime_data.get("regime", "UNKNOWN")
                            _regime_rec = _regime_data.get("strategy_recommendation", "DEFAULT")
                            _regime_ico = {"TRENDING": "📈", "RANGING": "📊", "BREAKOUT": "💥",
                                          "EXHAUSTION": "⚠️", "VOLATILE": "🌪️"}.get(_regime, "🔍")
                            await emit(team_name, "MarketRegimeAgent", "analysis",
                                f"{_regime_ico} {symbol} REGIME: {_regime} | "
                                f"Strategy: {_regime_rec} | "
                                f"Lot mult: {_regime_data.get('position_size_mult', 1.0):.2f}x | "
                                f"Volatility: {_regime_data.get('volatility_state', 'NORMAL')} | "
                                f"{_regime_data.get('reasons', [''])[0] if _regime_data.get('reasons') else ''}",
                                {"symbol": symbol, "regime": _regime_data})
                            await asyncio.sleep(0.3)

                        # ── ORDER FLOW AGENT ──
                        _orderflow_data = OrderFlowAgent.analyze(symbol, df_h1)
                        if _orderflow_data and _orderflow_data.get("bias") != "NEUTRAL":
                            _of_bias = _orderflow_data.get("bias", "NEUTRAL")
                            _of_ico = "🟢" if _of_bias == "BUY" else "🔴" if _of_bias == "SELL" else "🟡"
                            await emit(team_name, "OrderFlowAgent", "analysis",
                                f"{_of_ico} {symbol} ORDER FLOW: {_orderflow_data.get('volume_delta', 'NEUTRAL')} | "
                                f"Delta: {_orderflow_data.get('delta_score', 0):.1f}% | "
                                f"Climax: {'YES' if _orderflow_data.get('volume_climax') else 'NO'} | "
                                f"Absorption: {'YES' if _orderflow_data.get('absorption') else 'NO'} | "
                                f"{_orderflow_data.get('reasons', [''])[0] if _orderflow_data.get('reasons') else ''}",
                                {"symbol": symbol, "orderflow": _orderflow_data})
                            await asyncio.sleep(0.3)

                        # ── CORRELATION AGENT ──
                        _correlation_data = CorrelationAgent.analyze(symbol, df_h1)
                        if _correlation_data and _correlation_data.get("divergences"):
                            await emit(team_name, "CorrelationAgent", "warning",
                                f"🔗 {symbol} CORRELATION: {len(_correlation_data['divergences'])} divergence(s) | "
                                f"Conf adj: {_correlation_data.get('confidence_adjustment', 0):+d} | "
                                f"{_correlation_data.get('reasons', [''])[0] if _correlation_data.get('reasons') else ''}",
                                {"symbol": symbol, "correlation": _correlation_data})
                            await asyncio.sleep(0.3)

                        # ── DRAWDOWN RECOVERY AGENT ──
                        _drawdown_adj = DrawdownRecoveryAgent.get_adjustments()
                        if _drawdown_adj.get("mode") != "NORMAL":
                            _dd_mode = _drawdown_adj.get("mode", "NORMAL")
                            _dd_ico = {"CONSERVATIVE": "⚠️", "RECOVERY": "🔴",
                                      "AGGRESSIVE": "🟢", "LOCKDOWN": "⛔"}.get(_dd_mode, "🟡")
                            await emit(team_name, "DrawdownRecovery", "risk",
                                f"{_dd_ico} {symbol} DRAWDOWN MODE: {_dd_mode} | "
                                f"Lot: {_drawdown_adj.get('lot_multiplier', 1.0):.2f}x | "
                                f"Extra confluence: +{_drawdown_adj.get('extra_confluence', 0)} | "
                                f"{_drawdown_adj.get('reason', '')}",
                                {"symbol": symbol, "drawdown": _drawdown_adj})
                            await asyncio.sleep(0.3)

                    except Exception as _adv_err:
                        logger.warning(f"Advanced agents error [{symbol}]: {_adv_err}")

                # ══ INSTITUTIONAL COPY AGENT ════════════════════════════════
                # Copy big player trades: COT managed money, bank forecasts,
                # central bank buying, open interest changes
                copy_analysis = None
                if INST_COPY_AVAILABLE:
                    try:
                        copy_analysis = await asyncio.wait_for(
                            run_institutional_copy(symbol, float(cp)),
                            timeout=10.0,
                        )
                        _copy_dir = copy_analysis.get("copy_signal", "NEUTRAL")
                        _copy_conf = copy_analysis.get("confidence", 50)
                        _copy_reasons = copy_analysis.get("reasons", [])
                        _copy_ico = "🟢" if _copy_dir == "BUY" else "🔴" if _copy_dir == "SELL" else "🟡"

                        if _copy_reasons:
                            await emit(team_name, "InstitutionalCopy", "smart_money",
                                f"{_copy_ico} {symbol} COPY: {_copy_dir} ({_copy_conf}%) | "
                                f"{' | '.join(_copy_reasons[:2])}",
                                {"symbol": symbol, "copy": copy_analysis})
                            await asyncio.sleep(0.3)
                    except asyncio.TimeoutError:
                        logger.debug(f"Institutional copy timeout [{symbol}]")
                    except Exception as _copy_err:
                        logger.debug(f"Institutional copy error [{symbol}]: {_copy_err}")

                # ══ AI KNOWLEDGE INJECTION ══════════════════════════════════
                # Pull internet research + Claude knowledge base insights
                # BEFORE signal generation so wisdom influences scoring
                _kb_boost = 0
                _kb_reasons = []
                if AI_BRAIN_AVAILABLE:
                    try:
                        # 1) Claude Knowledge Base — pre-trained levels & rules
                        _sector_kb = get_knowledge_for_sector(team_name)
                        # 2) Internet research — latest Gemini web insights
                        _sector_research = get_sector_knowledge(team_name)

                        if _sector_kb or _sector_research:
                            _combined = (_sector_kb + "\n" + _sector_research).lower()
                            _sym_lower = symbol.lower().replace("/", "")

                            # Check if knowledge mentions this specific symbol
                            if _sym_lower in _combined or symbol.replace("/", "").lower() in _combined:
                                # Extract directional bias from knowledge
                                _bull_words = _combined.count("bullish") + _combined.count("support") + _combined.count("buy zone")
                                _bear_words = _combined.count("bearish") + _combined.count("resistance") + _combined.count("sell zone")

                                # Check for specific price-level warnings
                                _has_resistance_warn = ("near resistance" in _combined or
                                                       "at resistance" in _combined or
                                                       "overbought" in _combined)
                                _has_support_warn = ("near support" in _combined or
                                                    "at support" in _combined or
                                                    "oversold" in _combined)

                                if _has_resistance_warn and tr.get("direction") == "BULLISH":
                                    _kb_boost = -2
                                    _kb_reasons.append(f"🧠 KB: {symbol} near RESISTANCE zone — caution for BUY")
                                elif _has_support_warn and tr.get("direction") == "BEARISH":
                                    _kb_boost = +2
                                    _kb_reasons.append(f"🧠 KB: {symbol} near SUPPORT zone — caution for SELL")
                                elif _bull_words > _bear_words + 2:
                                    _kb_boost = +1
                                    _kb_reasons.append(f"🧠 KB: Research favors BULLISH {symbol}")
                                elif _bear_words > _bull_words + 2:
                                    _kb_boost = -1
                                    _kb_reasons.append(f"🧠 KB: Research favors BEARISH {symbol}")
                    except Exception as _kb_err:
                        logger.debug(f"Knowledge injection error [{symbol}]: {_kb_err}")

                # ══ AGENT 4 : SIGNAL GENERATOR ══════════════════════════════
                # Full signal with all 6 inputs: trend, momentum, BB, AMD/SMC,
                # candle patterns, RSI divergence, H4 confluence, ADX filter
                sig = SignalEngine.generate(
                    tr, mom, bb, amd, smc,
                    candle=candle,
                    divergence=divergence,
                    h4_trend=h4_trend,
                    sr=sr,
                    h4_sr=h4_sr,
                    current_price=cp,
                    adx_filter=True,
                )

                # Apply knowledge base adjustment to signal score
                if _kb_boost != 0 and not sig.get("filtered"):
                    sig["score"] += _kb_boost
                    sig["reasons"].extend(_kb_reasons)

                # ── M15 ENTRY PRECISION FILTER ─────────────────────────────
                # M15 micro-trend must confirm H1 direction for tight entries.
                # Prevents entering on H1 BUY when M15 is still pulling back.
                if m15_trend and not sig.get("filtered"):
                    _m15_dir = m15_trend.get("direction", "SIDEWAYS")
                    _sig_dir = sig.get("signal", "HOLD")
                    if _sig_dir == "BUY" and _m15_dir == "BULLISH":
                        sig["score"] += 1
                        sig["confidence"] = min(95, sig.get("confidence", 50) + 3)
                        sig["reasons"].append(f"⏱️ M15 confirms BUY (micro-trend UP, RSI {m15_rsi:.0f})")
                    elif _sig_dir == "SELL" and _m15_dir == "BEARISH":
                        sig["score"] -= 1
                        sig["confidence"] = min(95, sig.get("confidence", 50) + 3)
                        sig["reasons"].append(f"⏱️ M15 confirms SELL (micro-trend DOWN, RSI {m15_rsi:.0f})")
                    elif _sig_dir == "BUY" and _m15_dir == "BEARISH":
                        # M15 pulling back — risky BUY entry, reduce confidence
                        sig["confidence"] = max(10, sig.get("confidence", 50) - 5)
                        sig["reasons"].append(f"⏱️ M15 PULLBACK: micro-trend DOWN — wait for M15 flip")
                    elif _sig_dir == "SELL" and _m15_dir == "BULLISH":
                        sig["confidence"] = max(10, sig.get("confidence", 50) - 5)
                        sig["reasons"].append(f"⏱️ M15 PULLBACK: micro-trend UP — wait for M15 flip")

                    # M15 RSI extreme = entry timing (oversold for BUY, overbought for SELL)
                    if _sig_dir == "BUY" and m15_rsi < 30:
                        sig["score"] += 1
                        sig["reasons"].append(f"⏱️ M15 RSI OVERSOLD {m15_rsi:.0f} — excellent BUY entry")
                    elif _sig_dir == "SELL" and m15_rsi > 70:
                        sig["score"] -= 1
                        sig["reasons"].append(f"⏱️ M15 RSI OVERBOUGHT {m15_rsi:.0f} — excellent SELL entry")

                # ── NEWS BOOST: Adjust score based on news sentiment (±2) ──
                if not sig.get("filtered"):
                    if news["sentiment"] == "BULLISH" and news["score"] >= 2:
                        news_adj = min(2, news["score"])
                        sig["score"] += news_adj
                        sig["reasons"].append(f"📰 News BULLISH ({news['score']:+d})")
                    elif news["sentiment"] == "BEARISH" and news["score"] <= -2:
                        news_adj = max(-2, news["score"])
                        sig["score"] += news_adj
                        sig["reasons"].append(f"📰 News BEARISH ({news['score']:+d})")

                    # ── INSTITUTIONAL BOOST: Big players agree = big boost (±4) ──
                    if inst_analysis and not sig.get("filtered"):
                        _inst_dir = inst_analysis.get("institutional_direction", "NEUTRAL")
                        _inst_score_val = inst_analysis.get("institutional_score", 0)
                        _sig_dir = sig.get("signal", "HOLD")

                        if _inst_dir == "BUY" and _sig_dir == "BUY":
                            sig["score"] += 4
                            sig["reasons"].append(
                                f"🏦 INSTITUTIONAL CONFIRMS BUY — big players are long "
                                f"({inst_analysis.get('agents_agree', 0)} agents agree)"
                            )
                        elif _inst_dir == "SELL" and _sig_dir == "SELL":
                            sig["score"] -= 4  # More negative = stronger sell
                            sig["reasons"].append(
                                f"🏦 INSTITUTIONAL CONFIRMS SELL — big players are short "
                                f"({inst_analysis.get('agents_agree', 0)} agents agree)"
                            )
                        elif _inst_dir != "NEUTRAL" and _inst_dir != _sig_dir and _sig_dir != "HOLD":
                            # Institutional agents DISAGREE with technical signal
                            # BUT: TREND > INSTITUTIONS — only reduce by 20% (was 50% = too much!)
                            sig["score"] = int(sig["score"] * 0.8)  # Only 20% reduction
                            sig["reasons"].append(
                                f"⚠️ INSTITUTIONAL NOTE: Big players say {_inst_dir} "
                                f"but TREND says {_sig_dir} — trend wins, minor reduction"
                            )

                    # ── INSTITUTIONAL COPY BOOST ────────────────────────────
                    # Big players' positions confirm or conflict with signal
                    if copy_analysis and not sig.get("filtered"):
                        _copy_dir = copy_analysis.get("copy_signal", "NEUTRAL")
                        _sig_dir = sig.get("signal", "HOLD")
                        if _copy_dir == _sig_dir and _copy_dir != "NEUTRAL":
                            sig["score"] += 3
                            sig["confidence"] = min(95, sig.get("confidence", 50) + 8)
                            sig["reasons"].append(
                                f"🏦 COPY CONFIRMS: Big players also {_copy_dir} ({copy_analysis.get('confidence',50)}%)"
                            )
                        elif _copy_dir != "NEUTRAL" and _copy_dir != _sig_dir and _sig_dir != "HOLD":
                            sig["score"] = int(sig["score"] * 0.85)  # Only 15% reduction (trend > copy)
                            sig["reasons"].append(
                                f"ℹ️ COPY NOTE: Big players say {_copy_dir} but TREND says {_sig_dir}"
                            )

                    # ── GEOPOLITICAL WAR ADJUSTMENT ──────────────────────────
                    # Active wars affect safe havens and risk assets
                    if GEO_AVAILABLE and not sig.get("filtered"):
                        try:
                            # Scan for latest war status (cached, runs every 5 min)
                            geo_adj = GeopoliticalRiskAgent.get_symbol_adjustment(symbol)
                            _geo_dir = geo_adj.get("direction", "NEUTRAL")
                            _geo_conf = geo_adj.get("confidence_adj", 0)
                            _geo_wars = geo_adj.get("wars_active", [])

                            if _geo_wars and _geo_conf > 0:
                                _sig_dir = sig.get("signal", "HOLD")
                                if _geo_dir == _sig_dir:
                                    # War supports our trade direction → boost
                                    sig["score"] += min(3, _geo_conf // 5)
                                    sig["confidence"] = min(95, sig.get("confidence", 50) + _geo_conf)
                                    sig["reasons"].append(
                                        f"🌍 WAR BOOST: {', '.join(_geo_wars[:2])} → {_geo_dir} {symbol} "
                                        f"(+{_geo_conf} conf)"
                                    )
                                elif _geo_dir != "NEUTRAL" and _geo_dir != _sig_dir and _sig_dir != "HOLD":
                                    # War opposes our direction → small note only (TREND > WARS)
                                    sig["confidence"] = max(10, sig.get("confidence", 50) - min(5, _geo_conf // 4))
                                    sig["reasons"].append(
                                        f"🌍 WAR NOTE: Wars say {_geo_dir} but TREND says {_sig_dir} — trend wins"
                                    )
                        except Exception as _ge:
                            logger.debug(f"Geo adjustment error: {_ge}")

                    # ── ADVANCED AGENTS BOOST (OrderFlow + Regime + Correlation) ──
                    if ADVANCED_AGENTS_AVAILABLE and not sig.get("filtered"):
                        _sig_dir = sig.get("signal", "HOLD")

                        # OrderFlow confirmation
                        if _orderflow_data and _sig_dir != "HOLD":
                            _of_bias = _orderflow_data.get("bias", "NEUTRAL")
                            _of_conf_adj = _orderflow_data.get("confidence_adjustment", 0)
                            if _of_bias == _sig_dir:
                                sig["score"] += 2
                                sig["confidence"] = min(95, sig.get("confidence", 50) + _of_conf_adj)
                                sig["reasons"].append(
                                    f"📊 ORDER FLOW CONFIRMS {_sig_dir} — "
                                    f"{_orderflow_data.get('volume_delta', 'NEUTRAL')} pressure"
                                )
                            elif _of_bias != "NEUTRAL" and _of_bias != _sig_dir:
                                sig["confidence"] = max(10, sig.get("confidence", 50) - 5)
                                sig["reasons"].append(
                                    f"📊 ORDER FLOW CONFLICT: {_of_bias} vs signal {_sig_dir}"
                                )

                        # MarketRegime adjustment
                        if _regime_data:
                            _regime = _regime_data.get("regime", "UNKNOWN")
                            if _regime == "EXHAUSTION":
                                sig["confidence"] = max(10, sig.get("confidence", 50) - 15)
                                sig["reasons"].append(f"⚠️ REGIME: Trend exhaustion — reduced confidence")
                            elif _regime == "RANGING" and _sig_dir != "HOLD":
                                sig["confidence"] = max(10, sig.get("confidence", 50) - 10)
                                sig["reasons"].append(f"📊 REGIME: Ranging market — trade with caution")
                            elif _regime == "TRENDING" and _sig_dir != "HOLD":
                                sig["score"] += 1
                                sig["reasons"].append(f"📈 REGIME: Trending market — signal boosted")

                        # Correlation check
                        if _correlation_data:
                            _corr_adj = _correlation_data.get("confidence_adjustment", 0)
                            if _corr_adj != 0:
                                sig["confidence"] = max(10, min(95, sig.get("confidence", 50) + _corr_adj))
                                if _correlation_data.get("warning"):
                                    sig["reasons"].append(
                                        f"🔗 CORRELATION WARNING: {_correlation_data.get('reasons', [''])[0]}"
                                    )

                        # DrawdownRecovery gate
                        if _drawdown_adj and _drawdown_adj.get("mode") != "NORMAL":
                            _dd_mode = _drawdown_adj.get("mode")
                            if _dd_mode == "LOCKDOWN":
                                sig["signal"] = "HOLD"
                                sig["strength"] = "LOCKDOWN"
                                sig["reasons"].append(f"⛔ DRAWDOWN LOCKDOWN — no trading allowed")
                            else:
                                _extra_conf = _drawdown_adj.get("extra_confluence", 0)
                                if _extra_conf > 0:
                                    sig["confidence"] = max(10, sig.get("confidence", 50) - _extra_conf * 5)
                                    sig["reasons"].append(
                                        f"🔴 DRAWDOWN {_dd_mode}: +{_extra_conf} extra confluence required"
                                    )

                    # ── TRADINGVIEW INDICATORS BOOST (v2.0 — Team-Weighted) ──
                    # MACD Overlay(10,21,10,21) + SuperBollingerTrend(12,2) +
                    # Cash Open + Liquidity Heatmap → combined ±6 score (team-weighted)
                    tv_analysis = None
                    if TV_INDICATORS_AVAILABLE and not sig.get("filtered"):
                        try:
                            tv_analysis = tv_analyze(df_h1, current_price=cp,
                                                     symbol=symbol, team=team_name)
                            _tv_score = tv_analysis.get("tv_score", 0)
                            _tv_conf  = tv_analysis.get("tv_confidence_adj", 0)
                            _tv_reasons = tv_analysis.get("tv_reasons", [])
                            _tv_team  = tv_analysis.get("team", team_name)

                            if _tv_score != 0:
                                sig["score"] += _tv_score
                                sig["confidence"] = min(95, sig.get("confidence", 50) + _tv_conf)
                                sig["reasons"].extend(_tv_reasons)

                            # Growth tracking for agent/revenue monitoring
                            if tv_analysis.get("growth_positive"):
                                sig["reasons"].append(
                                    f"✅ TV GROWTH [{_tv_team}]: Positive growth confirmed — "
                                    f"MACD({tv_analysis['macd']['growth_rate']:+.1f}%) + "
                                    f"ST(conf {tv_analysis['supertrend']['confidence']}%) "
                                    f"[raw_wt: {tv_analysis.get('raw_weighted_score', 0):+.1f}]"
                                )
                            elif _tv_score == 0 and not tv_analysis.get("growth_positive"):
                                sig["reasons"].append(
                                    f"⚠️ TV GROWTH [{_tv_team}]: Contraction — "
                                    f"MACD growth {tv_analysis['macd']['growth_rate']:+.1f}%, "
                                    f"SBT growth {tv_analysis['supertrend']['growth_pct']:+.1f}%"
                                )

                            await emit(team_name, "TVIndicators", "analysis",
                                f"📺 {symbol} TV [{_tv_team}]: "
                                f"MACD({tv_analysis['macd']['signal']}) | "
                                f"SBT({tv_analysis['supertrend']['verdict']}, "
                                f"{tv_analysis['supertrend']['trend_score']}/3) | "
                                f"Cash({tv_analysis['cash_open']['sentiment']}) | "
                                f"Liq({'🔥SWEEP!' if tv_analysis['liquidity']['sweep_detected'] else 'normal'}) | "
                                f"Score: {_tv_score:+d} (raw:{tv_analysis.get('raw_weighted_score', 0):+.1f}) | "
                                f"Growth: {'✅' if tv_analysis.get('growth_positive') else '❌'}",
                                {"symbol": symbol, "team": _tv_team,
                                 "tv_indicators": tv_analysis})
                            await asyncio.sleep(0.5)

                        except Exception as _tv_err:
                            logger.debug(f"TV indicators error [{symbol}]: {_tv_err}")

                    # ── LIQUIDITY ENGINE 55/45 BOOST (Final Rule for ALL Teams) ──
                    # After all other agents have scored, apply liquidity confirmation
                    if LIQUIDITY_ENGINE_AVAILABLE and liq_analysis and not sig.get("filtered"):
                        _liq_sig = liq_analysis.get('liquidity_signal', 'NEUTRAL')
                        _liq_score = liq_analysis.get('liquidity_score', 0)
                        _liq_conf = liq_analysis.get('liquidity_confidence', 0)
                        _55_pass = liq_analysis.get('sweep_55_rule_passed', False)
                        _fake_block = liq_analysis.get('fake_signal_blocked', False)
                        _sig_dir = sig.get("signal", "HOLD")

                        if _55_pass and _liq_sig != 'NEUTRAL':
                            if _liq_sig == _sig_dir:
                                # ✅ LIQUIDITY CONFIRMS signal → big boost
                                sig["score"] += _liq_score
                                sig["confidence"] = min(95, sig.get("confidence", 50) + 15)
                                sig["reasons"].append(
                                    f"💧 LIQUIDITY 55/45 CONFIRMS {_liq_sig} — "
                                    f"sweep passed, targeting 45% remaining zone"
                                )
                                # Attach liquidity TP/SL
                                if liq_analysis.get('profit_target', 0) > 0:
                                    sig["liq_profit_target"] = liq_analysis['profit_target']
                                if liq_analysis.get('stop_loss_suggestion', 0) > 0:
                                    sig["liq_stop_loss"] = liq_analysis['stop_loss_suggestion']
                            elif _liq_sig != _sig_dir and _sig_dir != "HOLD":
                                # Liquidity says opposite direction → reduce confidence
                                sig["confidence"] = max(10, sig.get("confidence", 50) - 10)
                                sig["reasons"].append(
                                    f"💧 LIQUIDITY CONFLICT: Sweep says {_liq_sig} but "
                                    f"signal says {_sig_dir} — caution"
                                )
                        elif _fake_block:
                            # 🚫 FAKE SIGNAL DETECTED by liquidity engine
                            sig["confidence"] = max(5, sig.get("confidence", 50) - 20)
                            sig["reasons"].append(
                                f"🚫 LIQUIDITY: FAKE SIGNAL — sweep < 55% or filters failed"
                            )

                    # Re-derive signal/strength after all adjustments
                    sc = sig["score"]
                    if   sc >= 8:  sig["signal"], sig["strength"] = "BUY",  "STRONG"
                    elif sc >= 5:  sig["signal"], sig["strength"] = "BUY",  "MODERATE"
                    elif sc <= -8: sig["signal"], sig["strength"] = "SELL", "STRONG"
                    elif sc <= -5: sig["signal"], sig["strength"] = "SELL", "MODERATE"
                    else:          sig["signal"], sig["strength"] = "HOLD", "NEUTRAL"

                entry = SignalEngine.entry_zone(df_h1, sig["signal"])

                # ── LEARNING: Apply memory confidence multiplier ─────────────
                mult     = agent_memory.multiplier(symbol)
                raw_conf = sig["confidence"]
                adj_conf = min(95, int(raw_conf * mult))
                sig["confidence"] = adj_conf

                mem_note = ""
                if mult != 1.0 and mem_stats["total"] >= 5:
                    direction = "↑" if mult > 1.0 else "↓"
                    mem_note  = (
                        f" | 🧠 Memory {direction}{mult:.2f}× "
                        f"({mem_stats['accuracy']}% acc, {mem_stats['total']} sigs)"
                    )

                # ── TRAINING: Apply learned pattern adjustments + ML prediction ─
                train_note = ""
                if TRAINING_AVAILABLE and sig["signal"] != "HOLD":
                    try:
                        _h4_d = h4_trend.get("direction", "SIDEWAYS") if h4_trend else "SIDEWAYS"
                        _h1_d = tr.get("direction", "SIDEWAYS") if tr else "SIDEWAYS"
                        _inst_match = (inst_analysis or {}).get("institutional_direction", "NEUTRAL") == sig["signal"]
                        _kz = (inst_analysis or {}).get("institutional", {})
                        _kz_name = _kz.get("killzone", "NONE") if isinstance(_kz, dict) else "NONE"

                        # CHECK 1: Is symbol blacklisted by training?
                        if not TrainingEngine.is_symbol_allowed(symbol):
                            sig["signal"] = "HOLD"
                            sig["strength"] = "NEUTRAL"
                            sig["score"] = 0
                            sig["confidence"] = 5
                            sig["reasons"].append(f"⛔ TRAINING BLACKLIST: {symbol} has <35% win rate — auto-disabled")
                            train_note = f" | ⛔ BLACKLISTED by training"
                            await emit(team_name, "ML_Engine", "warning",
                                f"⛔ TRAINING BLACKLIST: {symbol} blocked — win rate <35%. "
                                f"ML Engine overrides all agents. Signal → HOLD",
                                {"symbol": symbol, "ml_prediction": True, "blacklisted": True})
                        # CHECK 2: Is this hour blacklisted for this symbol?
                        elif not TrainingEngine.is_hour_allowed(symbol, datetime.utcnow().hour):
                            sig["confidence"] = max(10, sig["confidence"] - 15)
                            sig["reasons"].append(f"📚 Bad session hour for {symbol} — confidence reduced")
                            train_note = f" | 📚 Bad hour (-15 conf)"
                        else:
                            # Statistical adjustments
                            train_adj = TrainingEngine.get_confidence_adjustment(
                                symbol=symbol,
                                direction=sig["signal"],
                                hour_utc=datetime.utcnow().hour,
                                h4_aligned=(_h4_d == _h1_d and _h4_d != "SIDEWAYS"),
                                score=sig["score"],
                                killzone=_kz_name,
                                institutional_match=_inst_match,
                            )

                            # Check if training wants to block this
                            if train_adj.get("blocked"):
                                sig["signal"] = "HOLD"
                                sig["strength"] = "NEUTRAL"
                                sig["score"] = 0
                                sig["confidence"] = 5
                                sig["reasons"].extend(train_adj["reasons"])
                                train_note = f" | ⛔ BLOCKED by training"
                            elif train_adj["adjustment"] != 0:
                                sig["confidence"] = max(10, min(95, sig["confidence"] + train_adj["adjustment"]))
                                train_reasons = " | ".join(train_adj["reasons"][:2])
                                train_note = f" | 📚 Training: {train_adj['adjustment']:+d} ({train_reasons})"

                            # ML PREDICTION (Level 2 — if model is trained)
                            if sig["signal"] != "HOLD":
                                ml_pred = TrainingEngine.ml_predict({
                                    "score": sig["score"],
                                    "confidence": sig["confidence"],
                                    "rsi": mom.get("rsi", 50) if mom else 50,
                                    "adx": tr.get("adx", 20) if tr else 20,
                                    "hour_utc": datetime.utcnow().hour,
                                    "institutional_conf": (inst_analysis or {}).get("institutional_score", 50),
                                    "h4_h1_aligned": (_h4_d == _h1_d and _h4_d != "SIDEWAYS"),
                                    "killzone": _kz_name,
                                    "institutional_dir": (inst_analysis or {}).get("institutional_direction", "NEUTRAL"),
                                    "direction": sig["signal"],
                                    "amd_phase": amd.get("phase", "") if amd else "",
                                    "volume_signal": (inst_analysis or {}).get("institutional", {}).get("volume_signal", "NORMAL") if isinstance((inst_analysis or {}).get("institutional"), dict) else "NORMAL",
                                    "news": news.get("sentiment", "NEUTRAL"),
                                })
                                if ml_pred.get("available"):
                                    sig["confidence"] = max(10, min(95, sig["confidence"] + ml_pred["confidence_adj"]))
                                    wp = ml_pred["win_prob"]
                                    pred_icon = "🟢" if wp >= 0.6 else "🔴" if wp <= 0.4 else "🟡"
                                    train_note += f" | {pred_icon} ML: {wp:.0%} win prob ({ml_pred['confidence_adj']:+d})"

                                    # ── Emit ML coordination event for dashboard ──
                                    await emit(team_name, "ML_Engine", "analysis",
                                        f"🤖 ML PREDICTION {symbol}: {pred_icon} Win Prob {wp:.0%} | "
                                        f"Conf Adj: {ml_pred['confidence_adj']:+d} | "
                                        f"Score: {sig['score']:+d} | Signal: {sig['signal']} | "
                                        f"Training: {ml_pred.get('train_samples', '?')} samples",
                                        {"symbol": symbol, "ml_prediction": True,
                                         "win_prob": wp, "confidence_adj": ml_pred['confidence_adj']})

                                    # ML says strong LOSS → block the trade
                                    if wp <= 0.30:
                                        sig["signal"] = "HOLD"
                                        sig["strength"] = "NEUTRAL"
                                        sig["reasons"].append(f"🤖 ML BLOCKED: {wp:.0%} win probability — too risky")
                                        train_note += " | ⛔ ML BLOCKED"

                                    # ── ML BOOST: High win probability → size up! ──
                                    # Kelly Criterion: f* = (bp - q) / b
                                    # where b = avg_win/avg_loss, p = win_prob, q = 1-p
                                    elif wp >= 0.65:
                                        # Use simplified Kelly: increase position size
                                        _kelly_b = 2.5  # Avg R:R is ~2.5:1
                                        _kelly_f = max(0, (_kelly_b * wp - (1 - wp)) / _kelly_b)
                                        _kelly_pct = min(0.5, _kelly_f)  # Cap at 50% Kelly (half-Kelly for safety)
                                        _kelly_boost = round(_kelly_pct * 10)  # +1 to +5 confidence points

                                        sig["confidence"] = min(95, sig["confidence"] + _kelly_boost)
                                        sig["score"] += 1  # Small score boost for strong ML signal
                                        sig["reasons"].append(
                                            f"🤖 ML BOOST: {wp:.0%} win prob → Kelly {_kelly_pct:.0%} "
                                            f"(+{_kelly_boost} conf, size UP)"
                                        )
                                        # Store Kelly info for position sizing
                                        sig["_kelly_multiplier"] = 1.0 + (_kelly_pct * 0.5)  # 1.0–1.25× size
                                        train_note += f" | 🟢 ML BOOST +{_kelly_boost}"

                    except Exception as _te:
                        logger.debug(f"Training adjustment error: {_te}")

                # ── LEARNING: Record this prediction for future evaluation ────
                if sig["signal"] != "HOLD":
                    agent_memory.record(symbol, sig["signal"], float(cp), adj_conf)

                # ── SENTIMENT: Update real-time sentiment for recovery system ──
                if SMART_RECOVERY_AVAILABLE:
                    try:
                        _inst_d = (inst_analysis or {}).get("institutional_direction", "NEUTRAL")
                        _inst_c = (inst_analysis or {}).get("institutional_score", 50)
                        _cross_b = (inst_analysis or {}).get("cross_market", {})
                        _cross_dir = _cross_b.get("bias", "NEUTRAL") if isinstance(_cross_b, dict) else "NEUTRAL"
                        update_sentiment(
                            symbol=symbol,
                            news_score=news.get("score", 0),
                            news_sentiment=news.get("sentiment", "NEUTRAL"),
                            institutional_dir=_inst_d,
                            institutional_conf=_inst_c,
                            cross_market_bias=_cross_dir,
                            h1_trend=tr.get("direction", "SIDEWAYS") if tr else "SIDEWAYS",
                            h4_trend=h4_trend.get("direction", "SIDEWAYS") if h4_trend else "SIDEWAYS",
                            rsi=mom.get("rsi", 50) if mom else 50,
                            adx=tr.get("adx", 20) if tr else 20,
                        )
                    except Exception as _se:
                        logger.debug(f"Sentiment update error: {_se}")

                s_ico       = "🟢" if sig["signal"]=="BUY" else "🔴" if sig["signal"]=="SELL" else "🟡"
                reasons_txt = " + ".join(sig["reasons"])

                # H4 trend display for clarity
                h4_dir_str = ""
                if h4_trend:
                    h4_d = h4_trend.get("direction", "?")
                    h4_a = h4_trend.get("adx", 0)
                    h4_ico = "📈" if h4_d == "BULLISH" else "📉" if h4_d == "BEARISH" else "🔄"
                    h4_dir_str = f" | {h4_ico} H4:{h4_d}(ADX:{h4_a})"

                # H1 trend display
                h1_d = tr.get("direction", "?")
                h1_ico = "📈" if h1_d == "BULLISH" else "📉" if h1_d == "BEARISH" else "🔄"

                system_state["teams"][team_name]["signals"][symbol] = to_native(sig)

                # Show H4→H1 alignment prominently in signal output
                mtf_status = ""
                if h4_trend and h4_trend.get("direction") not in ("SIDEWAYS", None):
                    if h4_trend["direction"] == h1_d:
                        mtf_status = f" | ✅ MTF ALIGNED ({h4_trend['direction']})"
                    else:
                        mtf_status = f" | ⛔ MTF CONFLICT (H4:{h4_trend['direction']} vs H1:{h1_d})"

                await emit(team_name, "SignalGenerator", "signal",
                    f"{s_ico} {symbol} SIGNAL: {sig['signal']} ({sig['strength']}) | "
                    f"Score: {sig['score']:+d}/20 | Conf: {adj_conf}%{mem_note}"
                    f"{h4_dir_str} | {h1_ico} H1:{h1_d}{mtf_status} | "
                    f"Entry: {entry['zone']} | {reasons_txt}",
                    {"symbol": symbol, "signal": sig, "entry": entry, "h4_trend": h4_trend})
                await asyncio.sleep(1.2)

                # ══ AGENT 5 : RISK MANAGER ══════════════════════════════════
                # Pass REAL account balance (not hardcoded 600)
                _real_balance = 600.0  # Default fallback
                if MT5_AVAILABLE:
                    try:
                        _acct = mt5.account_info()
                        if _acct:
                            _real_balance = float(_acct.balance)
                        else:
                            logger.warning(f"⚠️ MT5 account_info() returned None — using fallback balance ${_real_balance}")
                    except Exception as _bal_err:
                        logger.warning(f"⚠️ Balance fetch failed: {_bal_err} — using fallback ${_real_balance}")
                risk = RiskEngine.calculate(df_h1, sig, balance=_real_balance,
                                           risk_pct=_MAX_RISK_PCT, symbol=symbol)

                # Save RiskManager learning to team-specific file
                if AI_BRAIN_AVAILABLE:
                    try:
                        if risk["verdict"] == "NO TRADE":
                            save_learning(
                                topic=f"RiskManager {symbol} REJECTED",
                                lesson=f"Risk calculation rejected {symbol}: {risk['reason']}",
                                source="risk_manager",
                                team=team_name
                            )
                        else:
                            save_learning(
                                topic=f"RiskManager {symbol} APPROVED",
                                lesson=f"Risk calculation approved {symbol}: SL={risk['stop_loss']}, TP1={risk['tp1']}, "
                                       f"R:R={risk['rr1']}, Size={risk['pos_size']}, Risk Level={risk['risk_level']}",
                                source="risk_manager",
                                team=team_name
                            )
                    except Exception as learn_err:
                        logger.debug(f"RiskManager learning save error: {learn_err}")

                if risk["verdict"] == "NO TRADE":
                    await emit(team_name, "RiskManager", "risk",
                        f"🛡️ {symbol} RISK: {risk['reason']}", {"symbol": symbol, "risk": risk})
                    await asyncio.sleep(1.2)
                    continue  # ← CRITICAL FIX: Skip to next symbol — no SL/TP = crash if queued
                else:
                    await emit(team_name, "RiskManager", "risk",
                        f"🛡️ {symbol} RISK → SL: {risk['stop_loss']} | "
                        f"TP1: {risk['tp1']} | TP2: {risk['tp2']} | TP3: {risk['tp3']} | "
                        f"R:R TP1={risk['rr1']} TP2={risk['rr2']} | "
                        f"Size: {risk['pos_size']} | ATR: {risk['atr']} | "
                        f"Risk: {risk['risk_level']} | {risk['management']}",
                        {"symbol": symbol, "risk": risk})
                await asyncio.sleep(1.2)

                # ══ AGENT 6 : PATTERN MEMORY ════════════════════════════════
                pattern = PatternMemoryAgent.analyze(
                    symbol, df_h1, agent_memory, tr, amd, liquidity
                )
                p_score = pattern["pattern_score"]
                p_icon  = "🟢" if p_score >= 4 else "🟡" if p_score >= 0 else "🔴"
                pattern_lines = " | ".join(pattern["notes"][:4]) if pattern["notes"] else "No pattern flags"
                await emit(team_name, "PatternMemory", "analysis",
                    f"🧠 {symbol} PATTERN MEMORY [{pattern['session_dow']}] | "
                    f"Score: {p_icon} {p_score:+d}/10 | {pattern_lines}",
                    {"symbol": symbol, "pattern": pattern})
                await asyncio.sleep(1.0)

                # ══ AGENT 7 : OPERATOR MIND ═════════════════════════════════
                spread = float(tick.get("spread", 0)) if tick else 0.0
                operator = OperatorMindAgent.evaluate(
                    symbol=symbol, sig=sig, amd=amd, smc=smc, tr=tr,
                    h4_trend=h4_trend, spread=spread, sr=sr,
                    cp=float(cp), pattern=pattern, df=df_h1,
                    liquidity=liquidity,
                )
                op_verdict   = operator["verdict"]
                op_final_c   = operator["final_conf"]
                op_icon = ("✅" if op_verdict == "APPROVE" else
                           "⚠️" if op_verdict == "CAUTION" else "⛔")
                op_lines = " | ".join(operator["reasons"][:4]) if operator["reasons"] else ""

                # Apply operator's final confidence and verdict to sig dict
                sig["confidence"]       = op_final_c
                sig["operator_verdict"] = op_verdict
                if op_verdict == "REJECT":
                    sig["signal"]   = "HOLD"
                    sig["strength"] = "OPERATOR REJECTED"
                elif op_verdict == "CAUTION" and op_final_c < 60:
                    # CAUTION + below 60% = not worth it (balanced for volume)
                    sig["signal"]   = "HOLD"
                    sig["strength"] = "OPERATOR CAUTION (low conf)"
                    logger.info(f"⚠️ {symbol}: OperatorMind CAUTION with {op_final_c}% conf → blocking (need ≥60%)")
                system_state["teams"][team_name]["signals"][symbol] = to_native(sig)

                # Save OperatorMind learning to team-specific file
                if AI_BRAIN_AVAILABLE:
                    try:
                        save_learning(
                            topic=f"OperatorMind {symbol} {op_verdict}",
                            lesson=f"Operator evaluated {symbol} signal as {op_verdict} with {op_final_c}% confidence. "
                                   f"Reasons: {' | '.join(operator['reasons'][:3])}",
                            source="operator_mind",
                            team=team_name
                        )
                    except Exception as learn_err:
                        logger.debug(f"OperatorMind learning save error: {learn_err}")

                await emit(team_name, "OperatorMind", "smart_money",
                    f"🎯 {symbol} OPERATOR VERDICT: {op_icon} {op_verdict} | "
                    f"Final Confidence: {op_final_c}% (adj: {operator['conf_adj']:+d}) | "
                    f"{op_lines}",
                    {"symbol": symbol, "operator": operator})
                await asyncio.sleep(1.2)

                # ══ MT5 SIGNAL QUALITY GATE ═════════════════════════════
                # BILLIONAIRE QUALITY GATE:
                # 1. Score threshold (≥+6 / ≤-6)
                # 2. Session filter (Gold only London/NY)
                # 3. Daily drawdown protection (5% max)
                # 4. Smart pyramid check (add to winners only)
                # 5. Cooldown (10 min, or 5 min for pyramids)
                # 6. News confirmation (optional)
                _score     = sig.get("score", 0)
                _trade_dir = "BUY" if _score >= _MIN_SCORE_TO_TRADE else (
                             "SELL" if _score <= -_MIN_SCORE_TO_TRADE else None)

                # ── SESSION FILTER (Billionaire Edge) ───────────────────
                _session_ok, _session_name, _session_reason = is_trading_session(symbol)

                # ── DAILY DRAWDOWN CHECK ────────────────────────────────
                _dd_ok, _dd_pct, _dd_msg = check_daily_drawdown()

                # ── Cooldown check (with smart pyramid override) ────────
                _now = datetime.utcnow()
                _last_trade_dt = _symbol_last_trade.get(symbol)
                _cooldown_mins = _SYMBOL_COOLDOWN_MINUTES  # Default 10 min

                # Smart pyramid: if existing position is profitable, use shorter cooldown
                _pyramid_ok = False
                _pyramid_reason = ""
                if _trade_dir and _last_trade_dt:
                    _pyramid_ok, _pyramid_reason = check_pyramid_allowed(symbol, _trade_dir)
                    if _pyramid_ok and "Pyramid OK" in _pyramid_reason:
                        _cooldown_mins = _PYRAMID_COOLDOWN_MINUTES  # 5 min for pyramids

                _in_cooldown   = (
                    _last_trade_dt is not None and
                    (_now - _last_trade_dt).total_seconds() < _cooldown_mins * 60
                )
                _mins_since = int((_now - _last_trade_dt).total_seconds() / 60) if _last_trade_dt else 999

                # ── News confirmation check ──────────────────────────────
                _news_score  = news.get("score", 0)
                _news_sent   = news.get("sentiment", "NEUTRAL")
                _news_blocks = False
                if _NEWS_MUST_CONFIRM and _trade_dir is not None:
                    if _trade_dir == "BUY"  and _news_score <= -2:
                        _news_blocks = True   # News is BEARISH but signal is BUY
                    if _trade_dir == "SELL" and _news_score >= 2:
                        _news_blocks = True   # News is BULLISH but signal is SELL

                # ── DIRECTIONAL BIAS CHECK (prevent same-direction spam) ─
                _same_dir_count = _symbol_same_dir_count.get(symbol, 0)
                _last_dir = _symbol_last_direction.get(symbol)
                _dir_bias_blocks = False
                if _trade_dir and _last_dir == _trade_dir and _same_dir_count >= _MAX_SAME_DIR_TRADES:
                    _dir_bias_blocks = True

                # ── CORRELATION CHECK ───────────────────────────────────
                _corr_result = {"conflict": False, "boost": False, "conf_adj": 0, "reason": ""}
                if _trade_dir:
                    _corr_result = check_correlation_conflict(symbol, _trade_dir)
                    # Apply correlation confidence adjustment to signal
                    if _corr_result["conf_adj"] != 0 and not sig.get("filtered"):
                        sig["confidence"] = max(10, min(95, sig["confidence"] + _corr_result["conf_adj"]))
                        if _corr_result["boost"]:
                            sig["reasons"].append(f"🔗 {_corr_result['reason']}")
                _corr_blocks = _corr_result.get("conflict", False)

                # ── GLOBAL LIMITS (checked before gate) ──────────────────
                # 1. Total open trades across ALL teams/symbols
                _total_open = sum(
                    cnt for team_counts in _open_trade_counts.values()
                    for cnt in team_counts.values()
                )
                _total_open_exceeded = _total_open >= _MAX_OPEN_TRADES_TOTAL

                # 2. Daily trade cap (absolute limit per day)
                _daily_cap_exceeded = _daily_trade_counts.get("count", 0) >= _MAX_TRADES_PER_DAY_TOTAL

                # 3. Global cooldown (minimum time between ANY trade, any symbol)
                _global_last = max(
                    (dt for dt in _symbol_last_trade.values() if dt is not None),
                    default=None
                )
                _global_cooldown_active = (
                    _global_last is not None and
                    (_now - _global_last).total_seconds() < _GLOBAL_COOLDOWN_MINUTES * 60
                )

                # ── GATE SEQUENCE (ordered by priority) ─────────────────
                if _TRADING_HALTED_TODAY:
                    await emit(team_name, "OperatorMind", "error",
                        f"⛔ {symbol}: TRADING HALTED — daily drawdown limit hit ({_dd_pct:.1f}%). "
                        f"No new trades until tomorrow. Capital preservation mode.",
                        {"symbol": symbol, "drawdown_pct": _dd_pct})
                elif not _dd_ok:
                    await emit(team_name, "OperatorMind", "error",
                        f"⛔ {symbol}: {_dd_msg}",
                        {"symbol": symbol, "drawdown_pct": _dd_pct})
                elif _trade_dir is None:
                    await emit(team_name, "OperatorMind", "warning",
                        f"⏸ {symbol}: score={_score:+d} weak (need ≥{_MIN_SCORE_TO_TRADE} BUY / ≤-{_MIN_SCORE_TO_TRADE} SELL)",
                        {"symbol": symbol, "score": _score})
                elif not _session_ok:
                    await emit(team_name, "OperatorMind", "warning",
                        f"⏸ {symbol}: {_session_reason} — billionaire rule: trade only during optimal sessions",
                        {"symbol": symbol, "session": _session_name})
                elif _total_open_exceeded:
                    await emit(team_name, "OperatorMind", "warning",
                        f"⛔ {symbol}: MAX OPEN TRADES REACHED — {_total_open}/{_MAX_OPEN_TRADES_TOTAL} trades already open across all markets. "
                        f"Close existing trades first. Capital safety = priority.",
                        {"symbol": symbol, "total_open": _total_open, "max": _MAX_OPEN_TRADES_TOTAL})
                elif _daily_cap_exceeded:
                    await emit(team_name, "OperatorMind", "warning",
                        f"⛔ {symbol}: DAILY TRADE CAP HIT — {_daily_trade_counts['count']}/{_MAX_TRADES_PER_DAY_TOTAL} trades today. "
                        f"No more entries until tomorrow. Overtrading kills accounts.",
                        {"symbol": symbol, "daily_count": _daily_trade_counts['count']})
                elif _global_cooldown_active:
                    _global_secs = int((_now - _global_last).total_seconds())
                    await emit(team_name, "OperatorMind", "warning",
                        f"⏸ {symbol}: GLOBAL COOLDOWN — last trade was {_global_secs}s ago, need {_GLOBAL_COOLDOWN_MINUTES * 60}s between ANY trade. "
                        f"Prevents rapid-fire overtrading.",
                        {"symbol": symbol, "global_cooldown_secs": _global_secs})
                elif _open_trade_counts.get(team_name, {}).get(symbol, 0) >= _MAX_TRADES_PER_TEAM_PER_PAIR:
                    _cur_cnt = _open_trade_counts.get(team_name, {}).get(symbol, 0)
                    await emit(team_name, "OperatorMind", "warning",
                        f"⏸ {symbol}: max trades reached ({_cur_cnt}/{_MAX_TRADES_PER_TEAM_PER_PAIR}) — no new entry",
                        {"symbol": symbol, "open_count": _cur_cnt})
                elif _in_cooldown:
                    _cd_type = f"pyramid ({_cooldown_mins}min)" if _pyramid_ok else f"normal ({_cooldown_mins}min)"
                    await emit(team_name, "OperatorMind", "warning",
                        f"⏸ {symbol}: cooldown active [{_cd_type}] — {_mins_since}/{_cooldown_mins} min elapsed",
                        {"symbol": symbol, "cooldown_mins": _mins_since})
                elif _news_blocks:
                    await emit(team_name, "OperatorMind", "warning",
                        f"⏸ {symbol}: NEWS CONTRADICTS signal — "
                        f"signal={_trade_dir} but news is {_news_sent} (score {_news_score:+d}). Skipping.",
                        {"symbol": symbol, "news_score": _news_score})
                elif _dir_bias_blocks:
                    await emit(team_name, "OperatorMind", "warning",
                        f"🔄 {symbol}: DIRECTIONAL BIAS — {_same_dir_count} consecutive {_trade_dir} trades. "
                        f"Need opposite direction or wait. Preventing same-direction spam.",
                        {"symbol": symbol, "direction": _trade_dir, "same_dir_count": _same_dir_count})
                elif _corr_blocks:
                    await emit(team_name, "OperatorMind", "warning",
                        f"🔗 {symbol}: {_corr_result['reason']} — skipping to avoid correlated exposure",
                        {"symbol": symbol, "correlation": _corr_result})
                elif not system_state["mt5_connected"]:
                    await emit(team_name, "OperatorMind", "warning",
                        f"⏸ {symbol}: MT5 not connected (SIMULATION mode)",
                        {"symbol": symbol})
                else:
                    # ── AI Signal Validation (non-blocking) ────────────────────
                    # Ask AI to confirm the signal. If AI is down, auto-approves.
                    _ai_val = {"approved": True, "confidence_adj": 0, "ai_comment": "AI Brain unavailable — auto-approved"}
                    try:
                        if AI_BRAIN_AVAILABLE:
                            _ai_val = await ai_validate_signal(
                                symbol=symbol,
                                signal=_trade_dir,
                                score=_score,
                                reasons=sig.get("reasons", []),
                                price=float(cp),
                                atr=float(risk.get("atr", 0)),
                                news_sentiment=_news_sent,
                                team=team_name,
                            )
                            if _ai_val.get("ai_comment"):
                                await emit(team_name, "OperatorMind", "signal",
                                    f"🧠 AI VALIDATION {symbol}: {'✅' if _ai_val['approved'] else '❌'} "
                                    f"{_ai_val['ai_comment'][:150]}",
                                    {"symbol": symbol, "ai_validation": _ai_val})
                            # Apply confidence adjustment from AI
                            if _ai_val.get("confidence_adj", 0) != 0:
                                sig["confidence"] = max(10, min(95,
                                    sig["confidence"] + _ai_val["confidence_adj"]))
                    except Exception as _ai_err:
                        logger.warning(f"AI validation skipped: {_ai_err}")

                    # ── Recalculate position size if AI adjusted confidence ────
                    # FIX: Risk was calculated BEFORE AI changed confidence.
                    # Position size depends on confidence → must recalculate.
                    if _ai_val.get("confidence_adj", 0) != 0 and risk.get("verdict") != "NO TRADE":
                        risk = RiskEngine.calculate(df_h1, sig, balance=_real_balance,
                                                   risk_pct=_MAX_RISK_PCT, symbol=symbol)
                        logger.debug(f"Risk recalculated after AI adj: size={risk.get('pos_size')}")
                        # Guard: recalculated risk might be "NO TRADE" (e.g. R:R dropped)
                        if risk.get("verdict") == "NO TRADE":
                            await emit(team_name, "RiskManager", "warning",
                                f"🛡️ {symbol}: Risk recalc after AI adj → {risk.get('reason','NO TRADE')}",
                                {"symbol": symbol})
                            await asyncio.sleep(1.2)
                            continue

                    # ── Emit AI validation coordination event ──────────────────
                    if AI_BRAIN_AVAILABLE and _ai_val.get("ai_comment"):
                        _ai_approved = _ai_val.get('approved', True)
                        await emit(team_name, "AI_Brain", "analysis",
                            f"🧠 AI VALIDATION {symbol}: {'✅ APPROVED' if _ai_approved else '❌ REJECTED'} | "
                            f"AI Brain says: {_ai_val['ai_comment'][:100]} | "
                            f"Conf adj: {_ai_val.get('confidence_adj', 0):+d}",
                            {"symbol": symbol, "ai_validation": True,
                             "approved": _ai_approved,
                             "confidence_adj": _ai_val.get('confidence_adj', 0)})

                    # ── FINAL CONFIDENCE GATE (per-pair adaptive) ────────────────
                    _final_conf = sig.get("confidence", 0)
                    _pair_min_conf = _get_effective_gate(symbol)
                    _conf_passed = _final_conf >= _pair_min_conf

                    # ── COUNT CONFIRMATION SIGNALS (3+ required) ──────────────────
                    # Count distinct signal sources from reasons (technical, SMC, news, pattern, institutional)
                    _signal_sources = set()
                    _reasons = sig.get("reasons", [])
                    for reason in _reasons:
                        reason_lower = reason.lower()
                        if any(x in reason_lower for x in ["rsi", "macd", "bb", "ema", "adx"]):
                            _signal_sources.add("technical")
                        if any(x in reason_lower for x in ["smc", "fvg", "bos", "sweep", "amd phase"]):
                            _signal_sources.add("smc")
                        if any(x in reason_lower for x in ["news", "sentiment", "economic"]):
                            _signal_sources.add("news")
                        if any(x in reason_lower for x in ["pattern", "historical", "setup"]):
                            _signal_sources.add("pattern")
                        if any(x in reason_lower for x in ["institution", "killzone", "flow", "big player"]):
                            _signal_sources.add("institutional")
                    _conf_signal_count = len(_signal_sources)
                    _multi_conf_passed = _conf_signal_count >= _MIN_CONFIRMATION_SIGNALS

                    # ── SESSION QUALITY FILTER (high-quality hours) ──────────────
                    _current_hour_utc = datetime.utcnow().hour
                    _in_quality_session = (_LONDON_OVERLAP_UTC[0] <= _current_hour_utc < _LONDON_OVERLAP_UTC[1] or
                                         _NY_SESSION_UTC[0] <= _current_hour_utc < _NY_SESSION_UTC[1])
                    _quality_session_passed = (not _TRADING_QUALITY_FILTER) or _in_quality_session

                    # ── Queue as candidate (AI rejection OR low confidence OR missing confirmations = skip) ─
                    if not _ai_val.get("approved", True):
                        await emit(team_name, "OperatorMind", "warning",
                            f"⏸ {symbol}: AI REJECTED signal — {_ai_val.get('ai_comment', '')[:100]}",
                            {"symbol": symbol})
                    elif not _conf_passed:
                        await emit(team_name, "OperatorMind", "warning",
                            f"⛔ {symbol}: CONFIDENCE TOO LOW — {_final_conf}% < {_pair_min_conf}% required. "
                            f"{'(weak/dynamic pair — needs higher confidence)' if symbol in _WEAK_PAIRS or _DYNAMIC_GATE_ADJUSTMENTS.get(symbol, 0) > 0 else '(default threshold)'}",
                            {"symbol": symbol, "confidence": _final_conf, "required": _pair_min_conf})
                    elif not _multi_conf_passed:
                        await emit(team_name, "OperatorMind", "warning",
                            f"⛔ {symbol}: INSUFFICIENT CONFIRMATIONS — {_conf_signal_count} sources < {_MIN_CONFIRMATION_SIGNALS} required. "
                            f"Sources: {', '.join(_signal_sources) if _signal_sources else 'none'}",
                            {"symbol": symbol, "signals": _conf_signal_count, "required": _MIN_CONFIRMATION_SIGNALS})
                    elif not _quality_session_passed:
                        await emit(team_name, "OperatorMind", "warning",
                            f"⛔ {symbol}: POOR SESSION QUALITY — {_current_hour_utc:02d}:00 UTC outside high-liquidity hours. "
                            f"Trade during London (13-17 UTC) or NY (13-21 UTC) for better fills",
                            {"symbol": symbol, "hour": _current_hour_utc})
                    elif (TV_INDICATORS_AVAILABLE and tv_analysis is not None and
                          tv_analysis.get("tv_score", 0) == 0 and
                          not tv_analysis.get("growth_positive", True) and
                          abs(_score) < 12):
                        # TV growth negative + no TV score boost + non-elite signal → BLOCK
                        await emit(team_name, "OperatorMind", "warning",
                            f"⛔ {symbol}: TV GROWTH NEGATIVE — MACD({tv_analysis['macd']['growth_rate']:+.1f}%) + "
                            f"SBT({tv_analysis['supertrend']['growth_pct']:+.1f}%) both contracting. "
                            f"Score {_score:+d} not strong enough (need ≥12) to override growth gate.",
                            {"symbol": symbol, "tv_growth": False, "score": _score})
                    else:
                        if team_name not in _cycle_candidates:
                            _cycle_candidates[team_name] = []
                        _cur_cnt = _open_trade_counts.get(team_name, {}).get(symbol, 0)
                        _cycle_candidates[team_name].append({
                            "score":      _score,
                            "symbol":     symbol,
                            "direction":  _trade_dir,
                            "risk":       risk,
                            "sig":        sig,
                            "op_verdict": op_verdict,
                            "op_conf":    op_final_c,
                            "news":       news,
                            # Store per-symbol data for training snapshot (FIX: avoid scope leak)
                            "_tr":        tr,
                            "_mom":       mom,
                            "_bb":        bb,
                            "_amd":       amd,
                            "_h4_trend":  h4_trend,
                            "_inst":      inst_analysis,
                        })
                        await emit(team_name, "OperatorMind", "signal",
                            f"📌 CANDIDATE {_trade_dir} {symbol} | score={_score:+d} | "
                            f"Open on pair: {_cur_cnt}/{_MAX_TRADES_PER_TEAM_PER_PAIR} | "
                            f"News: {_news_sent}({_news_score:+d}) | "
                            f"Op: {op_verdict} {op_final_c}% — queued for execution",
                            {"symbol": symbol, "score": _score})

            # ══ FIRE QUEUED TRADES ═══════════════════════════════════════════
            # After all symbols analysed — execute every candidate that passed
            # the quality gate.  Max _MAX_TRADES_PER_TEAM_PER_PAIR (1) per pair.
            candidates = _cycle_candidates.pop(team_name, [])
            # Sort by: 1) Elite pair priority, 2) Score strength (strongest first)
            candidates.sort(key=lambda c: (
                c["symbol"] in _ELITE_PAIRS,  # Elite pairs first (True > False)
                abs(c["score"]),               # Then by signal strength
            ), reverse=True)

            for cand in candidates:
                _cand_sym   = cand["symbol"]
                _cand_dir   = cand["direction"]
                _cand_risk  = cand["risk"]
                _cand_sig   = cand["sig"]
                _cand_score = cand["score"]

                # Re-check limit at fire-time (previous cand may have raised count)
                _cur_cnt = _open_trade_counts.get(team_name, {}).get(_cand_sym, 0)
                if _cur_cnt >= _MAX_TRADES_PER_TEAM_PER_PAIR:
                    await emit(team_name, "OperatorMind", "warning",
                        f"⏩ {_cand_sym}: limit reached ({_cur_cnt}/{_MAX_TRADES_PER_TEAM_PER_PAIR}) — skipping",
                        {"symbol": _cand_sym})
                    continue

                # Safety guard: skip if risk dict is missing SL/TP (prevents KeyError crash)
                if "stop_loss" not in _cand_risk:
                    await emit(team_name, "OperatorMind", "warning",
                        f"⚠️ {_cand_sym}: risk dict missing stop_loss — skipping execution (verdict={_cand_risk.get('verdict','?')})",
                        {"symbol": _cand_sym})
                    continue

                await emit(team_name, "OperatorMind", "signal",
                    f"🚀 EXECUTING {_cand_dir} {_cand_sym} | score={_cand_score:+d} | "
                    f"risk={_cand_risk.get('pos_size','?')} | SL={_cand_risk.get('stop_loss','?')} | TP={_cand_risk.get('tp1','?')} | "
                    f"Trade {_cur_cnt+1}/{_MAX_TRADES_PER_TEAM_PER_PAIR} on this pair",
                    {"symbol": _cand_sym, "direction": _cand_dir, "score": _cand_score})

                exec_result = await mt5_execute_trade(
                    team_name, _cand_sym, _cand_sig, _cand_risk
                )

                if exec_result.get("success"):
                    ticket_str = str(exec_result.get("ticket", "?"))

                    # ── TRAINING: Capture trade snapshot for learning ────────
                    if TRAINING_AVAILABLE:
                        try:
                            # Use per-symbol data stored in candidate (not stale loop vars)
                            _c_tr = cand.get("_tr") or {}
                            _c_mom = cand.get("_mom") or {}
                            _c_bb = cand.get("_bb") or {}
                            _c_amd = cand.get("_amd") or {}
                            _c_h4 = cand.get("_h4_trend") or {}
                            _c_inst = cand.get("_inst") or {}
                            _c_news = cand.get("news") or {}

                            snap = TradeSnapshot.capture(
                                symbol=_cand_sym,
                                direction=_cand_dir,
                                score=_cand_score,
                                confidence=_cand_sig.get("confidence", 50),
                                h1_trend=_c_tr.get("direction", "SIDEWAYS"),
                                h4_trend=_c_h4.get("direction", "SIDEWAYS"),
                                rsi=_c_mom.get("rsi", 50),
                                adx=_c_tr.get("adx", 0),
                                macd_label=_c_mom.get("macd_label", ""),
                                bb_state=_c_bb.get("state", ""),
                                amd_phase=_c_amd.get("phase", ""),
                                news_sentiment=_c_news.get("sentiment", "NEUTRAL"),
                                session_hour=datetime.utcnow().hour,
                                institutional_direction=_c_inst.get("institutional_direction", "NEUTRAL"),
                                institutional_confidence=_c_inst.get("institutional_score", 50),
                                killzone=_c_inst.get("institutional", {}).get("killzone", "NONE") if isinstance(_c_inst.get("institutional"), dict) else "NONE",
                                volume_signal=_c_inst.get("institutional", {}).get("volume_signal", "NORMAL") if isinstance(_c_inst.get("institutional"), dict) else "NORMAL",
                                agents_involved=["InstitutionalFlow", "WebResearch", "CrossMarket", "EconomicCalendar", "SignalGenerator"],
                            )
                            TrainingEngine.record_entry(snap)
                            logger.info(f"📚 Training snapshot saved for {_cand_dir} {_cand_sym}")
                        except Exception as _train_err:
                            logger.warning(f"⚠️ Training snapshot FAILED [{symbol}]: {_train_err} — agents NOT learning from this trade!")

                    # ── DRAWDOWN RECOVERY: Apply lot multiplier from regime ──
                    if ADVANCED_AGENTS_AVAILABLE:
                        try:
                            _dd_adj = DrawdownRecoveryAgent.get_adjustments()
                            _lot_mult = _dd_adj.get("lot_multiplier", 1.0)
                            _regime_mult = 1.0
                            if _regime_data:
                                _regime_mult = _regime_data.get("position_size_mult", 1.0)
                            # Store lot adjustments for position management
                            exec_result["lot_multiplier"] = round(_lot_mult * _regime_mult, 2)
                            if _lot_mult != 1.0 or _regime_mult != 1.0:
                                logger.info(
                                    f"[ADV] {_cand_sym}: Lot adjusted — "
                                    f"DD: {_lot_mult:.2f}x, Regime: {_regime_mult:.2f}x = "
                                    f"Final: {exec_result['lot_multiplier']:.2f}x"
                                )
                        except Exception as _dd_err:
                            logger.debug(f"DrawdownRecovery lot adjustment error: {_dd_err}")

                    # ── Update trade counts + directional bias tracker ───────
                    _symbol_last_trade[_cand_sym] = datetime.utcnow()
                    # Increment DAILY trade counter (enforces _MAX_TRADES_PER_DAY_TOTAL)
                    _daily_trade_counts["count"] = _daily_trade_counts.get("count", 0) + 1
                    logger.info(f"📊 Daily trade count: {_daily_trade_counts['count']}/{_MAX_TRADES_PER_DAY_TOTAL}")
                    # Track consecutive same-direction trades
                    if _symbol_last_direction.get(_cand_sym) == _cand_dir:
                        _symbol_same_dir_count[_cand_sym] = _symbol_same_dir_count.get(_cand_sym, 0) + 1
                    else:
                        _symbol_same_dir_count[_cand_sym] = 1
                    _symbol_last_direction[_cand_sym] = _cand_dir
                    if team_name not in _open_trade_counts:
                        _open_trade_counts[team_name] = {}
                    _open_trade_counts[team_name][_cand_sym] = (
                        _open_trade_counts[team_name].get(_cand_sym, 0) + 1
                    )
                    _new_cnt = _open_trade_counts[team_name][_cand_sym]
                    # ── Record in system state ───────────────────────────────
                    system_state["active_trades"][ticket_str] = {
                        "team":      team_name,
                        "symbol":    _cand_sym,
                        "direction": _cand_dir,
                        "score":     _cand_score,
                        "price":     exec_result.get("price"),
                        "sl":        exec_result.get("sl"),
                        "tp":        exec_result.get("tp"),
                        "volume":    exec_result.get("volume"),
                        "opened_at": datetime.utcnow().isoformat(),
                    }
                    system_state["execution_stats"]["total_executed"] += 1
                    system_state["execution_stats"]["successful"]     += 1
                    # ── Broadcast success ────────────────────────────────────
                    await emit(team_name, "OperatorMind", "alert",
                        f"✅ TRADE PLACED ✅ | {_cand_dir} {_cand_sym} "
                        f"@ {exec_result.get('price','?')} | Ticket #{ticket_str} | "
                        f"SL={exec_result.get('sl','?')} TP={exec_result.get('tp','?')} | "
                        f"Open trades on pair: {_new_cnt}/{_MAX_TRADES_PER_TEAM_PER_PAIR}",
                        exec_result)
                    logger.info(
                        f"[{team_name}] ✅ {_cand_dir} {_cand_sym} Ticket#{ticket_str} "
                        f"@ {exec_result.get('price','?')} | pair count={_new_cnt}"
                    )
                else:
                    err_msg = exec_result.get("error", "Unknown error")
                    system_state["execution_stats"]["total_executed"] += 1
                    system_state["execution_stats"]["failed"]         += 1
                    await emit(team_name, "OperatorMind", "error",
                        f"❌ TRADE FAILED: {_cand_dir} {_cand_sym} — {err_msg}",
                        {"symbol": _cand_sym, "error": err_msg})
                    logger.error(f"[{team_name}] Trade FAILED {_cand_dir} {_cand_sym}: {err_msg}")

            # ══ AGENT 8+9 : COORDINATOR (confidence-gated) ═══════════════
            sigs  = system_state["teams"][team_name]["signals"]

            # Confidence gate — per-pair adaptive (weak pairs need higher confidence)
            approved_buys  = [s for s, v in sigs.items()
                              if v.get("signal") == "BUY"  and v.get("confidence", 0) >= _get_effective_gate(s)]
            approved_sells = [s for s, v in sigs.items()
                              if v.get("signal") == "SELL" and v.get("confidence", 0) >= _get_effective_gate(s)]
            low_conf       = [s for s, v in sigs.items()
                              if v.get("signal") not in ("HOLD",) and v.get("confidence", 0) < _get_effective_gate(s)]
            holds          = [s for s, v in sigs.items() if v.get("signal") == "HOLD"]

            bias = (
                "BULLISH"  if len(approved_buys)  > len(approved_sells) else
                "BEARISH"  if len(approved_sells) > len(approved_buys)  else
                "NEUTRAL"
            )
            avg_c = round(sum(v.get("confidence", 0) for v in sigs.values()) / max(len(sigs), 1), 0)

            system_state["teams"][team_name]["bias"]   = bias
            system_state["teams"][team_name]["status"] = bias

            quality_note = ""
            if low_conf:
                quality_note = f" | ⚠️ Low-conf filtered out: {low_conf} (below {_DEFAULT_CONF_GATE}%)"

            await emit(team_name, "Coordinator", "report",
                f"📋 {team_name} REPORT → Bias: {bias} | "
                f"🟢 BUY: {approved_buys or ['—']} | 🔴 SELL: {approved_sells or ['—']} | "
                f"🟡 HOLD/LOW-CONF: {holds + low_conf or ['—']} | "
                f"Avg Confidence: {avg_c}%{quality_note} | "
                f"9-Agent consensus forwarded to Admin...",
                {"team": team_name, "bias": bias, "signals": sigs})
            await asyncio.sleep(2)

            # ── Periodic Gemini key cooldown reset (every 15 min) ───────
            if AI_BRAIN_AVAILABLE and team_name == "METALS":  # Run once per cycle (METALS first)
                try:
                    from ai_brain import _reset_gemini_key_cooldowns, _get_gemini_key_stats
                    _reset_gemini_key_cooldowns()
                    stats = _get_gemini_key_stats()
                    logger.debug(f"🔑 Gemini Key Pool Status: {stats}")
                except Exception:
                    pass

            await asyncio.sleep(ANALYSIS_INTERVAL)

        except Exception as e:
            logger.error(f"{team_name} team error: {e}", exc_info=True)
            await emit(team_name, "DataFetcher", "error",
                f"❌ {team_name} error: {str(e)[:120]} — retrying in 30 s...")
            await asyncio.sleep(30)


# ═════════════════════════════════════════════════════════════════════
# ─────────────────────  ADMIN AGENT  ────────────────────────────────
# ═════════════════════════════════════════════════════════════════════
async def run_admin():
    await asyncio.sleep(25)   # Let teams produce initial data first

    while True:
        try:
            # ── Sync open positions: remove closed trades from guards ─────
            if system_state["mt5_connected"]:
                open_tickets = await mt5_sync_open_positions()  # {ticket_str: symbol}
                # Find tickets we tracked that MT5 no longer shows as open
                closed = [t for t in list(system_state["active_trades"].keys())
                          if t not in open_tickets]
                for t in closed:
                    trade_info = system_state["active_trades"].pop(t, {})
                    sym  = trade_info.get("symbol", "?")
                    tnm  = trade_info.get("team",   "")
                    # Decrement open count for this team+symbol
                    if tnm and tnm in _open_trade_counts:
                        cnt = _open_trade_counts[tnm].get(sym, 0)
                        if cnt > 0:
                            _open_trade_counts[tnm][sym] = cnt - 1
                    _remaining = _open_trade_counts.get(tnm, {}).get(sym, 0)
                    await emit("ADMIN", "AdminAgent", "signal",
                        f"📌 POSITION CLOSED: {trade_info.get('direction','?')} {sym} "
                        f"(Ticket #{t}) — SL/TP hit or manual close. "
                        f"Remaining open on pair: {_remaining}/{_MAX_TRADES_PER_TEAM_PER_PAIR}",
                        {"ticket": t, "symbol": sym})

                # Sync open_tickets to active_trades (restart recovery)
                # Any ticket not already tracked gets logged (count not adjusted to avoid double-count)
                for t, sym in open_tickets.items():
                    if t not in system_state["active_trades"]:
                        system_state["active_trades"][t] = {
                            "team":      "UNKNOWN",
                            "symbol":    sym,
                            "direction": "?",
                            "opened_at": "recovered",
                        }

                # ── Trailing Stop Manager: protect profits ──────────────────
                try:
                    trail_results = await manage_trailing_stops()
                    for tr in trail_results:
                        await emit("ADMIN", "AdminAgent", "signal",
                            f"🔒 DOLLAR TRAIL: {tr['symbol']} #{tr['ticket']} — "
                            f"SL {tr['old_sl']} → {tr['new_sl']} | "
                            f"{tr['progress']} | P&L: {tr.get('current_profit', '?')}",
                            tr)
                except Exception as _trail_err:
                    logger.warning(f"Trailing stop error: {_trail_err}")

                # ── Partial Take Profit: lock 50% at TP1 ─────────────────────
                try:
                    partial_results = await manage_partial_tp()
                    for pr in partial_results:
                        await emit("ADMIN", "AdminAgent", "alert",
                            f"💰 PARTIAL TP1: {pr['symbol']} #{pr['ticket']} — "
                            f"Closed {pr['closed_vol']} lots @ {pr['close_price']} | "
                            f"Remaining {pr['remain_vol']} lots running to TP2 | "
                            f"Progress: {pr['progress']}",
                            pr)
                except Exception as _ptp_err:
                    logger.warning(f"Partial TP error: {_ptp_err}")

                # ── Closed Trade Monitor: update anti-martingale tracker ──────
                try:
                    await check_closed_trades()
                except Exception as _ctm_err:
                    logger.warning(f"Closed trade monitor error: {_ctm_err}")

                # ── Geopolitical Scan: Update war status ──────────────────────
                if GEO_AVAILABLE:
                    try:
                        _geo_status = await GeopoliticalRiskAgent.scan()
                        # Log war status changes
                        _active_wars = [
                            f"{s.get('name', k)}({s.get('status', '?')})"
                            for k, s in _geo_status.items()
                            if s.get("status") in ("ACTIVE", "CEASEFIRE")
                        ]
                        if _active_wars:
                            await emit("ADMIN", "GeopoliticalAgent", "smart_money",
                                f"🌍 WAR STATUS: {' | '.join(_active_wars)} | "
                                f"{GeopoliticalRiskAgent.report().split(chr(10))[0]}",
                                {"wars": _geo_status})
                    except Exception as _geo_err:
                        logger.debug(f"Geo scan error: {_geo_err}")

                # ── Smart Recovery: FULLY DISABLED ────────────────
                # SmartRecovery caused multiple critical issues:
                # 1. Auto-reverse opened SELL when signal was BUY (dashboard ≠ MT5)
                # 2. H1_FLIP_EXIT closed trades at tiny loss (-$0.01) too aggressively
                # 3. Closed XAGUSD BUY at -$9.45 and XAUUSD BUY at -$4.68 unnecessarily
                # Main signal pipeline SL/TP handles exits. SmartRecovery = OFF.
                if False and SMART_RECOVERY_AVAILABLE:
                    try:
                        # Collect H1/H4 trends from system_state (stored directly by team loop)
                        _all_h1_trends = {}
                        _all_h4_trends = {}
                        for _t_name, _t_data in system_state.get("teams", {}).items():
                            for _s_sym, _trend_data in _t_data.get("trends", {}).items():
                                if isinstance(_trend_data, dict):
                                    _all_h1_trends[_s_sym] = _trend_data.get("h1", "SIDEWAYS")
                                    _all_h4_trends[_s_sym] = _trend_data.get("h4", "SIDEWAYS")

                        recovery_actions = await run_smart_recovery(
                            _all_h1_trends, _all_h4_trends
                        )

                        for ra in recovery_actions:
                            _ra_type = ra.get("recovery_type", ra.get("action", "?"))
                            _ra_icon = {
                                "H1_FLIP_EXIT": "🔄",
                                "SMART_REVERSE": "⚡",
                                "TIGHTEN_SL": "📉",
                                "TIME_EXIT": "⏰",
                                "BREAKEVEN_PROTECT": "🔒",
                            }.get(_ra_type, "🔧")

                            await emit("ADMIN", "SmartRecovery", "alert",
                                f"{_ra_icon} {ra.get('reason', 'Recovery action taken')}",
                                ra)

                            # DISABLED: Auto-reverse was CONFLICTING with main signal system.
                            # SmartRecovery would see H4 BEARISH → close BUY → open SELL,
                            # but SignalGenerator has H4 exhaustion override → still says BUY.
                            # Result: dashboard shows BUY, MT5 has SELL = DISASTER.
                            # Now SmartRecovery only CLOSES bad trades, NEVER opens new ones.
                            # Only the main signal pipeline (run_team) should open trades.
                            if ra.get("reverse_signal"):
                                _rev_sym = ra["symbol"]
                                _rev_dir = ra["reverse_signal"]
                                await emit("ADMIN", "SmartRecovery", "warning",
                                    f"🔄 REVERSE SIGNAL: {_rev_dir} {_rev_sym} detected — "
                                    f"logged only (auto-reverse disabled to prevent signal conflict). "
                                    f"Main signal pipeline will handle next entry.",
                                    ra)
                                logger.info(f"SmartRecovery: reverse signal {_rev_dir} {_rev_sym} — logged only (disabled)")

                        if recovery_actions:
                            logger.info(
                                f"🔧 Smart Recovery: {len(recovery_actions)} actions taken this cycle"
                            )

                    except Exception as _sr_err:
                        logger.warning(f"Smart recovery error: {_sr_err}")

            teams_data = system_state["teams"]

            # Aggregate all signals
            all_sigs: Dict[str, dict] = {}
            for tname, tdata in teams_data.items():
                for sym, s in tdata.get("signals", {}).items():
                    all_sigs[sym] = {**s, "team": tname}

            if not all_sigs:
                await asyncio.sleep(15)
                continue

            buys  = sum(1 for s in all_sigs.values() if s.get("signal") == "BUY")
            sells = sum(1 for s in all_sigs.values() if s.get("signal") == "SELL")
            holds = sum(1 for s in all_sigs.values() if s.get("signal") == "HOLD")
            total = buys + sells + holds

            bias = (
                "⚡ STRONGLY BULLISH"  if buys  >= total * 0.70 else
                "📈 BULLISH"          if buys  >  sells + 1    else
                "📉 BEARISH"          if sells >  buys  + 1    else
                "🔻 STRONGLY BEARISH" if sells >= total * 0.70 else
                "⚖️ NEUTRAL / MIXED"
            )

            system_state["admin"]["market_bias"]   = bias
            system_state["admin"]["signal_count"]  = {"BUY": buys, "SELL": sells, "HOLD": holds}

            # Active trade summary
            active_cnt = len(system_state["active_trades"])
            exec_stats = system_state["execution_stats"]
            if active_cnt > 0:
                trade_labels = ", ".join(
                    v["direction"] + " " + v["symbol"]
                    for v in list(system_state["active_trades"].values())[:3]
                )
                active_summary = f" | 🔴 LIVE TRADES: {active_cnt} ({trade_labels})"
            else:
                active_summary = " | 💤 No open positions"

            await emit("ADMIN", "AdminAgent", "admin",
                f"👁️ ADMIN OVERVIEW — 3 teams reporting | Instruments: {total} | "
                f"🟢 BUY: {buys}  🔴 SELL: {sells}  🟡 HOLD: {holds} | Overall bias: {bias} | "
                f"Executed today: {exec_stats['daily_count']} (0.01 lot/trade){active_summary}",
                {"buy": buys, "sell": sells, "hold": holds, "bias": bias,
                 "active_trades": system_state["active_trades"],
                 "exec_stats": exec_stats})
            await asyncio.sleep(2)

            # High-confidence alerts
            hot = sorted(
                [(sym, d) for sym, d in all_sigs.items()
                 if d.get("confidence", 0) >= 75 and d.get("signal") != "HOLD"],
                key=lambda x: x[1]["confidence"], reverse=True
            )
            for sym, d in hot[:4]:
                t_icon = TEAMS.get(d.get("team",""), {}).get("icon","")
                e_ico  = "🚨" if d["signal"] == "BUY" else "⛔"
                await emit("ADMIN", "AdminAgent", "alert",
                    f"{e_ico} HIGH-CONFIDENCE: {t_icon} {sym} → {d['signal']} ({d['strength']}) | "
                    f"Confidence: {d['confidence']}% | {' | '.join(d.get('reasons',[])[:3])}",
                    {"symbol": sym, "signal": d})
                await asyncio.sleep(0.7)

            await asyncio.sleep(2)

            # Cross-market correlation
            mb = teams_data.get("METALS", {}).get("bias", "NEUTRAL")
            fb = teams_data.get("FOREX",  {}).get("bias", "NEUTRAL")
            cb = teams_data.get("CRYPTO", {}).get("bias", "NEUTRAL")

            corr_msg = ""
            if mb == "BULLISH" and cb == "BULLISH":
                corr_msg = "📈 RISK-ON environment — Metals & Crypto both bullish → USD weakness / inflation demand"
            elif mb == "BULLISH" and cb == "BEARISH":
                corr_msg = "🏛️ SAFE HAVEN ROTATION — Gold up, Crypto down → Classic risk-off, prefer Gold"
            elif mb == "BEARISH" and cb == "BULLISH":
                corr_msg = "⚡ SPECULATIVE RISK-ON — Crypto leads, Gold lags → High risk appetite, digital assets favoured"
            elif mb == "BEARISH" and cb == "BEARISH":
                corr_msg = "🔻 BROAD RISK-OFF — Both safe havens & crypto under pressure → Cash / USD strength"

            if corr_msg:
                system_state["admin"]["correlation"] = corr_msg
                await emit("ADMIN", "AdminAgent", "admin",
                    f"🔗 CROSS-MARKET CORRELATION: {corr_msg} | "
                    f"Metals: {mb} | Forex: {fb} | Crypto: {cb}",
                    {"metals": mb, "forex": fb, "crypto": cb})
                await asyncio.sleep(1.5)

            # Operator-level narrative
            await emit("ADMIN", "AdminAgent", "admin",
                f"🧠 OPERATOR SUMMARY: Smart money appears to be "
                f"{'ACCUMULATING broad risk assets' if buys > sells + 2 else 'DISTRIBUTING into strength' if sells > buys + 2 else 'CONSOLIDATING — no dominant AMD direction'}. "
                f"High-confidence setups: {len(hot)} | Monitor {', '.join([s for s,_ in hot[:3]])} for entries.",
                {"hot_symbols": [s for s, _ in hot[:3]]})

            # Agent learning accuracy report
            mem_report = agent_memory.report()
            await emit("ADMIN", "AdminAgent", "admin",
                f"📚 AGENT LEARNING REPORT — Per-symbol signal accuracy: {mem_report}",
                {"learning": mem_report})

            # Daily stats reset at UTC midnight
            today = datetime.utcnow().strftime("%Y-%m-%d")
            if system_state["daily_stats"]["date"] != today:
                system_state["daily_stats"] = {
                    "date": today,
                    "signal_count": 0,
                    "approved_signals": sum(1 for s in all_sigs.values() if s.get("signal") != "HOLD"),
                    "rejected_signals": sum(1 for s in all_sigs.values() if s.get("operator_verdict") == "REJECT"),
                }
            else:
                system_state["daily_stats"]["signal_count"] += total
                system_state["daily_stats"]["approved_signals"] += buys + sells
                system_state["daily_stats"]["rejected_signals"] += sum(
                    1 for s in all_sigs.values() if s.get("operator_verdict") == "REJECT"
                )
            ds = system_state["daily_stats"]
            await emit("ADMIN", "AdminAgent", "admin",
                f"📊 DAILY STATS [{ds['date']}]: "
                f"Signals: {ds['signal_count']} | "
                f"Approved: {ds['approved_signals']} | "
                f"Rejected: {ds['rejected_signals']} | "
                f"Rejection rate: {round(ds['rejected_signals']/max(ds['signal_count'],1)*100,1)}%",
                {"daily_stats": ds})

            # Correlated risk monitor: warn if multiple pairs in same direction
            buy_teams  = {sym: d["team"] for sym, d in all_sigs.items() if d.get("signal") == "BUY"}
            sell_teams = {sym: d["team"] for sym, d in all_sigs.items() if d.get("signal") == "SELL"}
            if buys >= 4:
                await emit("ADMIN", "AdminAgent", "alert",
                    f"⚠️ CORRELATED RISK WARNING: {buys} BUY signals active simultaneously "
                    f"({list(buy_teams.keys())}) — one macro event could trigger cascading losses. "
                    f"Reduce individual sizes by 40%.",
                    {"correlated_buys": list(buy_teams.keys())})
            if sells >= 4:
                await emit("ADMIN", "AdminAgent", "alert",
                    f"⚠️ CORRELATED RISK WARNING: {sells} SELL signals active simultaneously "
                    f"({list(sell_teams.keys())}) — consider total exposure limit.",
                    {"correlated_sells": list(sell_teams.keys())})

            await asyncio.sleep(ANALYSIS_INTERVAL)

        except Exception as e:
            logger.error(f"Admin agent error: {e}", exc_info=True)
            await asyncio.sleep(15)


# ═════════════════════════════════════════════════════════════════════
# MESSAGE BROADCASTER
# ═════════════════════════════════════════════════════════════════════
async def broadcaster():
    """Drain message_queue → broadcast to all WebSocket clients."""
    while True:
        try:
            msg = await asyncio.wait_for(message_queue.get(), timeout=0.5)
            await ws_manager.broadcast({"type": "msg", "payload": msg})
            # Piggy-back a lightweight state update
            await ws_manager.broadcast({
                "type": "state",
                "payload": {
                    "teams": {
                        n: {
                            "prices":  d.get("prices",  {}),
                            "signals": d.get("signals", {}),
                            "bias":    d.get("bias",   "NEUTRAL"),
                            "status":  d.get("status", "—"),
                        }
                        for n, d in system_state["teams"].items()
                    },
                    "admin":          system_state["admin"],
                    "mt5":            system_state["mt5_connected"],
                    "mode":           system_state["mode"],
                    "active_trades":  system_state["active_trades"],
                    "exec_stats":     system_state["execution_stats"],
                },
            })
            message_queue.task_done()
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.warning(f"Broadcaster error: {e}")


# ═════════════════════════════════════════════════════════════════════
# FASTAPI  ROUTES
# ═════════════════════════════════════════════════════════════════════
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    await websocket.send_json({
        "type": "init",
        "payload": {
            "state":   system_state,
            "config":  {n: {"color": v["color"], "icon": v["icon"]} for n, v in TEAMS.items()},
        },
    })
    try:
        while True:
            raw = await websocket.receive_text()
            # ── Handle incoming admin chat messages ───────────────
            try:
                incoming = json.loads(raw)
                if incoming.get("type") == "admin_chat":
                    logger.info(f"💬 Admin chat received: {incoming.get('text','')[:80]} → {incoming.get('target','ALL')}")
                    asyncio.create_task(_handle_admin_chat(incoming))
            except json.JSONDecodeError:
                pass  # Ignore non-JSON pings
            except Exception as chat_err:
                logger.error(f"Chat handler error: {chat_err}", exc_info=True)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/api/state")
async def api_state():
    return JSONResponse(system_state)


@app.get("/api/liquidity")
async def api_liquidity():
    """Liquidity zones and sweep data for all symbols across all teams."""
    liquidity_data = {}
    for team_name in TEAMS:
        team_liq = system_state.get("teams", {}).get(team_name, {}).get("liquidity", {})
        for sym, data in team_liq.items():
            liquidity_data[sym] = to_native(data)
    return JSONResponse(liquidity_data)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    with open(html_path, encoding="utf-8") as f:
        return f.read()


# ─────────────────────────────────────────────────────────────────────
# AI BRAIN INTELLIGENCE DASHBOARD — Complete visibility into AI pipeline
# ─────────────────────────────────────────────────────────────────────
@app.get("/brain", response_class=HTMLResponse)
async def brain_dashboard():
    """AI Brain Intelligence Dashboard — shows how AI agents work, learn, collect data."""
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_brain_dashboard.html")
    with open(html_path, encoding="utf-8") as f:
        return f.read()


_AGENTS_DIR = os.path.dirname(os.path.abspath(__file__))

@app.get("/api/prediction_memory")
async def api_prediction_memory():
    """Serve prediction_memory.json for the brain dashboard."""
    fpath = os.path.join(_AGENTS_DIR, "prediction_memory.json")
    try:
        with open(fpath, encoding="utf-8") as f:
            return JSONResponse(json.load(f))
    except Exception:
        return JSONResponse({})

@app.get("/api/agent_memory")
async def api_agent_memory():
    """Serve agent_memory.json for the brain dashboard."""
    fpath = os.path.join(_AGENTS_DIR, "agent_memory.json")
    try:
        with open(fpath, encoding="utf-8") as f:
            return JSONResponse(json.load(f))
    except Exception:
        return JSONResponse({})

@app.get("/api/agent_learnings")
async def api_agent_learnings():
    """Serve agent_learnings.json for the brain dashboard."""
    fpath = os.path.join(_AGENTS_DIR, "agent_learnings.json")
    try:
        with open(fpath, encoding="utf-8") as f:
            return JSONResponse(json.load(f))
    except Exception:
        return JSONResponse([])

@app.get("/api/agent_training_data")
async def api_agent_training_data():
    """Serve agent_training_data.json for the brain dashboard."""
    fpath = os.path.join(_AGENTS_DIR, "agent_training_data.json")
    try:
        with open(fpath, encoding="utf-8") as f:
            return JSONResponse(json.load(f))
    except Exception:
        return JSONResponse({})

@app.get("/api/institutional_positions")
async def api_institutional_positions():
    """Serve institutional_positions.json for the brain dashboard."""
    fpath = os.path.join(_AGENTS_DIR, "institutional_positions.json")
    try:
        with open(fpath, encoding="utf-8") as f:
            return JSONResponse(json.load(f))
    except Exception:
        return JSONResponse({})

@app.get("/api/continuous_training")
async def api_continuous_training():
    """Status of continuous ML training loop + TrainingEngine report."""
    result = {
        "loop_status": system_state.get("continuous_training", {}),
        "training_report": TrainingEngine.report() if TRAINING_AVAILABLE else "Training not available",
        "ml_active": TRAINING_AVAILABLE,
    }
    if TRAINING_AVAILABLE:
        TrainingEngine.load()
        result["symbol_stats"] = TrainingEngine._data.get("symbol_stats", {})
        result["blacklisted"] = TrainingEngine._data.get("blacklisted_symbols", [])
        result["regime_stats"] = TrainingEngine._data.get("regime_stats", {})
        result["ml_accuracy"] = TrainingEngine._data.get("ml_model_accuracy", 0)
        result["total_trades"] = len([t for t in TrainingEngine._data.get("trades", []) if t.get("outcome")])
    return JSONResponse(result)

@app.get("/api/analytics")
async def api_analytics():
    """Comprehensive trading analytics — P&L, win rates, drawdown, per-symbol performance."""
    result = {
        "timestamp": datetime.now().isoformat(),
        "system_uptime": system_state.get("started_at", ""),
        "mode": system_state.get("mode", "SIMULATION"),
        "execution_stats": system_state.get("execution_stats", {}),
        "active_trades": {},
        "daily_pnl": 0,
        "total_pnl": 0,
        "win_rate": 0,
        "consecutive_losses": _consecutive_losses,
        "loss_multiplier": get_loss_streak_multiplier(),
        "trading_halted": _TRADING_HALTED_TODAY,
        "per_symbol": {},
        "per_team": {},
        "correlation_groups": _CORRELATION_GROUPS,
    }

    # Active trades summary
    active = system_state.get("active_trades", {})
    result["active_trades"] = {
        "count": len(active),
        "trades": [
            {"symbol": t.get("symbol"), "direction": t.get("direction"),
             "entry_price": t.get("entry_price"), "team": t.get("team")}
            for t in active.values()
        ]
    }

    # Training-based analytics
    if TRAINING_AVAILABLE:
        TrainingEngine.load()
        trades = TrainingEngine._data.get("trades", [])
        resolved = [t for t in trades if t.get("outcome")]
        wins = [t for t in resolved if t["outcome"] == "WIN"]
        losses = [t for t in resolved if t["outcome"] == "LOSS"]

        result["total_pnl"] = round(sum(t.get("pnl", 0) for t in resolved), 2)
        result["win_rate"] = round(len(wins) / len(resolved) * 100, 1) if resolved else 0
        result["total_trades"] = len(resolved)
        result["wins"] = len(wins)
        result["losses"] = len(losses)
        result["avg_win"] = round(sum(t.get("pnl", 0) for t in wins) / len(wins), 2) if wins else 0
        result["avg_loss"] = round(sum(t.get("pnl", 0) for t in losses) / len(losses), 2) if losses else 0

        # Profit factor
        gross_profit = sum(t.get("pnl", 0) for t in wins)
        gross_loss = abs(sum(t.get("pnl", 0) for t in losses))
        result["profit_factor"] = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0

        # Per-symbol performance — force _learn if stats not built yet
        sym_stats = TrainingEngine._data.get("symbol_stats", {})
        if not sym_stats and resolved:
            try:
                TrainingEngine._learn()
                sym_stats = TrainingEngine._data.get("symbol_stats", {})
            except Exception:
                pass
        result["per_symbol"] = sym_stats

        # Per-team aggregation
        for team_name, team_cfg in TEAMS.items():
            team_syms = team_cfg["symbols"]
            team_trades = [t for t in resolved if t.get("symbol") in team_syms]
            team_wins = [t for t in team_trades if t["outcome"] == "WIN"]
            team_pnl = sum(t.get("pnl", 0) for t in team_trades)
            result["per_team"][team_name] = {
                "trades": len(team_trades),
                "wins": len(team_wins),
                "win_rate": round(len(team_wins) / len(team_trades) * 100, 1) if team_trades else 0,
                "pnl": round(team_pnl, 2),
            }

        # Recent trades (last 20)
        result["recent_trades"] = [
            {
                "symbol": t.get("symbol"),
                "direction": t.get("direction"),
                "outcome": t.get("outcome"),
                "pnl": t.get("pnl", 0),
                "score": t.get("score", 0),
                "confidence": t.get("confidence", 0),
                "entry_time": t.get("entry_time", ""),
                "close_time": t.get("close_time", ""),
            }
            for t in resolved[-20:]
        ]

        # ML model info
        result["ml"] = {
            "active": TrainingEngine._ml_model is not None,
            "accuracy": TrainingEngine._data.get("ml_model_accuracy", 0),
            "top_features": TrainingEngine._data.get("ml_top_features", []),
        }

        # Regime detection
        result["regimes"] = TrainingEngine._data.get("regime_stats", {})

    return JSONResponse(result)


# ─────────────────────────────────────────────────────────────────────
# AI PROVIDER STATUS — Real-time view of all 7 AI providers
# ─────────────────────────────────────────────────────────────────────
@app.get("/api/ai_providers")
async def api_ai_providers():
    """Real-time status of all 7 AI providers — failures, routing, keys."""
    try:
        from ai_brain import (
            _provider_failures, _provider_order, _TASK_ROUTING,
            _gemini_keys, _openrouter_keys,
            GROQ_API_KEY, XAI_API_KEY, CEREBRAS_API_KEY,
            COHERE_API_KEY, TOGETHER_API_KEY,
            GROQ_MODEL, XAI_MODEL, CEREBRAS_MODEL, COHERE_MODEL, TOGETHER_MODEL,
        )

        providers = {}
        _key_counts = {
            "openrouter": len(_openrouter_keys),
            "gemini": len(_gemini_keys),
            "cerebras": 1 if CEREBRAS_API_KEY else 0,
            "groq": 1 if GROQ_API_KEY else 0,
            "xai": 1 if XAI_API_KEY else 0,
            "together": 1 if TOGETHER_API_KEY else 0,
            "cohere": 1 if COHERE_API_KEY else 0,
        }
        _models = {
            "openrouter": "DeepSeek R1 (free)",
            "gemini": "Gemini 2.0 Flash",
            "cerebras": CEREBRAS_MODEL,
            "groq": GROQ_MODEL,
            "xai": XAI_MODEL,
            "together": TOGETHER_MODEL,
            "cohere": COHERE_MODEL,
        }
        _labels = {
            "openrouter": "OpenRouter",
            "gemini": "Google Gemini",
            "cerebras": "Cerebras",
            "groq": "Groq",
            "xai": "xAI Grok",
            "together": "Together AI",
            "cohere": "Cohere",
        }

        for p in _provider_order:
            failures = _provider_failures.get(p, 0)
            has_key = _key_counts.get(p, 0) > 0
            providers[p] = {
                "name": _labels.get(p, p),
                "model": _models.get(p, "unknown"),
                "keys": _key_counts.get(p, 0),
                "failures": failures,
                "status": "ACTIVE" if has_key and failures < 3 else "DOWN" if failures >= 3 else "NO_KEY",
                "disabled": failures >= 3,
            }

        return JSONResponse({
            "providers": providers,
            "provider_order": _provider_order,
            "task_routing": _TASK_ROUTING,
            "total_active": sum(1 for p in providers.values() if p["status"] == "ACTIVE"),
            "total_providers": len(providers),
        })
    except Exception as e:
        return JSONResponse({"error": str(e), "providers": {}})


# ═════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False, log_level="info")
