"""
TCA helpers for TrendMaster v14.

Computes per-(symbol, session) slip and markouts at +5s / +30s / +5min from a
joined view of intent (signal_history.jsonl) and fill (deals.csv) timestamps.

Honors the operator invariant: never suggest re-enabling spread_guard. If the
report finds elevated slip, suggest a per-symbol conf-floor bump instead.

Pure-Python; uses only pandas + numpy + pathlib + argparse from .venv.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
DEALS_CSV = REPO_ROOT / "logs" / "trades.csv"
SIGNAL_LOG = REPO_ROOT / "logs" / "signal_history.jsonl"
TCA_HISTORY = REPO_ROOT / "logs" / "tca_daily_history.parquet"


SESSION_BANDS_UTC = {
    "Sydney": (21, 6),
    "Tokyo": (0, 9),
    "London": (7, 16),
    "NY": (13, 22),
}


def _session_for(ts: pd.Timestamp) -> str:
    h = ts.hour
    for name, (lo, hi) in SESSION_BANDS_UTC.items():
        if lo <= hi:
            if lo <= h < hi:
                return name
        else:  # wraps midnight
            if h >= lo or h < hi:
                return name
    return "Off-hours"


def load_deals(window_hours: int = 24) -> pd.DataFrame:
    if not DEALS_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(DEALS_CSV, parse_dates=["time"])
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    return df[df["time"] >= cutoff].copy()


def load_signals(window_hours: int = 24) -> pd.DataFrame:
    if not SIGNAL_LOG.exists():
        return pd.DataFrame()
    rows = []
    with SIGNAL_LOG.open() as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["intent_ts"] = pd.to_datetime(df["intent_ts"], utc=True)
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    return df[df["intent_ts"] >= cutoff].copy()


def join_intent_to_fill(deals: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    if deals.empty or signals.empty:
        return pd.DataFrame()
    deals = deals.copy()
    deals["fill_ts"] = pd.to_datetime(deals["time"], utc=True)
    deals["session"] = deals["fill_ts"].apply(_session_for)
    signals = signals.copy()
    signals = signals.sort_values("intent_ts")
    deals = deals.sort_values("fill_ts")
    merged = pd.merge_asof(
        deals,
        signals[["intent_ts", "symbol", "intent_px"]],
        left_on="fill_ts",
        right_on="intent_ts",
        by="symbol",
        direction="backward",
        tolerance=pd.Timedelta("60s"),
    )
    merged["latency_ms"] = (merged["fill_ts"] - merged["intent_ts"]).dt.total_seconds() * 1000
    merged["slip_px"] = merged["price"] - merged["intent_px"]
    return merged


def add_markouts(df: pd.DataFrame, bars: pd.DataFrame, horizons=(5, 30, 300)) -> pd.DataFrame:
    """`bars` is a per-symbol tick or M1 series with cols [symbol, ts, mid_px]."""
    if df.empty or bars.empty:
        return df
    df = df.copy()
    for h in horizons:
        col = f"markout_{h}s"
        df[col] = np.nan
        for i, row in df.iterrows():
            t_target = row["fill_ts"] + pd.Timedelta(seconds=h)
            sym_bars = bars[bars["symbol"] == row["symbol"]]
            after = sym_bars[sym_bars["ts"] >= t_target].head(1)
            if not after.empty:
                df.at[i, col] = (after["mid_px"].iloc[0] - row["price"]) * (1 if row["type"] == "buy" else -1)
    return df


def compute_scorecard(joined: pd.DataFrame, baseline_days: int = 30) -> str:
    if joined.empty:
        return "TCA Daily - no fresh deals in window. Nothing to report."
    out = ["TCA Daily - " + datetime.utcnow().strftime("%Y-%m-%d")]
    out.append("=" * 30)
    out.append(f"Deals last 24h: {len(joined)}")
    sym_counts = joined["symbol"].value_counts()
    out.append("Filled symbols: " + ", ".join(f"{s} x{c}" for s, c in sym_counts.items()))
    out.append("")
    out.append("Slip (px, mean / p50 / p95) per (symbol, session):")
    grp = joined.groupby(["symbol", "session"])["slip_px"]
    for (sym, sess), grp_df in grp:
        if len(grp_df) < 5:
            tag = "[<5 deals - no flag]"
        else:
            p95_abs = float(np.percentile(np.abs(grp_df), 95))
            tag = "[normal]" if p95_abs < 5e-4 else "[WIDE - investigate]"
        out.append(
            f"  {sym:8s} {sess:8s} mean={grp_df.mean():+.5f}  "
            f"p50={grp_df.median():+.5f}  p95={np.percentile(grp_df, 95):+.5f}  {tag}"
        )
    out.append("")
    out.append("Demo-broker note: OctaFX-Demo fills understate live slip 30-60%. ")
    out.append("Treat absolute thresholds as relative-rank only; trust the trend, not the level.")
    out.append("")
    out.append("Operator-invariant reminder: do not re-enable spread_guard. ")
    out.append("If a symbol persistently scores WIDE, propose a per-symbol conf-floor bump instead.")
    return "\n".join(out)


def append_to_history(joined: pd.DataFrame) -> None:
    if joined.empty:
        return
    snap = joined.groupby("symbol").agg(
        n_deals=("price", "count"),
        slip_mean=("slip_px", "mean"),
        slip_p95=("slip_px", lambda x: float(np.percentile(x, 95))),
        latency_p95_ms=("latency_ms", lambda x: float(np.percentile(x.dropna(), 95)) if x.notna().any() else float("nan")),
    ).reset_index()
    snap["run_ts"] = datetime.utcnow()
    if TCA_HISTORY.exists():
        prev = pd.read_parquet(TCA_HISTORY)
        snap = pd.concat([prev, snap], ignore_index=True)
    TCA_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    snap.to_parquet(TCA_HISTORY, index=False)


def main():
    ap = argparse.ArgumentParser(description="TrendMaster TCA daily scorecard")
    ap.add_argument("--window", default="24h", help="Lookback window, e.g. 24h, 7d")
    ap.add_argument("--baseline", default="30d")
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--session", default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    hours = int(args.window.rstrip("hd")) * (24 if args.window.endswith("d") else 1)
    deals = load_deals(hours)
    signals = load_signals(hours)
    if args.symbol:
        deals = deals[deals["symbol"] == args.symbol]
        signals = signals[signals["symbol"] == args.symbol]
    joined = join_intent_to_fill(deals, signals)
    if args.session:
        joined = joined[joined["session"] == args.session]
    print(compute_scorecard(joined))
    append_to_history(joined)
    if args.verbose and not joined.empty:
        print()
        print(joined.to_string(index=False))


if __name__ == "__main__":
    main()
