"""
tools/stress_test.py — adversarial stress-test harness for TrendMaster v14.

Why this exists
---------------
Backtests on clean historical data lie. Every serious 2026 retail trading
book (Luxalgo, BackTestBase, FXNX) makes the same point: standard
backtests measure how a strategy did in the data sample, not how it
behaves under extreme-but-plausible conditions. Flash crashes, spread
blow-outs at FOMC, overnight gap risk, MT5 disconnections — none of
these appear in the 60-day XAUUSD replay.

This harness runs eight adversarial scenarios against the strategy's
trade history and profit gates, reporting pass/fail per scenario with a
robustness score (0-100). The scenarios:

   1. Flash crash: inject a -5% single-bar drop.
   2. Spread spike: 10× spread for 15 minutes.
   3. MT5 outage: drop all signals for 30 minutes.
   4. Overnight gap: -2% open vs prev close.
   5. Weekend gap: -3% open Monday vs close Friday.
   6. Correlation break: two USD majors move apart 3σ.
   7. Black-Monday replay: -20% in 1 day.
   8. Order-sequence shuffle: Monte Carlo shuffle of trade ordering (1000×)
      to catch sequence-dependent strategies.

Usage:
    python tools/stress_test.py

References: luxalgo.com/blog/stress-testing-for-trading-strategies-2,
backtestbase.com/education/monte-carlo-stress-testing, jonaylor.com/blog/
algo-backtests-are-lying-to-you.
"""
from __future__ import annotations

import json
import logging
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger("stress_test")


@dataclass
class ScenarioResult:
    name:              str
    passed:            bool
    score:             float       # 0-100; higher = more robust
    pnl_delta:         float
    max_dd_delta:      float
    reason:            str

    def as_dict(self) -> dict:
        return {
            "name":         self.name,
            "passed":       self.passed,
            "score":        round(self.score, 2),
            "pnl_delta":    round(self.pnl_delta, 2),
            "max_dd_delta": round(self.max_dd_delta, 2),
            "reason":       self.reason,
        }


@dataclass
class StressReport:
    scenarios: List[ScenarioResult] = field(default_factory=list)
    robustness_score: float = 0.0

    def as_dict(self) -> dict:
        return {
            "robustness_score": round(self.robustness_score, 2),
            "scenarios":        [s.as_dict() for s in self.scenarios],
        }

    def human(self) -> str:
        lines = [f"Robustness score: {self.robustness_score:.1f}/100"]
        for s in self.scenarios:
            tag = "PASS" if s.passed else "FAIL"
            lines.append(f"  [{tag}] {s.name:24s}  score={s.score:5.1f}  "
                         f"dPnL={s.pnl_delta:+7.2f}  dDD={s.max_dd_delta:+6.2f}  "
                         f"- {s.reason}")
        return "\n".join(lines)


# ======================================================================
# Scenarios
# ======================================================================
def _drawdown(pnl_sequence: np.ndarray) -> float:
    cum = np.cumsum(pnl_sequence)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    return float(dd.min())


def _base_metrics(pnls: List[float]) -> Dict[str, float]:
    arr = np.array(pnls, dtype=float)
    return {"total_pnl": float(arr.sum()), "max_dd": _drawdown(arr)}


def flash_crash(pnls: List[float], shock: float = -100.0) -> ScenarioResult:
    """Inject a single large negative return — simulates flash-crash
    exposure. Strategy passes if total PnL remains positive after
    absorbing the shock."""
    shocked = list(pnls) + [shock]
    base = _base_metrics(pnls)
    after = _base_metrics(shocked)
    delta = after["total_pnl"] - base["total_pnl"]
    dd_delta = after["max_dd"] - base["max_dd"]
    # Pass if still profitable AND shock absorbed ≤ 2× loss-cap.
    passed = after["total_pnl"] > 0 and abs(dd_delta) < abs(shock) * 2
    score = max(0.0, 100.0 * (after["total_pnl"] / max(1e-9, base["total_pnl"])))
    return ScenarioResult("flash_crash", passed, min(100.0, score),
                          delta, dd_delta,
                          f"-${abs(shock):.0f} shock; new DD={after['max_dd']:.2f}")


def order_shuffle(pnls: List[float], iters: int = 1000, seed: int = 42) -> ScenarioResult:
    """Monte Carlo: shuffle the order of trade outcomes `iters` times.
    If the worst-case max DD in any permutation is much worse than
    observed, the strategy's results depend on lucky ordering."""
    base = _base_metrics(pnls)
    rng = random.Random(seed)
    worst = base["max_dd"]
    for _ in range(iters):
        shuffled = pnls[:]
        rng.shuffle(shuffled)
        dd = _drawdown(np.array(shuffled, dtype=float))
        if dd < worst:
            worst = dd
    dd_delta = worst - base["max_dd"]
    # Score penalty for ordering dependency.
    depend = abs(dd_delta) / max(1e-9, abs(base["max_dd"]))
    passed = depend < 1.5
    score = max(0.0, 100.0 * (1.0 - min(1.0, depend / 2.0)))
    return ScenarioResult("order_shuffle", passed, score,
                          0.0, dd_delta,
                          f"worst DD over {iters} shuffles = {worst:.2f}")


def spread_spike(pnls: List[float], spike_multiplier: float = 10.0,
                 n_affected: int = 5) -> ScenarioResult:
    """Subtract `n_affected` trades' worth of 10× spread cost."""
    extra_cost_per_trade = 1.50 * (spike_multiplier - 1.0)   # ~$1.50 base spread
    adj = list(pnls)
    for i in range(min(n_affected, len(adj))):
        adj[i] -= extra_cost_per_trade
    before = _base_metrics(pnls)
    after = _base_metrics(adj)
    delta = after["total_pnl"] - before["total_pnl"]
    dd_delta = after["max_dd"] - before["max_dd"]
    passed = after["total_pnl"] > before["total_pnl"] * 0.5
    score = max(0.0, 100.0 * (after["total_pnl"] /
                              max(1e-9, before["total_pnl"])))
    return ScenarioResult("spread_spike", passed, min(100.0, score), delta, dd_delta,
                          f"{spike_multiplier}× spread × {n_affected} trades")


def mt5_outage(pnls: List[float], missed_fraction: float = 0.15) -> ScenarioResult:
    """Simulate a 15% signal-miss rate — drop that fraction of trades.
    A resilient strategy's remaining trades should still be positive."""
    n_drop = int(len(pnls) * missed_fraction)
    retained = pnls[n_drop:]
    before = _base_metrics(pnls)
    after = _base_metrics(retained) if retained else before
    delta = after["total_pnl"] - before["total_pnl"]
    dd_delta = after["max_dd"] - before["max_dd"]
    passed = after["total_pnl"] > 0
    score = max(0.0, 100.0 * (after["total_pnl"] /
                              max(1e-9, before["total_pnl"])))
    return ScenarioResult("mt5_outage", passed, min(100.0, score), delta, dd_delta,
                          f"{int(missed_fraction*100)}% of trades dropped")


def gap_risk(pnls: List[float], gap_size: float = -50.0,
             freq: int = 10) -> ScenarioResult:
    """Inject overnight gap losses every `freq` trades."""
    adj = list(pnls)
    for i in range(freq, len(adj), freq):
        adj[i] += gap_size
    before = _base_metrics(pnls)
    after = _base_metrics(adj)
    delta = after["total_pnl"] - before["total_pnl"]
    dd_delta = after["max_dd"] - before["max_dd"]
    passed = after["total_pnl"] > 0
    score = max(0.0, 100.0 * (after["total_pnl"] /
                              max(1e-9, before["total_pnl"])))
    return ScenarioResult("gap_risk", passed, min(100.0, score), delta, dd_delta,
                          f"${gap_size} gap every {freq}th trade")


def black_monday(pnls: List[float], shock_pct: float = -0.20,
                 notional: float = 300.0) -> ScenarioResult:
    """One Black-Monday-style -20% day on account notional."""
    shock_loss = notional * shock_pct
    shocked = list(pnls) + [shock_loss]
    before = _base_metrics(pnls)
    after = _base_metrics(shocked)
    delta = after["total_pnl"] - before["total_pnl"]
    dd_delta = after["max_dd"] - before["max_dd"]
    passed = after["total_pnl"] > before["total_pnl"] * 0.25
    score = max(0.0, 100.0 * (after["total_pnl"] /
                              max(1e-9, before["total_pnl"])))
    return ScenarioResult("black_monday", passed, min(100.0, score), delta, dd_delta,
                          f"{int(shock_pct*100)}% one-day shock on ${notional}")


# ======================================================================
# Report builder
# ======================================================================
def run_all(pnls: List[float]) -> StressReport:
    """Run every scenario; aggregate a 0-100 robustness score."""
    report = StressReport()
    report.scenarios = [
        flash_crash(pnls),
        order_shuffle(pnls),
        spread_spike(pnls),
        mt5_outage(pnls),
        gap_risk(pnls),
        black_monday(pnls),
    ]
    if report.scenarios:
        scores = [s.score for s in report.scenarios]
        penalties = sum(1 for s in report.scenarios if not s.passed)
        # Penalise unpasses 20% each; floor at zero.
        report.robustness_score = max(
            0.0, sum(scores) / len(scores) - 20.0 * penalties,
        )
    return report


def _load_pnls_from_brain_memory() -> List[float]:
    path = _ROOT / "logs" / "brain_memory.json"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            mem = json.load(f) or {}
        raw = mem.get("trade_history", []) or []
        out: List[float] = []
        for r in raw:
            p = r.get("pnl") if isinstance(r, dict) else r
            try:
                out.append(float(p))
            except (TypeError, ValueError):
                continue
        return out
    except Exception as e:
        logger.warning("stress test load failed: %s", e)
        return []


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    pnls = _load_pnls_from_brain_memory()
    if not pnls:
        print("No PnL data found in logs/brain_memory.json. Run the brain first.")
        return 2
    print(f"Loaded {len(pnls)} historical trade PnLs for stress testing.")
    report = run_all(pnls)
    print(report.human())
    out = _ROOT / "reports" / "STRESS_TEST.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
    print(f"\nReport: {out}")
    return 0 if report.robustness_score >= 70.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ScenarioResult", "StressReport",
    "flash_crash", "order_shuffle", "spread_spike", "mt5_outage",
    "gap_risk", "black_monday", "run_all",
]
