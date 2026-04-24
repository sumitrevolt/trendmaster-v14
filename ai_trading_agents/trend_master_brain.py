"""
trend_master_brain.py — v14 TrendMaster Python AI brain
=========================================================

What it does
------------
Runs a tight inference loop (sub-second, "millisecond decision system"),
pulling the last M5 / M15 / H1 bars from MT5, building features, running
a LightGBM classifier, and writing a single JSON file:

    {"direction":"BUY","confidence":0.71,"ts":1712345678,"symbol":"XAUUSD"}

The companion EA `AI_SUPERBB_v14_TrendMaster.mq5` reads this file on every
new M5 bar and uses it as a THIRD confirmation gate, on top of the EA's
own SuperTrend + BB + MACD check.

So for an order to fire, we need:
    (EA 3-of-3 confirmations)  AND  (Python brain agrees with conf >= 0.58)

Why this architecture
---------------------
* MT5 EA stays in charge of execution (no IPC latency hell).
* Python brain owns feature engineering + ML + MTF alignment.
* Decoupled via a single JSON file — simple, robust, atomic.
* Either side can run standalone (brain missing → EA still works if
  InpAIRequired=false; EA missing → brain just logs and does nothing).

Safeguards
----------
* Atomic file write (temp file + os.replace) — EA never reads a torn file.
* Stale-check on timestamp — EA ignores anything older than 60 s.
* Fallback rule-based brain if LightGBM isn't installed — the system
  still works, just without the ML edge.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Allow imports from project root
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import settings  # noqa: E402
from ai_trading_agents.multi_agent import vote_all, AgentVote  # noqa: E402
from ai_trading_agents.profit_filters import evaluate_all  # noqa: E402
from ai_trading_agents.process_lock import SingleInstanceLock  # noqa: E402
from ai_trading_agents.state_store import StateStore  # noqa: E402
from ai_trading_agents.trade_tracker import TradeTracker, pnl_of  # noqa: E402
from ai_trading_agents.reentry_tracker import ReentryTracker  # noqa: E402

# [audit-fix 2026-04-22] wire portfolio-level risk manager into tick_once
from ai_trading_agents.risk_manager import (  # noqa: E402
    Position as _RMPosition,
    RiskConfig as _RMRiskConfig,
    RiskState as _RMRiskState,
    check_risk as _rm_check_risk,
    size_position as _rm_size_position,
    team_of as _rm_team_of,
)

# Telegram notifier — sync, throttled, never raises. Safe to call inline
# from the hot loop. If creds are missing or `requests` isn't installed it
# silently no-ops, so the brain runs identically with or without it.
try:
    from ai_trading_agents.telegram_notifier import get_notifier as _get_tg  # noqa: E402
except Exception:  # pragma: no cover — defensive, brain must never die on import
    _get_tg = None  # type: ignore

# Telegram command listener — pull-side counterpart to the notifier.
# Adds /status /pnl /symbols /ping /help. Same defensive import contract:
# missing creds or missing `requests` ⇒ silently disabled, brain unaffected.
try:
    from ai_trading_agents.telegram_commands import get_listener as _get_tg_cmds  # noqa: E402
except Exception:
    _get_tg_cmds = None  # type: ignore

# [enhancement 2026-04-23] Observability + drift + Kelly + panic — every
# one of these is gated on a settings.* toggle that defaults to False, so
# the import is safe on fresh checkouts. Imports are wrapped so a bug in
# any one module can't prevent the brain from booting.
try:
    from ai_trading_agents import metrics as _metrics  # noqa: E402
except Exception:
    _metrics = None  # type: ignore
try:
    from ai_trading_agents import drift_detector as _drift  # noqa: E402
except Exception:
    _drift = None  # type: ignore
try:
    from ai_trading_agents.kelly_sizer import (  # noqa: E402
        apply as _kelly_apply,
        KellyConfig as _KellyConfig,
    )
except Exception:
    _kelly_apply = None  # type: ignore
    _KellyConfig = None  # type: ignore
try:
    from ai_trading_agents.panic import flatten_all_positions as _panic_flatten  # noqa: E402
except Exception:
    _panic_flatten = None  # type: ignore

# [enhancement 2026-04-23 Round 3] Institutional-grade modules:
#   portfolio_risk: real-time VaR/CVaR snapshot
#   event_log:      append-only JSONL audit trail
#   meta_labeler:   Lopez de Prado secondary classifier
#   regime_hmm:     HMM chop/trend detector
#   rolling_corr:   live rolling-correlation risk cap
#   ab_test:        shadow-mode variant comparison
#   online_learner: per-team incremental classifier
# All gated on settings.*.enabled — imports are safe on fresh checkouts.
try:
    from ai_trading_agents import portfolio_risk as _portfolio_risk  # noqa: E402
except Exception:
    _portfolio_risk = None  # type: ignore
try:
    from ai_trading_agents import event_log as _event_log  # noqa: E402
except Exception:
    _event_log = None  # type: ignore
try:
    from ai_trading_agents.meta_labeler import MetaLabeler as _MetaLabeler  # noqa: E402
except Exception:
    _MetaLabeler = None  # type: ignore
try:
    from ai_trading_agents.regime_hmm import RegimeHMM as _RegimeHMM  # noqa: E402
except Exception:
    _RegimeHMM = None  # type: ignore
try:
    from ai_trading_agents.rolling_corr import RollingCorrMatrix as _RollingCorr  # noqa: E402
except Exception:
    _RollingCorr = None  # type: ignore
try:
    from ai_trading_agents.ab_test import ABTester as _ABTester  # noqa: E402
except Exception:
    _ABTester = None  # type: ignore
try:
    from ai_trading_agents.online_learner import OnlineLearner as _OnlineLearner  # noqa: E402
except Exception:
    _OnlineLearner = None  # type: ignore

# [enhancement 2026-04-23 R4 — operator grade] performance analytics, daily
# digest, market calendar, gate-value attribution.
try:
    from ai_trading_agents import performance as _perf  # noqa: E402
except Exception:
    _perf = None  # type: ignore
try:
    from ai_trading_agents import daily_digest as _digest  # noqa: E402
except Exception:
    _digest = None  # type: ignore
try:
    from ai_trading_agents.market_calendar import is_market_open as _is_market_open  # noqa: E402
except Exception:
    _is_market_open = None  # type: ignore
try:
    from ai_trading_agents import gate_value as _gate_value  # noqa: E402
except Exception:
    _gate_value = None  # type: ignore

# [R8 2026-04-23] Per-symbol optimized params from backtest sweep.
try:
    from ai_trading_agents.pair_params import PAIR_PARAMS as _PAIR_PARAMS
except Exception:
    _PAIR_PARAMS = {}  # type: ignore

# [R9 2026-04-23] Per-TEAM optimized params (research-informed asset-class
# grids). Team-level is less prone to overfitting than per-symbol — preferred
# when its expectancy is positive. Falls back to per-symbol then to defaults.
try:
    from ai_trading_agents.team_params import (
        TEAM_PARAMS as _TEAM_PARAMS,
        SYMBOL_TO_TEAM as _SYMBOL_TO_TEAM,
    )
except Exception:
    _TEAM_PARAMS = {}  # type: ignore
    _SYMBOL_TO_TEAM = {}  # type: ignore


def _pair_sl_tp(sym: str) -> tuple:
    """Return (sl_atr_mult, tp_atr_mult, adx_min) optimised for this symbol.

    Lookup order (R9):
      1. team-level config (TEAM_PARAMS) — robust, research-informed
      2. per-pair config (PAIR_PARAMS) — tighter but more overfit-prone
      3. conservative defaults

    Team-level is preferred because it pools 2-12 symbols' worth of data
    per config, reducing overfitting. Per-pair is fallback for symbols
    not yet in a team bucket.
    """
    # Team lookup first.
    team = _SYMBOL_TO_TEAM.get(sym)
    if team:
        tp_cfg = _TEAM_PARAMS.get(team) or {}
        if tp_cfg:
            return (
                float(tp_cfg.get("sl_atr_mult", 1.5)),
                float(tp_cfg.get("tp_atr_mult", 3.0)),
                float(tp_cfg.get("adx_min", 22.0)),
            )
    # Fallback — per-pair.
    p = _PAIR_PARAMS.get(sym) or {}
    sl = float(p.get("sl_atr_mult", 1.5))
    tp = float(p.get("tp_atr_mult", 3.0))
    adx = float(p.get("adx_min", 22.0))
    return sl, tp, adx


# ── Optional heavy deps ─────────────────────────────────────────────────
try:
    import lightgbm as lgb  # type: ignore

    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False

try:
    import MetaTrader5 as mt5  # type: ignore

    _HAS_MT5 = True
except ImportError:
    _HAS_MT5 = False

logger = logging.getLogger("trend_master_brain")


# =========================================================================
#                          CONFIG SHORTCUTS
# =========================================================================
CFG = getattr(settings, "TRENDMASTER_V14", {})
PF_CFG = getattr(settings, "PROFIT_OPTIMIZER", {})
USE_PROFIT_FILTERS = bool(PF_CFG.get("enabled", True))
SYMBOL = CFG.get("primary_symbol", "XAUUSD")
TF = CFG.get("primary_timeframe", "M5")
INFER_MS = int(CFG.get("inference_interval_ms", 250))
MIN_CONF = float(CFG.get("min_ml_confidence", 0.58))
# [R11 2026-04-23] Session confidence boost — when we're inside the London-NY
# overlap (peak_hours_utc) or on the shoulder, _effective_min_conf() returns
# MIN_CONF minus the configured boost, so more signals fire during high-
# liquidity windows WITHOUT raising risk_percent. Hard floor at 0.50 so we
# never degrade below coin-flip+margin.
SESSION_BOOST_CFG = getattr(settings, "SESSION_BOOST", {}) or {}


def _effective_min_conf(now_utc: Optional[datetime] = None) -> float:
    """Return MIN_CONF discounted by peak/shoulder session boost."""
    if not SESSION_BOOST_CFG.get("enabled", False):
        return MIN_CONF
    h = (now_utc or datetime.now(timezone.utc)).hour
    peak = SESSION_BOOST_CFG.get("peak_hours_utc", []) or []
    shoulder = SESSION_BOOST_CFG.get("shoulder_hours_utc", []) or []
    try:
        if h in peak:
            return max(0.50, MIN_CONF - float(SESSION_BOOST_CFG.get("peak_boost", 0.0)))
        if h in shoulder:
            return max(0.50, MIN_CONF - float(SESSION_BOOST_CFG.get("shoulder_boost", 0.0)))
    except (TypeError, ValueError):
        pass
    return MIN_CONF


SIG_FILE = CFG.get("signal_file", "trendmaster_signals.json")
USE_COMMON = bool(CFG.get("use_common_folder", False))
MTF = CFG.get("mtf_alignment", {"M5": True, "M15": True, "H1": True})
FEAT_WINDOWS = CFG.get("feature_windows", [5, 10, 20, 50])
AGENT_MIN_VOTES = int(CFG.get("agent_min_votes", 3))
USE_AGENTS = bool(CFG.get("use_multi_agent", True))

# [audit-fix 2026-04-22] RISK settings shortcut — risk_manager.check_risk()
# is called every signal BEFORE the brain writes a non-NONE direction.
RISK_CFG_RAW = getattr(settings, "RISK", {}) or {}


def _build_risk_config() -> "_RMRiskConfig":
    """Map config/settings.py RISK keys → risk_manager.RiskConfig fields.

    Settings keys don't line up 1:1 with the dataclass, so we translate
    defensively — anything missing falls back to the RiskConfig default.
    """
    kw: Dict = {}
    if "risk_percent" in RISK_CFG_RAW:
        kw["risk_per_trade_pct"] = float(RISK_CFG_RAW["risk_percent"])
    if "max_open_trades" in RISK_CFG_RAW:
        kw["max_open_total"] = int(RISK_CFG_RAW["max_open_trades"])
    # [R11 2026-04-23] Prefer explicit `max_open_per_team` from settings; fall
    # back to the legacy derived value (// 2 + 1) only when that key is absent
    # so older settings files keep working.
    if "max_open_per_team" in RISK_CFG_RAW:
        try:
            kw["max_open_per_team"] = max(1, int(RISK_CFG_RAW["max_open_per_team"]))
        except (TypeError, ValueError):
            if "max_open_trades" in RISK_CFG_RAW:
                kw["max_open_per_team"] = max(1, int(RISK_CFG_RAW["max_open_trades"]) // 2 + 1)
    elif "max_open_trades" in RISK_CFG_RAW:
        kw["max_open_per_team"] = max(1, int(RISK_CFG_RAW["max_open_trades"]) // 2 + 1)
    if "max_daily_drawdown_percent" in RISK_CFG_RAW:
        kw["max_daily_loss_pct"] = float(RISK_CFG_RAW["max_daily_drawdown_percent"])
    if "max_consecutive_losses" in RISK_CFG_RAW:
        kw["max_consec_losses"] = int(RISK_CFG_RAW["max_consecutive_losses"])
    # daily_profit_target_pct has no direct setting; leave default unless
    # operator adds one. PROFIT_OPTIMIZER.daily_profit_lock is handled by
    # profit_filters (separate layer), so we keep this conservative here.
    if "daily_profit_target_pct" in RISK_CFG_RAW:
        kw["daily_profit_target_pct"] = float(RISK_CFG_RAW["daily_profit_target_pct"])
    if "min_lot_size" in RISK_CFG_RAW:
        kw["min_lot"] = float(RISK_CFG_RAW["min_lot_size"])
    if "max_lot_size" in RISK_CFG_RAW:
        kw["max_lot"] = float(RISK_CFG_RAW["max_lot_size"])
    return _RMRiskConfig(**kw)


# Multi-symbol mode (added 2026-04-22) — when True, the brain iterates
# every symbol in TRADING_PAIRS each tick and writes a per-symbol signal
# file `trendmaster_signals_{SYMBOL}.json`. The legacy single-symbol JSON
# (`trendmaster_signals.json` for PRIMARY_SYMBOL) is preserved so existing
# EA installs keep working without recompile.
MULTI_SYMBOL = bool(CFG.get("multi_symbol", False))
ALL_SYMBOLS: List[str] = list(getattr(settings, "TRADING_PAIRS", [SYMBOL])) or [SYMBOL]
# Per-symbol timeframe override helper (falls back to M30/H1/H4).
try:
    _tf_for = settings.timeframes_for  # type: ignore[attr-defined]
except AttributeError:

    def _tf_for(_sym: str) -> List[str]:
        return ["M30", "H1", "H4"]


# Rate-limited "log this once per (symbol, key) per N seconds" helper.
# Stops EURGBP-style spam where the same veto ("dead market: ATR < q20")
# fires every 3-second tick and floods the log with hundreds of identical
# lines per minute. We keep the first occurrence (so you still see WHEN
# the gate first started biting) and then drop dups for `interval_s`.
# Added 2026-04-22.
_LOG_DEDUP_LAST: Dict[Tuple[str, str], float] = {}


def _log_dedup(key: Tuple[str, str], interval_s: float = 60.0) -> bool:
    """Return True if this (symbol, reason) hasn't been logged in the last
    `interval_s` seconds — i.e. it's safe to emit the log line now."""
    now = time.time()
    last = _LOG_DEDUP_LAST.get(key, 0.0)
    if now - last >= interval_s:
        _LOG_DEDUP_LAST[key] = now
        return True
    return False


def _tf_to_mt5(tf: str) -> int:
    if not _HAS_MT5:
        return 0
    return {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }.get(tf, mt5.TIMEFRAME_M5)


# =========================================================================
#                   MT5 CONNECTION RESILIENCE
# =========================================================================
# Production gripe: when MT5 freezes (broker push delay, antivirus, machine
# sleeping), the brain blocks for 60 s on copy_rates_from_pos and then dies.
# These wrappers give us:
#   * exponential-backoff initialize()
#   * single-call retry on data pulls
# Both are no-ops if _HAS_MT5 is False (CI / unit tests).
def _mt5_initialize_with_retry(max_attempts: int = 5, base_delay_s: float = 2.0) -> bool:
    if not _HAS_MT5:
        return False
    for attempt in range(1, max_attempts + 1):
        try:
            if mt5.initialize():
                if attempt > 1:
                    logger.info("MT5 connected on attempt %d", attempt)
                return True
            err = mt5.last_error()
            logger.warning("MT5 initialize attempt %d/%d failed: %s", attempt, max_attempts, err)
        except Exception as e:
            logger.warning("MT5 initialize attempt %d crashed: %s", attempt, e)
        delay = min(60.0, base_delay_s * (2 ** (attempt - 1)))
        time.sleep(delay)
    return False


def _mt5_copy_rates_safe(symbol: str, tf: int, n: int, retries: int = 2):
    """copy_rates_from_pos with one re-init attempt on transient failure."""
    if not _HAS_MT5:
        return None
    for attempt in range(1, retries + 1):
        try:
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, n)
            if rates is not None and len(rates) > 0:
                return rates
        except Exception as e:
            logger.debug("copy_rates_from_pos %s attempt %d failed: %s", symbol, attempt, e)
        # On second failure, try a quick re-init — broker may have nudged us.
        if attempt < retries:
            try:
                mt5.shutdown()
            except Exception:
                pass
            _mt5_initialize_with_retry(max_attempts=2, base_delay_s=1.0)
    return None


# =========================================================================
#                         FEATURE ENGINEERING
# =========================================================================
def _ema(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(span=n, adjust=False).mean()


def _rsi(x: pd.Series, n: int = 14) -> pd.Series:
    d = x.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    up = h.diff()
    dn = -l.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr_n = tr.rolling(n).mean().replace(0, np.nan)
    pdi = 100 * pd.Series(plus, index=df.index).rolling(n).mean() / atr_n
    ndi = 100 * pd.Series(minus, index=df.index).rolling(n).mean() / atr_n
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.rolling(n).mean()


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build the feature matrix the ML model consumes."""
    x = df.copy()
    x["ret_1"] = x["close"].pct_change()
    x["hl_rng"] = (x["high"] - x["low"]) / x["close"]

    for w in FEAT_WINDOWS:
        x[f"ema_{w}"] = _ema(x["close"], w)
        x[f"ret_{w}"] = x["close"].pct_change(w)
        x[f"vol_{w}"] = x["ret_1"].rolling(w).std()
        x[f"close_ema_{w}"] = (x["close"] - x[f"ema_{w}"]) / x["close"]

    x["rsi_14"] = _rsi(x["close"], 14)
    x["atr_14"] = _atr(x, 14)
    x["adx_14"] = _adx(x, 14)

    # EMA stack (trend signature)
    x["ema_stack_bull"] = ((x["ema_5"] > x["ema_20"]) & (x["ema_20"] > x["ema_50"])).astype(int)
    x["ema_stack_bear"] = ((x["ema_5"] < x["ema_20"]) & (x["ema_20"] < x["ema_50"])).astype(int)

    # BB context
    sma20 = x["close"].rolling(20).mean()
    std20 = x["close"].rolling(20).std()
    x["bb_z"] = (x["close"] - sma20) / std20.replace(0, np.nan)
    x["bb_width"] = (4 * std20) / sma20.replace(0, np.nan)

    # Session one-hot
    if CFG.get("include_session_feature", True):
        try:
            hours = x.index.hour  # type: ignore[attr-defined]
        except Exception:
            hours = pd.Series([0] * len(x))
        x["sess_london"] = ((hours >= 7) & (hours < 12)).astype(int)
        x["sess_ny"] = ((hours >= 13) & (hours < 20)).astype(int)
        x["sess_overlap"] = ((hours >= 12) & (hours < 16)).astype(int)
        x["sess_asian"] = ((hours >= 0) & (hours < 7)).astype(int)

    return x


FEATURE_COLS = [
    "ret_1",
    "hl_rng",
    "ret_5",
    "ret_10",
    "ret_20",
    "ret_50",
    "vol_5",
    "vol_10",
    "vol_20",
    "vol_50",
    "close_ema_5",
    "close_ema_10",
    "close_ema_20",
    "close_ema_50",
    "rsi_14",
    "atr_14",
    "adx_14",
    "ema_stack_bull",
    "ema_stack_bear",
    "bb_z",
    "bb_width",
    "sess_london",
    "sess_ny",
    "sess_overlap",
    "sess_asian",
]


# =========================================================================
#                               BRAIN
# =========================================================================
@dataclass
class BrainState:
    model: Optional[object] = None
    rule_wr_buy: float = 0.5
    rule_wr_sell: float = 0.5
    last_signal: Dict = field(default_factory=dict)
    last_write_ts: float = 0.0
    wins: int = 0
    losses: int = 0
    # 2026-04-22: per-symbol last veto reason for /why command and tick_all
    # debugging. Populated by tick_once() whenever a profit_gate vetoes.
    last_veto_per_symbol: Dict[str, str] = field(default_factory=dict)


class TrendMasterBrain:
    """
    Reads MT5 bars → builds features → ML/rule inference → writes signal file.
    """

    def __init__(self, state_dir: Optional[Path] = None):
        self.state = BrainState()
        self.state_dir = state_dir or _ROOT / "ai_trading_agents"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.state_dir / "trend_master_model.lgb"
        self._load_model()

        # Durable state across restarts — recent results, cooldown, etc.
        # Loaded once at construction; mutated in tick_once; persisted at
        # most every PERSIST_EVERY_N ticks (or on shutdown via run_forever).
        self.store = StateStore()
        self.persistent: Dict = self.store.load()
        self._persist_counter = 0
        self._persist_every_n = int(CFG.get("persist_state_every_n_ticks", 10))

        # [audit-fix 2026-04-22] Reconcile durable /halt flag on startup.
        # The canonical key is `halted`; `trading_paused` is the legacy key
        # tick_once() reads. If either is True, the brain starts halted so
        # a /halt issued right before a crash/restart is still in effect.
        halted_persist = bool(self.persistent.get("halted"))
        paused_legacy = bool(self.persistent.get("trading_paused"))
        if halted_persist or paused_legacy:
            self.persistent["halted"] = True
            self.persistent["trading_paused"] = True
            try:
                self.store.save(self.persistent)
            except Exception:
                pass
            logger.warning(
                "Brain booted in HALTED state (persistent flag was set). "
                "Send /resume on Telegram to re-enable new entries."
            )

        # Trade outcome poller — closes the loop between EA fills and the
        # brain's `loss_streak_cooldown` gate by appending each closed
        # broker deal to `state["recent_results"]`. Throttled internally
        # (default 30s) so calling it every tick is cheap. See
        # `trade_tracker.py` docstring for the full rationale.
        self.tracker = TradeTracker(
            lookback_days=int(CFG.get("trade_tracker_lookback_days", 1)),
            poll_interval_s=float(CFG.get("trade_tracker_poll_s", 30.0)),
        )

        # [R11 2026-04-23] Smart re-entry tracker — mints a 0.7x-size permit
        # after a full-1R stop so high-edge setups aren't abandoned for the
        # whole cooldown window. Opt-in via settings.REENTRY.enabled.
        _reentry_cfg = getattr(settings, "REENTRY", {}) or {}
        self._reentry: Optional[ReentryTracker] = (
            ReentryTracker(dict(_reentry_cfg)) if _reentry_cfg.get("enabled") else None
        )

    # ─── MODEL ──────────────────────────────────────────────────────────
    def _load_model(self) -> None:
        if not _HAS_LGB:
            logger.warning(
                "LightGBM not installed — falling back to rule-based inference. Install with: pip install lightgbm"
            )
            return
        if self.model_path.exists():
            try:
                self.state.model = lgb.Booster(model_file=str(self.model_path))
                logger.info("Loaded LGBM model: %s", self.model_path)
                # Feature-alignment audit (added 2026-04-24). The 2026-04-24
                # retrain produced a model whose confidence stuck at
                # 0.344 +/- 0.005 across 18 diverse markets — classic
                # feature-order mismatch fingerprint. Log the model's
                # trained feature order vs the brain's FEATURE_COLS so
                # any future drift is visible in the log.
                try:
                    from ai_trading_agents.ml_align import trained_feature_names

                    model_feats = trained_feature_names(self.state.model)
                except Exception:
                    model_feats = []
                if model_feats:
                    order_match = model_feats == list(FEATURE_COLS)
                    logger.info(
                        "ML feature audit: order_match=%s  model_count=%d  brain_count=%d",
                        order_match,
                        len(model_feats),
                        len(FEATURE_COLS),
                    )
                    if not order_match:
                        missing = [c for c in model_feats if c not in FEATURE_COLS]
                        extra = [c for c in FEATURE_COLS if c not in model_feats]
                        logger.warning(
                            "ML feature alignment MISMATCH — inference will reindex to model order at runtime. "
                            "model[:5]=%s brain[:5]=%s missing_in_brain=%s extra_in_brain=%s",
                            model_feats[:5],
                            list(FEATURE_COLS)[:5],
                            missing[:5],
                            extra[:5],
                        )
            except Exception as e:
                logger.warning("Failed to load model (%s), will use rules.", e)

    # ─── DATA PULL ──────────────────────────────────────────────────────
    def pull_bars(self, tf: str, n: int = 500, symbol: Optional[str] = None) -> Optional[pd.DataFrame]:
        if not _HAS_MT5:
            return None
        sym = symbol or SYMBOL
        rates = _mt5_copy_rates_safe(sym, _tf_to_mt5(tf), n)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time")
        df = df.rename(columns={"tick_volume": "volume"})
        return df[["open", "high", "low", "close", "volume"]]

    # ─── INFERENCE ──────────────────────────────────────────────────────
    def infer_ml(self, x: pd.DataFrame) -> Tuple[str, float]:
        """Returns (direction, confidence). direction is 'BUY' / 'SELL' / 'NONE'."""
        if self.state.model is None:
            return self.infer_rule(x)
        try:
            # Align to model's training-time feature order (via feature_name()
            # if exposed) rather than the module-level FEATURE_COLS, so a
            # post-retrain drift between the two cannot silently feed the
            # booster columns in the wrong order. See ai_trading_agents/ml_align.py.
            from ai_trading_agents.ml_align import align_feature_row

            feats, _used, _missing = align_feature_row(x, self.state.model, FEATURE_COLS)
            if feats is None:
                logger.warning("ML inference: missing features %s — falling back to rules.", _missing[:5])
                return self.infer_rule(x)
            # LGBM multi-class: [P(SELL), P(NONE), P(BUY)]
            p = self.state.model.predict(feats)[0]
            p = np.asarray(p, dtype=float)
            if p.ndim == 0:
                # binary model: single probability = P(BUY)
                p_buy = float(p)
                _thr = _effective_min_conf()
                if p_buy >= _thr:
                    return "BUY", p_buy
                if p_buy <= 1.0 - _thr:
                    return "SELL", 1.0 - p_buy
                return "NONE", max(p_buy, 1.0 - p_buy)
            idx = int(np.argmax(p))
            conf = float(p[idx])
            cls = ["SELL", "NONE", "BUY"][idx] if len(p) == 3 else "NONE"
            return cls, conf
        except Exception as e:
            logger.warning("ML inference failed (%s) — rule fallback.", e)
            return self.infer_rule(x)

    def infer_rule(self, x: pd.DataFrame) -> Tuple[str, float]:
        """Rule-based fallback when no trained model is available."""
        last = x.iloc[-1]
        bull = bool(last.get("ema_stack_bull", 0))
        bear = bool(last.get("ema_stack_bear", 0))
        adx = float(last.get("adx_14", 0) or 0)
        rsi = float(last.get("rsi_14", 50))
        bbz = float(last.get("bb_z", 0) or 0)

        # weighted rule: trend + momentum + volatility context
        score = 0.0
        if bull and adx > 22:
            score += 0.35
        if bull and bbz > 0:
            score += 0.15
        if bull and rsi > 50 and rsi < 75:
            score += 0.10
        if bear and adx > 22:
            score -= 0.35
        if bear and bbz < 0:
            score -= 0.15
        if bear and rsi < 50 and rsi > 25:
            score -= 0.10

        if score >= 0.35:
            return "BUY", 0.55 + min(0.4, score - 0.35)
        if score <= -0.35:
            return "SELL", 0.55 + min(0.4, -(score + 0.35))
        return "NONE", 0.5

    # ─── MTF ALIGNMENT ──────────────────────────────────────────────────
    def mtf_agree(self, direction: str, symbol: Optional[str] = None) -> bool:
        if direction not in ("BUY", "SELL"):
            return False
        for tf, required in MTF.items():
            if not required:
                continue
            df = self.pull_bars(tf, 200, symbol=symbol)
            if df is None or len(df) < 50:
                # no data for this TF — fail-open (don't block)
                continue
            x = build_features(df).dropna()
            if x.empty:
                continue
            last = x.iloc[-1]
            bull = bool(last.get("ema_stack_bull", 0))
            bear = bool(last.get("ema_stack_bear", 0))
            if direction == "BUY" and not bull:
                return False
            if direction == "SELL" and not bear:
                return False
        return True

    # ─── MULTI-AGENT VOTE (per-symbol timeframes) ──────────────────────
    def agent_vote(self, symbol: Optional[str] = None) -> Tuple[int, List[AgentVote]]:
        """
        Pulls the symbol's configured fast/mid/slow bars, runs the three
        specialist agents, returns (direction, votes).

        direction: +1 BUY / -1 SELL / 0 NONE
        """
        sym = symbol or SYMBOL
        tfs = _tf_for(sym)
        frames: Dict[str, pd.DataFrame] = {}
        for tf in tfs:
            df = self.pull_bars(tf, 250, symbol=sym)
            if df is not None and len(df) > 0:
                # Re-key into the canonical M30/H1/H4 slots the agent bus
                # expects, in fast→mid→slow order. This keeps multi_agent.py
                # symbol-agnostic.
                slot = {0: "M30", 1: "H1", 2: "H4"}[tfs.index(tf)]
                frames[slot] = df
        if not frames:
            return 0, []
        return vote_all(frames, min_votes=AGENT_MIN_VOTES)

    # ─── SIGNAL FILE WRITER ─────────────────────────────────────────────
    def _resolve_signal_path(self, file_name: Optional[str] = None) -> Path:
        name = file_name or SIG_FILE
        if _HAS_MT5:
            info = mt5.terminal_info()
            if info is not None:
                if USE_COMMON:
                    base = Path(info.commondata_path) / "Files"
                else:
                    base = Path(info.data_path) / "MQL5" / "Files"
                base.mkdir(parents=True, exist_ok=True)
                return base / name
        # fallback: project root
        return _ROOT / name

    def _signal_filename_for(self, symbol: str) -> str:
        """Per-symbol signal filename. Primary symbol keeps the legacy name
        so existing EA installs that hardcode `trendmaster_signals.json`
        keep working without recompile.
        """
        if symbol == SYMBOL:
            return SIG_FILE
        # `trendmaster_signals.json` → `trendmaster_signals_GBPJPY.json`
        stem = Path(SIG_FILE).stem
        suffix = Path(SIG_FILE).suffix or ".json"
        return f"{stem}_{symbol}{suffix}"

    def write_signal(
        self,
        direction: str,
        confidence: float,
        agent_dir: int = 0,
        agent_votes: Optional[List[AgentVote]] = None,
        symbol: Optional[str] = None,
    ) -> None:
        sym = symbol or SYMBOL
        path = self._resolve_signal_path(self._signal_filename_for(sym))
        # [R8 2026-04-23] Include per-symbol SL/TP/ADX so EA can use
        # symbol-specific params instead of flat InpSL/InpTP defaults.
        sl_m, tp_m, adx_min = _pair_sl_tp(sym)
        payload = {
            "direction": direction,
            "confidence": round(float(confidence), 4),
            "ts": int(time.time()),
            "symbol": sym,
            "brain": "TrendMaster_v14",
            "model": "lgbm" if self.state.model is not None else "rule",
            "agents": {
                "dir": {+1: "BUY", -1: "SELL", 0: "NONE"}.get(int(agent_dir), "NONE"),
                "votes": [v.as_dict() for v in (agent_votes or [])],
            },
            # Per-symbol SL/TP/ADX guidance (EA picks these up if it
            # supports per-signal overrides; ignored otherwise).
            "sl_atr_mult": round(sl_m, 3),
            "tp_atr_mult": round(tp_m, 3),
            "adx_min": round(adx_min, 1),
        }
        # [R11 2026-04-23] EA runtime-override block — when enabled, EA
        # reads require_all_3 + max_spread_atr_pct from here instead of
        # using its stored Inp values. Lets us tune strictness without
        # detaching the EA on every chart.
        _ea_over = getattr(settings, "EA_OVERRIDES", {}) or {}
        if _ea_over.get("enabled", False):
            payload["require_all_3"] = bool(_ea_over.get("require_all_3", True))
            payload["max_spread_atr_pct"] = float(_ea_over.get("max_spread_atr_pct", 0.20))
        tmp = path.with_suffix(path.suffix + ".tmp")
        # Atomic write with retry. WinError 5 (Access denied) on os.replace
        # happens when EA or dashboard has the .json open for read at the
        # exact moment we try to swap. The window is microseconds, so a
        # short backoff almost always wins on the next try. We keep the
        # error-log path for the truly unrecoverable case so we don't drop
        # signals silently. Added 2026-04-22 after observing intermittent
        # WinError 5 on EURGBP / multi-symbol writes.
        try:
            with open(tmp, "w", encoding="ascii") as f:
                json.dump(payload, f, separators=(",", ":"))
                f.flush()
                os.fsync(f.fileno())
            last_err: Optional[Exception] = None
            for attempt in range(4):  # 4 tries: 0, 50ms, 100ms, 200ms backoff
                try:
                    os.replace(tmp, path)
                    last_err = None
                    break
                except PermissionError as pe:  # WinError 5
                    last_err = pe
                    time.sleep(0.05 * (2**attempt))
            if last_err is not None:
                # All retries exhausted — log once with the final error.
                logger.error("Signal write failed after retries (%s): %s", sym, last_err)
                try:
                    if tmp.exists():
                        tmp.unlink()
                except Exception:
                    pass
            else:
                self.state.last_signal = payload
                self.state.last_write_ts = time.time()
        except Exception as e:
            logger.error("Signal write failed (%s): %s", sym, e)
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass

        # ── Telegram push (throttled inside notifier) ────────────────────
        # Only fires on direction *change* per symbol — but across 19 symbols
        # even that is noisy when the project runs live 24/7. Gated on
        # settings.TELEGRAM.notify_on_signal (default False). Operator sees
        # only trade fills (see trade_tracker.poll()), never per-signal.
        _tg_cfg = getattr(settings, "TELEGRAM", {}) or {}
        if _get_tg is not None and _tg_cfg.get("notify_on_signal", False):
            try:
                _get_tg().notify_signal(
                    symbol=sym,
                    direction=direction,
                    confidence=float(confidence),
                    model=("lgbm" if self.state.model is not None else "rule"),
                    agent_dir={+1: "BUY", -1: "SELL", 0: "NONE"}.get(int(agent_dir), "NONE"),
                )
            except Exception as e:
                logger.debug("telegram notify skipped: %s", e)

    # ─── MAIN LOOP ──────────────────────────────────────────────────────
    def tick_once(self, symbol: Optional[str] = None) -> Optional[Dict]:
        """Single inference cycle for one symbol — callable for tests and for the loop."""
        sym = symbol or SYMBOL
        # [enhancement 2026-04-23] Per-symbol latency histogram — gated
        # on METRICS.enabled so the prod default is zero overhead.
        _t0 = time.perf_counter()
        _metrics_enabled = _metrics is not None and getattr(settings, "METRICS", {}).get("enabled", False)
        df = self.pull_bars(TF, 500, symbol=sym)
        if df is None or len(df) < 120:
            return None
        x = build_features(df).dropna()
        if x.empty:
            return None

        direction, conf = self.infer_ml(x)

        # [enhancement 2026-04-23 R4] Market-calendar gate — weekends +
        # holidays. Gated on settings.MARKET_CALENDAR.enabled (default ON
        # because it's pure safety). Crypto symbols are exempt.
        if _is_market_open is not None:
            _mc_cfg = getattr(settings, "MARKET_CALENDAR", {}) or {}
            if _mc_cfg.get("enabled", True):
                try:
                    ok, mc_reason = _is_market_open(sym)
                    if not ok:
                        if _log_dedup((sym, f"mc:{mc_reason}"), interval_s=600.0):
                            logger.info("[%s] market_calendar: %s", sym, mc_reason)
                        self.state.last_veto_per_symbol[sym] = f"market_calendar: {mc_reason}"
                        return None
                except Exception as _mce:
                    logger.debug("market_calendar check skipped: %s", _mce)

        # ── KILL-SWITCH (set by /halt via Telegram) ────────────────────
        # When Sumit types /halt, the brain still ticks — still pulls bars,
        # still runs features — but EVERY signal is forced to NONE so the
        # EA won't open new positions. /resume flips it back. We don't
        # touch existing open trades; those remain under the EA's own
        # TP/SL/BE management.
        # [audit-fix 2026-04-22] read both `trading_paused` (legacy) and
        # `halted` (canonical) so durable halts survive schema migrations.
        if self.persistent.get("trading_paused") or self.persistent.get("halted"):
            direction = "NONE"

        # MTF (feature-based) check
        if direction != "NONE" and not self.mtf_agree(direction, symbol=sym):
            direction = "NONE"

        # confidence gate — session-aware (see _effective_min_conf).
        if direction != "NONE" and conf < _effective_min_conf():
            direction = "NONE"

        # ── PROFIT-OPTIMIZER GATES (2026-04-22) ────────────────────────
        # Layered after the MTF + confidence checks. Same gates the
        # dispatcher applies, so the brain and dispatcher can't disagree
        # about whether a trade should fire. Anything that fails here
        # downgrades direction to NONE.
        if direction != "NONE" and USE_PROFIT_FILTERS:
            try:
                atr_last = float(x["atr_14"].iloc[-1]) if "atr_14" in x else 0.0
                atr_series = x["atr_14"].dropna() if "atr_14" in x else pd.Series(dtype=float)
                spread_price = 0.0
                if _HAS_MT5:
                    info = mt5.symbol_info(sym)
                    if info is not None and getattr(info, "point", 0) > 0:
                        spread_price = float(info.spread) * float(info.point)
                eq_now = eq_start = 0.0
                if _HAS_MT5:
                    acct = mt5.account_info()
                    if acct is not None:
                        eq_now = float(acct.equity)
                # [audit-fix 2026-04-22] SoD equity source: prefer the
                # persisted snapshot (survives restart / flips back on
                # UTC midnight roll below). Only fall back to the live
                # acct.equity when no snapshot exists yet, and persist
                # that fallback immediately so the next tick is stable.
                # Previous code read acct.balance first, which drifted
                # against realized PnL and broke the daily-DD gate.
                eq_start = float(self.persistent.get("start_of_day_equity") or 0.0)
                if eq_start <= 0.0:
                    eq_start = eq_now
                    if eq_start > 0.0:
                        self.persistent["start_of_day_equity"] = eq_start
                        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        if not self.persistent.get("start_of_day_date"):
                            self.persistent["start_of_day_date"] = today_str
                        try:
                            self.store.save(self.persistent)
                        except Exception:
                            pass
                cooldown_until = float(self.persistent.get("cooldown_until_ts", 0) or 0)
                cooldown_active = time.time() < cooldown_until
                # Drawdown lockout (set by the new daily_loss_limit gate)
                # also acts as a "trading_paused" overlay — once tripped it
                # stays tripped until UTC day rolls over (handled below).
                dd_lock_until = float(self.persistent.get("drawdown_lockout_until", 0) or 0)
                if dd_lock_until > time.time():
                    cooldown_active = True
                # Roll daily peak forward — used by the intraday-trail leg
                # of daily_loss_limit. We don't reset on a new day here;
                # that happens in the SoD-roll block below.
                peak_today = float(self.persistent.get("daily_drawdown_peak_eq", 0.0) or 0.0)
                if eq_now > peak_today:
                    peak_today = eq_now
                    self.persistent["daily_drawdown_peak_eq"] = peak_today
                gate = evaluate_all(
                    spread_price=spread_price,
                    atr_price=atr_last,
                    atr_series=atr_series,
                    equity_now=eq_now,
                    equity_start_of_day=eq_start,
                    recent_results=list(self.persistent.get("recent_results", [])),
                    cooldown_active=cooldown_active,
                    equity_peak_today=peak_today,
                    cfg=dict(PF_CFG),
                )
                conf = max(0.0, min(1.0, conf + gate.score_adjust))
                if not gate.allow:
                    # Rate-limit identical veto-reasons per symbol so a long
                    # dead-market window doesn't generate hundreds of identical
                    # log lines (see _log_dedup). The first hit always logs.
                    veto_key = (sym, "; ".join(gate.reasons))
                    if _log_dedup(veto_key, interval_s=60.0):
                        logger.info("[%s] profit_gate veto: %s", sym, "; ".join(gate.reasons))
                    direction = "NONE"
                    # Stash for /why command + tick_all summary.
                    self.state.last_veto_per_symbol[sym] = "; ".join(gate.reasons)
                    # If the veto specifically came from the daily-DD gate,
                    # stamp a lockout so the rest of the UTC day is blocked
                    # even if equity briefly rebounds. Cleared on SoD roll.
                    dd_reason = next(
                        (r for r in gate.reasons if r.startswith("daily_dd:")),
                        None,
                    )
                    if dd_reason:
                        # Lock out for the remainder of the UTC day.
                        now_utc = datetime.now(timezone.utc)
                        end_of_day = int(
                            time.time()
                            + ((23 - now_utc.hour) * 3600 + (59 - now_utc.minute) * 60 + (60 - now_utc.second))
                        )
                        prev = float(self.persistent.get("drawdown_lockout_until", 0) or 0)
                        if end_of_day > prev:
                            self.persistent["drawdown_lockout_until"] = end_of_day
                            # Telegram alert — operator must know.
                            if _get_tg is not None:
                                try:
                                    _get_tg().notify_alert(
                                        "TrendMaster v14 DRAWDOWN LOCKOUT",
                                        f"<b>Trading halted for the rest of UTC day.</b>\n"
                                        f"Trigger: <code>{dd_reason}</code>\n"
                                        f"Equity now: <code>{eq_now:.2f}</code>\n"
                                        f"Day open:   <code>{eq_start:.2f}</code>\n"
                                        f"Peak today: <code>{peak_today:.2f}</code>\n"
                                        f"Auto-resume on next UTC midnight.",
                                        emoji="🛑",
                                    )
                                except Exception:
                                    pass
            except Exception as e:
                # Filters must never crash the brain; log and continue.
                logger.warning("[%s] profit_gate skipped (%s)", sym, e)

        # Multi-agent vote (per-symbol fast/mid/slow, unanimous required).
        # This is the new "advance agents" gate — simple rule-based,
        # transparent, and independent of the ML brain.
        agent_dir, agent_votes = (0, [])
        if USE_AGENTS:
            agent_dir, agent_votes = self.agent_vote(symbol=sym)

            # Final direction = intersection of ML brain and agent bus.
            ml_sign = {"BUY": +1, "SELL": -1, "NONE": 0}.get(direction, 0)
            if ml_sign == 0 or agent_dir == 0 or ml_sign != agent_dir:
                direction = "NONE"

        # [audit-fix 2026-04-22] Portfolio-level risk manager gate.
        # Runs AFTER profit_filters + MTF + agent intersection, BEFORE
        # we persist/emit the signal. On block, we override direction
        # to NONE and append the reason to the veto chain so /why sees
        # it alongside profit-gate reasons. Wrapped so a risk_manager
        # bug can never crash the brain.
        if direction in ("BUY", "SELL"):
            try:
                # Pull live equity + open positions from MT5.
                rm_equity = 0.0
                rm_positions: List[_RMPosition] = []
                if _HAS_MT5:
                    acct = mt5.account_info()
                    if acct is not None:
                        rm_equity = float(acct.equity)
                    try:
                        pos_rows = mt5.positions_get()
                    except Exception:
                        pos_rows = None
                    if pos_rows:
                        for p in pos_rows:
                            try:
                                # MT5 position.type: 0=BUY, 1=SELL
                                pdir = "BUY" if int(getattr(p, "type", 0)) == 0 else "SELL"
                                rm_positions.append(
                                    _RMPosition(
                                        symbol=str(getattr(p, "symbol", "")),
                                        direction=pdir,
                                        lots=float(getattr(p, "volume", 0.0)),
                                        entry_price=float(getattr(p, "price_open", 0.0)),
                                        sl_price=float(getattr(p, "sl", 0.0) or 0.0),
                                        tp_price=float(getattr(p, "tp", 0.0) or 0.0),
                                    )
                                )
                            except Exception:
                                continue
                # SL distance (price units) — derived from last ATR
                # the same way the EA / profit gates do, so sizing is
                # consistent across the stack.
                atr_px = float(x["atr_14"].iloc[-1]) if "atr_14" in x else 0.0
                sl_mult = float(RISK_CFG_RAW.get("default_sl_atr_multiple", 2.0))
                sl_distance = max(1e-9, atr_px * sl_mult)
                # Pip value per lot — best-effort via MT5 symbol_info.
                # Falls back to a conservative 10 USD/lot if unavailable.
                pip_value_per_lot = 10.0
                if _HAS_MT5:
                    try:
                        sinfo = mt5.symbol_info(sym)
                        if sinfo is not None:
                            tv = float(getattr(sinfo, "trade_tick_value", 0.0) or 0.0)
                            ts = float(getattr(sinfo, "trade_tick_size", 0.0) or 0.0)
                            if tv > 0 and ts > 0:
                                # $ per (1 price unit) per 1 lot.
                                pip_value_per_lot = tv / ts
                    except Exception:
                        pass
                rm_cfg = _build_risk_config()
                rm_risk_pct = float(RISK_CFG_RAW.get("risk_percent", rm_cfg.risk_per_trade_pct))
                # [enhancement 2026-04-23 R3] Meta-labeling gate (Lopez de
                # Prado). If a trained per-team model exists and
                # META_LABELER.enabled is True, its p_win decides (a)
                # whether to act and (b) a size scale multiplier applied
                # to rm_risk_pct. Fails-open when no model is present.
                _ml_cfg = getattr(settings, "META_LABELER", {}) or {}
                _meta_scale = 1.0
                if _MetaLabeler is not None and _ml_cfg.get("enabled"):
                    try:
                        team = _rm_team_of(sym)
                        ml_path = str(
                            _ml_cfg.get(
                                "model_path_template",
                                "ai_trading_agents/ml_models/meta_{team}.pkl",
                            )
                        ).format(team=team)
                        ml_path_abs = _ROOT / ml_path
                        lab = _MetaLabeler.load(str(ml_path_abs))
                        # Best-effort features: the ML brain's feature row.
                        feat_dict = {
                            c: float(x[c].iloc[-1]) if c in x.columns else 0.0
                            for c in ("ema_ratio", "rsi_14", "atr_14", "adx_14")
                            if True
                        }
                        pred = lab.predict(feat_dict, direction)
                        if not pred.act:
                            reason = f"meta_labeler: p_win={pred.p_win:.2f} below threshold"
                            prev_veto = self.state.last_veto_per_symbol.get(sym, "")
                            self.state.last_veto_per_symbol[sym] = f"{prev_veto} | {reason}" if prev_veto else reason
                            direction = "NONE"
                        elif _ml_cfg.get("apply_to_sizing"):
                            _meta_scale = float(pred.scale)
                    except Exception as _mle:
                        logger.debug("meta_labeler skipped: %s", _mle)

                # [enhancement 2026-04-23 R3] HMM regime gate — veto when
                # market is in a high-probability chop state.
                _hmm_cfg = getattr(settings, "REGIME_HMM", {}) or {}
                if direction in ("BUY", "SELL") and _RegimeHMM is not None and _hmm_cfg.get("enabled"):
                    try:
                        team = _rm_team_of(sym)
                        hmm_path = str(
                            _hmm_cfg.get(
                                "model_path_template",
                                "ai_trading_agents/ml_models/regime_{team}.pkl",
                            )
                        ).format(team=team)
                        hmm = _RegimeHMM.load(str(_ROOT / hmm_path))
                        if hmm.trained:
                            obs = hmm.classify(list(df["close"].tail(200)))
                            veto_thr = float(_hmm_cfg.get("chop_veto_prob", 0.70))
                            bonus_thr = float(_hmm_cfg.get("trend_bonus_prob", 0.70))
                            if obs.state == "chop" and obs.prob > veto_thr:
                                reason = f"regime_hmm: chop prob={obs.prob:.2f} > {veto_thr}"
                                prev_veto = self.state.last_veto_per_symbol.get(sym, "")
                                self.state.last_veto_per_symbol[sym] = (
                                    f"{prev_veto} | {reason}" if prev_veto else reason
                                )
                                direction = "NONE"
                            elif obs.state.startswith("trend") and obs.prob > bonus_thr:
                                conf = min(1.0, conf + float(_hmm_cfg.get("trend_bonus", 0.03)))
                    except Exception as _he:
                        logger.debug("regime_hmm skipped: %s", _he)

                # [enhancement 2026-04-23] Kelly-fraction sizing (shadow
                # or live, per settings). In shadow mode the helper only
                # logs what it WOULD do and returns the base unchanged.
                # Activation requires BOTH the settings flag and the
                # TRENDMASTER_V14.use_kelly_sizing toggle.
                _kelly_cfg_blk = getattr(settings, "KELLY_SIZING", {}) or {}
                if _kelly_apply is not None and _kelly_cfg_blk.get("enabled") and CFG.get("use_kelly_sizing", False):
                    try:
                        kcfg = _KellyConfig(
                            lookback_trades=int(_kelly_cfg_blk.get("lookback_trades", 40)),
                            min_samples=int(_kelly_cfg_blk.get("min_samples", 20)),
                            max_fraction=float(_kelly_cfg_blk.get("max_fraction", 2.0)),
                            floor_fraction=float(_kelly_cfg_blk.get("floor_fraction", 0.25)),
                            kelly_fraction=float(_kelly_cfg_blk.get("kelly_fraction", 0.5)),
                            shadow_mode=bool(_kelly_cfg_blk.get("shadow", True)),
                        )
                        rm_risk_pct = float(
                            _kelly_apply(
                                list(self.persistent.get("recent_results", [])),
                                rm_risk_pct,
                                kcfg,
                            )
                        )
                    except Exception as _ke:
                        logger.debug("kelly sizer skipped: %s", _ke)
                # Apply meta-labeler sizing scale last.
                if _meta_scale != 1.0:
                    rm_risk_pct = float(rm_risk_pct * _meta_scale)

                # [R11 2026-04-23] Smart re-entry sizing hook — if the re-entry
                # tracker has an available permit matching (symbol, direction),
                # reduce lots by permit.size_mult (e.g. 0.7 = 70 % of base) and
                # consume the permit. Event-logged for attribution.
                _reentry_permit = None
                if self._reentry is not None and direction in ("BUY", "SELL"):
                    try:
                        _reentry_permit = self._reentry.available_permit(
                            symbol=sym,
                            direction=direction,
                            now_ts=int(time.time()),
                            state=self.persistent,
                        )
                    except Exception as _re:
                        logger.debug("reentry lookup skipped: %s", _re)
                        _reentry_permit = None
                if _reentry_permit is not None:
                    rm_risk_pct = float(rm_risk_pct * float(_reentry_permit.size_mult))

                rm_lots = _rm_size_position(
                    equity=rm_equity,
                    risk_pct=rm_risk_pct,
                    sl_distance_price=sl_distance,
                    pip_value_per_lot=pip_value_per_lot,
                    cfg=rm_cfg,
                )
                rm_cooldown_until = float(self.persistent.get("cooldown_until_ts", 0) or 0)
                rm_state = _RMRiskState(
                    equity=rm_equity,
                    start_of_day=float(self.persistent.get("start_of_day_equity") or rm_equity),
                    open_positions=rm_positions,
                    recent_results=[pnl_of(r) for r in list(self.persistent.get("recent_results", []))[-20:]],
                    cooldown_active=(time.time() < rm_cooldown_until),
                )
                rm_decision = _rm_check_risk(sym, direction, rm_lots, rm_state, rm_cfg)
                if not rm_decision.allow:
                    reason = f"risk_manager: {rm_decision.reason}"
                    if _log_dedup((sym, reason), interval_s=60.0):
                        logger.info("[%s] %s", sym, reason)
                    # Append to veto chain so /why picks it up alongside
                    # any profit-gate reason.
                    prev_veto = self.state.last_veto_per_symbol.get(sym, "")
                    self.state.last_veto_per_symbol[sym] = f"{prev_veto} | {reason}" if prev_veto else reason
                    direction = "NONE"
            except Exception as e:
                logger.warning("[%s] risk_manager skipped (%s)", sym, e)

        # [R11 2026-04-23] If a re-entry permit was reserved for sizing AND
        # the trade actually survived all gates (direction still BUY/SELL),
        # consume the permit so it can't be re-used, and log the event.
        try:
            if (
                direction in ("BUY", "SELL")
                and self._reentry is not None
                and locals().get("_reentry_permit") is not None
            ):
                _rp = _reentry_permit  # type: ignore[name-defined]
                self._reentry.consume(_rp, state=self.persistent)
                logger.info(
                    "[%s] reentry permit CONSUMED (deal_id=%d size_mult=%.2f)",
                    sym,
                    _rp.deal_id,
                    float(_rp.size_mult),
                )
                # Event-log the re-entry for attribution.
                try:
                    _el_cfg_re = getattr(settings, "EVENT_LOG", {}) or {}
                    if _event_log is not None and _el_cfg_re.get("enabled"):
                        _event_log.get_log().append(
                            kind="reentry",
                            symbol=sym,
                            payload={
                                "direction": direction,
                                "size_mult": float(_rp.size_mult),
                                "deal_id": int(_rp.deal_id),
                                "original_sl_ts": int(_rp.original_sl_ts),
                            },
                        )
                except Exception:
                    pass
                # Best-effort Telegram alert (if enabled in config).
                try:
                    _re_cfg_blk = getattr(settings, "REENTRY", {}) or {}
                    if _re_cfg_blk.get("alert_telegram") and _get_tg is not None:
                        _get_tg().notify_alert(
                            "TrendMaster v14 RE-ENTRY",
                            f"<b>{sym} {direction}</b> re-entry at "
                            f"<code>{float(_rp.size_mult):.2f}x</code> size "
                            f"after SL (deal <code>{int(_rp.deal_id)}</code>).",
                            emoji="🔁",
                        )
                except Exception:
                    pass
        except Exception as _rce:
            logger.debug("reentry consume skipped: %s", _rce)

        # [R11 2026-04-23] Stamp last_signal_direction BEFORE the permit
        # scanner runs on the next tick, so when a fresh SL hits the permit
        # carries the original direction (needed for require_same_direction).
        if direction in ("BUY", "SELL"):
            self.persistent.setdefault("last_signal_direction", {})[sym] = direction

        self.write_signal(direction, conf, agent_dir, agent_votes, symbol=sym)

        # ── Persist last-signal + start-of-day equity snapshot ──────────
        # We only checkpoint to disk every N ticks so the brain doesn't
        # hammer the disk in the 250ms loop. Direction CHANGES are forced
        # to persist so a restart never re-fires the same direction twice.
        try:
            self.store.update_signal(self.persistent, sym, direction, conf)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if self.persistent.get("start_of_day_date") != today:
                # Roll the daily window — capture current equity as today's open.
                eq_open = 0.0
                if _HAS_MT5:
                    acct = mt5.account_info()
                    if acct is not None:
                        eq_open = float(acct.equity)
                self.persistent["start_of_day_date"] = today
                self.persistent["start_of_day_equity"] = eq_open
                self.persistent["daily_pnl_close"] = 0.0
                # Reset drawdown tracking for the fresh day.
                self.persistent["daily_drawdown_peak_eq"] = eq_open
                # Auto-release yesterday's drawdown lockout (midnight clear).
                prev_lockout = float(self.persistent.get("drawdown_lockout_until", 0) or 0)
                if prev_lockout > 0:
                    self.persistent["drawdown_lockout_until"] = 0
                    if _get_tg is not None:
                        try:
                            _get_tg().notify_alert(
                                "TrendMaster v14 drawdown lockout CLEARED",
                                f"New UTC day. Trading re-enabled for <code>{today}</code>.",
                                emoji="🟢",
                            )
                        except Exception:
                            pass
                self._persist_counter = self._persist_every_n  # force flush
            self._persist_counter += 1
            if self._persist_counter >= self._persist_every_n:
                self.store.save(self.persistent)
                self._persist_counter = 0
        except Exception as e:
            logger.debug("state persist skipped: %s", e)

        # [enhancement 2026-04-23 R3] Event-log append — one line per tick.
        # Opt-in via EVENT_LOG.enabled; cheap and high-value for replay.
        try:
            _el_cfg = getattr(settings, "EVENT_LOG", {}) or {}
            if _event_log is not None and _el_cfg.get("enabled"):
                log = _event_log.get_log()
                log.append(
                    kind="signal",
                    symbol=sym,
                    payload={
                        "direction": direction,
                        "confidence": round(float(conf), 4),
                        "agent_dir": agent_dir if isinstance(agent_dir, int) else 0,
                        "model": ("lgbm" if self.state.model is not None else "rule"),
                    },
                )
                # Also log the veto reason if direction was pulled to NONE.
                if direction == "NONE" and self.state.last_veto_per_symbol.get(sym):
                    log.append(
                        kind="veto",
                        symbol=sym,
                        payload={"reason": self.state.last_veto_per_symbol[sym]},
                    )
        except Exception as _ee:
            logger.debug("event_log append skipped: %s", _ee)

        # [enhancement 2026-04-23] Emit observability signals at end-of-tick.
        if _metrics_enabled:
            try:
                _metrics.tick_latency.labels(symbol=sym).observe(
                    time.perf_counter() - _t0,
                )
                if direction in ("BUY", "SELL"):
                    _metrics.signal_writes.labels(
                        symbol=sym,
                        direction=direction,
                    ).inc()
                elif self.state.last_veto_per_symbol.get(sym):
                    # First token of the veto chain is the category
                    # (e.g. "session", "risk_manager", "daily_dd") —
                    # cardinality-safe (< 20 distinct reasons).
                    cat = str(self.state.last_veto_per_symbol[sym]).split(":", 1)[0]
                    _metrics.veto_total.labels(symbol=sym, reason=cat).inc()
            except Exception as _me:
                logger.debug("metrics emit skipped: %s", _me)

        return self.state.last_signal

    # ─── TELEGRAM COMMAND HANDLERS / DAILY SUMMARY ──────────────────────
    def _build_status_message(self) -> str:
        """Snapshot for `/status` — what the brain is doing right now.
        Touches MT5 only with try/except so a broker hiccup never wedges
        the listener thread."""
        mode = f"MULTI ({len(ALL_SYMBOLS)} syms)" if MULTI_SYMBOL else f"SINGLE ({SYMBOL})"
        last = self.state.last_signal or {}
        last_dir = last.get("direction", "—")
        last_conf = last.get("confidence", 0.0)
        last_sym = last.get("symbol", SYMBOL)
        age_s = int(time.time() - (self.state.last_write_ts or time.time()))
        cooldown_until = float(self.persistent.get("cooldown_until_ts", 0) or 0)
        cooldown_left = max(0, int(cooldown_until - time.time()))
        # `recent_results` may be plain floats (legacy) or rich dicts
        # (current — see trade_tracker.py). pnl_of() hides the difference.
        recent = list(self.persistent.get("recent_results", []))[-10:]
        wins = sum(1 for r in recent if pnl_of(r) > 0)
        losses = sum(1 for r in recent if pnl_of(r) < 0)

        eq_now = bal = 0.0
        if _HAS_MT5:
            try:
                acct = mt5.account_info()
                if acct is not None:
                    eq_now = float(acct.equity)
                    bal = float(acct.balance)
            except Exception:
                pass

        # [audit-fix 2026-04-22] honor both legacy and canonical keys.
        paused = bool(self.persistent.get("trading_paused") or self.persistent.get("halted"))
        paused_line = "Trading: <b>🛑 HALTED</b> (use /resume)\n" if paused else "Trading: <b>🟢 LIVE</b>\n"

        return (
            f"<b>🧠 TrendMaster v14 status</b>\n"
            f"{paused_line}"
            f"Mode: <code>{mode}</code>\n"
            f"Last sig: <code>{last_sym} {last_dir} {last_conf * 100:.1f}%</code> "
            f"({age_s}s ago)\n"
            f"Equity: <code>{eq_now:.2f}</code>  |  Bal: <code>{bal:.2f}</code>\n"
            f"Cooldown: <code>{cooldown_left}s</code>\n"
            f"Recent W/L (last 10): <code>{wins}/{losses}</code>\n"
            f"Restarts: <code>{self.persistent.get('restart_count', 0)}</code>"
        )

    def _build_pnl_message(self) -> str:
        """Daily PnL snapshot used by `/pnl` and the auto daily summary."""
        eq_now = 0.0
        if _HAS_MT5:
            try:
                acct = mt5.account_info()
                if acct is not None:
                    eq_now = float(acct.equity)
            except Exception:
                pass
        eq_open = float(self.persistent.get("start_of_day_equity") or 0.0)
        day = self.persistent.get("start_of_day_date") or "—"
        pnl = eq_now - eq_open if eq_open else 0.0
        pct = (pnl / eq_open * 100.0) if eq_open else 0.0
        recent = list(self.persistent.get("recent_results", []))
        # Filter to today's UTC date. Dict entries carry a ts; legacy float
        # entries don't, so treat them as "today" to be conservative — they
        # only exist on freshly-upgraded installs.
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        def _is_today(r) -> bool:
            if not isinstance(r, dict):
                return True  # legacy float — count it
            try:
                ts = int(r.get("ts", 0) or 0)
            except (TypeError, ValueError):
                return True
            if ts <= 0:
                return True
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") == today

        todays = [r for r in recent if _is_today(r)]
        wins = sum(1 for r in todays if pnl_of(r) > 0)
        losses = sum(1 for r in todays if pnl_of(r) < 0)
        sign = "🟢" if pnl >= 0 else "🔴"
        return (
            f"<b>{sign} Daily PnL — {day}</b>\n"
            f"Equity open: <code>{eq_open:.2f}</code>\n"
            f"Equity now : <code>{eq_now:.2f}</code>\n"
            f"PnL: <b>{pnl:+.2f}</b> (<code>{pct:+.2f}%</code>)\n"
            f"Trades today: <code>{len(todays)}</code> "
            f"(W/L <code>{wins}/{losses}</code>)"
        )

    # ─── DRIFT (/drift) + PANIC (/halt close) HANDLERS ─────────────────
    def _handle_perf(self, args: str = "") -> str:
        """`/perf` — Sharpe / Sortino / MDD / win-rate over 7d / 30d / 90d."""
        if _perf is None:
            return "Performance module not importable."
        trades = list(self.persistent.get("recent_results", []))
        if not trades:
            return "No trades recorded yet."
        lines = ["<b>Performance</b>"]
        for w in ("7d", "30d", "90d"):
            days = int(w.rstrip("d"))
            m = _perf.compute(trades, window_days=days).as_dict()
            lines.append(
                f"<b>{w}</b> n=<code>{m['n_trades']}</code> "
                f"WR=<code>{m['win_rate'] * 100:.1f}%</code> "
                f"PnL=<code>{m['total_pnl']:+.2f}</code> "
                f"Sharpe=<code>{m['sharpe']:+.2f}</code> "
                f"Sortino=<code>{m['sortino']:+.2f}</code> "
                f"MDD=<code>{m['max_drawdown']:.2f}</code>"
            )
        # Top 3 / bottom 3 30-day.
        bysym = _perf.by_symbol(trades, window_days=30)
        if bysym:
            items = list(bysym.items())
            lines.append("")
            lines.append(
                "<b>Top 30d</b>: " + ", ".join(f"{s}=<code>{m['total_pnl']:+.2f}</code>" for s, m in items[:3])
            )
            lines.append(
                "<b>Worst 30d</b>: " + ", ".join(f"{s}=<code>{m['total_pnl']:+.2f}</code>" for s, m in items[-3:][::-1])
            )
        return "\n".join(lines)

    def _handle_digest(self, args: str = "") -> str:
        """`/digest` — generate + return today's daily digest (also writes file)."""
        if _digest is None:
            return "Daily-digest module not importable."
        try:
            d = _digest.generate_report(self.persistent, team_of_fn=_rm_team_of)
            _digest.write_daily(d, _ROOT / "reports")
        except Exception as e:
            return f"digest failed: <code>{e!r}</code>"
        return _digest.to_telegram(d)

    def _handle_gates(self, args: str = "") -> str:
        """`/gates` — gate-value attribution over the last 30 days."""
        if _gate_value is None:
            return "Gate-value module not importable."
        try:
            rep = _gate_value.analyze(window_days=30)
        except Exception as e:
            return f"gate analysis failed: <code>{e!r}</code>"
        if rep.total_vetoes == 0:
            return "No veto events logged yet (need EVENT_LOG.enabled=True)."
        lines = [
            f"<b>Gate value — 30d</b>",
            f"vetoes=<code>{rep.total_vetoes}</code> "
            f"saved=<code>${rep.total_saved:+.2f}</code> "
            f"cost=<code>${rep.total_cost:+.2f}</code>",
        ]
        for g in sorted(rep.by_gate.values(), key=lambda g: -g.net)[:8]:
            lines.append(f" • <code>{g.gate:15s}</code> n=<code>{g.vetoes:4d}</code> net=<code>${g.net:+6.2f}</code>")
        return "\n".join(lines)

    def _handle_var(self, args: str = "") -> str:
        """`/var` — portfolio VaR + CVaR snapshot via historical +
        parametric + Cornish-Fisher methods.
        """
        if _portfolio_risk is None:
            return "Portfolio-risk module not importable."
        cfg = getattr(settings, "PORTFOLIO_RISK", {}) or {}
        if not cfg.get("enabled"):
            return "Portfolio VaR/CVaR disabled (<code>PORTFOLIO_RISK.enabled=False</code>)."
        conf = float(cfg.get("confidence", 0.95))
        snap = _portfolio_risk.snapshot(
            list(self.persistent.get("recent_results", [])),
            confidence=conf,
        )
        lines = [f"<b>📉 Portfolio VaR ({int(conf * 100)}%)</b>"]
        for method_key, method_data in snap.items():
            lines.append(
                f"<b>{method_key}</b>: "
                f"VaR=<code>${method_data.get('var', 0):.2f}</code>  "
                f"CVaR=<code>${method_data.get('cvar', 0):.2f}</code>  "
                f"n=<code>{method_data.get('n_samples', 0)}</code>"
            )
            if method_data.get("reason"):
                lines.append(f"  <i>{method_data['reason']}</i>")
        return "\n".join(lines)

    def _handle_drift(self, args: str = "") -> str:
        """`/drift` — snapshot the ADWIN detector state. `/drift reset`
        clears the sliding window (keeps the drift-count history).
        """
        if _drift is None:
            return "Drift detector module not importable."
        cfg_blk = getattr(settings, "DRIFT", {}) or {}
        if not cfg_blk.get("enabled"):
            return (
                "Drift detection is disabled (<code>DRIFT.enabled=False</code>).\n"
                "Flip the flag in <code>config/settings.py</code> and restart."
            )
        arg = (args or "").strip().lower()
        det = _drift.get_detector("pnl")
        if arg == "reset":
            det.reset()
            return "🔄 drift window cleared (counters retained)."
        s = det.state
        return (
            f"<b>📊 Drift detector (PnL)</b>\n"
            f"Total obs:   <code>{s.total_observations}</code>\n"
            f"Window size: <code>{s.current_window_size}</code>\n"
            f"Mean:        <code>{s.mean:.4f}</code>\n"
            f"Variance:    <code>{s.variance:.4f}</code>\n"
            f"Drift count: <code>{s.drift_count}</code>\n"
            f"Warnings:    <code>{s.warning_count}</code>\n"
            f"Last drift:  <code>{s.last_drift_at}</code> obs ago\n"
            f"<i>Send</i> <code>/drift reset</code> <i>to clear window.</i>"
        )

    def _handle_halt(self, args: str = "") -> str:
        """`/halt` — block all new entries.
        `/halt close YES` — ALSO close every open position tagged by the
        EA magic number (two-step confirmation required).

        Back-compat: accepts zero args as before (legacy /halt behaviour).
        """
        parts = (args or "").strip().split()
        if parts and parts[0].lower() == "close":
            return self._handle_halt_close(parts[1:])
        return self._handle_halt_plain()

    def _handle_halt_close(self, extra: list) -> str:
        """Close-all flavour of /halt. Gated behind `PANIC.enabled` and
        requires `YES` as the next token to prevent accidental triggers."""
        panic_cfg = getattr(settings, "PANIC", {}) or {}
        if not panic_cfg.get("enabled"):
            return (
                "Panic-flatten is disabled (<code>PANIC.enabled=False</code>).\n"
                "Plain <code>/halt</code> still blocks new entries. "
                "Enable in <code>config/settings.py</code>, restart, and "
                "re-issue <code>/halt close YES</code>."
            )
        if not extra or (panic_cfg.get("require_yes", True) and extra[0].upper() != "YES"):
            return (
                "⚠️  <b>Confirmation required.</b>\n"
                "To flatten all open TrendMaster positions AND block new "
                "entries, type:\n<code>/halt close YES</code>\n\n"
                "Plain <code>/halt</code> (no <code>close</code>) only "
                "blocks new entries — existing positions keep running "
                "under EA management."
            )
        # Step 1 — set the halt flag (idempotent).
        halt_reply = self._handle_halt_plain()
        if _panic_flatten is None:
            return halt_reply + "\n\n<i>(panic module not importable — no positions were closed.)</i>"
        # Step 2 — run the flatten.
        try:
            res = _panic_flatten(
                comment="tm_halt_close",
                magic_filter=int(panic_cfg.get("magic_filter", 20260420)),
                dry_run=False,
                deviation=int(panic_cfg.get("deviation", 50)),
                max_retries=int(panic_cfg.get("max_retries", 5)),
                retry_backoff_s=float(panic_cfg.get("retry_backoff_s", 0.5)),
            )
            return halt_reply + "\n\n<b>Panic flatten</b>\n<pre>" + res.human + "</pre>"
        except Exception as e:
            logger.error("panic flatten failed: %s", e)
            return halt_reply + f"\n\n<b>⚠ panic flatten FAILED:</b> <code>{e}</code>"

    # ─── KILL-SWITCH HANDLERS (/halt /resume) ───────────────────────────
    def _handle_halt_plain(self) -> str:
        """`/halt` — flip the brain into 'no new trades' mode.

        We persist `trading_paused=True` so the state survives a restart;
        a Telegram halt sent right before the supervisor restarts the
        process should still be in effect after recovery (otherwise the
        kill switch is useless during the very window operators care
        about most). `tick_once` reads this flag every cycle and forces
        direction=NONE when it's True.
        """
        already = bool(self.persistent.get("trading_paused") or self.persistent.get("halted"))
        self.persistent["trading_paused"] = True
        # [audit-fix 2026-04-22] also write canonical `halted` key so the
        # durable flag is explicit in brain_state.json. tick_once still
        # reads `trading_paused`, so this is purely additive — idempotent
        # on re-halt and safe on restart (defaults to False if absent).
        self.persistent["halted"] = True
        self.persistent["trading_paused_at"] = int(time.time())
        try:
            self.store.save(self.persistent)
        except Exception as e:
            logger.debug("halt save skipped: %s", e)
        if already:
            return "🛑 trading already <b>HALTED</b> — every signal forced to NONE."
        # Push a separate alert so the user sees a red banner, not just a reply.
        if _get_tg is not None:
            try:
                _get_tg().notify_alert(
                    "TrendMaster v14 HALTED",
                    "All new entries blocked via <code>/halt</code>.\nSend <code>/resume</code> to re-enable.",
                    emoji="🛑",
                )
            except Exception:
                pass
        return (
            "🛑 <b>HALTED</b>. New entries blocked across all symbols.\n"
            "Existing trades remain under EA TP/SL management.\n"
            "Send <code>/resume</code> to re-enable."
        )

    def _handle_resume(self) -> str:
        """`/resume` — undo `/halt`. Idempotent."""
        was_paused = bool(self.persistent.get("trading_paused") or self.persistent.get("halted"))
        self.persistent["trading_paused"] = False
        # [audit-fix 2026-04-22] mirror canonical `halted` key.
        self.persistent["halted"] = False
        self.persistent["trading_resumed_at"] = int(time.time())
        try:
            self.store.save(self.persistent)
        except Exception as e:
            logger.debug("resume save skipped: %s", e)
        if not was_paused:
            return "🟢 trading was already active — nothing to resume."
        if _get_tg is not None:
            try:
                _get_tg().notify_alert(
                    "TrendMaster v14 RESUMED",
                    "Brain back to live signal generation.",
                    emoji="🟢",
                )
            except Exception:
                pass
        return "🟢 <b>RESUMED</b>. Brain is live again — new signals will fire on the next tick."

    def _handle_why(self, args: str = "") -> str:
        """`/why <SYMBOL>` — explain why a symbol is currently NONE.

        Reads the latest agent vote breakdown from the symbol's signal
        JSON and pairs it with the most recent profit-gate veto reason
        captured in `state.last_veto_per_symbol`. Lets the operator
        debug "why isn't EURUSD trading?" without grep-ing the log file.
        Added 2026-04-22.
        """
        sym = (args or "").strip().upper()
        if not sym:
            sample = ", ".join(ALL_SYMBOLS[:6])
            return (
                "Usage: <code>/why &lt;SYMBOL&gt;</code>\n"
                f"e.g. <code>/why XAUUSD</code>\n"
                f"Known symbols: <code>{sample}…</code>"
            )
        if sym not in ALL_SYMBOLS:
            return f"<code>{sym}</code> is not in TRADING_PAIRS.\nUse <code>/symbols</code> to list active pairs."

        # 1) Read the latest signal file for this symbol from disk.
        try:
            sig_path = self._resolve_signal_path(self._signal_filename_for(sym))
            payload = json.loads(sig_path.read_text(encoding="ascii"))
        except Exception as e:
            return (
                f"<b>{sym}</b>: signal file unreadable (<code>{e}</code>).\nBrain may not have ticked this symbol yet."
            )

        direction = payload.get("direction", "?")
        conf = float(payload.get("confidence", 0.0))
        ts = int(payload.get("ts", 0))
        age_s = int(time.time() - ts) if ts else -1
        agent_blob = payload.get("agents") or {}
        votes = agent_blob.get("votes") or []

        lines = [
            f"<b>/why {sym}</b>",
            f"direction: <code>{direction}</code>  conf: <code>{conf * 100:.0f}%</code>  age: <code>{age_s}s</code>",
        ]

        if votes:
            lines.append("<b>Agents</b>:")
            for v in votes:
                name = v.get("name", "?")
                vote = v.get("vote", 0)
                arrow = "↑BUY" if vote > 0 else ("↓SELL" if vote < 0 else "·NONE")
                reason = v.get("reason", "")
                lines.append(f" • <code>{name}</code> {arrow}  <i>{reason}</i>")
        else:
            lines.append("<i>(no agent votes recorded — agent bus may be disabled)</i>")

        # 2) Last profit-gate veto reason — populated by tick_once().
        veto = self.state.last_veto_per_symbol.get(sym)
        if veto:
            lines.append(f"<b>Last profit-gate veto</b>: <i>{veto}</i>")
        elif direction == "NONE":
            lines.append("<i>(no recent profit-gate veto — NONE is from agent disagreement)</i>")
        else:
            lines.append("<i>(profit gates passed — direction came from agents)</i>")

        return "\n".join(lines)

    def _build_symbols_message(self) -> str:
        rows = []
        for sym in ALL_SYMBOLS:
            ls = self.persistent.get("last_signal_per_symbol", {}).get(sym) or {}
            d = ls.get("direction", "—")
            c = ls.get("confidence", 0.0)
            try:
                c = float(c)
            except Exception:
                c = 0.0
            rows.append(f"• <code>{sym}</code> → <code>{d} {c * 100:.0f}%</code>")
        return ("<b>Active symbols</b>\n" if MULTI_SYMBOL else "<b>Active symbol</b>\n") + "\n".join(rows)

    def _maybe_send_daily_summary(self) -> None:
        """Once per UTC day, after `daily_summary_hour_utc` (default 22:00),
        push a one-shot Telegram summary. Idempotent — guarded by
        `daily_summary_sent_date` in persistent state so a restart in the
        same window doesn't double-send."""
        if _get_tg is None:
            return
        try:
            hour_target = int(CFG.get("daily_summary_hour_utc", 22))
            now = datetime.now(timezone.utc)
            today = now.strftime("%Y-%m-%d")
            already = self.persistent.get("daily_summary_sent_date")
            if already == today:
                return
            if now.hour < hour_target:
                return
            # Build & send.
            body = self._build_pnl_message()
            _get_tg().notify_alert("TrendMaster v14 daily summary", body, emoji="📊")
            self.persistent["daily_summary_sent_date"] = today
            self.store.save(self.persistent)
        except Exception as e:
            logger.debug("daily summary skipped: %s", e)

    # ─── MULTI-SYMBOL DRIVER ────────────────────────────────────────────
    def tick_all(self) -> Dict[str, Optional[Dict]]:
        """
        Run one inference cycle across every configured symbol in
        ALL_SYMBOLS. Each symbol gets its own per-symbol JSON written by
        write_signal() (the primary symbol keeps the legacy filename).

        Failures on any one symbol are isolated — a broker pulling data
        for GBPJPY shouldn't kill the EURUSD or XAUUSD signal that tick.
        Returns {symbol: signal_dict_or_None} for visibility/tests.

        Per-cycle summary (added 2026-04-22): once every 30s we emit ONE
        condensed log line covering all 19 symbols so you can see at a
        glance which are firing vs. flat-NONE. Was: log only contained
        EURGBP veto spam, no signal of life from the other 18 symbols.
        """
        out: Dict[str, Optional[Dict]] = {}
        for sym in ALL_SYMBOLS:
            try:
                out[sym] = self.tick_once(symbol=sym)
            except Exception as e:
                logger.warning("[%s] tick_all leg failed: %s", sym, e)
                out[sym] = None

        # [enhancement 2026-04-23] Drift detection — feed the latest
        # recent_results tail into ADWIN. One update per tick_all (not
        # per-symbol) so the stream is the PnL stream, not a mixed
        # per-symbol stream. Gated on settings.DRIFT.enabled.
        _drift_cfg = getattr(settings, "DRIFT", {}) or {}
        if _drift is not None and _drift_cfg.get("enabled"):
            try:
                _results_snap = list(self.persistent.get("recent_results", []))
                if _results_snap:
                    drifted, warned = _drift.feed_recent_results(_results_snap)
                    if drifted and _get_tg is not None and _drift_cfg.get("alert_telegram", True):
                        if _log_dedup(("__drift__", "alert"), interval_s=300.0):
                            det = _drift.get_detector("pnl")
                            try:
                                _get_tg().notify_alert(
                                    "TrendMaster v14 DRIFT",
                                    f"<b>ADWIN flagged a distribution shift.</b>\n"
                                    f"Window size: <code>{det.state.current_window_size}</code>\n"
                                    f"Total obs:   <code>{det.state.total_observations}</code>\n"
                                    f"Drift count: <code>{det.state.drift_count}</code>\n"
                                    f"Mean: <code>{det.state.mean:.4f}</code> "
                                    f"Var: <code>{det.state.variance:.4f}</code>\n"
                                    f"Consider: re-run CPCV trainer, revisit gate "
                                    f"thresholds. No auto-action taken.",
                                    emoji="⚠️",
                                )
                            except Exception:
                                pass
            except Exception as _de:
                logger.debug("drift feed skipped: %s", _de)

        # Per-cycle summary (rate-limited to once / 30 s).
        if _log_dedup(("__tick_all__", "summary"), interval_s=30.0):
            buckets: Dict[str, List[str]] = {"BUY": [], "SELL": [], "NONE": [], "ERR": []}
            for sym, sig in out.items():
                if sig is None:
                    buckets["ERR"].append(sym)
                    continue
                d = str(sig.get("direction", "NONE")).upper()
                buckets.setdefault(d, []).append(sym)
            line_parts = []
            for k in ("BUY", "SELL", "NONE", "ERR"):
                if buckets[k]:
                    line_parts.append(
                        f"{k}={len(buckets[k])}({','.join(buckets[k][:6])}{'…' if len(buckets[k]) > 6 else ''})"
                    )
            logger.info("tick_all summary: %s", " | ".join(line_parts) or "no symbols")
        return out

    def run_forever(self) -> None:
        if not _HAS_MT5:
            logger.error("MetaTrader5 package not available — cannot run brain. Install with: pip install MetaTrader5")
            return

        # Single-instance guard. Two brains writing the same JSON ⇒ EA
        # reads torn writes ⇒ duplicate orders. Refuse to start a second
        # one rather than crash later in confusing ways.
        with SingleInstanceLock("brain") as lock:
            if not lock.acquired:
                msg = f"Another brain is already running (PID={lock.holder_pid}). Refusing to start a second instance."
                logger.error(msg)
                if _get_tg is not None:
                    try:
                        _get_tg().notify_alert("TrendMaster v14 startup blocked", msg, emoji="🛑")
                    except Exception:
                        pass
                return

            # Reconnect-safe MT5 init. If even the retry-loop can't get a
            # connection, surface that on Telegram immediately — silent
            # death is the worst failure mode for an unattended bot.
            if not _mt5_initialize_with_retry(max_attempts=5):
                err = None
                try:
                    err = mt5.last_error()
                except Exception:
                    err = "unknown"
                logger.error("mt5.initialize() failed after retries: %s", err)
                if _get_tg is not None:
                    try:
                        _get_tg().notify_alert(
                            "TrendMaster v14 MT5 OFFLINE",
                            f"<b>Brain could not connect to MetaTrader 5</b> "
                            f"after 5 retries with exponential backoff.\n"
                            f"Last error: <code>{err}</code>\n"
                            f"Brain is exiting — supervisor will retry shortly. "
                            f"If this persists, check that MT5 terminal is "
                            f"open and logged in.",
                            emoji="🛑",
                        )
                    except Exception as e:
                        logger.debug("MT5-offline TG alert failed: %s", e)
                return

            # Bump restart counter so the dashboard / Telegram can show
            # how often we've come back from the dead.
            self.persistent["restart_count"] = int(self.persistent.get("restart_count", 0)) + 1
            self.persistent["last_started_at"] = int(time.time())
            self.store.save(self.persistent)

            mode_label = f"MULTI ({len(ALL_SYMBOLS)} syms)" if MULTI_SYMBOL else f"SINGLE ({SYMBOL})"
            logger.info(
                "TrendMaster brain online | mode=%s tf=%s interval=%dms model=%s restart#%d",
                mode_label,
                TF,
                INFER_MS,
                "lgbm" if self.state.model else "rule",
                self.persistent["restart_count"],
            )
            # Spin up the Telegram /command listener in a daemon thread.
            # If creds missing or `requests` isn't installed it silently
            # no-ops, so the brain runs identically with or without it.
            if _get_tg_cmds is not None:
                try:
                    listener = _get_tg_cmds()
                    listener.register_command("status", self._build_status_message)
                    listener.register_command("pnl", self._build_pnl_message)
                    listener.register_command("symbols", self._build_symbols_message)
                    listener.register_command("halt", self._handle_halt)
                    listener.register_command("resume", self._handle_resume)
                    listener.register_command("why", self._handle_why)
                    # [enhancement 2026-04-23] /drift snapshot command.
                    listener.register_command("drift", self._handle_drift)
                    # [enhancement 2026-04-23 R3] /var portfolio-risk snapshot.
                    listener.register_command("var", self._handle_var)
                    # [enhancement 2026-04-23 R4] operator-grade surface.
                    listener.register_command("perf", self._handle_perf)
                    listener.register_command("digest", self._handle_digest)
                    listener.register_command("gates", self._handle_gates)
                    listener.start()
                except Exception as e:
                    logger.debug("telegram command listener init skipped: %s", e)

            # Heartbeat ping so the user sees "I'm alive" on Telegram at boot.
            if _get_tg is not None:
                try:
                    sym_block = (
                        f"Symbols: <code>{', '.join(ALL_SYMBOLS)}</code>"
                        if MULTI_SYMBOL
                        else f"Symbol: <code>{SYMBOL}</code>"
                    )
                    _get_tg().notify_alert(
                        "TrendMaster v14 brain ONLINE",
                        f"{sym_block}\n"
                        f"Mode: <code>{mode_label}</code>\n"
                        f"TF: <code>{TF}</code>\n"
                        f"Model: <code>{'lgbm' if self.state.model else 'rule'}</code>\n"
                        f"Restart count: <code>{self.persistent['restart_count']}</code>",
                        emoji="🟢",
                    )
                except Exception as e:
                    logger.debug("telegram boot ping skipped: %s", e)
            try:
                while True:
                    t0 = time.time()
                    try:
                        if MULTI_SYMBOL:
                            sigs = self.tick_all()
                            logger.debug(
                                "tick_all wrote %d/%d signals",
                                sum(1 for v in sigs.values() if v),
                                len(ALL_SYMBOLS),
                            )
                        else:
                            sig = self.tick_once()
                            if sig:
                                logger.debug("sig=%s", sig)
                    except Exception as tick_e:  # never let a tick crash the loop
                        logger.warning("tick loop failed: %s", tick_e)
                    # Poll MT5 history for newly-closed deals and feed them
                    # into recent_results so the loss-streak cooldown can
                    # actually see real trade outcomes. Internally throttled
                    # so this is a no-op on most ticks; persists state when
                    # it does append anything.
                    try:
                        added = self.tracker.poll(self.persistent)
                        if added:
                            self.store.save(self.persistent)
                    except Exception as e:
                        logger.debug("trade_tracker tick skipped: %s", e)
                    # [R11 2026-04-23] After trade_tracker has appended any
                    # new closes to recent_results, let the re-entry tracker
                    # mint permits for fresh SL hits. Any newly-minted permit
                    # forces a state flush so a restart doesn't lose it.
                    try:
                        if self._reentry is not None:
                            minted = self._reentry.scan_for_sl_hits(self.persistent)
                            if minted:
                                self.store.save(self.persistent)
                    except Exception as e:
                        logger.debug("reentry_tracker scan skipped: %s", e)
                    # Daily summary check is cheap (date compare + dict get);
                    # safe to call every tick and idempotent per UTC day.
                    try:
                        self._maybe_send_daily_summary()
                    except Exception as e:
                        logger.debug("daily summary tick skipped: %s", e)
                    dt = (time.time() - t0) * 1000
                    sleep_s = max(0.0, (INFER_MS - dt) / 1000.0)
                    time.sleep(sleep_s)
            except KeyboardInterrupt:
                logger.info("Shutdown requested.")
            finally:
                # Final state flush — important so the next start doesn't
                # forget the cooldown / streak we just tracked.
                try:
                    self.store.save(self.persistent)
                except Exception:
                    pass
                try:
                    mt5.shutdown()
                except Exception:
                    pass


# =========================================================================
#                             TRAINER (offline)
# =========================================================================
def train_from_history(
    bars_csv: str, out_model: Optional[str] = None, horizon: int = 6, threshold_atr: float = 1.0
) -> None:
    """
    Train a LightGBM multi-class (SELL / NONE / BUY) classifier from a CSV
    of OHLCV. Label rule: look `horizon` bars ahead; if move > +threshold*ATR
    label BUY, if < -threshold*ATR label SELL, else NONE.

    Usage:
        python trend_master_brain.py train bars.csv
    """
    if not _HAS_LGB:
        print("LightGBM not installed. Run: pip install lightgbm")
        return

    df = pd.read_csv(bars_csv, parse_dates=True, index_col=0)
    df = df.rename(columns=str.lower)
    x = build_features(df).dropna().copy()

    atr = x["atr_14"]
    fwd = x["close"].shift(-horizon) - x["close"]
    lbl = np.where(fwd > threshold_atr * atr, 2, np.where(fwd < -threshold_atr * atr, 0, 1)).astype(int)
    x["label"] = lbl
    x = x.dropna().iloc[:-horizon]

    feats = x[FEATURE_COLS].values
    y = x["label"].values

    cut = int(len(x) * 0.8)
    d_tr = lgb.Dataset(feats[:cut], y[:cut])
    d_va = lgb.Dataset(feats[cut:], y[cut:], reference=d_tr)

    params = dict(
        objective="multiclass",
        num_class=3,
        metric="multi_logloss",
        learning_rate=0.05,
        num_leaves=31,
        min_data_in_leaf=50,
        feature_fraction=0.8,
        bagging_fraction=0.8,
        bagging_freq=5,
        verbosity=-1,
    )
    model = lgb.train(params, d_tr, num_boost_round=500, valid_sets=[d_va], callbacks=[lgb.early_stopping(30)])

    out = out_model or str(_HERE / "trend_master_model.lgb")
    model.save_model(out)
    print(f"Saved model -> {out}")


# =========================================================================
#                                 MAIN
# =========================================================================
def _setup_logging() -> None:
    """
    Wire up a rotating file handler + a console handler. Without rotation
    `logs/trend_master_brain.log` would grow without bound — at 24/7 it
    can pass 1 GB per quarter and hang anything tailing it.

    50 MB × 5 backups = 250 MB hard ceiling. Plenty for a week of debug
    history; older noise rolls off automatically.
    """
    from logging.handlers import RotatingFileHandler

    log_dir = _ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "trend_master_brain.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    # Replace any existing handlers so re-runs don't pile up.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.INFO)

    fh = RotatingFileHandler(log_path, maxBytes=50 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    root.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)
    root.addHandler(sh)


def main() -> None:
    _setup_logging()
    argv = sys.argv[1:]
    if len(argv) >= 2 and argv[0] == "train":
        train_from_history(argv[1], argv[2] if len(argv) >= 3 else None)
        return
    if argv and argv[0] == "once":
        brain = TrendMasterBrain()
        if not _HAS_MT5:
            print("MT5 not available — exiting.")
            return
        if not mt5.initialize():
            print("mt5.initialize() failed:", mt5.last_error())
            return
        try:
            sig = brain.tick_once()
            print(json.dumps(sig or {}, indent=2))
        finally:
            mt5.shutdown()
        return

    TrendMasterBrain().run_forever()


if __name__ == "__main__":
    main()
