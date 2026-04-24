"""
risk_manager.py — portfolio-level risk controller for TrendMaster v14.

Responsibilities
----------------
1. Size positions off % account risk and the SL distance the EA supplies.
2. Enforce hard limits:
      - max concurrent open positions (global + per-team)
      - max daily loss (% of starting-day equity)
      - max correlated exposure (e.g. EURUSD + GBPUSD both long)
      - daily profit lock (stop trading after +N% intraday)
      - loss-streak cooldown (halt after N consecutive losses)
3. Produce a single allow / block decision with a human-readable reason.

Pure-Python; no MT5 import at module level so the module is unit-testable
without MetaTrader5 installed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, List, Optional


# --- Pair -> team mapping (must stay in sync with config/settings.py) ---
TEAM_METALS      = {"XAUUSD", "XAGUSD"}
TEAM_FOREX       = {"GBPJPY", "USDCAD", "USDCHF", "EURUSD", "GBPUSD",
                    "AUDUSD", "USDJPY", "NZDUSD", "EURJPY", "EURGBP",
                    "AUDJPY", "CADJPY"}
TEAM_CRYPTO      = {"BTCUSD", "ETHUSD"}
TEAM_COMMODITIES = {"XTIUSD", "XBRUSD", "XNGUSD"}  # 2026-04-22: broker names; CORN/WHEAT not offered by OctaFX-Demo


def team_of(symbol: str) -> str:
    if symbol in TEAM_METALS:       return "METALS"
    if symbol in TEAM_FOREX:        return "FOREX"
    if symbol in TEAM_CRYPTO:       return "CRYPTO"
    if symbol in TEAM_COMMODITIES:  return "COMMODITIES"
    return "OTHER"


# Correlation groups — pairs inside the same group cannot stack same-direction.
_CORR_GROUPS = [
    {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"},
    {"USDJPY", "USDCHF", "USDCAD"},
    {"EURJPY", "GBPJPY", "AUDJPY", "CADJPY"},
    {"XAUUSD", "XAGUSD"},
    {"XTIUSD", "XBRUSD"},
    {"BTCUSD", "ETHUSD"},
]


@dataclass
class Position:
    symbol: str
    direction: str
    lots: float
    entry_price: float
    sl_price: float
    tp_price: float


@dataclass
class RiskConfig:
    risk_per_trade_pct: float    = 1.0
    max_open_total:     int      = 6
    max_open_per_team:  int      = 3
    max_daily_loss_pct: float    = 5.0
    max_corr_same_dir:  int      = 2
    min_lot:            float    = 0.01
    lot_step:           float    = 0.01
    max_lot:            float    = 5.0
    daily_profit_target_pct: float = 2.0
    max_consec_losses:       int   = 3


@dataclass
class RiskDecision:
    allow: bool
    reason: str
    lots: float = 0.0

    def as_dict(self) -> dict:
        return {"allow": self.allow, "reason": self.reason, "lots": self.lots}


@dataclass
class RiskState:
    equity:        float
    start_of_day:  float
    open_positions:  List[Position] = field(default_factory=list)
    recent_results:  List[float]    = field(default_factory=list)
    cooldown_active: bool           = False


def size_position(equity: float,
                  risk_pct: float,
                  sl_distance_price: float,
                  pip_value_per_lot: float,
                  cfg: Optional[RiskConfig] = None) -> float:
    cfg = cfg or RiskConfig()
    if equity <= 0 or sl_distance_price <= 0 or pip_value_per_lot <= 0:
        return 0.0
    risk_amt = equity * (risk_pct / 100.0)
    raw_lots = risk_amt / (sl_distance_price * pip_value_per_lot)
    stepped = math.floor(raw_lots / cfg.lot_step) * cfg.lot_step
    return max(cfg.min_lot, min(cfg.max_lot, round(stepped, 2)))


def _corr_conflict(symbol: str, direction: str,
                   positions: Iterable[Position],
                   max_same_dir: int) -> Optional[str]:
    for group in _CORR_GROUPS:
        if symbol not in group:
            continue
        same_dir = [p for p in positions
                    if p.symbol in group and p.direction == direction]
        if len(same_dir) >= max_same_dir:
            return (f"correlation cap: {len(same_dir)} {direction} in "
                    f"group {sorted(group)}")
    return None


def _loss_streak(results: Iterable[float]) -> int:
    streak = 0
    for r in reversed(list(results)):
        if r is None:
            continue
        if r < 0:
            streak += 1
        else:
            break
    return streak


def check_risk(symbol: str,
               direction: str,
               lots: float,
               state: RiskState,
               cfg: Optional[RiskConfig] = None) -> RiskDecision:
    cfg = cfg or RiskConfig()

    if state.start_of_day > 0:
        dd_pct = (state.start_of_day - state.equity) / state.start_of_day * 100.0
        if dd_pct >= cfg.max_daily_loss_pct:
            return RiskDecision(
                False,
                f"daily loss stop: {dd_pct:.2f}% >= {cfg.max_daily_loss_pct:.2f}%")

        gain_pct = (state.equity - state.start_of_day) / state.start_of_day * 100.0
        if gain_pct >= cfg.daily_profit_target_pct:
            return RiskDecision(
                False,
                f"daily profit lock: +{gain_pct:.2f}% >= "
                f"target {cfg.daily_profit_target_pct:.2f}%")

    if state.cooldown_active:
        return RiskDecision(False, "cooldown active from prior loss streak")

    streak = _loss_streak(state.recent_results)
    if streak >= cfg.max_consec_losses:
        return RiskDecision(
            False, f"loss streak {streak} >= cap {cfg.max_consec_losses}")

    if len(state.open_positions) >= cfg.max_open_total:
        return RiskDecision(False,
                            f"max open total {cfg.max_open_total} reached")

    t = team_of(symbol)
    team_open = [p for p in state.open_positions if team_of(p.symbol) == t]
    if len(team_open) >= cfg.max_open_per_team:
        return RiskDecision(
            False,
            f"team {t} has {len(team_open)} open >= cap {cfg.max_open_per_team}")

    corr_reason = _corr_conflict(symbol, direction, state.open_positions,
                                 cfg.max_corr_same_dir)
    if corr_reason:
        return RiskDecision(False, corr_reason)

    if lots < cfg.min_lot:
        return RiskDecision(False, f"lots {lots:.4f} < min {cfg.min_lot}")
    lots = min(lots, cfg.max_lot)

    return RiskDecision(True, "ok", lots=lots)


__all__ = [
    "Position", "RiskConfig", "RiskState", "RiskDecision",
    "team_of", "size_position", "check_risk",
]
