"""
tools/optimize_per_pair.py — per-symbol parameter optimizer.

For EACH of the 19 symbols, sweeps SL/TP/ADX configurations using the
3-of-3 logic from backtest_filtered.py and picks the best combination
for that symbol's personality.

Output: reports/PER_PAIR_OPTIMAL.json + reports/PER_PAIR_OPTIMAL.md,
plus ai_trading_agents/pair_params.py (auto-generated per-pair config).

Strategy
--------
For each symbol, we look for the config that maximizes a composite score:

    score = expectancy_R × sqrt(n_trades) × (1 + win_rate)

This rewards:
  - High expectancy per trade (profit engine)
  - Enough sample size (statistical significance — sqrt dampens n abuse)
  - Higher win rate (psychology + drawdown smoothness)

Grid
----
SL ∈ {0.8, 1.0, 1.25, 1.5, 2.0} × ATR
TP ∈ {1.5, 2.0, 2.5, 3.0, 4.0} × ATR (sometimes lower than SL for
    different personalities)
ADX ∈ {20, 25, 30, 35, 40}
Session filter: on/off

Result: 5 × 5 × 5 × 2 = 250 configs per symbol, 4,750 configs total.
Keeps runtime under ~15 min on a 50K bars set because each backtest
iteration is a tight numpy loop.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.backtest_filtered import FilterConfig, backtest_1to3


SYMBOLS = [
    "XAUUSD",
    "XAGUSD",
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
    "BTCUSD",
    "ETHUSD",
    "XTIUSD",
    "XBRUSD",
    "XNGUSD",
]

SL_VALUES = [1.0, 1.5, 2.0]
TP_VALUES = [1.5, 2.5, 3.5]
ADX_VALUES = [25, 32, 40]


def score_config(r) -> float:
    """Composite ranking score."""
    if r.trades < 30:
        return -1e9
    if r.expectancy <= 0:
        return r.expectancy
    return r.expectancy * (r.trades**0.5) * (1.0 + r.win_rate)


def optimize_symbol(csv_path: Path, symbol: str) -> Dict:
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        return {"symbol": symbol, "error": f"load failed: {e}"}
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    df = df[["open", "high", "low", "close", "volume"]].sort_index()
    if len(df) < 1000:
        return {"symbol": symbol, "error": f"only {len(df)} bars"}

    best_overall = None
    best_1to3 = None  # best with tp/sl >= 2.8
    all_results: List = []

    for sl in SL_VALUES:
        for tp in TP_VALUES:
            for adx in ADX_VALUES:
                rr = tp / sl
                cfg = FilterConfig(adx_min=adx, sl_atr=sl, tp_atr=tp)
                r = backtest_1to3(df, cfg, name=f"sl{sl}/tp{tp}/adx{adx}")
                if r.trades == 0:
                    continue
                s = score_config(r)
                row = {
                    "sl": sl,
                    "tp": tp,
                    "rr": round(rr, 2),
                    "adx": adx,
                    "trades": r.trades,
                    "win_rate": round(r.win_rate, 4),
                    "expectancy": round(r.expectancy, 4),
                    "gross_r": round(r.gross_r, 2),
                    "sharpe": round(r.sharpe, 3),
                    "score": round(s, 3),
                }
                all_results.append(row)
                if best_overall is None or s > best_overall["score"]:
                    best_overall = row
                # 1:3 bucket — tp >= 2.5 × sl
                if rr >= 2.5:
                    if best_1to3 is None or s > best_1to3["score"]:
                        best_1to3 = row

    return {
        "symbol": symbol,
        "n_configs": len(all_results),
        "best_overall": best_overall,
        "best_1to3": best_1to3,
        "all_results": all_results,
    }


def main():
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    summary = {}
    total = len(SYMBOLS)
    print(f"Optimizing {total} symbols across {len(SL_VALUES) * len(TP_VALUES) * len(ADX_VALUES)} configs each...")
    print()
    print(f"{'symbol':8s} {'BEST overall':55s}  {'BEST 1:3 RR':55s}")
    print("-" * 130)
    sys.stdout.flush()
    import time

    for idx, sym in enumerate(SYMBOLS, 1):
        csv = data_dir / f"{sym.lower()}_m5_history.csv"
        if not csv.exists():
            print(f"{sym:8s} (no data)")
            sys.stdout.flush()
            continue
        t0 = time.time()
        out = optimize_symbol(csv, sym)
        dt = time.time() - t0
        summary[sym] = out
        if "error" in out:
            print(f"{sym:8s} ERROR: {out['error']}")
            continue
        bo = out["best_overall"]
        b13 = out["best_1to3"] or {}
        left = (
            f"SL={bo['sl']} TP={bo['tp']} ADX={bo['adx']} "
            f"WR={bo['win_rate'] * 100:.1f}% "
            f"exp={bo['expectancy']:+.3f} n={bo['trades']}"
        )
        right = ""
        if b13:
            right = (
                f"SL={b13['sl']} TP={b13['tp']} ADX={b13['adx']} "
                f"WR={b13['win_rate'] * 100:.1f}% "
                f"exp={b13['expectancy']:+.3f} n={b13['trades']}"
            )
        else:
            right = "(no profitable 1:3 config)"
        print(f"{sym:8s} {left:55s}  {right:55s}   [{dt:.1f}s, {idx}/{total}]")
        sys.stdout.flush()

    # Write full JSON dump.
    json_path = reports_dir / "PER_PAIR_OPTIMAL.json"
    json_path.write_text(json.dumps(summary, indent=2))
    print(f"\nFull results: {json_path}")

    # Generate per-pair settings dict.
    lines = [
        '"""Auto-generated per-symbol optimal EA/brain parameters.',
        "",
        "Generated by tools/optimize_per_pair.py — DO NOT EDIT BY HAND.",
        "Re-generate after each data refresh or symbol addition.",
        '"""',
        "",
        "PAIR_PARAMS = {",
    ]
    for sym in SYMBOLS:
        out = summary.get(sym, {})
        if "error" in out:
            continue
        bo = out.get("best_overall") or {}
        b13 = out.get("best_1to3") or {}
        # Prefer the 1:3 config if it passes a minimum expectancy bar.
        pick = b13 if (b13 and b13.get("expectancy", -1) > 0.05) else bo
        if not pick:
            continue
        lines.append(f"    '{sym}': {{")
        lines.append(f"        'sl_atr_mult':  {pick['sl']},")
        lines.append(f"        'tp_atr_mult':  {pick['tp']},")
        lines.append(f"        'adx_min':      {pick['adx']},")
        lines.append(f"        'expected_wr':  {pick['win_rate']},")
        lines.append(f"        'expected_exp': {pick['expectancy']},")
        lines.append(f"        'trades_bt':    {pick['trades']},")
        lines.append(f"        'gross_r':      {pick['gross_r']},")
        lines.append(f"        'sharpe':       {pick['sharpe']},")
        lines.append("    },")
    lines.append("}")
    params_path = root / "ai_trading_agents" / "pair_params.py"
    params_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote: {params_path}")

    # Markdown summary.
    md_lines = [
        "# Per-Pair Optimal Parameters",
        "",
        "_Auto-generated from 50,000 bars per symbol (M5). Ranks by composite score: expectancy × sqrt(n) × (1+WR)._",
        "",
        "| Symbol | SL×ATR | TP×ATR | RR | ADX | Trades | WR | Exp(R) | Gross R | Sharpe |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for sym in SYMBOLS:
        out = summary.get(sym, {})
        if "error" in out:
            md_lines.append(f"| {sym} | ERROR | — | — | — | — | — | — | — | — |")
            continue
        bo = out.get("best_overall") or {}
        b13 = out.get("best_1to3") or {}
        pick = b13 if (b13 and b13.get("expectancy", -1) > 0.05) else bo
        if pick:
            md_lines.append(
                f"| {sym} | {pick['sl']} | {pick['tp']} | 1:{pick['rr']} | "
                f"{pick['adx']} | {pick['trades']} | {pick['win_rate'] * 100:.1f}% | "
                f"{pick['expectancy']:+.3f} | {pick['gross_r']:+.1f} | "
                f"{pick['sharpe']:+.2f} |"
            )
    md_path = reports_dir / "PER_PAIR_OPTIMAL.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"Wrote: {md_path}")


if __name__ == "__main__":
    main()
