"""
multi_market_dispatcher.py — iterate TRADING_PAIRS across 4 teams,
run the agent bus per symbol, apply the risk + profit gates, and
produce a per-symbol signal dict that the brain / CLI can write / print.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import settings  # noqa: E402
from ai_trading_agents.multi_agent import vote_all  # noqa: E402
from ai_trading_agents.risk_manager import (  # noqa: E402
    RiskConfig,
    RiskState,
    check_risk,
    team_of,
)
from ai_trading_agents.profit_filters import evaluate_all  # noqa: E402

logger = logging.getLogger("dispatcher")

try:
    import MetaTrader5 as mt5  # type: ignore

    _HAS_MT5 = True
except ImportError:
    _HAS_MT5 = False


_TF_MINUTES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}


def _csv_path(symbol: str) -> Path:
    return _ROOT / "data" / f"{symbol.lower()}_m5_history.csv"


def _resample_m5_to(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    minutes = _TF_MINUTES.get(tf, 5)
    rule = f"{minutes}min"
    return (
        df.resample(rule)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )


def load_frames(symbol: str, tfs: List[str] = ["M30", "H1", "H4"]) -> Dict[str, pd.DataFrame]:
    frames: Dict[str, pd.DataFrame] = {}
    if _HAS_MT5:
        for tf in tfs:
            mt5_tf = {"M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4}.get(tf)
            if mt5_tf is None:
                continue
            rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, 500)
            if rates is None or len(rates) == 0:
                continue
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df = df.set_index("time").rename(columns={"tick_volume": "volume"})
            frames[tf] = df[["open", "high", "low", "close", "volume"]]
        return frames

    csv = _csv_path(symbol)
    if not csv.exists():
        return {}
    df5 = pd.read_csv(csv)
    if "time" in df5.columns:
        df5["time"] = pd.to_datetime(df5["time"], utc=True)
        df5 = df5.set_index("time")
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df5.columns]
    if not cols:
        return {}
    df5 = df5[cols]
    for tf in tfs:
        frames[tf] = _resample_m5_to(df5, tf)
    return frames


def _profit_filter_cfg() -> dict:
    return dict(getattr(settings, "PROFIT_OPTIMIZER", {}) or {})


def _last_atr(df: pd.DataFrame, n: int = 14):
    if df is None or len(df) < n + 2:
        return 0.0, pd.Series(dtype=float)
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean().dropna()
    return float(atr.iloc[-1]) if len(atr) else 0.0, atr


def scan_once(
    symbols: Optional[List[str]] = None,
    min_votes: int = 3,
    risk_state: Optional[RiskState] = None,
    risk_cfg: Optional[RiskConfig] = None,
    spread_lookup: Optional[Dict[str, float]] = None,
    recent_results: Optional[List[float]] = None,
    cooldown_active: bool = False,
) -> Dict[str, dict]:
    symbols = symbols or getattr(settings, "TRADING_PAIRS", ["XAUUSD"])
    risk_cfg = risk_cfg or RiskConfig()
    spread_lookup = spread_lookup or {}
    recent_results = recent_results or []
    pf_cfg = _profit_filter_cfg()
    out: Dict[str, dict] = {}

    for sym in symbols:
        frames = load_frames(sym)
        if not frames:
            out[sym] = {
                "direction": "NONE",
                "confidence": 0.0,
                "votes": [],
                "risk": {"allow": False, "reason": "no data"},
                "profit_gate": {"allow": False, "reasons": ["no data"], "score_adjust": 0.0, "detail": {}},
                "team": team_of(sym),
                "agent_summary": "no-data",
            }
            continue

        direction, votes = vote_all(frames, min_votes=min_votes)
        dir_name = {1: "BUY", -1: "SELL", 0: "NONE"}[direction]
        conf = 0.5 + 0.15 * sum(1 for v in votes if v.vote == direction and direction != 0)

        ref_tf = "H1" if "H1" in frames else next(iter(frames))
        atr_last, atr_series = _last_atr(frames[ref_tf])
        equity_now = getattr(risk_state, "equity", 0.0) if risk_state else 0.0
        equity_start = getattr(risk_state, "start_of_day", 0.0) if risk_state else 0.0

        profit_gate = evaluate_all(
            spread_price=float(spread_lookup.get(sym, 0.0)),
            atr_price=atr_last,
            atr_series=atr_series,
            equity_now=equity_now,
            equity_start_of_day=equity_start,
            recent_results=recent_results,
            cooldown_active=cooldown_active,
            cfg=pf_cfg,
        )
        conf = max(0.0, min(1.0, conf + profit_gate.score_adjust))

        if direction != 0 and not profit_gate.allow:
            dir_name = "NONE"
            direction = 0

        risk = {"allow": True, "reason": "n/a"}
        if direction != 0 and risk_state is not None:
            dec = check_risk(sym, dir_name, risk_cfg.min_lot, risk_state, risk_cfg)
            risk = dec.as_dict()

        summary = "+".join(f"{v.name}:{v.vote:+d}" for v in votes)
        out[sym] = {
            "direction": dir_name,
            "confidence": round(conf, 3),
            "votes": [v.as_dict() for v in votes],
            "risk": risk,
            "profit_gate": profit_gate.as_dict(),
            "team": team_of(sym),
            "agent_summary": summary,
        }
    return out


__all__ = ["scan_once", "load_frames"]
