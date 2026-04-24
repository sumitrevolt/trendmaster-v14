"""
tools/backtest_rr_sweep.py — exhaustive R:R vs WR trade-off curve.

Answers the question: given the EA's 3-of-3 logic + various filters,
what win rate can we achieve at 1:1, 1:1.5, 1:2, 1:2.5, 1:3 RR?
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.backtest_filtered import FilterConfig, backtest_1to3


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "data/xauusd_m5_history.csv"
    df = pd.read_csv(csv_path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.set_index("time")
    df = df[["open", "high", "low", "close", "volume"]].sort_index()
    print(f"Loaded {len(df)} bars")

    # R:R ratios (SL=1.0, vary TP). Heavy filters for each.
    rr_targets = [(1.0, 1.0), (1.0, 1.5), (1.0, 2.0), (1.0, 2.5), (1.0, 3.0)]
    adx_mins = [25, 30, 35, 40]

    print()
    print(f"{'config':30s} {'SL':>4s} {'TP':>4s} {'RR':>6s} {'trades':>6s} {'WR':>7s} {'exp(R)':>8s} {'gross':>9s}")
    print("-" * 90)

    best_by_rr = {}

    for sl, tp in rr_targets:
        rr = tp / sl
        for adx in adx_mins:
            cfg = FilterConfig(adx_min=adx, sl_atr=sl, tp_atr=tp)
            r = backtest_1to3(df, cfg, name=f"adx{adx}")
            if r.trades == 0:
                continue
            mark = ""
            if r.win_rate >= 0.80 and r.trades >= 30:
                mark = " [PASS!]"
            print(
                f"sl{sl}tp{tp}_adx{adx:<2d}{'':14s} "
                f"{sl:>4.1f} {tp:>4.1f} 1:{rr:<4.2f} "
                f"{r.trades:6d} {r.win_rate * 100:5.1f}% "
                f"{r.expectancy:+8.3f} {r.gross_r:+9.2f}{mark}"
            )
            key = f"1:{rr:.1f}"
            if key not in best_by_rr or r.win_rate > best_by_rr[key][1]:
                best_by_rr[key] = (f"adx{adx} sl{sl}/tp{tp}", r.win_rate, r.expectancy, r.trades, r.gross_r)

    print()
    print("=" * 90)
    print("BEST WR PER R:R RATIO")
    print("=" * 90)
    for rr, (name, wr, exp, n, gross) in sorted(best_by_rr.items()):
        flag = " [80%+]" if wr >= 0.80 else ""
        print(f"  {rr:6s}  {name:30s}  WR={wr * 100:5.1f}%  exp={exp:+6.3f}R  n={n:4d}  gross={gross:+8.2f}R{flag}")


if __name__ == "__main__":
    main()
