"""
profit_filters.py — high-leverage P&L gates layered on top of the v14 brain.

Why this module exists
----------------------
The brain + EA already produce decent signals. The single biggest leak on a
small ($300) account is **trading conditions**, not signal direction:

  * Wide spreads silently eat 30-60 % of expected edge.
  * Dead / overheated volatility regimes kill RR consistency.
  * Trading after the daily target is hit gives back gains.
  * Trading after a loss streak compounds tilt and drawdown.

This module bundles four pure-Python, unit-testable gates that wrap the
existing dispatcher signal *before* it reaches the EA. Each gate returns a
small, structured decision the dashboard can render and the brain can log.

All gates are individually toggleable via config/settings.py
PROFIT_OPTIMIZER block — so a paranoid user can ship them off-by-default
and turn them on one by one after backtesting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dtime, timezone
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Decision record (mirrors RiskDecision so logs/dashboard stay uniform).
# ---------------------------------------------------------------------
@dataclass
class FilterDecision:
    allow: bool
    reason: str
    score_adjust: float = 0.0  # optional confidence nudge for the brain

    def as_dict(self) -> dict:
        return {
            "allow": self.allow,
            "reason": self.reason,
            "score_adjust": round(self.score_adjust, 3),
        }


# =====================================================================
# 1. SPREAD GUARD
# =====================================================================
def spread_guard(spread_price: float, atr_price: float, max_ratio: float = 0.25) -> FilterDecision:
    """
    Block trade if current spread > max_ratio * ATR.

    Why this matters
    ----------------
    On gold/crypto/oil, broker spread can routinely exceed 0.25 * ATR(14)
    during off-session minutes. Paying that on entry caps even a perfect
    signal's RR below the configured `min_rr_actual=1.5`.

    `spread_price` and `atr_price` must be in the same units (price points).
    """
    if atr_price <= 0:
        return FilterDecision(False, "atr is zero / undefined")
    ratio = float(spread_price) / float(atr_price)
    if ratio > max_ratio:
        return FilterDecision(
            False,
            f"spread/ATR={ratio:.2f} > cap {max_ratio:.2f}",
            score_adjust=-0.10,
        )
    # Tiny score boost when spread is *very* tight — a free quality signal.
    boost = 0.05 if ratio < (max_ratio * 0.5) else 0.0
    return FilterDecision(True, f"spread/ATR={ratio:.2f} ok", score_adjust=boost)


# =====================================================================
# 2. VOLATILITY REGIME FILTER
# =====================================================================
def volatility_regime(atr_series: pd.Series, min_pct: float = 0.20, max_pct: float = 0.95) -> FilterDecision:
    """
    Block trade when current ATR is in the bottom `min_pct` quantile
    (dead market — RR doesn't develop) OR above `max_pct` quantile
    (fat-tail spike — SL gets hit on noise).

    `atr_series` must be the most recent ATR(14) values (>= 100 bars
    recommended).
    """
    a = pd.Series(atr_series).dropna()
    if len(a) < 50:
        return FilterDecision(True, "regime n/a (insufficient ATR samples)")
    cur = float(a.iloc[-1])
    low_thr = float(a.quantile(min_pct))
    hi_thr = float(a.quantile(max_pct))
    if cur < low_thr:
        return FilterDecision(
            False, f"dead market: ATR {cur:.5f} < q{int(min_pct * 100)} {low_thr:.5f}", score_adjust=-0.05
        )
    if cur > hi_thr:
        return FilterDecision(
            False, f"spike regime: ATR {cur:.5f} > q{int(max_pct * 100)} {hi_thr:.5f}", score_adjust=-0.05
        )
    # Sweet spot bonus when ATR sits in the upper-middle band — clean trend conditions.
    mid_low = float(a.quantile(0.45))
    mid_high = float(a.quantile(0.85))
    boost = 0.05 if mid_low <= cur <= mid_high else 0.0
    return FilterDecision(True, f"regime ok: ATR {cur:.5f} in band", score_adjust=boost)


# =====================================================================
# 3. DAILY PROFIT LOCK (a.k.a. "stop trading after target")
# =====================================================================
def daily_profit_lock(equity_now: float, equity_start_of_day: float, target_pct: float = 2.0) -> FilterDecision:
    """
    Block any new trade when the account has hit `target_pct` for the day.

    Locking gains is the single most reliable equity-curve smoother for
    small accounts: most retail blowups happen *after* a green session
    when the trader keeps clicking. We just stop.
    """
    if equity_start_of_day <= 0:
        return FilterDecision(True, "start-of-day equity unknown")
    pnl_pct = (equity_now - equity_start_of_day) / equity_start_of_day * 100.0
    if pnl_pct >= target_pct:
        return FilterDecision(
            False,
            f"daily profit lock hit: +{pnl_pct:.2f}% ≥ target {target_pct:.2f}%",
        )
    return FilterDecision(True, f"day P&L +{pnl_pct:.2f}% < target {target_pct:.2f}%")


# =====================================================================
# 4. LOSS-STREAK COOLDOWN
# =====================================================================
def loss_streak_cooldown(
    recent_results: Iterable, max_consec_losses: int = 3, cooldown_active: bool = False
) -> FilterDecision:
    """
    Block trades for the rest of the cooldown window after N consecutive
    losing trades. `recent_results` is an iterable of trade results — each
    entry may be either a plain float P&L (legacy) OR a dict produced by
    `trade_tracker.TradeTracker` (newer). The `pnl_of()` helper hides the
    shape difference. `cooldown_active` lets the caller persist cooldown
    across calls (e.g. read from a file).
    """
    if cooldown_active:
        return FilterDecision(False, "cooldown active from prior loss streak")

    # Local import — avoids a circular import at module load time, since
    # trade_tracker may eventually import config-side helpers from here.
    try:
        from ai_trading_agents.trade_tracker import pnl_of as _pnl_of
    except Exception:
        # Fallback inline shim so this gate still functions if the tracker
        # module is somehow missing — keeps the brain bootable.
        def _pnl_of(entry):
            if entry is None:
                return 0.0
            if isinstance(entry, (int, float)):
                return float(entry)
            if isinstance(entry, dict):
                for k in ("pnl", "r_mult", "r"):
                    if k in entry and entry[k] is not None:
                        try:
                            return float(entry[k])
                        except (TypeError, ValueError):
                            pass
            return 0.0

    streak = 0
    for r in reversed(list(recent_results)):
        if r is None:
            continue
        p = _pnl_of(r)
        if p < 0:
            streak += 1
        elif p > 0:
            break
        # p == 0 (break-even / fee-only) — neither extends nor resets streak
    if streak >= max_consec_losses:
        return FilterDecision(
            False,
            f"loss streak {streak} ≥ cap {max_consec_losses}",
        )
    nudge = -0.05 if streak >= max(1, max_consec_losses - 1) else 0.0
    return FilterDecision(True, f"streak {streak} ok", score_adjust=nudge)


# =====================================================================
# 4b. DAILY-LOSS LIMIT (max-drawdown circuit breaker)
# =====================================================================
def daily_loss_limit(
    equity_now: float,
    equity_start_of_day: float,
    max_loss_pct: float = 3.0,
    intraday_dd_pct: Optional[float] = None,
    equity_peak_today: float = 0.0,
) -> FilterDecision:
    """
    Circuit breaker that blocks all new entries once the account hits an
    intraday drawdown threshold. Two thresholds, both optional:

      * `max_loss_pct`     — % loss vs. start-of-day equity (e.g. -3 %)
      * `intraday_dd_pct`  — % drop from intraday equity peak (e.g. -2 %)

    The 2nd one is the more aggressive, prop-firm-style trail — it locks
    when you give back gains, not just when you go red. We compute both
    and trip on whichever fires first.

    Why two thresholds?
    -------------------
    `max_loss_pct` alone is the classic "max daily loss" rule. But a
    common failure mode is: account goes +1.5 % in the morning, then
    bleeds back to -1 % by NY close. `max_loss_pct` only triggers at
    -3 %, but the equity curve already cratered ~2.5 % from peak. The
    intraday-peak trail catches that.

    Returns
    -------
    FilterDecision(allow=False, ...) once tripped — caller is expected to
    stamp `state["drawdown_lockout_until"]` so the cooldown survives a
    restart. (This function is pure — it doesn't touch state itself.)
    """
    if equity_start_of_day <= 0:
        return FilterDecision(True, "start-of-day equity unknown")

    # 1) Loss vs. SoD equity
    loss_pct = (equity_now - equity_start_of_day) / equity_start_of_day * 100.0
    if loss_pct <= -abs(max_loss_pct):
        return FilterDecision(
            False,
            f"daily loss limit hit: {loss_pct:.2f}% ≤ -{abs(max_loss_pct):.2f}%",
            score_adjust=-0.20,
        )

    # 2) Drop from intraday peak (only if a peak is provided)
    if intraday_dd_pct is not None and equity_peak_today > 0:
        dd_pct = (equity_now - equity_peak_today) / equity_peak_today * 100.0
        if dd_pct <= -abs(intraday_dd_pct):
            return FilterDecision(
                False,
                f"intraday drawdown {dd_pct:.2f}% from peak {equity_peak_today:.2f} ≤ -{abs(intraday_dd_pct):.2f}%",
                score_adjust=-0.15,
            )

    return FilterDecision(True, f"day P&L {loss_pct:+.2f}% within limits")


# =====================================================================
# 5. NEWS BLACKOUT WINDOW
# =====================================================================
# High-impact macro events (NFP, FOMC, CPI, ECB, BOE, GDP) blow out spreads
# 5–20× and whipsaw price across both stops on a single tick. The brain
# should NOT trade in the +/- N minute window around them.
#
# We don't ship a live calendar feed — keeping the brain dependency-free
# matters more than convenience. Instead we read a JSON file the user can
# refresh weekly: `config/news_calendar.json`. Format:
#
#   [
#     {"ts_utc": "2026-04-23T12:30:00Z", "event": "USD CPI",  "impact": "high"},
#     {"ts_utc": "2026-04-30T18:00:00Z", "event": "FOMC",     "impact": "high"},
#     ...
#   ]
#
# Anything not in the file is treated as "no news" (fail-open). A 24h
# missing-feed sniff is logged so an operator notices stale data.
import json as _json
from pathlib import Path as _Path

_NEWS_CACHE: dict = {"loaded_ts": 0.0, "events": []}
_NEWS_CACHE_TTL_S = 600.0  # re-read calendar at most every 10 min


def _load_news_calendar(path: Optional[_Path] = None) -> list:
    import time as _time

    now = _time.time()
    if (now - _NEWS_CACHE["loaded_ts"]) < _NEWS_CACHE_TTL_S and _NEWS_CACHE["events"]:
        return _NEWS_CACHE["events"]
    if path is None:
        # Junction-safe project root — see ai_trading_agents._paths and the
        # 2026-04-30 postmortem.
        from ai_trading_agents._paths import project_root

        path = project_root() / "config" / "news_calendar.json"
    events: list = []
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                raw = _json.load(f)
            if isinstance(raw, list):
                for ev in raw:
                    ts_str = (ev.get("ts_utc") or "").replace("Z", "+00:00")
                    try:
                        ev_ts = datetime.fromisoformat(ts_str)
                        if ev_ts.tzinfo is None:
                            ev_ts = ev_ts.replace(tzinfo=timezone.utc)
                        events.append(
                            {
                                "ts": ev_ts,
                                "event": ev.get("event", ""),
                                "impact": (ev.get("impact") or "").lower(),
                            }
                        )
                    except (ValueError, TypeError):
                        continue
    except (OSError, _json.JSONDecodeError):
        events = []
    _NEWS_CACHE["loaded_ts"] = now
    _NEWS_CACHE["events"] = events
    return events


def news_blackout(
    now_utc: Optional[datetime] = None,
    window_minutes: int = 30,
    impacts: Iterable[str] = ("high",),
    calendar_path: Optional[_Path] = None,
) -> FilterDecision:
    """
    Block trades inside ±`window_minutes` of any high-impact news event.
    Fails OPEN (allow=True) when the calendar file is missing — a paranoid
    operator can flip that to fail-closed by checking the reason string.
    """
    now = now_utc or datetime.now(timezone.utc)
    events = _load_news_calendar(calendar_path)
    if not events:
        return FilterDecision(True, "news calendar empty / not configured")
    impacts_l = {i.lower() for i in impacts}
    win_s = float(window_minutes) * 60.0
    for ev in events:
        if impacts_l and ev["impact"] not in impacts_l:
            continue
        delta = abs((ev["ts"] - now).total_seconds())
        if delta <= win_s:
            mins = int(delta // 60)
            return FilterDecision(
                False,
                f"news blackout: {ev['event']} ({ev['impact']}) in ±{window_minutes}m (now {mins}m away)",
                score_adjust=-0.10,
            )
    return FilterDecision(True, "no news event in blackout window")


# =====================================================================
# 6. SESSION TIME FILTER (cheap, high-payoff)
# =====================================================================
def session_window(now_utc: Optional[datetime] = None, best_hours: Iterable[int] = range(7, 21)) -> FilterDecision:
    """
    Block trades outside the configured London/NY hours. Asian-session
    chop hits backtests harder than people expect — easy filter to add.
    """
    now = now_utc or datetime.now(timezone.utc)
    h = now.hour
    best = list(best_hours)
    if h in best:
        peak = list(range(12, 16))  # London-NY overlap
        boost = 0.03 if h in peak else 0.0
        return FilterDecision(True, f"hour {h} UTC in best window", score_adjust=boost)
    return FilterDecision(False, f"hour {h} UTC outside best window {best[0]}-{best[-1]}")


# =====================================================================
# Compose all gates into one entry point — the dispatcher / brain calls this.
# =====================================================================
@dataclass
class CombinedDecision:
    allow: bool
    reasons: List[str]
    score_adjust: float
    detail: dict

    def as_dict(self) -> dict:
        return {
            "allow": self.allow,
            "reasons": self.reasons,
            "score_adjust": round(self.score_adjust, 3),
            "detail": self.detail,
        }


def evaluate_all(
    *,
    spread_price: float,
    atr_price: float,
    atr_series: pd.Series,
    equity_now: float,
    equity_start_of_day: float,
    recent_results: Iterable,
    cooldown_active: bool = False,
    equity_peak_today: float = 0.0,
    now_utc: Optional[datetime] = None,
    cfg: Optional[dict] = None,
) -> CombinedDecision:
    """
    Run every gate; the trade is allowed only if **all** gates that are
    enabled in `cfg` return allow=True.
    """
    cfg = cfg or {}
    gates: dict[str, FilterDecision] = {}

    if cfg.get("spread_guard", True):
        gates["spread"] = spread_guard(
            spread_price,
            atr_price,
            max_ratio=float(cfg.get("max_spread_atr_ratio", 0.25)),
        )
    if cfg.get("vol_regime", True):
        gates["regime"] = volatility_regime(
            atr_series,
            min_pct=float(cfg.get("vol_min_quantile", 0.20)),
            max_pct=float(cfg.get("vol_max_quantile", 0.95)),
        )
    if cfg.get("profit_lock", True):
        gates["profit_lock"] = daily_profit_lock(
            equity_now,
            equity_start_of_day,
            target_pct=float(cfg.get("daily_profit_target_pct", 2.0)),
        )
    if cfg.get("loss_cooldown", True):
        gates["loss_streak"] = loss_streak_cooldown(
            recent_results,
            max_consec_losses=int(cfg.get("max_consec_losses", 3)),
            cooldown_active=cooldown_active,
        )
    if cfg.get("daily_loss_limit", True):
        gates["daily_dd"] = daily_loss_limit(
            equity_now,
            equity_start_of_day,
            max_loss_pct=float(cfg.get("daily_max_loss_pct", 3.0)),
            intraday_dd_pct=cfg.get("intraday_dd_pct"),  # may be None
            equity_peak_today=float(equity_peak_today or 0.0),
        )
    if cfg.get("session_window", True):
        gates["session"] = session_window(
            now_utc=now_utc,
            best_hours=cfg.get("best_hours_utc", range(7, 21)),
        )
    if cfg.get("news_blackout", True):
        gates["news"] = news_blackout(
            now_utc=now_utc,
            window_minutes=int(cfg.get("news_window_minutes", 30)),
            impacts=cfg.get("news_impact_levels", ("high",)),
        )

    allow = all(g.allow for g in gates.values())
    reasons = [f"{name}: {g.reason}" for name, g in gates.items() if not g.allow]
    if not reasons:
        reasons = [f"{name}: ok" for name in gates]
    score_adjust = sum(g.score_adjust for g in gates.values())
    return CombinedDecision(
        allow=allow, reasons=reasons, score_adjust=score_adjust, detail={k: v.as_dict() for k, v in gates.items()}
    )


__all__ = [
    "FilterDecision",
    "CombinedDecision",
    "spread_guard",
    "volatility_regime",
    "daily_profit_lock",
    "loss_streak_cooldown",
    "daily_loss_limit",
    "session_window",
    "news_blackout",
    "evaluate_all",
]
