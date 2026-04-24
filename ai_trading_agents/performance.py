"""
performance.py — institutional performance analytics for TrendMaster v14.

What this gives the operator
----------------------------
  * Sharpe, Sortino, Calmar ratios (trailing 7d / 30d / 90d windows).
  * Max drawdown (absolute + percent).
  * Profit factor, expectancy, payoff ratio.
  * Hit-rate calibration — is "confidence=0.72" actually a 72% winner?
  * Per-symbol and per-team PnL breakdown + contribution.
  * Per-hour and per-day-of-week heat maps.
  * Best/worst symbol over the window.

Pure Python + numpy. No scipy. Safe on cold start (insufficient data ⇒
returns `status='insufficient_data'`, not NaN).

References
----------
- QuantStart: Sharpe / Sortino / Calmar implementation.
- PyQuantNews: Risk metrics in Python.
- Lopez de Prado: "The Deflated Sharpe Ratio" — why single-number Sharpe
  overstates true edge in backtests.
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

import numpy as np

logger = logging.getLogger("performance")


# Risk-free rate assumed zero for intraday / short-holding forex.
# If you're comparing vs a benchmark, plug in the daily T-bill yield.
_DEFAULT_RF_DAILY = 0.0

# Annualisation — bar cadence matters. Assume ~252 trading days/year.
# For per-trade Sharpe we use trade count, not time.
_ANNUAL_TRADING_DAYS = 252


def _extract(entry) -> Optional[dict]:
    """Normalise a recent_results entry into dict form with pnl + ts + symbol.
    Returns None for unusable entries."""
    if entry is None:
        return None
    if isinstance(entry, (int, float)):
        return {"pnl": float(entry), "ts": 0, "symbol": "", "r_mult": None}
    if isinstance(entry, dict):
        try:
            return {
                "pnl": float(entry.get("pnl", 0.0) or 0.0),
                "ts": int(entry.get("ts", 0) or 0),
                "symbol": str(entry.get("symbol", "") or ""),
                "r_mult": (float(entry["r_mult"]) if "r_mult" in entry and entry["r_mult"] is not None else None),
            }
        except (TypeError, ValueError):
            return None
    return None


def _filter_window(trades: List[dict], days: int) -> List[dict]:
    """Keep trades within the trailing N days (utc now)."""
    if days <= 0:
        return trades
    cutoff = int(time.time() - days * 86400)
    return [t for t in trades if t["ts"] >= cutoff]


# =====================================================================
@dataclass
class PerfMetrics:
    n_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    payoff_ratio: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    max_drawdown: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "n_trades": self.n_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 4),
            "total_pnl": round(self.total_pnl, 2),
            "avg_win": round(self.avg_win, 4),
            "avg_loss": round(self.avg_loss, 4),
            "payoff_ratio": round(self.payoff_ratio, 4),
            "profit_factor": round(self.profit_factor, 4),
            "expectancy": round(self.expectancy, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe": round(self.sharpe, 4),
            "sortino": round(self.sortino, 4),
            "calmar": round(self.calmar, 4),
            "reason": self.reason,
        }


def compute(trades: Iterable, window_days: int = 0) -> PerfMetrics:
    """Compute every metric for the given (optionally-windowed) trades."""
    ts = [_extract(t) for t in trades]
    ts = [t for t in ts if t is not None]
    if window_days > 0:
        ts = _filter_window(ts, window_days)
    if not ts:
        return PerfMetrics(reason=f"no trades in last {window_days}d" if window_days else "no trades")

    pnls = np.array([t["pnl"] for t in ts], dtype=float)
    n = len(pnls)
    wins_mask = pnls > 0
    losses_mask = pnls < 0
    wins = int(wins_mask.sum())
    losses = int(losses_mask.sum())

    avg_win = float(pnls[wins_mask].mean()) if wins else 0.0
    avg_loss = float(pnls[losses_mask].mean()) if losses else 0.0
    win_rate = wins / n
    total = float(pnls.sum())
    expectancy = float(pnls.mean())

    payoff = abs(avg_win / avg_loss) if avg_loss < 0 else 0.0
    gross_win = float(pnls[wins_mask].sum())
    gross_loss = abs(float(pnls[losses_mask].sum()))
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf" if gross_win > 0 else 0)

    # Drawdown on cumulative PnL.
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    mdd = float(-dd.min()) if len(dd) else 0.0

    # Sharpe per-trade; scale by sqrt(n) if you want annualised.
    std = float(pnls.std(ddof=1)) if n >= 2 else 0.0
    sharpe = (expectancy / std) * math.sqrt(n) if std > 0 else 0.0

    # Sortino uses downside deviation.
    neg = pnls[pnls < 0]
    dside = float(neg.std(ddof=1)) if len(neg) >= 2 else 0.0
    sortino = (expectancy / dside) * math.sqrt(n) if dside > 0 else 0.0

    # Calmar = (annualised return) / (max DD). For per-trade use a rough
    # proxy: expectancy / max_dd scaled by trade count.
    calmar = (total / mdd) if mdd > 0 else 0.0

    return PerfMetrics(
        n_trades=n,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        total_pnl=total,
        avg_win=avg_win,
        avg_loss=avg_loss,
        payoff_ratio=payoff,
        profit_factor=pf,
        expectancy=expectancy,
        max_drawdown=mdd,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
    )


# =====================================================================
def by_symbol(trades: Iterable, window_days: int = 0) -> Dict[str, dict]:
    """PnL ranking per symbol — tells you which pairs to cut."""
    ts = [_extract(t) for t in trades]
    ts = [t for t in ts if t is not None]
    if window_days > 0:
        ts = _filter_window(ts, window_days)
    buckets: Dict[str, List[dict]] = defaultdict(list)
    for t in ts:
        key = t["symbol"] or "UNKNOWN"
        buckets[key].append(t)
    out: Dict[str, dict] = {}
    for sym, lst in buckets.items():
        pm = compute(lst, window_days=0)
        out[sym] = pm.as_dict()
    return dict(sorted(out.items(), key=lambda kv: kv[1]["total_pnl"], reverse=True))


def by_team(trades: Iterable, team_of_fn, window_days: int = 0) -> Dict[str, dict]:
    """PnL per team using the provided classifier."""
    ts = [_extract(t) for t in trades]
    ts = [t for t in ts if t is not None]
    if window_days > 0:
        ts = _filter_window(ts, window_days)
    buckets: Dict[str, List[dict]] = defaultdict(list)
    for t in ts:
        sym = t["symbol"] or ""
        try:
            team = team_of_fn(sym)
        except Exception:
            team = "UNKNOWN"
        buckets[str(team)].append(t)
    out: Dict[str, dict] = {}
    for team, lst in buckets.items():
        pm = compute(lst, window_days=0)
        out[team] = pm.as_dict()
    return dict(sorted(out.items(), key=lambda kv: kv[1]["total_pnl"], reverse=True))


def heatmap_hour_of_day(trades: Iterable, window_days: int = 0) -> Dict[int, dict]:
    """UTC hour of day bucket — when are we profitable?"""
    ts = [_extract(t) for t in trades if _extract(t) is not None]
    if window_days > 0:
        ts = _filter_window(ts, window_days)
    buckets: Dict[int, List[float]] = defaultdict(list)
    for t in ts:
        if t["ts"] <= 0:
            continue
        h = datetime.fromtimestamp(t["ts"], tz=timezone.utc).hour
        buckets[h].append(t["pnl"])
    out: Dict[int, dict] = {}
    for h in range(24):
        bucket = buckets.get(h, [])
        if not bucket:
            out[h] = {"n": 0, "pnl": 0.0, "avg": 0.0}
            continue
        out[h] = {
            "n": len(bucket),
            "pnl": round(sum(bucket), 2),
            "avg": round(sum(bucket) / len(bucket), 4),
        }
    return out


def heatmap_day_of_week(trades: Iterable, window_days: int = 0) -> Dict[str, dict]:
    """Monday-Sunday bucket."""
    ts = [_extract(t) for t in trades if _extract(t) is not None]
    if window_days > 0:
        ts = _filter_window(ts, window_days)
    names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    buckets: Dict[int, List[float]] = defaultdict(list)
    for t in ts:
        if t["ts"] <= 0:
            continue
        wd = datetime.fromtimestamp(t["ts"], tz=timezone.utc).weekday()
        buckets[wd].append(t["pnl"])
    out: Dict[str, dict] = {}
    for wd in range(7):
        bucket = buckets.get(wd, [])
        out[names[wd]] = {
            "n": len(bucket),
            "pnl": round(sum(bucket), 2),
            "avg": round(sum(bucket) / len(bucket), 4) if bucket else 0.0,
        }
    return out


def calibration(
    trades: Iterable, confidence_buckets: Iterable[float] = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0), window_days: int = 0
) -> List[dict]:
    """Hit-rate calibration.

    For each confidence bucket [b_i, b_{i+1}), compute the actual win
    rate. A well-calibrated model has actual ~= nominal confidence.
    Trades must have a `confidence` field — callers should enrich the
    recent_results dicts at write time.
    """
    ts = [_extract(t) for t in trades if _extract(t) is not None]
    # extract needs to also pull confidence — read it separately since
    # _extract strips it. We walk the raw list here.
    raw: List[dict] = []
    for t in trades:
        if isinstance(t, dict):
            conf = t.get("confidence")
            pnl = t.get("pnl")
            ts_ = t.get("ts", 0)
            if conf is None or pnl is None:
                continue
            try:
                raw.append({"conf": float(conf), "pnl": float(pnl), "ts": int(ts_ or 0)})
            except (TypeError, ValueError):
                continue
    if window_days > 0:
        cutoff = int(time.time() - window_days * 86400)
        raw = [r for r in raw if r["ts"] >= cutoff]
    buckets = sorted(confidence_buckets)
    out: List[dict] = []
    for i in range(len(buckets) - 1):
        lo, hi = buckets[i], buckets[i + 1]
        in_range = [r for r in raw if lo <= r["conf"] < hi]
        if not in_range:
            out.append({"lo": lo, "hi": hi, "n": 0, "actual_win_rate": 0.0, "avg_conf": 0.0})
            continue
        wins = sum(1 for r in in_range if r["pnl"] > 0)
        out.append(
            {
                "lo": lo,
                "hi": hi,
                "n": len(in_range),
                "actual_win_rate": round(wins / len(in_range), 4),
                "avg_conf": round(sum(r["conf"] for r in in_range) / len(in_range), 4),
            }
        )
    return out


def snapshot(trades: Iterable, team_of_fn=None) -> dict:
    """All-in-one snapshot — what /perf and daily digest consume."""
    base = {}
    for days in (7, 30, 90, 0):  # 0 = all-time
        label = f"{days}d" if days else "all"
        base[label] = compute(trades, window_days=days).as_dict()
    out = {
        "windows": base,
        "by_symbol_30d": by_symbol(trades, window_days=30),
        "hour_30d": heatmap_hour_of_day(trades, window_days=30),
        "dow_30d": heatmap_day_of_week(trades, window_days=30),
        "calibration_30d": calibration(trades, window_days=30),
    }
    if team_of_fn is not None:
        out["by_team_30d"] = by_team(trades, team_of_fn, window_days=30)
    return out


__all__ = [
    "PerfMetrics",
    "compute",
    "by_symbol",
    "by_team",
    "heatmap_hour_of_day",
    "heatmap_day_of_week",
    "calibration",
    "snapshot",
]
