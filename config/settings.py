"""
MULTI-MARKET AI TRADING BOT - Configuration Settings
======================================================
FULL MULTI-MARKET MODE - 4 TEAMS (METALS, FOREX, CRYPTO, COMMODITIES)
All pairs enabled. Blacklisted pairs removed. New commodities team added.
Uses M5 for entries, M15/H1 for confirmation, H4 for trend bias.
Updated: 2026-04-14
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# =============================================================================
# MT5 CONNECTION SETTINGS (OctaFX)
# =============================================================================
MT5_LOGIN = int(os.getenv("MT5_LOGIN", 0))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "OctaFX-Demo")

# =============================================================================
# TRADING PAIRS - FULL MULTI-MARKET MODE (4 TEAMS)
# Updated 2026-04-14: All blacklisted pairs removed. New pairs + COMMODITIES team added.
# =============================================================================
TRADING_PAIRS = [
    # ── TEAM 1: METALS ───────────────────────────────────────────────
    "XAUUSD",  # Gold   - SWING mode H4/Daily, star performer
    "XAGUSD",  # Silver - Correlated with gold, good volatility
    # ── TEAM 2: FOREX ────────────────────────────────────────────────
    "GBPJPY",  # 97.7% prediction accuracy - STAR PERFORMER
    "USDCAD",  # 87.0% prediction accuracy - strong secondary
    "USDCHF",  # Tight spreads, good for London session
    "EURUSD",  # Most liquid forex pair, London/NY sessions
    "GBPUSD",  # High volatility, London open plays
    "AUDUSD",  # Commodity currency, Asian + London sessions
    "USDJPY",  # High liquidity, low spread
    "NZDUSD",  # Commodity currency, Asian + London sessions
    "EURJPY",  # High volatility cross pair
    # 'EURGBP',   # [R10 2026-04-23] DROPPED — only loser in profit-max backtest (-$39).
    "AUDJPY",  # Risk-on pair, good Asian session
    "CADJPY",  # Oil-linked, good volatility
    # ── TEAM 3: CRYPTO ───────────────────────────────────────────────
    "BTCUSD",  # Bitcoin - 24/7 trading, high volatility
    "ETHUSD",  # Ethereum - 24/7, follows BTC
    # ── TEAM 4: COMMODITIES (NEW) ─────────────────────────────────────
    # 2026-04-22: Broker (OctaFX-Demo) symbol names verified via mt5.symbols_get():
    #   WTI crude     -> XTIUSD   (was 'USOIL', not present at broker)
    #   Brent crude   -> XBRUSD   (was 'UKOIL', not present at broker)
    #   Natural gas   -> XNGUSD   (already correct)
    #   CORN / WHEAT  -> NOT OFFERED by OctaFX-Demo, removed from rotation
    "XTIUSD",  # WTI Crude Oil  - high volatility, news-driven
    "XBRUSD",  # Brent Crude    - correlated with XTIUSD
    "XNGUSD",  # Natural Gas    - seasonal volatility
]

# =============================================================================
# GOLD SWING TRADING MODE (replaces scalping for XAUUSD)
# =============================================================================
GOLD_SWING_MODE = True  # True = swing trading on H4/Daily, False = legacy scalping

GOLD_SWING = {
    # Timeframes for gold swing trading
    "entry_timeframe": "H4",  # Primary entry on H4
    "trend_timeframe": "D1",  # Daily for trend bias
    "confirmation_timeframe": "H1",  # H1 for entry timing
    # EMA parameters for swing (slower than scalp)
    "ema_fast": 21,
    "ema_slow": 50,
    "ema_trend": 200,
    # RSI for swing (standard, not fast)
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    # Wider SL/TP for gold volatility
    "sl_atr_mult": 5.0,  # 5x ATR (was 2x for scalping)
    "tp_atr_mult": 10.0,  # 10x ATR (was 3.5x)
    "min_rr": 2.0,  # Minimum 1:2 R:R
    # Trade frequency limits
    "max_trades_per_week": 3,  # Max 3 trades per week (not per day)
    "max_trades_per_day": 1,  # Max 1 per day
    "trade_cooldown_hours": 8,  # 8 hour cooldown between trades
    # News-based entry filters
    # FIX 2026-04-14: DISABLED news catalyst requirement — was blocking ALL gold trades
    # Gold moves on technicals too. News = BONUS score, not mandatory gate.
    "require_news_catalyst": False,  # FIXED: Was True — was blocking every single XAUUSD entry
    "news_events": [
        "NFP",
        "CPI",
        "FOMC",
        "PPI",
        "GDP",
        "PCE",
        "RETAIL_SALES",
        "UNEMPLOYMENT",
        "FED_SPEECH",
        "ECB_RATE",
        "BOE_RATE",
        "GEOPOLITICAL",
    ],
    "news_window_hours": 4,  # Trade within 4 hours of news event (bonus score)
    # Geopolitical filter
    "use_geopolitical_bias": True,  # Gold reacts to wars, inflation
    "geopolitical_weight": 0.3,  # 30% weight to geopolitical signals
    # Session filters for swing (wider windows)
    "best_hours": [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
    "peak_hours": [12, 13, 14, 15],  # London-NY overlap
    # Key levels for gold
    "use_daily_levels": True,  # Previous day high/low
    "use_weekly_levels": True,  # Previous week high/low
    "use_fibonacci": True,  # Fib retracement levels (0.382, 0.5, 0.618, 0.786)
    "fib_levels": [0.236, 0.382, 0.5, 0.618, 0.786],
    # Minimum confluences for swing entry
    # FIX 2026-04-14: Reduced from 4 to 3 — market rarely gives 4+ at once on H4
    "min_confluences": 3,  # FIXED: 3 out of 8 confluences (was 4 — too strict)
    # Partial TP for swing
    "partial_tp1_pct": 0.30,  # Close 30% at TP1
    "partial_tp2_pct": 0.30,  # Close 30% at TP2
    "runner_pct": 0.40,  # Keep 40% as runner with trailing
    "tp1_rr": 2.0,  # TP1 at 2:1 R:R
    "tp2_rr": 3.0,  # TP2 at 3:1 R:R
    "tp3_rr": 5.0,  # TP3 at 5:1 R:R (runner target)
}

# =============================================================================
# MULTI-TIMEFRAME SCALPING ARCHITECTURE
# =============================================================================
SCALP_TIMEFRAME = "M5"  # Primary entry timeframe
SPIKE_TIMEFRAME = "M1"  # Spike detection (fast)
CONFIRM_TIMEFRAME = "M15"  # Setup confirmation
TREND_TIMEFRAME = "H1"  # Trend direction bias

# Legacy alias used by other modules
PRIMARY_TIMEFRAME = "M5"

# =============================================================================
# MULTI-TIMEFRAME ENTRY CONFIGURATION
# =============================================================================
ENTRY_TIMEFRAMES = {
    "M15": {
        "trend_tf": "H4",  # Trend context from H4
        "min_candles": 60,
        "candle_seconds": 900,
        "tf_multiplier": 1.5,  # Wider trail for swing entries
        "max_candles": 16,  # 4 hours max hold
        "breakeven_atr": 0.5,  # Breakeven at 0.5x ATR
        "activation_atr": 0.8,  # Trail activates at 0.8x ATR
        "trail_atr": 0.4,  # Trail 0.4x ATR (tighter)
    },
    "M30": {
        "trend_tf": "H4",  # Trend context from H4
        "min_candles": 60,
        "candle_seconds": 1800,
        "tf_multiplier": 2.0,
        "max_candles": 12,
        "breakeven_atr": 0.6,
        "activation_atr": 1.0,
        "trail_atr": 0.5,
    },
    "H1": {
        "trend_tf": "H4",  # Trend context from H4
        "min_candles": 50,
        "candle_seconds": 3600,
        "tf_multiplier": 3.0,
        "max_candles": 12,
        "breakeven_atr": 0.7,
        "activation_atr": 1.2,
        "trail_atr": 0.6,
    },
    "H4": {
        "trend_tf": "D1",
        "min_candles": 50,
        "candle_seconds": 14400,
        "tf_multiplier": 5.0,
        "max_candles": 8,
        "breakeven_atr": 0.8,
        "activation_atr": 1.5,
        "trail_atr": 0.7,
    },
}

# =============================================================================
# ACCOUNT SETTINGS ($300 USD on OctaFX MT5 Demo)
# =============================================================================
ACCOUNT_CURRENCY = "USD"
INITIAL_BALANCE_INR = 25000  # ~$300 USD
INITIAL_BALANCE_USD = 300
LEVERAGE = 200  # 1:200 leverage

# [audit-cleanup 2026-04-22] Removed SCALP config — no live readers in ai_trading_agents/ or tools/. See archive/ for legacy copy.
# [audit-cleanup 2026-04-22] Removed SPIKE config — no live readers in ai_trading_agents/ or tools/. See archive/ for legacy copy.
# [audit-cleanup 2026-04-22] Removed SMC config — no live readers in ai_trading_agents/ or tools/. See archive/ for legacy copy.
# [audit-cleanup 2026-04-22] Removed LIQUIDITY + LIQUIDITY_PAIR_OVERRIDES configs — no live readers in ai_trading_agents/ or tools/. See archive/ for legacy copy.
# [audit-cleanup 2026-04-22] Removed ACCUMULATION config — no live readers in ai_trading_agents/ or tools/. See archive/ for legacy copy.
# [audit-cleanup 2026-04-22] Removed MANIPULATION config — no live readers in ai_trading_agents/ or tools/. See archive/ for legacy copy.
# [audit-cleanup 2026-04-22] Removed DISTRIBUTION config — no live readers in ai_trading_agents/ or tools/. See archive/ for legacy copy.

# =============================================================================
# RISK MANAGEMENT - CONSERVATIVE FOR $300 ACCOUNT
# =============================================================================
# -----------------------------------------------------------------------------
# RISK.risk_percent vs MQL5 EA InpRiskPct — KEEP IN SYNC MANUALLY
# -----------------------------------------------------------------------------
# 1. The Python `RISK` dict below is AUTHORITATIVE for the Python brain's risk
#    decisions (sizing, daily DD checks, cooldowns, per-symbol caps).
# 2. The MQL5 EA exposes `InpRiskPct` as a separate input (default 1.0). That
#    value is INDEPENDENT of this file and only affects EA-side sizing logic
#    (if the EA does any independent sizing — a parallel agent is reviewing
#    exactly how it's used). Changing one does NOT change the other.
# 3. Until we build a shared config file read by both Python and MQL5, these
#    two numbers MUST be kept in sync manually. If you edit `risk_percent`
#    here, also update `InpRiskPct` in the EA properties (or vice versa),
#    otherwise the brain's intended risk and the EA's executed risk diverge.
# -----------------------------------------------------------------------------
RISK = {
    "risk_percent": float(os.getenv("RISK_PERCENT", 0.5)),  # 0.5% per trade = $1.50 max loss
    "max_daily_drawdown_percent": float(os.getenv("MAX_DAILY_DRAWDOWN", 3.0)),  # 3% daily max = $9 max
    # [R11 2026-04-23] Lifted concurrency so per-team caps can actually bind.
    # Previous value (2) meant the single global gate starved every pair after
    # 2 fills. With 4 teams × max 2 per team = 8 theoretical concurrent slots
    # (realistically 3-5 on any given day due to session + corr filters).
    "max_open_trades": int(os.getenv("MAX_OPEN_TRADES", 8)),  # was 2; bumped for per-team gating
    "max_open_per_team": int(os.getenv("MAX_OPEN_PER_TEAM", 2)),  # NEW — real binding limit
    "trade_cooldown_minutes": 5,
    "symbol_cooldown_minutes": 20,
    "max_trades_per_day": 20,
    "max_trades_per_symbol_per_day": 2,
    "max_consecutive_losses": 2,
    "cooldown_duration_hours": 1,
    "equity_drawdown_halt_pct": 5.0,
    # [R7 2026-04-23] True 1:3 RR sustainable mode. Backtest proved 80% WR
    # at 1:3 RR NOT achievable on real XAUUSD M5 (trader's triangle math).
    # BEST profitable 1:3 config:
    #   ADX40 filter + SL 1.0 / TP 3.0 = 32.5% WR, +0.266R expectancy.
    # Every additional filter made it LESS profitable — filtering kills
    # edge faster than it kills loss count. Accept 32.5% WR; math works:
    #   expectancy = 0.325 * 3 + 0.675 * (-1) = +0.3R per trade
    # 295 trades on 50K bars = ~1 trade per 170 M5 bars = selective.
    "min_risk_reward": 2.5,  # back to sensible 1:3 alignment
    "default_sl_atr_multiple": 1.0,
    "default_tp_atr_multiple": 3.0,
    "min_sl_pips": 5,  # MINIMUM stop-loss: 5 pips (hardcoded floor)
    # Adaptive Trailing Stop
    "trailing_stop_enabled": True,
    "trailing_activation_pips": 30,
    "trailing_distance_pips": 20,
    "trailing_distance_pips_spike": 12,
    "trail_atr_multiplier": 0.8,
    "trail_atr_multiplier_spike": 0.5,
    "max_trail_pips": 30,
    "max_trail_pips_spike": 18,
    "trailing_step_pips": 4,
    "breakeven_pips": 20,
    "max_candles_in_trade": 24,
    "min_lot_size": 0.01,  # Conservative lot size
    "max_lot_size": 0.03,  # Max 0.03 lots per trade
    "compound_profits": False,
}

# =============================================================================
# PER-MARKET SL/TP OVERRIDES - ALL TEAMS
# Updated 2026-04-14: Added all pairs + new COMMODITIES team
# =============================================================================
MARKET_PARAMS = {
    # ── TEAM 1: METALS ───────────────────────────────────────────────────────
    "XAUUSD": {
        "sl_atr_mult": 5.0,
        "tp_atr_mult": 10.0,
        "min_rr": 2.0,
        "trail_activation_pips": 150,
        "trail_distance_pips": 80,
        "max_spread_pips": 40,
        "max_trades_per_day": 1,
        "strategy_mode": "SWING",
    },
    "XAGUSD": {
        "sl_atr_mult": 3.0,
        "tp_atr_mult": 6.0,
        "min_rr": 2.0,
        "trail_activation_pips": 80,
        "trail_distance_pips": 50,
        "max_spread_pips": 30,
        "max_trades_per_day": 2,
        "strategy_mode": "SCALP",
    },
    # ── TEAM 2: FOREX ─────────────────────────────────────────────────────────
    "GBPJPY": {  # STAR PERFORMER 97.7% accuracy
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 5.0,
        "min_rr": 2.0,
        "trail_activation_pips": 25,
        "trail_distance_pips": 18,
        "max_spread_pips": 25,
        "max_trades_per_day": 3,
    },
    "USDCAD": {  # 87% accuracy — star secondary
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 4.0,
        "min_rr": 2.0,
        "trail_activation_pips": 20,
        "trail_distance_pips": 15,
        "max_spread_pips": 20,
        "max_trades_per_day": 3,
    },
    "USDCHF": {
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 3.5,
        "min_rr": 1.5,
        "trail_activation_pips": 25,
        "trail_distance_pips": 18,
        "max_spread_pips": 20,
        "max_trades_per_day": 2,
    },
    "EURUSD": {  # Most liquid, tight spreads
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 4.0,
        "min_rr": 2.0,
        "trail_activation_pips": 20,
        "trail_distance_pips": 15,
        "max_spread_pips": 15,
        "max_trades_per_day": 3,
    },
    "GBPUSD": {  # High volatility, wider SL
        "sl_atr_mult": 2.5,
        "tp_atr_mult": 5.0,
        "min_rr": 2.0,
        "trail_activation_pips": 25,
        "trail_distance_pips": 18,
        "max_spread_pips": 20,
        "max_trades_per_day": 2,
    },
    "AUDUSD": {  # Commodity-linked, moderate volatility
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 4.0,
        "min_rr": 1.8,
        "trail_activation_pips": 20,
        "trail_distance_pips": 15,
        "max_spread_pips": 18,
        "max_trades_per_day": 2,
    },
    "USDJPY": {  # High liquidity, fast moves
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 4.0,
        "min_rr": 2.0,
        "trail_activation_pips": 20,
        "trail_distance_pips": 15,
        "max_spread_pips": 15,
        "max_trades_per_day": 3,
    },
    "NZDUSD": {  # Commodity currency, moderate
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 3.5,
        "min_rr": 1.8,
        "trail_activation_pips": 18,
        "trail_distance_pips": 13,
        "max_spread_pips": 20,
        "max_trades_per_day": 2,
    },
    "EURJPY": {  # Volatile cross, good moves
        "sl_atr_mult": 2.5,
        "tp_atr_mult": 5.0,
        "min_rr": 2.0,
        "trail_activation_pips": 25,
        "trail_distance_pips": 18,
        "max_spread_pips": 25,
        "max_trades_per_day": 2,
    },
    "EURGBP": {  # Range-bound, tight moves
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 3.5,
        "min_rr": 1.5,
        "trail_activation_pips": 15,
        "trail_distance_pips": 12,
        "max_spread_pips": 20,
        "max_trades_per_day": 2,
    },
    "AUDJPY": {  # Risk-on cross, good Asian/London
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 4.0,
        "min_rr": 2.0,
        "trail_activation_pips": 20,
        "trail_distance_pips": 15,
        "max_spread_pips": 22,
        "max_trades_per_day": 2,
    },
    "CADJPY": {  # Oil-linked cross
        "sl_atr_mult": 2.0,
        "tp_atr_mult": 4.0,
        "min_rr": 2.0,
        "trail_activation_pips": 20,
        "trail_distance_pips": 15,
        "max_spread_pips": 25,
        "max_trades_per_day": 2,
    },
    # ── TEAM 3: CRYPTO ────────────────────────────────────────────────────────
    "BTCUSD": {  # High volatility, 24/7 — wider SL needed
        "sl_atr_mult": 3.0,
        "tp_atr_mult": 6.0,
        "min_rr": 2.0,
        "trail_activation_pips": 300,
        "trail_distance_pips": 200,
        "max_spread_pips": 100,
        "max_trades_per_day": 2,
    },
    "ETHUSD": {  # Follows BTC, slightly less volatile
        "sl_atr_mult": 3.0,
        "tp_atr_mult": 6.0,
        "min_rr": 2.0,
        "trail_activation_pips": 200,
        "trail_distance_pips": 150,
        "max_spread_pips": 80,
        "max_trades_per_day": 2,
    },
    # ── TEAM 4: COMMODITIES (NEW) ─────────────────────────────────────────────
    # 2026-04-22: Renamed to OctaFX-Demo broker symbol names. CORN/WHEAT removed
    # (broker doesn't list them). See TRADING_PAIRS comment for details.
    "XTIUSD": {  # WTI Crude (was 'USOIL') — news-driven, high volatility
        "sl_atr_mult": 3.0,
        "tp_atr_mult": 6.0,
        "min_rr": 2.0,
        "trail_activation_pips": 100,
        "trail_distance_pips": 60,
        "max_spread_pips": 50,
        "max_trades_per_day": 2,
        "strategy_mode": "SWING",
    },
    "XBRUSD": {  # Brent Crude (was 'UKOIL') — correlated with XTIUSD
        "sl_atr_mult": 3.0,
        "tp_atr_mult": 6.0,
        "min_rr": 2.0,
        "trail_activation_pips": 100,
        "trail_distance_pips": 60,
        "max_spread_pips": 50,
        "max_trades_per_day": 2,
        "strategy_mode": "SWING",
    },
    "XNGUSD": {  # Natural Gas — high seasonal volatility
        "sl_atr_mult": 3.5,
        "tp_atr_mult": 7.0,
        "min_rr": 2.0,
        "trail_activation_pips": 80,
        "trail_distance_pips": 50,
        "max_spread_pips": 60,
        "max_trades_per_day": 1,
        "strategy_mode": "SWING",
    },
}

# =============================================================================
# SESSION DEFINITIONS - 24/7 Trading with Session Awareness
# =============================================================================
SESSIONS = {
    "asian_open": 0,
    "asian_close": 7,
    "london_open": 7,
    "london_close": 16,
    "ny_open": 12,
    "ny_close": 21,
    "trade_london": True,
    "trade_ny": True,
    "trade_overlap": True,
    "trade_asian": False,
    "avoid_asian": True,
}

# =============================================================================
# PER-PAIR SESSION FILTERS - ALL 4 TEAMS
# Updated 2026-04-14: Full session coverage for all pairs + commodities
# =============================================================================
PAIR_SESSION_FILTERS = {
    # ── TEAM 1: METALS ───────────────────────────────────────────────────────
    "XAUUSD": {
        "best_hours": [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
        "min_atr_mult": 0.3,
        "peak_hours": [12, 13, 14, 15],
        "strategy_mode": "SWING",
    },
    "XAGUSD": {
        "best_hours": [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
        "min_atr_mult": 0.4,
        "peak_hours": [12, 13, 14, 15],
    },
    # ── TEAM 2: FOREX ─────────────────────────────────────────────────────────
    "GBPJPY": {
        "best_hours": [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17],
        "min_atr_mult": 0.4,
        "peak_hours": [7, 8, 9, 12, 13, 14],
    },
    "USDCAD": {
        "best_hours": [12, 13, 14, 15, 16, 17, 18, 19, 20],  # NY session best for CAD
        "min_atr_mult": 0.4,
        "peak_hours": [13, 14, 15, 16],
    },
    "USDCHF": {
        "best_hours": [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
        "min_atr_mult": 0.4,
        "peak_hours": [12, 13, 14, 15],
    },
    "EURUSD": {
        "best_hours": [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17],
        "min_atr_mult": 0.3,
        "peak_hours": [8, 9, 12, 13, 14],
    },
    "GBPUSD": {
        "best_hours": [7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
        "min_atr_mult": 0.4,
        "peak_hours": [8, 9, 12, 13],
    },
    "AUDUSD": {
        "best_hours": [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14],  # Asian + London
        "min_atr_mult": 0.4,
        "peak_hours": [0, 1, 2, 7, 8],
    },
    "USDJPY": {
        "best_hours": [0, 1, 2, 3, 7, 8, 9, 12, 13, 14, 15],
        "min_atr_mult": 0.3,
        "peak_hours": [0, 1, 7, 8, 12, 13],
    },
    "NZDUSD": {
        "best_hours": [21, 22, 23, 0, 1, 2, 3, 7, 8],  # NZ/Asian session
        "min_atr_mult": 0.4,
        "peak_hours": [22, 23, 0, 1],
    },
    "EURJPY": {
        "best_hours": [7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
        "min_atr_mult": 0.4,
        "peak_hours": [8, 9, 12, 13],
    },
    "EURGBP": {
        "best_hours": [7, 8, 9, 10, 11, 12, 13, 14, 15],
        "min_atr_mult": 0.4,
        "peak_hours": [8, 9, 10],
    },
    "AUDJPY": {
        "best_hours": [0, 1, 2, 3, 4, 5, 7, 8, 9, 12, 13],  # Asian + London
        "min_atr_mult": 0.4,
        "peak_hours": [0, 1, 2, 7, 8],
    },
    "CADJPY": {
        "best_hours": [12, 13, 14, 15, 16, 17, 18],  # NY session (CAD active)
        "min_atr_mult": 0.4,
        "peak_hours": [13, 14, 15],
    },
    # ── TEAM 3: CRYPTO ───────────────────────────────────────────────────────
    "BTCUSD": {
        "best_hours": list(range(24)),  # 24/7
        "min_atr_mult": 0.5,
        "peak_hours": [12, 13, 14, 15, 16],  # NY session = highest volume
    },
    "ETHUSD": {
        "best_hours": list(range(24)),  # 24/7
        "min_atr_mult": 0.5,
        "peak_hours": [12, 13, 14, 15, 16],
    },
    # ── TEAM 4: COMMODITIES (NEW) ─────────────────────────────────────────────
    # 2026-04-22: Renamed to broker (OctaFX-Demo) symbols. CORN/WHEAT removed.
    "XTIUSD": {  # WTI Crude (was 'USOIL')
        "best_hours": [13, 14, 15, 16, 17, 18, 19, 20],  # NY session (NYMEX)
        "min_atr_mult": 0.5,
        "peak_hours": [14, 15, 16],  # NYMEX open + NY overlap
        "strategy_mode": "SWING",
    },
    "XBRUSD": {  # Brent Crude (was 'UKOIL')
        "best_hours": [8, 9, 10, 11, 12, 13, 14, 15, 16, 17],  # London + NY
        "min_atr_mult": 0.5,
        "peak_hours": [9, 10, 13, 14],
        "strategy_mode": "SWING",
    },
    "XNGUSD": {
        "best_hours": [13, 14, 15, 16, 17, 18, 19, 20],  # NY/NYMEX session
        "min_atr_mult": 0.6,
        "peak_hours": [14, 15, 16],
        "strategy_mode": "SWING",
    },
}

# [audit-cleanup 2026-04-22] Removed PARTIAL_TP config — no live readers in ai_trading_agents/ or tools/. See archive/ for legacy copy.
# [audit-cleanup 2026-04-22] Removed SCALP_TARGET config — no live readers in ai_trading_agents/ or tools/. See archive/ for legacy copy.

# =============================================================================
# ORDER EXECUTION SETTINGS
# =============================================================================
# NOTE 2026-04-22 audit-cleanup: KEPT — live reader in tools/cleanup_orphans.py
# (line 45) reads `getattr(settings, 'ORDER', {}).get('magic_number', ...)`.
ORDER = {
    "magic_number": 234000,
    "deviation": 20,  # Max slippage in points
    "comment": "AMD_BOT",
}

# [audit-cleanup 2026-04-22] Removed SMART_FILTERS config — no live readers in ai_trading_agents/ or tools/. See archive/ for legacy copy.

# =============================================================================
# v14 TRENDMASTER INTEGRATION (2026-04-20)
# =============================================================================
# Bridge between Python AI brain and the AI_SUPERBB_v14_TrendMaster.mq5 EA.
# Python writes `trendmaster_signals.json`; EA reads it as a 3rd-confirmation
# gate. When the EA's own SuperTrend+BB+MACD agree AND Python's ML brain
# agrees, order fires — otherwise skipped.
# =============================================================================
TRENDMASTER_V14 = {
    "enabled": True,
    # Shared-file bridge (must match InpAISignalFile in the EA)
    # If MT5 is set to the default data folder, use the MQL5/Files path.
    # If MT5 is set to the Common folder, pass FILE_COMMON in the EA.
    "signal_file": "trendmaster_signals.json",
    "use_common_folder": False,
    # Symbol this brain drives. The primary symbol keeps the legacy
    # signal_file name (`trendmaster_signals.json`) for backward-compat
    # with already-deployed EAs.
    "primary_symbol": "XAUUSD",
    "primary_timeframe": "H1",  # trigger timeframe (mid-TF sweet spot)
    # MULTI-SYMBOL MODE — when True, the brain runs tick_all() every
    # interval and writes one signal file per symbol in TRADING_PAIRS:
    #   trendmaster_signals.json           (XAUUSD — legacy name)
    #   trendmaster_signals_EURUSD.json
    #   trendmaster_signals_GBPJPY.json
    #   ... (one per pair)
    # When False the brain ticks only the primary symbol — that's why
    # only XAUUSD signals were produced before this flag was added.
    "multi_symbol": True,
    # Brain update cadence — 3 s is ample for H1 bars.
    "inference_interval_ms": 3000,
    # Multi-timeframe alignment — ALL THREE must agree for a signal.
    # This is the "simple but profitable" filter the user asked for:
    #   M30 = entry timing (fast momentum kicks in)
    #   H1  = short-trend confirmation
    #   H4  = macro/regime direction
    # 3-of-3 MTF + 3-of-3 EA confirmations = very high-quality entries only.
    "mtf_alignment": {
        "M30": True,
        "H1": True,
        "H4": True,
    },
    # Minimum confidence before brain writes BUY/SELL. Higher = fewer, stronger.
    # [R11 2026-04-23] Lowered 0.82 → 0.70 after zero-trades-in-24hrs audit.
    # The 0.82 floor combined with 3/3 agents + EA 3/3 + vol_regime was
    # filtering >99% of signals. At 0.70 we still require strong conviction
    # but allow London/NY trades to fire. Session-boost drops peak to 0.65.
    "min_ml_confidence": 0.70,
    # Advanced-agent voting. Each agent returns +1/-1/0. Final direction needs
    # at least `agent_min_votes` agreeing votes (out of len(agents)).
    # Agents:
    #   trend_agent      — H4 EMA20 vs EMA50 + ADX strength
    #   momentum_agent   — H1 MACD histogram direction + momentum
    #   timing_agent     — M30 Bollinger mid cross + RSI midband
    # [R11 2026-04-23] 3 → 2. Three-of-three agent agreement is rare in
    # low-vol regimes (overnight/Asian). Two-of-three is still selective
    # (66% quorum) but actually fires. If quality degrades, raise back.
    "agent_min_votes": 2,
    # Kelly sizing parameters (scales EA's risk % by this).
    "kelly_lookback_trades": 40,
    "kelly_min_samples": 20,
    "kelly_max_fraction": 2.0,  # hard cap multiplier
    "kelly_floor_fraction": 0.25,  # never go below 25% of base risk
    # Feature engineering windows (for LightGBM model)
    "feature_windows": [5, 10, 20, 50],
    "include_orderflow": True,  # tick imbalance if MT5 tick stream available
    "include_session_feature": True,  # London / NY / overlap / Asian one-hot
    # [Phase B3 2026-04-26] Smart-money (COT + EIA) feature enrichment.
    # model has been replaced with the B3-trained model (trend_master_model_v2.lgb
    # copied to trend_master_model.lgb). Restart brain to activate V2 inference.
    "smartmoney_features_enabled": True,
    # [Phase C1 2026-04-26] Meta-label act/skip gate (binary secondary classifier).
    # Flip to True ONLY after meta_label_model.lgb has been trained and validated
    # (run tools/train_v14_c1_metalabel.py, check OOF AUC >= 0.55, then enable).
    # act_threshold: P_act must exceed this to allow a BUY/SELL signal through.
    "metalabel_enabled": False,
    "metalabel_act_threshold": 0.55,
    # [Phase C2 2026-04-26] Per-team meta-label heads (METALS/FOREX/CRYPTO/COMMODITIES).
    # Flip to True ONLY after all 4 team models are trained and validated
    # (run tools/train_v14_c2_metalabel_perteam.py, check OOF AUC >= 0.55 per team).
    # When True, per-team head takes precedence over global C1 head for each symbol.
    # Keep metalabel_enabled=True as well so global head is available as fallback.
    "metalabel_perteam_enabled": False,
}

# =============================================================================
# PROFIT OPTIMIZER (2026-04-22)
# =============================================================================
# These are layered AFTER the brain + agent vote. Each gate is independently
# toggleable so a paranoid user can A/B them. Defaults are tuned for a small
# ($300) account where preserving capital matters more than chasing edge.
#
# What each one does (one line each):
#   spread_guard      → block when broker spread > X * ATR (kills bad fills)
#   vol_regime        → skip dead OR fat-tail markets (keeps RR realistic)
#   profit_lock       → stop trading after daily target hit (locks gains)
#   loss_cooldown     → halt after N consecutive losses (kills tilt)
#   session_window    → only trade London/NY hours (Asian chop is unprofitable)
# =============================================================================
PROFIT_OPTIMIZER = {
    # Master toggle — set False to bypass every gate (NOT recommended).
    "enabled": True,
    # Individual gates (every gate MUST pass for a trade to fire).
    # 2026-04-22: spread_guard DISABLED at user request — operator decision
    # that broker-spread alone shouldn't gate entries (dead-market regime
    # check via vol_regime is the real "is this worth trading?" filter).
    "spread_guard": False,
    "vol_regime": True,
    "profit_lock": True,
    "loss_cooldown": True,
    "session_window": True,
    "news_blackout": True,
    "daily_loss_limit": True,  # max-DD circuit breaker (Phase G4)
    # Spread guard
    "max_spread_atr_ratio": 0.25,  # spread > 25 % of ATR → veto
    # Volatility regime
    "vol_min_quantile": 0.20,  # below 20th-pct ATR = dead market, skip
    "vol_max_quantile": 0.95,  # above 95th-pct ATR = spike regime, skip
    # Profit lock
    "daily_profit_target_pct": 2.0,  # +2 % equity = stop trading for the day
    # (lock 2 % a day = ~50 %/month compounded
    #  — far above retail-bot reality, so any
    #  green day is worth securing.)
    # Loss-streak cooldown
    "max_consec_losses": 3,
    "cooldown_hours": 4,  # how long to stay flat after 3 losses
    # Session window (UTC hours we consider tradable)
    "best_hours_utc": list(range(7, 21)),  # 07:00–20:59 UTC = London + NY
    # News blackout — looks at config/news_calendar.json for events
    # of the listed impact and refuses trades within ±N minutes.
    "news_window_minutes": 30,
    "news_impact_levels": ("high",),  # 'high' / 'medium' / 'low'
    # Daily-loss limit (Phase G4 — max-drawdown circuit breaker)
    # max_loss_pct: hard stop at -X % vs. start-of-day equity. Once tripped,
    # the brain stamps `drawdown_lockout_until` to the end of the UTC day so
    # the rest of the session is blocked even if equity briefly rebounds.
    # intraday_dd_pct: tighter prop-firm-style trail — locks when you give
    # back gains, not just when you go red. Set to None to disable.
    "daily_max_loss_pct": 3.0,  # -3 % vs. SoD equity → lock the day
    "intraday_dd_pct": 2.0,  # -2 % from intraday peak → lock the day
}


# =============================================================================
# PER-SYMBOL TIMEFRAME OVERRIDES (2026-04-22)
# =============================================================================
# XAUUSD swings beautifully on H4/D1. GBPJPY scalps on M5/H1. Forcing them
# both through the same M30/H1/H4 agent stack throws away half the edge of
# each. Anything not listed falls back to the default M30/H1/H4 trio.
#
# Format: { symbol: {'fast': str, 'mid': str, 'slow': str} }
# fast = entry timing, mid = trend confirm, slow = macro bias
PAIR_TIMEFRAME_OVERRIDES = {
    # METALS — slow swings, wider noise tolerance
    "XAUUSD": {"fast": "H1", "mid": "H4", "slow": "D1"},
    "XAGUSD": {"fast": "H1", "mid": "H4", "slow": "D1"},
    # CRYPTO — 24/7, slower regime
    "BTCUSD": {"fast": "H1", "mid": "H4", "slow": "D1"},
    "ETHUSD": {"fast": "H1", "mid": "H4", "slow": "D1"},
    # OIL — news-driven, mid-cadence (broker symbols)
    "XTIUSD": {"fast": "M30", "mid": "H1", "slow": "H4"},  # WTI (was USOIL)
    "XBRUSD": {"fast": "M30", "mid": "H1", "slow": "H4"},  # Brent (was UKOIL)
    "XNGUSD": {"fast": "M30", "mid": "H1", "slow": "H4"},
    # JPY scalp pairs
    "GBPJPY": {"fast": "M15", "mid": "M30", "slow": "H1"},
    "EURJPY": {"fast": "M15", "mid": "M30", "slow": "H1"},
    "AUDJPY": {"fast": "M15", "mid": "M30", "slow": "H1"},
    "CADJPY": {"fast": "M15", "mid": "M30", "slow": "H1"},
    "USDJPY": {"fast": "M15", "mid": "M30", "slow": "H1"},
    # Other forex use the default M30/H1/H4 trio.
}


def timeframes_for(symbol: str) -> list:
    """Return [fast, mid, slow] timeframes for the given symbol.
    Falls back to the project-wide M30/H1/H4 stack."""
    cfg = PAIR_TIMEFRAME_OVERRIDES.get(symbol)
    if not cfg:
        return ["M30", "H1", "H4"]
    return [cfg["fast"], cfg["mid"], cfg["slow"]]


# =============================================================================
# ENHANCEMENT MODULES (2026-04-23) — opt-in, off by default.
# =============================================================================
# Every block below wires in one of the new modules shipped with the
# 2026-04-23 enhancement report (reports/ENHANCEMENT_REPORT_2026-04-23.md).
# All are disabled by default — no live-trading behaviour change unless the
# operator explicitly flips `enabled=True` and restarts the brain.
# Activation order (observability first, execution changes last) is
# documented in the report.
# =============================================================================

# ---- Drift detection (ai_trading_agents/drift_detector.py) -----------------
# Detects regime shifts in the rolling PnL stream using ADWIN. When the
# detector trips, emits a Telegram alert (no auto-action in v1).
# 2026-04-23 ACTIVATED in alerts-only mode — no auto-action on drift,
# just a Telegram /drift alert so operators can rerun CPCV training.
DRIFT = {
    "enabled": True,  # ALERTS ONLY — no auto-action.
    "adwin_delta": 0.002,  # smaller => more conservative (fewer alerts).
    "min_window": 32,  # don't flag until window has this many samples.
    "alert_telegram": True,  # emit Telegram alert when drift fires.
    "reset_on_drift": True,  # drop pre-drift observations from the window
    # so the detector stops re-firing on the same
    # event forever.
}

# ---- Prometheus-style metrics (ai_trading_agents/metrics.py) ---------------
# Collects counters / gauges / histograms in memory and exposes /metrics on
# the dashboard in Prometheus 0.0.4 text format. No outbound calls; pull-
# based. Safe to enable — purely observational.
# 2026-04-23 ACTIVATED — zero trading-behaviour change, pure observability.
METRICS = {
    "enabled": True,  # ON — /metrics live on dashboard.
    "expose_on_dashboard": True,
    "collect_tick_latency": True,
    "collect_per_symbol": True,
    "collect_veto_reasons": True,
}

# ---- Kelly-fraction sizing (ai_trading_agents/kelly_sizer.py) --------------
# Reads `TRENDMASTER_V14.kelly_*` tuning knobs and computes a risk multiplier
# from recent closed trades. Wiring into the brain requires TWO flags:
#   KELLY_SIZING.enabled=True                 AND
#   TRENDMASTER_V14.use_kelly_sizing=True
# so you can A/B shadow mode without accidentally flipping live sizing.
# 2026-04-23 ACTIVATED in SHADOW mode — logs what it WOULD do, but returns
# base risk unchanged. Promote to live after 2 weeks of shadow.
KELLY_SIZING = {
    "enabled": True,  # ON but shadow=True so no live effect.
    "shadow": True,  # CRITICAL — keep True until shadow review.
    "kelly_fraction": 0.5,  # half-Kelly (literature consensus safest).
    "min_samples": 20,
    "lookback_trades": 40,
    "floor_fraction": 0.25,
    "max_fraction": 2.0,
}

# ---- Structured JSON logging (ai_trading_agents/structured_log.py) ---------
# Purely a formatter swap — behaviour unchanged. Set the env var
# `LOG_FORMAT=json` to activate (this block is documentation + defaults).
STRUCTURED_LOG = {
    "default_format": "text",  # 'text' | 'json'
    "env_override": "LOG_FORMAT",
    "level_env": "LOG_LEVEL",
    "level_default": "INFO",
}

# ---- Panic-flatten extension (ai_trading_agents/panic.py) ------------------
# Extends /halt to optionally close every open position tagged by our EA
# magic number. Requires two-step confirmation ("/halt close YES") even
# when enabled — belt-and-braces against accidental triggers. Not wired
# into the brain yet; see ENHANCEMENT_REPORT_2026-04-23.md for the
# opt-in snippet.
PANIC = {
    "enabled": False,
    "magic_filter": 20260420,  # AI_SUPERBB_v14 default magic
    "require_yes": True,  # force `/halt close YES` confirmation
    "max_retries": 5,
    "retry_backoff_s": 0.5,
    "deviation": 50,  # slippage points on close orders
}


# =============================================================================
# ENHANCEMENT MODULES — ROUND 3 (2026-04-23)
# =============================================================================
# Extended institutional-grade features: VaR/CVaR, meta-labeling, HMM regime,
# rolling correlation, online learning, A/B testing, event sourcing.
# All opt-in. See docs/ENHANCEMENTS_2026-04-23.md for activation steps.
# =============================================================================

# ---- Meta-labeling (ai_trading_agents/meta_labeler.py) ---------------------
# Lopez de Prado secondary classifier. Sits AFTER the brain's primary
# direction pick and decides (a) whether to act, (b) size multiplier.
META_LABELER = {
    "enabled": False,  # OFF until CPCV-trained model is promoted
    "model_path_template": "ai_trading_agents/ml_models/meta_{team}.pkl",
    "p_win_threshold": 0.55,
    "min_scale": 0.5,
    "max_scale": 1.5,
    "apply_to_sizing": False,  # when True, multiplies lots by scale
}

# ---- HMM regime detection (ai_trading_agents/regime_hmm.py) ----------------
# Hidden Markov model on log-returns + realized vol → chop/trend state.
# When enabled, acts as an ADDITIONAL veto alongside the vol_regime gate.
REGIME_HMM = {
    "enabled": False,  # OFF until trained + validated
    "model_path_template": "ai_trading_agents/ml_models/regime_{team}.pkl",
    "chop_veto_prob": 0.70,  # block trade if P(chop) > this
    "trend_bonus_prob": 0.70,  # +conf nudge if P(trend) > this
    "trend_bonus": 0.03,
}

# ---- Rolling correlation cap (ai_trading_agents/rolling_corr.py) -----------
# Replaces the static `_CORR_GROUPS` in risk_manager.py with live rolling
# correlations. Threshold-based. Supplements (not replaces) static groups.
ROLLING_CORR = {
    "enabled": False,  # OFF; requires ~20 bars warmup
    "window": 20,  # rolling window size (bars)
    "threshold": 0.8,  # |corr| > 0.8 ⇒ conflict
    "mode": "supplement",  # 'supplement' (adds to static) | 'replace'
}

# ---- Portfolio VaR / CVaR (ai_trading_agents/portfolio_risk.py) ------------
# Observability + optional soft veto when 95-CVaR exceeds a cap. Three methods
# (historical, parametric, Cornish-Fisher) computed in one snapshot.
PORTFOLIO_RISK = {
    "enabled": True,  # ON — observability only by default
    "confidence": 0.95,
    "min_samples": 30,  # don't compute until we have enough trades
    "alert_telegram": True,
    "cvar_soft_veto": False,  # if True + cvar>cap ⇒ size halved
    "cvar_cap_usd": 30.0,  # example cap for $300 account
}

# ---- Strategy A/B testing (ai_trading_agents/ab_test.py) --------------------
# Run variant strategies in shadow mode alongside live — log divergences.
AB_TEST = {
    "enabled": False,
    "variants": [],  # list of {'name': ..., 'callable_path': 'mod:fn'}
    "log_path": "logs/ab_shadow.jsonl",
}

# ---- Event sourcing (ai_trading_agents/event_log.py) -----------------------
# Append-only JSONL audit log of every brain decision. Enables perfect replay.
EVENT_LOG = {
    "enabled": True,  # ON — cheap and high-value
    "path": "logs/events.jsonl",
    "buffer_max": 100,
    "flush_every_s": 1.0,
    "kinds": ["signal", "veto", "drift", "halt", "resume", "fill"],
}

# ---- Online learning (ai_trading_agents/online_learner.py) -----------------
# Incremental per-team classifier — updates on every closed trade.
# Complements (does not replace) the batch LGBM models.
ONLINE_LEARNER = {
    "enabled": False,  # OFF until shadow-mode data reviewed
    "predict_active": False,  # if True, blends p_win into conf gate
    "model_path_template": "ai_trading_agents/ml_models/online_{team}.pkl",
    "update_on_close": True,  # learn_one on every trade_tracker hit
    "blend_weight": 0.2,  # weight given to online prediction
}


# =============================================================================
# ENHANCEMENT MODULES — ROUND 4 OPERATOR GRADE (2026-04-23)
# =============================================================================
# Daily digest, log rotation, market calendar, gate attribution, model
# governance, performance analytics. Institutional-operator features.
# =============================================================================

# ---- Market calendar gate (ai_trading_agents/market_calendar.py) -----------
# Weekend + holiday veto. Crypto exempt. Safe to leave ON always.
MARKET_CALENDAR = {
    "enabled": True,  # ON — pure safety, no downside to leaving on
}

# ---- Daily digest (ai_trading_agents/daily_digest.py) ----------------------
DAILY_DIGEST = {
    "enabled": True,  # generate on /digest and via scheduled task
    "telegram_push": True,
    "reports_dir": "reports",
}

# ---- Telegram notification switches ---------------------------------------
# Per-event gating for the Telegram push notifier. Operational alerts
# (DD lockout, MT5 disconnect, startup/shutdown, daily digest, drift,
# panic, /command replies, re-entry) always fire regardless — those
# are rare and load-bearing. This block only controls the two chatty
# buckets:
#   - notify_on_signal: one message per direction CHANGE per symbol
#     (can still be dozens per day across 19 symbols). Default OFF so
#     Telegram stays quiet when the project runs live 24/7.
#   - notify_on_fill:   one message per closed/filled deal (rare in
#     our 3-of-3 gated strategy). Default ON — the operator wants to
#     know when an actual trade happened, and only then.
TELEGRAM = {
    "notify_on_signal": False,
    "notify_on_fill": True,
}

# ---- Ops maintenance (ai_trading_agents/ops_maintenance.py) ----------------
OPS_MAINTENANCE = {
    "enabled": True,
    "log_max_mb": 10.0,
    "log_keep_count": 7,
    "state_keep_days": 14,
    "events_max_lines": 500000,
    "events_max_age_days": 60,
}

# ---- Model governance (ai_trading_agents/model_governance.py) --------------
MODEL_GOVERNANCE = {
    "enabled": True,
    "promote_margin_auc": 0.02,  # challenger must beat champion by 2pp
    "auto_promote": False,  # operator decision by default
    "auto_rollback_on_drop": True,
}


# =============================================================================
# ENHANCEMENT MODULES — ROUND 5 DAILY-TRADE CADENCE (2026-04-23)
# =============================================================================
# Five algo-quality enhancements designed to hit "at least one trade per pair
# per day" without cranking risk_percent. Opt-in by default (enabled=True),
# but each feature is independently toggleable for A/B comparison.
# =============================================================================

# ---- Session confidence boost (profit_filters.session_window already
# returns score_adjust=+0.03 on London-NY overlap; brain must CONSUME it).
# When peak hour is active, MIN_CONF is effectively reduced by `boost`, so
# more — but still high-quality — signals fire during 12:00-15:59 UTC.
SESSION_BOOST = {
    "enabled": True,
    "peak_hours_utc": list(range(12, 16)),  # London-NY overlap (UTC)
    "peak_boost": 0.05,  # MIN_CONF(peak) = MIN_CONF - 0.05
    "shoulder_hours_utc": [11, 16, 17],
    "shoulder_boost": 0.02,  # smaller nudge on the edges
}

# ---- Smart re-entry after SL (ai_trading_agents/reentry_tracker.py).
# When a trade is stopped out, if the original setup is still structurally
# intact after `cooldown_min`, fire a re-entry at `size_mult` of base lots
# (i.e. 0.7 = 70% of normal risk). Capped at `max_reentries` per symbol-day
# so a pair in a losing regime can't spiral.
REENTRY = {
    "enabled": True,
    "cooldown_minutes": 30,  # minimum time between SL and re-entry
    "size_mult": 0.7,  # 70% of base lots
    "max_reentries": 1,  # per symbol per UTC day
    "require_same_direction": True,  # only re-enter if new signal matches original
    "max_age_minutes": 180,  # after 3h the re-entry permit expires
    "alert_telegram": True,  # send /reentry alert when permit used
}

# ---- Pyramid at +1R (EA-side, see AI_SUPERBB_v14_TrendMaster.mq5 Inp*).
# This Python block is metadata only — the EA inputs control actual behavior.
# Kept here so ops can see at a glance what the pyramid contract is.
PYRAMID = {
    "enabled": True,  # mirror of EA's InpUsePyramid
    "trigger_r": 1.0,  # R-multiple at which tranche fires (EA: InpPyramidR)
    "size_pct": 0.5,  # 50% of original lots for add-on tranche (EA: InpPyramidSizePct)
    "max_pyramids": 1,  # one add-on per trade
    "require_trend_confirm": True,  # EA re-checks SuperTrend direction before adding
    "notes": "Python side is observational; EA enforces all pyramid logic.",
}

# ---- EA runtime overrides — written to each signal JSON, read by EA at
# ---- runtime so we don't need to detach + re-attach on 18 charts when
# ---- tuning gate strictness. Added 2026-04-23 (R11).
EA_OVERRIDES = {
    "enabled": True,
    "require_all_3": False,  # EA will accept 2-of-3 agreement
    "max_spread_atr_pct": 0.40,  # EA will allow spread up to 40% of ATR
}


# ---- Partial TP ladder (EA-side). Python observational mirror.
# EA currently: 40% at +1R (InpPartial1Pct=0.4), 30% at +2R (InpPartial2Pct=0.3),
# 30% runner with Chandelier trail. To switch to 33/33/34 set EA inputs:
#   InpPartial1Pct=0.33 ; InpPartial2Pct=0.33  (34% runs)
# Operator decision — default left at 40/30/30 which backtested better.
PARTIAL_TP_LADDER = {
    "enabled": True,
    "tp1_r": 1.0,
    "tp1_pct": 0.40,
    "tp2_r": 2.0,
    "tp2_pct": 0.30,
    "runner_pct": 0.30,
    "trail_type": "chandelier",
    "notes": "Python mirror; EA InpPartial1Pct/InpPartial2Pct/InpUseChandelier authoritative.",
}

# [R11 2026-04-23] End of enhancement-module block.
