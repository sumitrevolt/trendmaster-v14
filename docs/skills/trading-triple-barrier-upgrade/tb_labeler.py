"""
Asymmetric vol-scaled triple-barrier labeler for TrendMaster v14.

Loads a per-symbol M5 history CSV, resamples to H1, computes ATR(t-window),
applies TP/SL/time barriers, writes labeled parquet, prints a label-quality
report and refuses to write if any class drops below 15%.

Pure-Python; pandas + numpy + argparse + pathlib + json.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
DATA_DIR = REPO_ROOT / "data"
LABELS_DIR = REPO_ROOT / "data" / "labels"
QUALITY_DIR = REPO_ROOT / "logs" / "label_quality"

MIN_CLASS_FRAC = 0.15  # refuse to write if any class < 15%


def load_h1(symbol: str) -> pd.DataFrame:
    p = DATA_DIR / f"{symbol.lower()}_m5_history.csv"
    if not p.exists():
        raise SystemExit(f"Missing {p}")
    df = pd.read_csv(p, parse_dates=["time"])
    df = df.set_index("time").sort_index()
    h1 = df.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    h1 = h1.reset_index().rename(columns={"time": "ts"})
    return h1


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Wilder ATR using only past bars (shifted by 1 to avoid lookahead)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    # Wilder smoothing
    a = tr.ewm(alpha=1 / window, adjust=False).mean()
    return a.shift(1)  # one extra shift: ensure ATR(t) excludes bar t itself


def label_triple_barrier(
    df: pd.DataFrame,
    k1: float = 2.0,
    k2: float = 1.5,
    horizon: int = 24,
    atr_window: int = 14,
    side: str = "both",
) -> pd.DataFrame:
    df = df.copy()
    df["atr"] = atr(df, atr_window)
    df = df.dropna(subset=["atr"]).reset_index(drop=True)
    n = len(df)
    out_rows = []
    for i in range(n - horizon):
        entry_px = df.at[i, "close"]
        a = df.at[i, "atr"]
        if a <= 0 or np.isnan(a):
            continue
        tp_long, sl_long = entry_px + k1 * a, entry_px - k2 * a
        tp_short, sl_short = entry_px - k1 * a, entry_px + k2 * a
        window = df.iloc[i + 1: i + 1 + horizon]
        # long evaluation
        if side in ("long", "both"):
            hit_tp_idx = window.index[window["high"] >= tp_long].min()
            hit_sl_idx = window.index[window["low"] <= sl_long].min()
            label = _resolve(hit_tp_idx, hit_sl_idx)
            out_rows.append({
                "ts": df.at[i, "ts"], "side": "long", "entry_px": entry_px, "atr": a,
                "tp_px": tp_long, "sl_px": sl_long, "label": label,
                "hit_ts": _hit_ts(label, hit_tp_idx, hit_sl_idx, df, horizon, i),
                "holding_bars": _holding(label, hit_tp_idx, hit_sl_idx, i, horizon),
            })
        if side in ("short", "both"):
            hit_tp_idx = window.index[window["low"] <= tp_short].min()
            hit_sl_idx = window.index[window["high"] >= sl_short].min()
            label = _resolve(hit_tp_idx, hit_sl_idx)
            out_rows.append({
                "ts": df.at[i, "ts"], "side": "short", "entry_px": entry_px, "atr": a,
                "tp_px": tp_short, "sl_px": sl_short, "label": label,
                "hit_ts": _hit_ts(label, hit_tp_idx, hit_sl_idx, df, horizon, i),
                "holding_bars": _holding(label, hit_tp_idx, hit_sl_idx, i, horizon),
            })
    return pd.DataFrame(out_rows)


def _resolve(tp_idx, sl_idx) -> int:
    tp_ok = pd.notna(tp_idx)
    sl_ok = pd.notna(sl_idx)
    if not tp_ok and not sl_ok:
        return 0
    if tp_ok and (not sl_ok or tp_idx < sl_idx):
        return 1
    return -1


def _hit_ts(label, tp_idx, sl_idx, df, horizon, i):
    if label == 1:
        return df.at[int(tp_idx), "ts"]
    if label == -1:
        return df.at[int(sl_idx), "ts"]
    return df.at[i + horizon, "ts"]


def _holding(label, tp_idx, sl_idx, i, horizon):
    if label == 1:
        return int(tp_idx) - i
    if label == -1:
        return int(sl_idx) - i
    return horizon


def label_quality_report(labels: pd.DataFrame) -> dict:
    n = len(labels)
    counts = labels["label"].value_counts(normalize=True).to_dict()
    holding = labels["holding_bars"]
    # Mean uniqueness - proportion of non-overlapping co-events
    # Approximation: 1 / mean(holding) over horizon
    horizon = labels["holding_bars"].max()
    uniqueness = 1.0 / (holding.mean() if holding.mean() > 0 else 1)
    return {
        "n_labeled": n,
        "class_balance": {str(k): round(v, 4) for k, v in counts.items()},
        "holding_bars_p25": int(holding.quantile(0.25)),
        "holding_bars_p50": int(holding.median()),
        "holding_bars_p75": int(holding.quantile(0.75)),
        "holding_bars_p95": int(holding.quantile(0.95)),
        "horizon": int(horizon),
        "mean_uniqueness_approx": round(float(uniqueness), 3),
    }


def render_report(symbol: str, params: dict, q: dict) -> str:
    out = [f"Label quality - {symbol} H1 - k1={params['k1']} k2={params['k2']} horizon={params['horizon']}"]
    out.append("=" * 60)
    out.append(f"Bars labeled: {q['n_labeled']:,}")
    out.append("Class balance:")
    for cls in ("1", "0", "-1"):
        v = q["class_balance"].get(cls, 0)
        out.append(f"  {cls:>3s}: {v * 100:5.1f}%")
    out.append("")
    out.append("Time-to-resolution (bars):")
    out.append(f"  median: {q['holding_bars_p50']}")
    out.append(f"  p25 / p75: {q['holding_bars_p25']} / {q['holding_bars_p75']}")
    out.append(f"  p95: {q['holding_bars_p95']} (close to horizon={q['horizon']} = consider widening N)")
    out.append("")
    out.append(f"Approx mean uniqueness: {q['mean_uniqueness_approx']}")
    out.append("Recommendation: feed sample_weight = uniqueness (per-bar) to LightGBM, OR")
    out.append("use sequential bootstrap if available, to avoid memorization on overlapping labels.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True, help="Symbol or 'all'")
    ap.add_argument("--k1", type=float, default=2.0)
    ap.add_argument("--k2", type=float, default=1.5)
    ap.add_argument("--horizon", type=int, default=24)
    ap.add_argument("--atr-window", type=int, default=14)
    ap.add_argument("--side", choices=["long", "short", "both"], default="both")
    args = ap.parse_args()

    symbols = []
    if args.symbol == "all":
        symbols = [p.stem.replace("_m5_history", "").upper() for p in DATA_DIR.glob("*_m5_history.csv")]
    else:
        symbols = [args.symbol.upper()]

    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    QUALITY_DIR.mkdir(parents=True, exist_ok=True)

    for sym in symbols:
        try:
            h1 = load_h1(sym)
        except SystemExit as e:
            print(f"Skipping {sym}: {e}")
            continue
        labels = label_triple_barrier(h1, args.k1, args.k2, args.horizon, args.atr_window, args.side)
        q = label_quality_report(labels)

        # Class-balance gate
        balance_min = min(q["class_balance"].get(c, 0) for c in ("1", "0", "-1"))
        if balance_min < MIN_CLASS_FRAC:
            print(f"REFUSE-WRITE for {sym}: minority class {balance_min * 100:.1f}% < {MIN_CLASS_FRAC * 100:.0f}% - re-tune k1/k2/horizon.")
            continue

        out_path = LABELS_DIR / f"{sym}_tb_h{args.horizon}_k{args.k1}_{args.k2}.parquet"
        labels.to_parquet(out_path, index=False)
        print(render_report(sym, vars(args), q))
        print(f"WROTE: {out_path}\n")

        qpath = QUALITY_DIR / f"{sym}_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.json"
        qpath.write_text(json.dumps({"symbol": sym, "params": vars(args), "quality": q}, indent=2))


if __name__ == "__main__":
    main()
