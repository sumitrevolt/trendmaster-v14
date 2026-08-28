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

# Shared YAML config loader (env > yaml > hardcoded fallback).
# See config/trading_config.yaml + config/shared_config_loader.py.
# Soft-imports so this file never breaks if pyyaml is missing.
try:
    from config.shared_config_loader import env_or_shared as _es
except Exception:  # noqa: BLE001
    def _es(env_key, _yaml_path, default, cast=float):
        v = os.getenv(env_key)
        if v is None:
            return default
        try:
            return cast(v)
        except (TypeError, ValueError):
            return default

# =============================================================================
# MT5 CONNECTION SETTINGS (OctaFX)
# =============================================================================
MT5_LOGIN = int(os.getenv("MT5_LOGIN", 0))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "OctaFX-Demo")

# =============================================================================
# TRADING PAIRS — CONCENTRATED MODE (top-8 alpha, 2 per team)
# Updated 2026-05-01: Switched from FULL 18-symbol rotation to TOP-8 by Sharpe
# proxy from walkforward 2026-05-01_0230 (50K M5 bars/symbol, EA-parity).
#   Reason: per-team max=2 means we never trade more than 2 from a team
#   simultaneously. Carrying 11 FOREX symbols when only 2 can be live at
#   once = noise in dispatcher + ML feature drift on idle pairs. Keep the
#   2 highest-Sharpe per team. Better fills, cleaner signal-to-noise,
#   no impact on max-concurrent capacity.
#
# Dropped (-10 syms, all preserved as comments for easy revert):
#   FOREX  : GBPJPY, USDCAD, EURUSD, GBPUSD, AUDUSD, USDJPY, NZDUSD,
#            EURJPY, CADJPY  (Sharpe 0.118-0.165, mid-pack)
#   COMMOD : XBRUSD          (Sharpe 0.141, correlated with XTIUSD ~0.85)
#
# To revert: uncomment the dropped lines below. No other code change needed.
# Walkforward source: reports/walkforward/2026-05-01_0230.json
# =============================================================================
TRADING_PAIRS = [
    # [2026-08-26] EXPANDED MODE — 8 core scalping + metals/crypto/oil/JPY crosses
    # Core forex scalps
    "EURUSD",  # Core forex — high liquidity, tight spreads
    "GBPUSD",  # Core forex — volatile, good momentum moves
    "NZDUSD",  # Core forex — consistent session moves
    "USDCHF",  # Core forex — safe-haven counterbalance
    "GBPJPY",  # Scalping star — high momentum, M15 fast TF
    "AUDUSD",  # Commodity forex — Asian/London overlap
    "USDCAD",  # Oil-correlated — good volatility
    "USDJPY",  # Yen pairs — fast moves, scalping-friendly
    # JPY crosses (restored 2026-08-26)
    "EURJPY",  # Volatile cross, good London moves
    "AUDJPY",  # Risk-on cross, good Asian/London
    "CADJPY",  # Oil-linked cross
    # Metals (restored 2026-08-26)
    "XAUUSD",  # Gold — swing mode (GOLD_SWING), primary symbol
    "XAGUSD",  # Silver — WR 34.6%, PF 1.05 scalp
    # Crypto (restored 2026-08-26)
    "BTCUSD",  # High volatility, 24/7
    "ETHUSD",  # Follows BTC
    # Energy / commodities (restored 2026-08-26)
    "XTIUSD",  # WTI crude
    "XBRUSD",  # Brent crude
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
# SCALPING ENGINE (advanced SMC liquidity-sweep + statistical mean-reversion)
# =============================================================================
# Decoupled scalping strategy driven by ai_trading_agents/scalping_engine.py.
# It writes its own signal files (trendmaster_scalp_<SYM>.json) consumed by the
# executor. Latency-insensitive by design: entries are PENDING LIMIT orders
# (server-side fills) + strict spread/session/kill-switch filters, so the
# async Python-brain -> JSON -> executor path is viable for retail scalping.
ENABLE_SCALPING = True

SCALPING = {
    # Min confidence before a scalp setup is emitted (engine also gates).
    "min_confidence": 0.60,
    # Symbol allowlist for scalping. Validated by walk-forward (in-sample vs
    # out-of-sample, ~10k bars each) on 2026-05..08 data: only these THREE were
    # positive-expectancy AND profit-factor>1 on BOTH windows. All other tested
    # pairs (GBPJPY, AUDUSD, EURJPY, GBPUSD, AUDJPY, NZDUSD, USDCAD, NAS100...)
    # flipped negative out-of-sample and are excluded until they pass their own
    # walk-forward. Add a symbol here only after it clears that bar.
    "symbols": [
        "EURUSD", "USDJPY", "XAUUSD",
    ],
    # Spread filter is THE scalping killer. Max spread in POINTS (1.0 pip on
    # most FX = 10 pts; XAUUSD 1 pip = 10 pts; JPY pairs 1 pip = 100 pts).
    # Abandon market when spread exceeds this. Per-symbol override below.
    "max_spread_points": 35,
    "max_spread_points_per_symbol": {
        "XAUUSD": 60, "XAGUSD": 80, "BTCUSD": 200, "ETHUSD": 200,
        "USDJPY": 45, "GBPJPY": 60, "EURJPY": 55, "AUDJPY": 55,
        "CADJPY": 55, "GBPUSD": 35, "EURUSD": 30, "AUDUSD": 35,
        "USDCAD": 40, "NZDUSD": 38,
    },
    # Sessions allowed to trade (UTC-hour windows). London/NY overlap is the
    # highest-quality scalping window; Asian is reserved for mean-reversion.
    "sessions": {
        "london_open": [7, 10],     # 07:00-10:00 UTC
        "london_ny_overlap": [12, 16],  # 12:00-16:00 UTC (best)
        "ny_open": [13, 17],         # 13:00-17:00 UTC
        "asian": [0, 5],             # 00:00-05:00 UTC (mean-reversion only)
    },
    # Strategy mode selection by session/volatility.
    "momentum_sessions": ["london_open", "london_ny_overlap", "ny_open"],
    "meanrev_sessions": ["asian"],
    # SMC (momentum-sweep) tuning.
    "smc": {
        "pivot_left": 3,
        "pivot_right": 3,
        "swing_lookback": 60,        # bars to hunt liquidity pools
        "min_impulse_atr": 0.6,      # impulse leg must exceed this x ATR
        "ob_lookback": 30,
        "sl_buffer_atr": 0.3,        # SL beyond liquidity sweep extreme
        "tp_sl_ratio": 2.0,          # TP = tp_sl_ratio * SL distance
        # Raised from 18 -> 25 after walk-forward showed the edge collapsed
        # out-of-sample in choppy regimes. Stronger-trend requirement = fewer
        # but higher-quality SMC entries that survive regime change.
        "min_htf_adx": 25,           # H1 trend strength required
        # Quality gates below are OPT-IN. Backtests showed enabling them
        # over-filtered and regressed expectancy; left disabled (0) for now.
        "vol_z": 0.0,                # sweep bar must exceed vol_z x avg volume (0=off)
        "min_sweep_atr": 0.0,        # min sweep displacement in xATR (0=off)
        # Confluence filters (research-backed, Unicorn model = OB + FVG + displacement).
        # Left DISABLED (0): enabling them over-filtered and collapsed signal count
        # in walk-forward (edge needs volume of trades, not just quality). They
        # remain available as tuning knobs once more history is available.
        "require_fvg": 0.0,          # 1=require FVG confluence, 0=off
        "min_displacement_atr": 0.0, # CHoCH candle body must exceed this x ATR (0=off)
        "fib_low": 0.50, "fib_high": 0.79,  # discount/OTE zone for limit entry
    },
    # Mean-reversion tuning (quiet sessions).
    "meanrev": {
        "boll_period": 20,
        "boll_std": 2.0,
        "zscore_period": 50,
        "zscore_entry": 2.5,         # tighter: only fade a genuinely stretched market
        "rsi_period": 14,
        "rsi_extreme": 28,           # enter fade when RSI beyond this
        # Lowered 24 -> 20: only fade when H1 is clearly NOT trending, so MR
        # stops getting run over in trending OOS regimes.
        "max_htf_adx": 20,           # only fade when H1 NOT trending hard
        "sl_atr_mult": 1.0,
        "tp_atr_mult": 1.4,          # target VWAP/mid-band
    },
    # Kill-switch: if recent loss streak >= this, halt scalp emissions.
    "max_consecutive_losses": 3,
    # Max scalp signals per symbol per UTC day (enforced in engine state).
    "max_per_symbol_per_day": 8,
    # Max scalp signals per minute across all symbols (rate limiter).
    "max_per_minute": 6,
    # Trade management (research: 1R break-even + 50% scale-out is the most
    # robust exit for momentum/SMC trades; mean-reversion keeps full exits).
    "scale_out": {
        "enabled": True,     # SMC only; MR exits full
        "frac": 0.5,         # close this fraction at TP1 (=+1R)
        "be_at_r": 1.0,      # move rest to break-even once TP1 hit
    },
    # Max hold: close the scalp if neither SL nor TP triggers within this many
    # M5 bars (~90 min at 18). Caps bleeders that never reach a target.
    "max_hold_bars": 18,
    # Min ATR (price units) to avoid dead markets.
    "min_atr": 0.0,
    # Magic numbers for scalp legs (separate from QUICK/TREND so the trailing
    # manager / dashboard can tell them apart).
    "magic": 241000,
}

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
# ACCOUNT SETTINGS ($200 USD — Compound Growth Mode)
# =============================================================================
# [2026-08-25] Switched to $200 seed capital for compound growth strategy.
# Target: $200 -> $500,000 in ~14 months via aggressive compounding.
# Monte Carlo validated: 0% blow-up rate across 500 simulations.
# Key: 3% risk per trade, compound all profits, 5 quality trades/day.
ACCOUNT_CURRENCY = "USD"
INITIAL_BALANCE_USD = 200
INITIAL_BALANCE_INR = 17000  # ~$200 USD
LEVERAGE = 500  # 1:500 leverage (maximizes compounding on small account)
COMPOUND_GROWTH_MODE = True  # Enable phase-based risk scaling

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
    # [shared-config 2026-04-29] Values now derive from
    # config/trading_config.yaml first, then env override, then hardcoded
    # fallback. Edit the YAML to change Python AND MQL5 EA in one place.
    "risk_percent": _es("RISK_PERCENT", "risk.risk_percent", 3.0, float),  # [2026-08-25] 0.5% -> 3% for compound growth phase 1
    "max_daily_drawdown_percent": _es(
        "MAX_DAILY_DRAWDOWN", "risk.max_daily_drawdown_percent", 3.0, float
    ),
    # [R11 2026-04-23] Lifted concurrency so per-team caps can actually bind.
    # Previous value (2) meant the single global gate starved every pair after
    # 2 fills. With 4 teams × max 2 per team = 8 theoretical concurrent slots
    # (realistically 3-5 on any given day due to session + corr filters).
    "max_open_trades": _es("MAX_OPEN_TRADES", "risk.max_open_trades", 8, int),
    "max_open_per_team": _es(
        "MAX_OPEN_PER_TEAM", "risk.max_open_per_team", 15, int  # [2026-08-26] SCALPING: 2→15 no per-team limit
    ),
    "trade_cooldown_minutes": 5,
    "symbol_cooldown_minutes": 20,
    "max_trades_per_day": 35,  # [2026-08-25] 20 -> 35 for multi-pair scalping (5/pair x 7 pairs)
    "max_trades_per_symbol_per_day": 5,  # [2026-08-25] 2 -> 5 for high-frequency scalping
    "max_consecutive_losses": 3,  # aligned with PROFIT_OPTIMIZER.max_consec_losses
    "cooldown_duration_hours": 1,
    "equity_drawdown_halt_pct": 8.0,  # [2026-08-25] 5% -> 8% — compound mode needs more room
    # [R7 2026-04-23] True 1:3 RR sustainable mode. Backtest proved 80% WR
    # at 1:3 RR NOT achievable on real XAUUSD M5 (trader's triangle math).
    # BEST profitable 1:3 config:
    #   ADX40 filter + SL 1.0 / TP 3.0 = 32.5% WR, +0.266R expectancy.
    # Every additional filter made it LESS profitable — filtering kills
    # edge faster than it kills loss count. Accept 32.5% WR; math works:
    #   expectancy = 0.325 * 3 + 0.675 * (-1) = +0.3R per trade
    # 295 trades on 50K bars = ~1 trade per 170 M5 bars = selective.
    "min_risk_reward": 2.0,  # TP/SL = 2.5/1.2 = 2.08R minimum
    "default_sl_atr_multiple": 0.8,  # [2026-08-25] Tighter SL for scalping (was 1.2)
    "default_tp_atr_multiple": 2.0,  # [2026-08-25] Faster TP for scalping (was 2.5)
    "min_sl_pips": 5,  # MINIMUM stop-loss: 5 pips (hardcoded floor)
    # Adaptive Trailing Stop
    "trailing_stop_enabled": True,
    "trailing_activation_pips": 25,  # Activate at 1.5R
    "trailing_distance_pips": 18,  # Trail by 0.5x ATR
    "trailing_distance_pips_spike": 12,
    "trail_atr_multiplier": 0.8,
    "trail_atr_multiplier_spike": 0.5,
    "max_trail_pips": 30,
    "max_trail_pips_spike": 18,
    "trailing_step_pips": 4,
    "breakeven_pips": 20,
    "max_candles_in_trade": 24,
    "min_lot_size": 0.01,
    "max_lot_size": 0.50,  # [2026-08-25] 0.03 -> 0.50 for compound growth (scales with equity)
    "compound_profits": True,  # [2026-08-25] REINVEST all profits for exponential growth
    "max_corr_same_dir": 8,  # [2026-08-26] SCALPING: 2→8 no correlation limit
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
    "XAGUSD": {  # [2026-08-25] #2 PAIR: WR 34.6%, PF 1.05, AvgR +$0.254
        "sl_atr_mult": 1.2,
        "tp_atr_mult": 2.5,
        "min_rr": 2.0,
        "trail_activation_pips": 60,
        "trail_distance_pips": 40,
        "max_spread_pips": 25,
        "max_trades_per_day": 6,
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
    "USDCHF": {  # [2026-08-25] Grid-search: WR 31.5%, PF 1.37, ExpR +$0.010
        "sl_atr_mult": 1.2,
        "tp_atr_mult": 3.0,  # Wider TP — patient on CHF
        "min_rr": 2.5,
        "trail_activation_pips": 22,
        "trail_distance_pips": 16,
        "max_spread_pips": 18,
        "max_trades_per_day": 5,
    },
    "EURUSD": {  # [2026-08-25] Grid-search: WR 35.8%, PF 1.32, ExpR +$0.012
        "sl_atr_mult": 1.2,
        "tp_atr_mult": 3.0,  # Wider TP for EURUSD — more patient
        "min_rr": 2.5,
        "trail_activation_pips": 20,
        "trail_distance_pips": 15,
        "max_spread_pips": 12,
        "max_trades_per_day": 5,
    },
    "GBPUSD": {  # [2026-08-25] Grid-search optimized: WR 31.0%, PF 1.25, ExpR +$0.008
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 2.0,
        "min_rr": 2.5,
        "trail_activation_pips": 18,
        "trail_distance_pips": 12,
        "max_spread_pips": 18,
        "max_trades_per_day": 6,
    },
    "AUDUSD": {  # [2026-08-25] Grid-search: WR 37.3%, PF 1.35, ExpR +$0.011
        "sl_atr_mult": 1.2,
        "tp_atr_mult": 2.5,
        "min_rr": 2.0,
        "trail_activation_pips": 18,
        "trail_distance_pips": 13,
        "max_spread_pips": 15,
        "max_trades_per_day": 5,
    },
    "USDJPY": {  # [2026-08-25] STAR PAIR: WR 34.7%, PF 1.32, AvgR +$1.00
        "sl_atr_mult": 0.8,  # Grid-search optimal: tight SL = faster exit on losers
        "tp_atr_mult": 2.0,  # Grid-search optimal: quick TP captures momentum
        "min_rr": 2.5,  # Enforce 2.5R minimum
        "trail_activation_pips": 15,
        "trail_distance_pips": 10,
        "max_spread_pips": 12,
        "max_trades_per_day": 8,  # High-frequency scalping
    },
    "NZDUSD": {  # [2026-08-25] Grid-search: WR 30.7%, PF 1.02, marginal
        "sl_atr_mult": 1.2,
        "tp_atr_mult": 2.5,
        "min_rr": 2.0,
        "trail_activation_pips": 16,
        "trail_distance_pips": 12,
        "max_spread_pips": 20,
        "max_trades_per_day": 4,
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
    # Brain update cadence — 2s for scalping speed.
    "inference_interval_ms": 2000,
    # Multi-timeframe alignment — ALL THREE must agree for a signal.
    # This is the "simple but profitable" filter the user asked for:
    #   M30 = entry timing (fast momentum kicks in)
    #   H1  = short-trend confirmation
    #   H4  = macro/regime direction
    # 3-of-3 MTF + 3-of-3 EA confirmations = very high-quality entries only.
    # [2026-08-25] M30 dropped per operator "more trades" — H1+H4 trend
    # agreement still required; M30 was the strictest timing gate.
    "mtf_alignment": {
        "M30": False,
        "H1": True,
        "H4": True,
    },
    # Minimum confidence before brain writes BUY/SELL. Higher = fewer, stronger.
    # [R11 2026-04-23] Lowered 0.82 → 0.70 after zero-trades-in-24hrs audit.
    # [R12 2026-04-30] Lowered 0.70 → 0.58 after 1-trade-in-6-weeks audit.
    #   At 0.70 only 7/18 symbols ever clear the gate (rule-mode peak conf=0.83);
    #   live trade count was 1 deal in 47 days. Walkforward across all 19 CSVs
    #   (reports/walkforward/2026-04-30_1535.md) shows positive expR=0.11–0.43R
    #   for every pair at SL=1.5/TP=3.0, so admitting moderate-conviction rule
    #   signals (score ≥0.38) is data-supported, not a noise-trade decision.
    #   0.58 matches brain's hardcoded fallback (trend_master_brain.py:266).
    #   Session-boost drops peak to 0.53 (still above the 0.50 hard floor in
    #   _effective_min_conf). Operator floor preserved.
    "min_ml_confidence": _es("MIN_ML_CONFIDENCE", "brain.min_ml_confidence", 0.46, float),  # [2026-08-26] SCALPING MODE: lowered 0.54→0.46 to let more signals through
    # Advanced-agent voting. Each agent returns +1/-1/0. Final direction needs
    # at least `agent_min_votes` agreeing votes (out of len(agents)).
    # Agents:
    #   trend_agent      — H4 EMA20 vs EMA50 + ADX strength
    #   momentum_agent   — H1 MACD histogram direction + momentum
    #   timing_agent     — M30 Bollinger mid cross + RSI midband
    # [R11 2026-04-23] 3 → 2. Three-of-three agent agreement is rare in
    # low-vol regimes (overnight/Asian). Two-of-three is still selective
    # (66% quorum) but actually fires. If quality degrades, raise back.
    "agent_min_votes": 1,  # [2026-08-26] SCALPING: 1-of-3 agents = enough (was 2, too strict)
    # Kelly sizing parameters (scales EA's risk % by this).
    "kelly_lookback_trades": 40,
    "kelly_min_samples": 20,
    "kelly_max_fraction": 2.0,  # hard cap multiplier
    "kelly_floor_fraction": 0.25,  # never go below 25% of base risk
    "use_kelly_sizing": True,  # 2026-08-25: flipped from False after shadow review
    # Feature engineering windows (for LightGBM model)
    "feature_windows": [5, 10, 20, 50],
    "include_orderflow": True,  # tick imbalance if MT5 tick stream available
    "include_session_feature": True,  # London / NY / overlap / Asian one-hot
    # [Phase B3 2026-04-26] Smart-money (COT + EIA) feature enrichment.
    # model has been replaced with the B3-trained model (trend_master_model_v2.lgb
    # copied to trend_master_model.lgb). Restart brain to activate V2 inference.
    "smartmoney_features_enabled": True,
    "advanced_features_enabled": True,  # frac-diff, Hurst, realized skew, Donchian distance
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
    # [2026-08-26] SCALPING MODE: disabled vol_regime + session_window + news_blackout
    # to maximize trade frequency. Loss cooldown + daily loss limit remain for safety.
    "spread_guard": False,
    "vol_regime": False,   # [2026-08-26] Disabled for scalping — let all vol through
    "profit_lock": False,  # [2026-08-26] Disabled — no daily profit cap, let winners run
    "loss_cooldown": True,
    "session_window": False,  # [2026-08-26] SCALPING: trade all hours
    "news_blackout": False,  # [2026-08-26] SCALPING: ignore news calendar
    "daily_loss_limit": True,  # max-DD circuit breaker (Phase G4)
    # Spread guard
    "max_spread_atr_ratio": 0.25,  # spread > 25 % of ATR → veto
    # Volatility regime
    # 2026-04-28: lowered from 0.20 -> 0.10 after extended dead-market veto
    # streak (XAUUSD/ETHUSD/XBRUSD/XTIUSD/EURUSD all stuck below q20 for hours).
    # 2026-05-10: lowered 0.10 -> 0.05 after weekend BTC sustained dead-market
    # veto blocked all signals (ATR ~207 vs q10 ~216 for hours). Operator
    # chose this over enabling INFERRED guessing on TV alerts. Direction
    # stays correct via brain rule-based ema/adx/rsi; just admits more
    # low-volatility regimes. NOTE: this is the load-bearing value. YAML
    # was edited too but PROFIT_OPTIMIZER doesn't yet route through
    # env_or_shared for this field (TODO: migrate via shared_config_loader).
    "vol_min_quantile": 0.05,  # below 5th-pct ATR = dead market, skip
    "vol_max_quantile": 0.95,  # above 95th-pct ATR = spike regime, skip
    # Profit lock
    # [2026-08-25] Compound mode: NO daily profit cap — let winners run!
    "daily_profit_target_pct": 100.0,  # Effectively disabled — compound all profits
    # (lock 2 % a day = ~50 %/month compounded
    #  — far above retail-bot reality, so any
    #  green day is worth securing.)
    # Loss-streak cooldown
    # [2026-08-25] Compound growth mode: 4 losses before cooldown (was 3)
    # At 35% WR with 5 trades/day, expect 2-3 losses per day. Need room.
    "max_consec_losses": 4,
    "cooldown_hours": 2,  # [2026-08-25] 4h -> 2h — faster recovery for compound mode
    # Session window (UTC hours we consider tradable)
    # [2026-08-25] was range(7,21); operator wants more trades → 24h.
    # NOTE: PyYAML is missing in prod venv so trading_config.yaml is INERT;
    # this hardcoded dict is the live source. Keep both in sync when PyYAML lands.
    "best_hours_utc": list(range(0, 24)),  # [2026-08-26] SCALPING: 24h trading
    # News blackout — looks at config/news_calendar.json for events
    # of the listed impact and refuses trades inside the asymmetric window.
    # Operator policy 2026-05-04: TV signals get 60 min runway BEFORE a
    # high-impact release (catches the spread blow-out and pre-positioning),
    # then 30 min cooldown AFTER (post-release whipsaw protection).
    "news_lead_minutes": 60,        # blocked window BEFORE event (minutes)
    "news_lag_minutes": 30,         # blocked window AFTER event (minutes)
    "news_window_minutes": 60,      # legacy symmetric — kept for callers that don't pass lead/lag
    "news_impact_levels": ("high",),  # 'high' / 'medium' / 'low'
    # Daily-loss limit (Phase G4 — max-drawdown circuit breaker)
    # max_loss_pct: hard stop at -X % vs. start-of-day equity. Once tripped,
    # the brain stamps `drawdown_lockout_until` to the end of the UTC day so
    # the rest of the session is blocked even if equity briefly rebounds.
    # intraday_dd_pct: tighter prop-firm-style trail — locks when you give
    # back gains, not just when you go red. Set to None to disable.
    # 2026-05-07 (Sumit): bumped 3.0 -> 5.0 because $1k account size means
    # 3% = only $30 headroom; one normal stop on XAUUSD M15 (~$15) plus
    # any spread/slippage already eats half. 5% keeps the brake but stops
    # blocking the whole day after a single bad cluster of trades. Pair-cap
    # enforcement (long-USD/short-USD <=3) and per-symbol cooldown still
    # provide upstream protection.
    "daily_max_loss_pct": 5.0,  # -5 % vs. SoD equity → lock the day
    "intraday_dd_pct": 3.0,  # -3 % from intraday peak → lock the day
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
    # [2026-08-26] SCALPING overrides for restored pairs
    "AUDUSD": {"fast": "M15", "mid": "M30", "slow": "H1"},  # commodity forex scalp
    "USDCAD": {"fast": "M15", "mid": "M30", "slow": "H1"},  # oil-correlated scalp
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
# 2026-08-25: Promoted from shadow to live after review period.
KELLY_SIZING = {
    "enabled": True,  # LIVE — sizes positions based on recent win rate.
    "shadow": False,  # flipped 2026-08-25 after shadow review period.
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
    "enabled": True,  # ON — supplements static _CORR_GROUPS with live correlations
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
    "enabled": True,  # ON — incremental per-team classifier updates on every closed trade
    "predict_active": False,  # if True, blends p_win into conf gate
    "model_path_template": "ai_trading_agents/ml_models/online_{team}.pkl",
    "update_on_close": True,  # learn_one on every trade_tracker hit
    "blend_weight": 0.2,  # weight given to online prediction
}

# ---- 8-Layer Confluence Scoring (ai_trading_agents/scoring.py) ----------
# Precision strategy gate — only fire signals with sufficient confluence
# across trend, momentum, volatility, session, MTF, price action, volume,
# and stochastic. Grid-search optimized: min_score=5.0 across 192 configs.
# 2026-08-25: Activated as final gate in tick_once() after agent vote + risk_manager.
CONFLUENCE_SCORING = {
    "enabled": True,
    "min_score": 2.5,  # [2026-08-26] SCALPING: lowered 6.0→2.5 for more trades (score range 0-10.3)
    # Max possible score: ~10.3. At 3.0, only 3 of 8 layers need to align.
    # Previously 6.0+ produced 2059 trades (too few, breakeven)
    "confidence_boost_pct": 0.05,  # +5% conf per point above min_score
    "max_confidence_boost": 0.20,  # Cap boost at +20% (was 15%)
    # [2026-08-26] SCALPING: relaxed chop veto
    "veto_chop_adx_threshold": 10,  # ADX < 10 only (was 18 — too aggressive)
    "veto_high_vol_atr_mult": 0,    # Disabled — high_vol is best regime
    # [2026-08-25] VALIDATED PAIRS (dropped after 350K-bar backtest):
    # EURUSD: PF 1.14, MaxDD 0.5% — KEEP
    # NZDUSD: PF 1.13, MaxDD 0.3% — KEEP
    # USDCHF: PF 1.11, MaxDD 0.3% — KEEP
    # GBPUSD: PF 1.03, MaxDD 0.5% — KEEP
    # XAGUSD: PF 0.80, MaxDD 90.5% — DROPPED (account killer)
    # USDJPY: PF 0.94, MaxDD 84.4% — DROPPED (account killer)
    # AUDUSD: PF 0.94, MaxDD 0.6% — DROPPED (marginal)
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
    "require_all_3": False,  # EA will accept 2-of-3 agreement (was 3-of-3)
    "max_spread_atr_pct": 0.40,  # EA spread guard threshold
}

# =============================================================================
# TRADINGVIEW SIGNAL MODE (added 2026-05-01)
# =============================================================================
# When enabled, the TradingView webhook receiver becomes the sole writer of
# the EA signal JSON. The brain still runs a full tick (features → ML → rule
# → confidence) but its `write_signal()` is short-circuited into shadow-log
# mode (logs/brain_shadow_predictions.jsonl) so we accumulate "what the brain
# would have done" data without it racing the TV path on disk.
#
# Why this exists: 6 weeks of live trading with the rule+ML stack produced
# 1 trade. Operator decision to hand the entry decision to TradingView and
# let the brain learn from real outcomes for future advance work.
#
# To activate:
#   1. Set TV_WEBHOOK_SECRET in config/.env (random 32+ chars)
#   2. Set TV_SIGNAL.enabled = True below
#   3. start_brain_clean.cmd          (so shadow mode kicks in)
#   4. start_tv_webhook.cmd            (in another shell)
#   5. Expose port via ngrok / Cloudflare tunnel
#   6. Configure TV alert with the JSON template — see docs/TV_SIGNAL_SETUP.md
TV_SIGNAL = {
    "enabled": False,             # ← flipped OFF 2026-08-22: TV Pro lapsed; local brain trades again
    "shadow_brain": True,          # brain still infers, but doesn't write EA signals
    "default_confidence": 0.95,    # what we pass to EA when TV alert lacks one
    "force_skip_quorum": True,     # write require_all_3=False so EA bypasses 3-of-3
    "max_signal_age_s": 60,        # reject TV alerts older than this many seconds
    "log_path": "logs/tv_signals.jsonl",       # audit trail of every TV→EA hop
    "shadow_log_path": "logs/brain_shadow_predictions.jsonl",  # brain's "what I would've done"
    "signal_filename": "trendmaster_signals.json",  # base; per-symbol uses _<SYMBOL>.json
    "primary_symbol": "XAUUSD",
    "use_common": False,            # MT5 FILE_COMMON path; matches brain's USE_COMMON
}

# =============================================================================
# TV SIGNAL QUALITY FILTER (added 2026-05-04 — Phase 2 learner)
# =============================================================================
# Brain consumes incoming TV webhook signals + tracks MT5 trade outcomes,
# computes per-(symbol, TF, direction, hour-bucket) rolling expectancy.
#
#   enabled=False (default): Phase 1 mode — TAKE ALL signals, just log
#                            outcomes. Lets data accumulate.
#   enabled=True:            Phase 2 mode — BLOCK signal classes whose
#                            rolling expectancy is below threshold AFTER
#                            min_trades_to_filter trades have closed.
#                            Classes still under min_trades are ALLOWED
#                            (still learning).
#
# Operator should leave Phase 1 active for at least 100-200 trades worth
# of data per signal class before flipping to Phase 2.
TV_QUALITY_FILTER = {
    "enabled": True,                   # 2026-05-06: activated early — start filtering as data arrives
    "min_trades_to_filter": 10,        # 30 -> 10: filter activates earlier per class
    "expectancy_threshold_R": -0.1,    # 0.0 -> -0.1: lenient initially; tighten later
    "rolling_window_trades": 100,      # only consider last N trades per class
    "hour_bucket_size": 4,             # 4h buckets = 6 buckets/day (London/NY/Asian split)
}

# =============================================================================
# TRADINGVIEW EMAIL POLLER (added 2026-05-01 — free-plan path)
# =============================================================================
# TV Free plan has no webhook support. This block configures the IMAP poller
# (`ai_trading_agents/tv_email_receiver.py`) which polls Gmail for TV alert
# emails and dispatches them to the same `write_tv_signal()` the webhook uses.
# Latency: ~10–20 s end-to-end (TV email send + IMAP poll). Acceptable for
# swing / intra-day; not for sub-minute scalp.
#
# To activate:
#   1. Generate Gmail App Password (Google Account → Security → 2-Step
#      Verification → App passwords). NOT your real Gmail password.
#   2. Add to config/.env:
#         TV_EMAIL_USER=you@gmail.com
#         TV_EMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx
#   3. Set TV_SIGNAL.enabled = True (above) so brain enters shadow mode.
#   4. start_tv_email.cmd
#   5. In TradingView: Create Alert → enable "Send email" notification.
#      No webhook URL needed (Free plan doesn't show that field anyway).
#
# Indicator messages on Free plan: TV's `alert()` mode usually carries the
# indicator's own hardcoded message (we can't override). The poller's
# fallback parser handles common formats — Rocket Prime "Buy Observation @"
# / "Sell Observation @", plus generic buy/sell/long/short keywords. Symbol
# is always extracted from the email subject ("Alert: <indicator> on <SYM>").
TV_EMAIL = {
    "enabled": True,                         # re-enabled 2026-08-22 — TV Pro lapsed, free-plan email path active
    "poll_interval_s": 10,                   # IMAP poll cadence (seconds)
    "from_filter": "noreply@tradingview.com",
    "max_age_minutes": 5,                    # skip emails older than this (stale)
    "telegram_echo": True,                   # mirror each signal to Telegram
    "dedup_window": 256,                     # last N Message-IDs cached
    "search_hours_back": 1,                  # IMAP search window (advisory)
    "backoff_min_s": 5,                      # IMAP reconnect backoff start
    "backoff_max_s": 120,                    # IMAP reconnect backoff cap
}
