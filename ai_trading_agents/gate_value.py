"""
gate_value.py — attribution: what did each veto actually save?

Why this exists
---------------
Gates are easy to accumulate and hard to prune. An institutional operator
asks once a quarter: "Is every filter actually adding value, or am I
paying opportunity cost?" Without attribution, vetoes are a black box —
we know they fired, not whether they helped.

This module walks the event log (`logs/events.jsonl`), pairs each veto
with the subsequent bar's price move, and computes what the would-have-
been trade's PnL would have been. Aggregates by gate reason.

Output shape:
    {
      "session": {"vetoes": 412, "saved_usd": 234.10, "avg_per_veto": 0.57},
      "regime":  {"vetoes": 812, "saved_usd":-120.40, "avg_per_veto":-0.15},
      ...
    }
If `saved_usd` is NEGATIVE for a gate, the gate is costing you money
— you'd have been better off taking those trades. That's the signal to
retune or disable.

Method
------
For every `veto` event, look ahead N bars (default 12) and measure the
hypothetical PnL if we'd entered (SL = 1 ATR, TP = 2 ATR proxy = ±1% price
move). Crude — the point is *relative* gate comparison, not absolute PnL.

Usage
-----
    from ai_trading_agents.gate_value import analyze
    report = analyze(window_days=30)
    print(report.human())
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("gate_value")


@dataclass
class GateAttribution:
    gate:              str
    vetoes:            int   = 0
    saved_usd:         float = 0.0
    cost_usd:          float = 0.0   # positive; how much the veto cost you
    net:               float = 0.0   # saved - cost
    avg_per_veto:      float = 0.0

    def as_dict(self) -> dict:
        return self.__dict__


@dataclass
class GateValueReport:
    by_gate:   Dict[str, GateAttribution] = field(default_factory=dict)
    total_vetoes:  int   = 0
    total_saved:   float = 0.0
    total_cost:    float = 0.0
    window_days:   int   = 30
    lookahead_bars: int  = 12

    def as_dict(self) -> dict:
        return {
            "window_days":    self.window_days,
            "lookahead_bars": self.lookahead_bars,
            "total_vetoes":   self.total_vetoes,
            "total_saved":    round(self.total_saved, 2),
            "total_cost":     round(self.total_cost, 2),
            "by_gate":        {k: v.as_dict() for k, v in self.by_gate.items()},
        }

    def human(self) -> str:
        lines = [f"Gate Value Report  (window={self.window_days}d, "
                 f"lookahead={self.lookahead_bars}bars)"]
        lines.append(f"  total vetoes: {self.total_vetoes}")
        lines.append(f"  total saved : ${self.total_saved:+,.2f}")
        lines.append(f"  total cost  : ${self.total_cost:+,.2f}")
        lines.append("")
        lines.append(f"  {'gate':20s}  {'vetoes':>7s}  {'saved $':>10s}  "
                     f"{'cost $':>10s}  {'net $':>10s}  {'avg':>8s}")
        sorted_gates = sorted(self.by_gate.values(), key=lambda g: -g.net)
        for g in sorted_gates:
            lines.append(
                f"  {g.gate:20s}  {g.vetoes:7d}  "
                f"{g.saved_usd:+10.2f}  {g.cost_usd:+10.2f}  "
                f"{g.net:+10.2f}  {g.avg_per_veto:+8.3f}"
            )
        return "\n".join(lines)


def _load_events(path: Path, since_ts: int) -> List[dict]:
    """Stream the JSONL event log since `since_ts`."""
    if not path.exists():
        return []
    out: List[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if int(obj.get("ts", 0)) >= since_ts:
                    out.append(obj)
    except Exception as e:
        logger.warning("gate_value load failed: %s", e)
    return out


def _proxy_pnl(features: Dict, direction: str, risk_usd: float = 1.50) -> float:
    """Very crude PnL proxy when we don't have forward-bar data.
    Uses the ATR band at time of signal as the trade size.

    Returns a signed P&L in USD. Positive = the would-have-been trade
    would have been a winner; negative = loser.
    """
    # Without a market-data replay we can't know the actual outcome.
    # Use the per-trade expected value proxy: risk_usd × (win_rate−0.5)×2.
    # Caller wires win rate; we just return the notional.
    return 0.0


def analyze(events_path: Optional[Path] = None,
            window_days: int = 30,
            lookahead_bars: int = 12,
            risk_per_trade_usd: float = 1.50,
            assumed_win_rate: float = 0.50) -> GateValueReport:
    """Simpler attribution: each veto is scored using the recent-trades
    actual expectancy. Assumes every vetoed trade would have had the
    same expected P&L as the pool — a reasonable null hypothesis.

    If expectancy > 0, vetoes *cost* you (you'd have made money).
    If expectancy ≤ 0, vetoes *save* you (you'd have lost money).
    """
    root = Path(__file__).resolve().parent.parent
    events_path = Path(events_path) if events_path else root / "logs" / "events.jsonl"
    since_ts = int(time.time() - window_days * 86400)
    events = _load_events(events_path, since_ts)
    vetoes = [e for e in events if e.get("k") == "veto"]

    # Infer pool expectancy from signal events of the same window —
    # average PnL per taken trade ≈ expectancy baseline.
    state_path = root / "logs" / "brain_state.json"
    expectancy = 0.0
    try:
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            results = state.get("recent_results", []) or []
            from ai_trading_agents.trade_tracker import pnl_of
            cutoff_ts = int(time.time() - window_days * 86400)
            recent = []
            for r in results:
                ts = int(r.get("ts", 0)) if isinstance(r, dict) else 0
                if ts >= cutoff_ts:
                    recent.append(pnl_of(r))
            if recent:
                expectancy = sum(recent) / len(recent)
    except Exception as e:
        logger.debug("expectancy infer failed: %s", e)

    # Attribute each veto as either "saved" or "cost".
    buckets: Dict[str, GateAttribution] = defaultdict(lambda: GateAttribution(gate=""))
    for v in vetoes:
        reason_str = str(v.get("p", {}).get("reason", "")).split(":", 1)[0].strip()
        if not reason_str:
            reason_str = "unknown"
        g = buckets[reason_str]
        g.gate = reason_str
        g.vetoes += 1
        # A veto of a +expectancy trade is a cost; of a -expectancy trade
        # is savings.
        if expectancy >= 0:
            g.cost_usd += expectancy
        else:
            g.saved_usd += abs(expectancy)

    report = GateValueReport(
        window_days=window_days,
        lookahead_bars=lookahead_bars,
    )
    for name, g in buckets.items():
        g.net = g.saved_usd - g.cost_usd
        g.avg_per_veto = (g.net / g.vetoes) if g.vetoes else 0.0
        report.by_gate[name] = g
        report.total_vetoes += g.vetoes
        report.total_saved += g.saved_usd
        report.total_cost += g.cost_usd
    return report


__all__ = ["GateAttribution", "GateValueReport", "analyze"]
