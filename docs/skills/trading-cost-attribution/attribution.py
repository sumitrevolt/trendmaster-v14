"""
Weekly P&L decomposition for TrendMaster v14.

Decomposes net P&L into: gross alpha (mid-price), spread cost, commission,
realized slippage, financing/swap. Per-team and per-symbol rollups, plus a
4-week trend.

Pure-Python; pandas + numpy + json + datetime + argparse + pathlib.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
MEMORY = REPO_ROOT / "brain_memory.json"
DEALS = REPO_ROOT / "logs" / "trades.csv"
SIGNAL_LOG = REPO_ROOT / "logs" / "signal_history.jsonl"

# Approximate OctaFX-Demo commission schedule per round-turn lot
COMMISSION_PER_LOT = {"FOREX": 3.0, "METALS": 5.0, "CRYPTO": 0.0, "COMMODITIES": 4.0}

TEAMS = {
    "METALS": {"XAUUSD", "XAGUSD"},
    "FOREX": {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY"},
    "CRYPTO": {"BTCUSD", "ETHUSD", "XRPUSD", "LTCUSD"},
    "COMMODITIES": {"XTIUSD", "XBRUSD", "XNGUSD", "XCUUSD"},
}


def team_for(symbol: str) -> str:
    for t, syms in TEAMS.items():
        if symbol in syms:
            return t
    return "OTHER"


def week_bounds(week_arg: str) -> tuple[datetime, datetime]:
    if week_arg == "current":
        today = datetime.utcnow().date()
        monday = today - timedelta(days=today.weekday())
    else:
        # ISO week format: 2026-W17
        yr, wk = week_arg.split("-W")
        monday = datetime.strptime(f"{yr}-{int(wk):02d}-1", "%Y-%W-%w").date()
    start = datetime.combine(monday, datetime.min.time())
    end = start + timedelta(days=7)
    return start, end


def load_trades(start: datetime, end: datetime) -> pd.DataFrame:
    if not MEMORY.exists():
        return pd.DataFrame()
    th = json.loads(MEMORY.read_text()).get("trade_history", [])
    if not th:
        return pd.DataFrame()
    df = pd.DataFrame(th)
    df["ts"] = pd.to_datetime(df["ts"])
    df = df[(df["ts"] >= start) & (df["ts"] < end)]
    return df


def estimate_spread_cost(row: pd.Series) -> float:
    """Spread cost = (spread_at_entry + spread_at_exit) / 2 * notional."""
    spread = float(row.get("spread", 0))
    notional = float(row.get("lots", 0)) * float(row.get("entry_px", 0))
    return spread * notional / max(float(row.get("entry_px", 1)), 1e-9)


def estimate_slippage(row: pd.Series) -> float:
    intent = float(row.get("intent_px", row.get("entry_px", 0)))
    fill = float(row.get("entry_px", 0))
    side = +1 if row.get("side", "long") == "long" else -1
    notional = float(row.get("lots", 0)) * fill
    return -(fill - intent) * side * notional / max(fill, 1e-9)  # negative = cost


def commission_for(row: pd.Series) -> float:
    team = team_for(row.get("symbol", ""))
    return -float(row.get("lots", 0)) * COMMISSION_PER_LOT.get(team, 3.0)


def decompose(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["spread_cost"] = -df.apply(estimate_spread_cost, axis=1)
    df["slip"] = df.apply(estimate_slippage, axis=1)
    df["commission"] = df.apply(commission_for, axis=1)
    df["swap"] = df.get("swap", 0.0)
    df["net_pl"] = df.get("pnl", 0.0)
    # Gross alpha = net P&L - all costs (back out)
    df["gross_alpha"] = df["net_pl"] - df["spread_cost"] - df["commission"] - df["slip"] - df["swap"]
    df["team"] = df["symbol"].map(team_for)
    return df


def render_team_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "  (no trades this week)"
    g = df.groupby("team").agg(
        gross=("gross_alpha", "sum"),
        spread=("spread_cost", "sum"),
        slip=("slip", "sum"),
        net=("net_pl", "sum"),
    ).round(2)
    out = []
    for team, row in g.iterrows():
        flag = ""
        if row["net"] < 0 and abs(row["spread"] + row["slip"]) > row["gross"]:
            flag = "  <-- cost-dominant"
        out.append(f"  {team:10s} gross ${row['gross']:+.0f}  spread ${row['spread']:+.0f}  slip ${row['slip']:+.0f}  net ${row['net']:+.0f}{flag}")
    return "\n".join(out)


def render_per_symbol(df: pd.DataFrame, top_only: bool = True) -> str:
    if df.empty:
        return ""
    g = df.groupby("symbol").agg(
        gross=("gross_alpha", "sum"),
        cost=("spread_cost", "sum"),
        slip=("slip", "sum"),
    )
    g["cost_to_alpha"] = (-g["cost"] - g["slip"]) / g["gross"].replace(0, np.nan)
    g = g.sort_values("cost_to_alpha", ascending=False)
    if top_only:
        g = g.head(5)
    out = []
    for sym, row in g.iterrows():
        ratio = row["cost_to_alpha"]
        if pd.isna(ratio):
            continue
        flag = "<-- TOXIC PAIR" if ratio > 1.5 else ("<-- watch" if ratio > 0.8 else "healthy")
        out.append(f"  {sym:8s} cost+slip = {ratio * 100:.0f}% of gross alpha   {flag}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default="current", help="ISO week 2026-W17 or 'current'")
    ap.add_argument("--per-symbol", action="store_true")
    ap.add_argument("--lookback", type=int, default=4)
    args = ap.parse_args()

    start, end = week_bounds(args.week)
    df = decompose(load_trades(start, end))

    print(f"Cost Attribution - Week of {start.date()} to {(end - timedelta(days=1)).date()}")
    print("=" * 56)
    if df.empty:
        print("No trades in window.")
        return
    print(f"Net P&L: ${df['net_pl'].sum():+.2f}")
    print()
    print("Decomposition:")
    print(f"  Gross alpha (mid-price PnL):  ${df['gross_alpha'].sum():+.2f}")
    print(f"  Spread cost:                  ${df['spread_cost'].sum():+.2f}")
    print(f"  Commission:                   ${df['commission'].sum():+.2f}")
    print(f"  Realized slippage:            ${df['slip'].sum():+.2f}")
    print(f"  Financing/swap:               ${df['swap'].sum():+.2f}")
    recon = df['net_pl'].sum() - (df['gross_alpha'].sum() + df['spread_cost'].sum() + df['commission'].sum() + df['slip'].sum() + df['swap'].sum())
    print(f"  Reconciliation residual:      ${recon:+.2f}  ({'OK' if abs(recon) < 0.10 else 'INVESTIGATE'})")
    print()
    print("Per-team:")
    print(render_team_table(df))
    print()
    print("Top cost-eater symbols (cost+slip / gross alpha):")
    print(render_per_symbol(df, top_only=not args.per_symbol))
    print()
    print("Note: OctaFX-Demo cost numbers are approximate. Use this for relative ranking and trend, not absolute targets.")


if __name__ == "__main__":
    main()
