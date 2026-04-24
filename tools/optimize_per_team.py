"""
tools/optimize_per_team.py — per-TEAM (asset-class) parameter optimizer.

Research-informed design (2025-2026 SOTA)
-----------------------------------------
- METALS (XAU/XAG): Gold EAs use 1.5x ATR SL by default; high volatility
  late 2025/early 2026 requires wider TP for trend capture.
  [beirmancapital.com, tradewizards.org 2025]
- FOREX (12 majors/crosses): Profitable trend EAs on EUR/USD, USD/JPY, GBP/USD
  achieve 70%+ WR with Sharpe >1.5. Common TP: 2-3× ATR. [earnforex.com 2025]
- CRYPTO (BTC/ETH): Bollinger-band-based volatility filtering; stop at
  1.5× ATR or recent swing low. Take profit at 2-3× SL or key level.
  [zignaly.com, cvi.finance 2025]
- COMMODITIES (WTI/Brent/NatGas): High news-driven volatility; scalpers use
  momentum oscillators + Fib retracement. Wider SL for news spikes.
  [cmegroup, stonex.com]

Strategy
--------
For each team, pool trades across all member symbols. Find the SL/TP/ADX
combination that maximizes pooled expectancy × sqrt(n) × (1+WR). Team
config is less prone to overfitting than per-symbol because:
  - Larger sample size (2-12 symbols merged)
  - Robust to one symbol's quirks
  - Easier to maintain over time

Output: ai_trading_agents/team_params.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.optimize_fast import backtest


TEAMS = {
    "METALS": ["XAUUSD", "XAGUSD"],
    "FOREX": [
        "GBPJPY",
        "USDCAD",
        "USDCHF",
        "EURUSD",
        "GBPUSD",
        "AUDUSD",
        "USDJPY",
        "NZDUSD",
        "EURJPY",
        "EURGBP",
        "AUDJPY",
        "CADJPY",
    ],
    "CRYPTO": ["BTCUSD", "ETHUSD"],
    "COMMODITIES": ["XTIUSD", "XBRUSD", "XNGUSD"],
}

# Research-informed grids per team.
TEAM_GRIDS = {
    "METALS": {
        # Gold research: 1.5× ATR baseline; news-driven so wider SL wins.
        "sl": [1.0, 1.5, 2.0],
        "tp": [2.5, 3.5, 5.0],
        "adx": [22, 30, 40],
    },
    "FOREX": {
        # Major pairs research: tight spreads allow tight SL; 2-3× ATR TP typical.
        "sl": [0.8, 1.0, 1.5],
        "tp": [1.5, 2.5, 3.5],
        "adx": [22, 30, 40],
    },
    "CRYPTO": {
        # Crypto research: wider SL (1.5-2× ATR) for volatility; 2-3× TP.
        "sl": [1.5, 2.0, 2.5],
        "tp": [2.0, 3.0, 4.0],
        "adx": [22, 30, 40],
    },
    "COMMODITIES": {
        # Energy: news-driven big moves; wider SL, long TPs for trend capture.
        "sl": [1.0, 1.5, 2.0],
        "tp": [2.5, 3.5, 5.0],
        "adx": [22, 30, 40],
    },
}


def _load_df(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    return df[["open", "high", "low", "close", "volume"]].sort_index()


def team_backtest(team: str, symbols: list, data_dir: Path, sl: float, tp: float, adx: int) -> dict:
    """Run a config across every symbol in the team, pool the results."""
    totals = {"trades": 0, "wins": 0, "losses": 0, "timeouts": 0, "gross_r": 0.0, "per_symbol": {}}
    all_outcomes = []
    for sym in symbols:
        csv = data_dir / f"{sym.lower()}_m5_history.csv"
        if not csv.exists():
            continue
        df = _load_df(csv)
        if len(df) < 500:
            continue
        r = backtest(df, sl, tp, adx)
        totals["per_symbol"][sym] = r
        totals["trades"] += r["trades"]
        totals["wins"] += r["wins"]
        totals["losses"] += r["losses"]
        totals["timeouts"] += r["timeouts"]
        totals["gross_r"] += r["gross_r"]
        # Reconstruct approximate outcome list.
        if r["trades"] > 0:
            all_outcomes.extend([tp / sl] * r["wins"])
            all_outcomes.extend([-1.0] * r["losses"])
    if totals["trades"] == 0:
        totals.update({"win_rate": 0.0, "expectancy": 0.0, "sharpe": 0.0})
        return totals
    totals["win_rate"] = totals["wins"] / totals["trades"]
    arr = np.array(all_outcomes)
    totals["expectancy"] = float(arr.mean()) if len(arr) else 0.0
    std = float(arr.std(ddof=0)) if len(arr) else 0.0
    totals["sharpe"] = totals["expectancy"] / std if std > 0 else 0.0
    return totals


def score(r: dict) -> float:
    if r["trades"] < 100:
        return -1e9
    if r["expectancy"] <= 0:
        return r["expectancy"]
    return r["expectancy"] * (r["trades"] ** 0.5) * (1.0 + r["win_rate"])


def optimize_team(team: str, symbols: list, data_dir: Path) -> dict:
    grid = TEAM_GRIDS[team]
    best = None
    all_cfgs = []
    for sl in grid["sl"]:
        for tp in grid["tp"]:
            for adx in grid["adx"]:
                r = team_backtest(team, symbols, data_dir, sl, tp, adx)
                if r["trades"] == 0:
                    continue
                rr = tp / sl
                row = {
                    "sl": sl,
                    "tp": tp,
                    "adx": adx,
                    "rr": round(rr, 2),
                    "trades": r["trades"],
                    "win_rate": r["win_rate"],
                    "expectancy": r["expectancy"],
                    "gross_r": r["gross_r"],
                    "sharpe": r["sharpe"],
                    "score": score(r),
                    "per_symbol": {
                        k: {"trades": v["trades"], "win_rate": v["win_rate"], "gross_r": v["gross_r"]}
                        for k, v in r["per_symbol"].items()
                    },
                }
                all_cfgs.append(row)
                if best is None or row["score"] > best["score"]:
                    best = row
    return {"team": team, "best": best, "all": all_cfgs}


def main():
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    reports = root / "reports"

    summary = {}
    print(
        f"{'TEAM':12s}  {'SL':>5s} {'TP':>5s} {'RR':>5s} {'ADX':>4s}  "
        f"{'trades':>6s} {'WR':>6s} {'exp(R)':>8s} {'gross':>9s} {'sec':>6s}"
    )
    print("-" * 95)
    for team, syms in TEAMS.items():
        t0 = time.time()
        out = optimize_team(team, syms, data_dir)
        dt = time.time() - t0
        summary[team] = out
        b = out.get("best")
        if not b:
            print(f"{team:12s}  (no data)")
            continue
        print(
            f"{team:12s}  {b['sl']:>5.1f} {b['tp']:>5.1f} 1:{b['rr']:<3.1f} "
            f"{b['adx']:>4d}  {b['trades']:>6d} {b['win_rate'] * 100:5.1f}% "
            f"{b['expectancy']:+8.3f} {b['gross_r']:+9.2f} {dt:>5.1f}s"
        )
        sys.stdout.flush()

    # Write JSON
    (reports / "PER_TEAM_OPTIMAL.json").write_text(json.dumps(summary, indent=2, default=str))

    # Write team_params.py
    lines = [
        '"""Auto-generated per-TEAM optimal parameters.',
        "",
        "Generated by tools/optimize_per_team.py. Research-informed grids",
        "per asset class (METALS/FOREX/CRYPTO/COMMODITIES).",
        "DO NOT EDIT BY HAND.",
        '"""',
        "",
        "TEAM_PARAMS = {",
    ]
    for team, data in summary.items():
        b = data.get("best")
        if not b:
            continue
        lines.append(f"    '{team}': {{")
        lines.append(f"        'sl_atr_mult':  {b['sl']},")
        lines.append(f"        'tp_atr_mult':  {b['tp']},")
        lines.append(f"        'adx_min':      {b['adx']},")
        lines.append(f"        'expected_wr':  {b['win_rate']:.4f},")
        lines.append(f"        'expected_exp': {b['expectancy']:.4f},")
        lines.append(f"        'trades_bt':    {b['trades']},")
        lines.append(f"        'gross_r':      {b['gross_r']:.2f},")
        lines.append(f"        'sharpe':       {b['sharpe']:.4f},")
        lines.append("    },")
    lines.append("}")
    lines.append("")
    lines.append("# Symbol → team lookup (mirrors risk_manager.team_of)")
    lines.append("SYMBOL_TO_TEAM = {")
    for team, syms in TEAMS.items():
        for s in syms:
            lines.append(f"    '{s}': '{team}',")
    lines.append("}")
    (root / "ai_trading_agents" / "team_params.py").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Write markdown report
    md = [
        "# Per-Team Optimal Parameters",
        "",
        "_Research-informed per-asset-class grids. Pooled across all symbols in each team._",
        "",
        "## Summary",
        "",
        "| Team | SL×ATR | TP×ATR | R:R | ADX | Trades | WR | Exp(R) | Gross R | Sharpe |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for team, data in summary.items():
        b = data.get("best")
        if not b:
            md.append(f"| {team} | — | — | — | — | — | — | — | — | — |")
            continue
        md.append(
            f"| {team} | {b['sl']} | {b['tp']} | 1:{b['rr']} | {b['adx']} | "
            f"{b['trades']} | {b['win_rate'] * 100:.1f}% | "
            f"{b['expectancy']:+.3f} | {b['gross_r']:+.1f} | {b['sharpe']:+.3f} |"
        )
    md.append("")
    md.append("## Per-team detail")
    for team, data in summary.items():
        b = data.get("best")
        if not b:
            continue
        md.append("")
        md.append(f"### {team}")
        md.append("")
        md.append(f"Winning config: **SL={b['sl']}×ATR  TP={b['tp']}×ATR  1:{b['rr']} R:R  ADX≥{b['adx']}**")
        md.append("")
        md.append("Per-symbol breakdown:")
        md.append("")
        md.append("| Symbol | Trades | WR | Gross R |")
        md.append("| --- | ---: | ---: | ---: |")
        for sym, r in (b.get("per_symbol") or {}).items():
            md.append(f"| {sym} | {r['trades']} | {r['win_rate'] * 100:.1f}% | {r['gross_r']:+.2f} |")
    (reports / "PER_TEAM_OPTIMAL.md").write_text("\n".join(md) + "\n")
    print()
    print(f"Wrote: {reports / 'PER_TEAM_OPTIMAL.json'}")
    print(f"Wrote: {reports / 'PER_TEAM_OPTIMAL.md'}")
    print(f"Wrote: ai_trading_agents/team_params.py")


if __name__ == "__main__":
    main()
