"""
backtest_profit_filters.py — head-to-head A/B test:
   baseline (no profit gates)  vs.  v14+gates  on identical synthetic data.

What this proves
----------------
The new profit_filters layer is supposed to *raise expectancy* by skipping
the worst trade conditions (wide spread, dead ATR, tilt streak, off-hours).
This script generates a deterministic synthetic price series, runs the
dispatcher over it both ways, and prints a side-by-side report:

   trades fired, win rate, avg R, total R, max drawdown.

It is intentionally synthetic-data only (no MT5 dependency) so anyone can
re-run it in CI / locally without broker creds.

Usage:
    python tools/backtest_profit_filters.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_trading_agents.profit_filters import evaluate_all  # noqa: E402
from ai_trading_agents.multi_agent import vote_all          # noqa: E402


# ---------------------------------------------------------------------
# Synthetic OHLCV generator. We build a 60-day M5 series with three
# regimes mixed in: trend, chop, and a fat-tail spike day. The mix is
# deliberately picked so a *naive* signal generator will fire badly in
# the chop and spike segments — that's where the filters earn their keep.
# ---------------------------------------------------------------------
def make_series(seed: int = 7, n_days: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    bars_per_day = 24 * 12     # M5 = 288 bars / day
    n = bars_per_day * n_days
    ts = pd.date_range(datetime(2026, 1, 1, tzinfo=timezone.utc),
                       periods=n, freq="5min")

    # Build returns block by block: 60% trend, 30% chop, 10% spike.
    out = []
    for d in range(n_days):
        roll = rng.random()
        if roll < 0.60:                          # trend day (clean direction)
            mu = rng.choice([0.05, -0.05])
            sd = 0.20
        elif roll < 0.90:                        # chop day (zero drift, low vol)
            mu, sd = 0.0, 0.10
        else:                                    # spike day (fat tail)
            mu, sd = 0.0, 1.20
        out.append(rng.normal(mu, sd, size=bars_per_day))
    rets = np.concatenate(out)
    close = 1900 + np.cumsum(rets)               # gold-ish baseline
    high  = close + rng.uniform(0.05, 0.45, size=n)
    low   = close - rng.uniform(0.05, 0.45, size=n)
    open_ = close - rng.normal(0, 0.10, size=n)
    vol   = rng.integers(50, 800, size=n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low,
         "close": close, "volume": vol},
        index=ts,
    )


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    return df.resample(f"{minutes}min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()


def atr14(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(n).mean()


# ---------------------------------------------------------------------
# Outcome model: once a trade is taken at price P with direction d, we
# look forward `horizon` bars (12 = 1 hour on M5) and resolve it as
# +R if (close - P) * d >= +tp_atr * ATR, -1R if <= -sl_atr * ATR, else 0.
# This is the standard "fixed RR" walk-forward model used in backtesting
# papers — simple, transparent, no curve-fitting.
# ---------------------------------------------------------------------
def trade_result(df5: pd.DataFrame, idx: int, direction: int,
                 sl_atr: float = 1.0, tp_atr: float = 2.0,
                 horizon: int = 12) -> float:
    if direction == 0:
        return 0.0
    if idx + horizon >= len(df5):
        return 0.0
    entry = df5["close"].iloc[idx]
    a     = atr14(df5).iloc[idx]
    if not np.isfinite(a) or a == 0:
        return 0.0
    win_dist  = tp_atr * a
    loss_dist = sl_atr * a
    seg = df5.iloc[idx + 1: idx + 1 + horizon]
    for _, row in seg.iterrows():
        move_up   = row["high"] - entry
        move_down = entry - row["low"]
        if direction > 0:
            if move_down >= loss_dist:
                return -1.0
            if move_up   >= win_dist:
                return +tp_atr / sl_atr
        else:
            if move_up   >= loss_dist:
                return -1.0
            if move_down >= win_dist:
                return +tp_atr / sl_atr
    return 0.0


# ---------------------------------------------------------------------
# Run a single configuration end-to-end and emit summary stats.
# ---------------------------------------------------------------------
def run_strategy(df5: pd.DataFrame, *, use_gates: bool, label: str,
                 spread_jitter: bool = True) -> dict:
    df30 = resample(df5, 30)
    df1h = resample(df5, 60)
    df4h = resample(df5, 240)

    rng = np.random.default_rng(123)
    results: list[float] = []
    equity = 1000.0
    peak   = equity
    dd     = 0.0
    trades = 0
    skipped = 0
    skip_reasons: dict[str, int] = {}
    sod_stamp = df5.index[0].date()
    sod_equity = equity

    # Vote every 4 H1 bars to keep runtime sane (~ 360 decisions / 60 days).
    h1_atr = atr14(df1h)
    for h1_idx, ts in enumerate(df1h.index):
        if h1_idx < 50:
            continue
        if h1_idx % 4 != 0:                  # decide every 4h to keep runtime sane
            continue

        # Roll start-of-day equity for the profit-lock gate.
        if ts.date() != sod_stamp:
            sod_stamp = ts.date()
            sod_equity = equity

        # Resample windows up to ts for the agent vote.
        frames = {
            "M30": df30.loc[:ts].iloc[-200:],
            "H1":  df1h.loc[:ts].iloc[-200:],
            "H4":  df4h.loc[:ts].iloc[-200:],
        }
        if min(len(v) for v in frames.values()) < 60:
            continue
        direction, _ = vote_all(frames, min_votes=3)
        if direction == 0:
            continue

        # Map H1 ts back to nearest M5 idx for trade resolution.
        m5_idx = df5.index.get_indexer([ts], method="nearest")[0]

        # Spread oscillates: sometimes super tight, sometimes very wide.
        cur_atr = float(h1_atr.iloc[h1_idx]) if np.isfinite(h1_atr.iloc[h1_idx]) else 0.5
        if spread_jitter:
            spread = rng.choice([0.05, 0.10, 0.30, 0.55]) * cur_atr
        else:
            spread = 0.05 * cur_atr

        if use_gates:
            gate = evaluate_all(
                spread_price=spread,
                atr_price=cur_atr,
                atr_series=h1_atr.iloc[max(0, h1_idx - 200): h1_idx + 1],
                equity_now=equity,
                equity_start_of_day=sod_equity,
                recent_results=results[-10:],
                cooldown_active=False,
                now_utc=ts.to_pydatetime(),
            )
            if not gate.allow:
                skipped += 1
                for r in gate.reasons:
                    key = r.split(":")[0]
                    skip_reasons[key] = skip_reasons.get(key, 0) + 1
                continue

        r = trade_result(df5, m5_idx, direction)
        # Risk one unit of equity per trade (simplified — same for both arms).
        pnl = r * 10.0          # $10 per 1R unit
        equity += pnl
        results.append(pnl)
        trades += 1
        peak = max(peak, equity)
        dd = max(dd, (peak - equity) / peak * 100.0)

    wins = sum(1 for x in results if x > 0)
    losses = sum(1 for x in results if x < 0)
    win_rate = wins / max(trades, 1) * 100.0
    avg_r = (sum(results) / max(trades, 1)) / 10.0   # back to R units
    total_r = sum(results) / 10.0
    return {
        "label":       label,
        "trades":      trades,
        "skipped":     skipped,
        "win_rate_%":  round(win_rate, 1),
        "avg_R":       round(avg_r, 3),
        "total_R":     round(total_r, 2),
        "final_$":     round(equity, 2),
        "max_dd_%":    round(dd, 2),
        "wins":        wins,
        "losses":      losses,
        "skip_reasons": skip_reasons,
    }


def fmt_row(r: dict) -> str:
    return (f"{r['label']:<24s} trades={r['trades']:<4d} "
            f"skipped={r['skipped']:<4d} "
            f"WR={r['win_rate_%']:>5.1f}% "
            f"avgR={r['avg_R']:+.3f} totalR={r['total_R']:+7.2f} "
            f"final=${r['final_$']:>7.2f} maxDD={r['max_dd_%']:>5.2f}%")


def main():
    print("=" * 96)
    print("  PROFIT-FILTER A/B BACKTEST  —  60 days synthetic M5 x 3 seeds (XAUUSD-like)")
    print("=" * 96)

    seeds   = [7, 19, 41]
    base_runs, gated_runs = [], []
    for s in seeds:
        df5 = make_series(seed=s, n_days=60)
        b = run_strategy(df5, use_gates=False, label=f"base.s{s}")
        g = run_strategy(df5, use_gates=True,  label=f"gate.s{s}")
        print(f"  seed={s}: {fmt_row(b)}")
        print(f"  seed={s}: {fmt_row(g)}")
        base_runs.append(b); gated_runs.append(g)

    def avg(runs, key):
        vals = [r[key] for r in runs]
        return sum(vals) / len(vals)

    def agg(runs, label):
        return {
            "label":      label,
            "trades":     int(avg(runs, "trades")),
            "skipped":    int(avg(runs, "skipped")),
            "win_rate_%": round(avg(runs, "win_rate_%"), 1),
            "avg_R":      round(avg(runs, "avg_R"), 3),
            "total_R":    round(avg(runs, "total_R"), 2),
            "final_$":    round(avg(runs, "final_$"), 2),
            "max_dd_%":   round(avg(runs, "max_dd_%"), 2),
            "wins":       int(avg(runs, "wins")),
            "losses":     int(avg(runs, "losses")),
        }

    base  = agg(base_runs,  "baseline (no gates)")
    gated = agg(gated_runs, "v14 + profit gates")
    print(fmt_row(base))
    print(fmt_row(gated))
    print()

    # Aggregate skip reasons across seeds.
    skip_total: dict[str, int] = {}
    for r in gated_runs:
        for k, v in r["skip_reasons"].items():
            skip_total[k] = skip_total.get(k, 0) + v
    print("Skip reasons (gated arm, sum across seeds):")
    for k, v in sorted(skip_total.items(), key=lambda kv: -kv[1]):
        print(f"   {k:<14s} {v}")
    print()

    print("Delta (gated - baseline, averaged):")
    print(f"   avg expectancy per trade  {gated['avg_R'] - base['avg_R']:+.3f} R")
    print(f"   total R over period       {gated['total_R'] - base['total_R']:+.2f} R")
    print(f"   max drawdown              {gated['max_dd_%'] - base['max_dd_%']:+.2f} pp")
    print(f"   trades fired              {gated['trades'] - base['trades']:+d}")
    if gated['avg_R'] > base['avg_R']:
        print("RESULT: gated arm has HIGHER expectancy per trade.")
    elif gated['avg_R'] == base['avg_R']:
        print("RESULT: same expectancy, fewer trades = bounded screen-time risk.")
    else:
        print("RESULT: lower expectancy on synthetic data; tune thresholds.")


if __name__ == "__main__":
    main()
