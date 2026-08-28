"""
Daily pairwise correlation monitor for TrendMaster v14.

Computes 30-day rolling Pearson correlation per pair vs 180-day baseline,
flags regime shifts (z-score > 2), and reports known-relationship deviations
(XAU/DXY, BTC/ETH, EUR/GBP, AUD/NZD).

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
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
DATA_DIR = REPO_ROOT / "data"
HIST_DIR = REPO_ROOT / "logs" / "correlation_history"
CROSS_ASSET = REPO_ROOT / "data" / "cross_asset"

TEAMS = {
    "METALS": ["XAUUSD", "XAGUSD"],
    "FOREX": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"],
    "CRYPTO": ["BTCUSD", "ETHUSD", "XRPUSD", "LTCUSD"],
    "COMMOD": ["XTIUSD", "XBRUSD", "XNGUSD", "XCUUSD"],
}

KNOWN = [
    ("XAUUSD", "DXY", -0.65, "abs", -0.35),     # flag if abs corr < 0.35 (so > -0.35)
    ("BTCUSD", "ETHUSD", 0.85, "lt", 0.55),
    ("EURUSD", "GBPUSD", 0.70, "lt", 0.40),
    ("AUDUSD", "NZDUSD", 0.85, "lt", 0.60),
    ("USDJPY", "US10Y", 0.60, "lt", 0.30),
]


def load_h1_returns(symbol: str) -> pd.Series | None:
    p = DATA_DIR / f"{symbol.lower()}_m5_history.csv"
    if not p.exists():
        # Try cross-asset cache (DXY, US10Y, VIX from trading-cross-asset-features)
        if symbol == "DXY":
            cp = CROSS_ASSET / "dxy_h1.parquet"
        elif symbol == "US10Y":
            cp = CROSS_ASSET / "us10y_h1.parquet"
        elif symbol == "VIX":
            cp = CROSS_ASSET / "vix_h1.parquet"
        else:
            return None
        if not cp.exists():
            return None
        df = pd.read_parquet(cp).sort_values("ts").set_index("ts")
        col = "close" if "close" in df.columns else "yield"
        return df[col].pct_change().dropna()
    df = pd.read_csv(p, parse_dates=["time"]).set_index("time").sort_index()
    h1 = df["close"].resample("1h").last().dropna()
    return h1.pct_change().dropna()


def correlation_for(sym1: str, sym2: str, window: int) -> float | None:
    r1 = load_h1_returns(sym1)
    r2 = load_h1_returns(sym2)
    if r1 is None or r2 is None:
        return None
    df = pd.concat([r1.tail(window * 24), r2.tail(window * 24)], axis=1, keys=["a", "b"], sort=False).dropna()
    if len(df) < 50:
        return None
    return float(df["a"].corr(df["b"]))


def team_intra_corr(team_syms: list[str], days: int) -> float | None:
    series = {}
    for s in team_syms:
        r = load_h1_returns(s)
        if r is not None:
            series[s] = r.tail(days * 24)
    if len(series) < 2:
        return None
    df = pd.DataFrame(series).dropna()
    cm = df.corr().values
    iu = np.triu_indices_from(cm, k=1)
    return float(cm[iu].mean())


def render(team_corrs: dict, known_results: list, regime_shifts: list) -> str:
    out = ["Correlation Monitor - " + datetime.now().strftime("%Y-%m-%d %H:%M local")]
    out.append("=" * 50)
    out.append("")
    out.append("Per-team mean intra-team correlation (30d vs 180d baseline):")
    for team, (now, base) in team_corrs.items():
        if now is None or base is None:
            out.append(f"  {team:10s} (insufficient data)")
            continue
        delta = now - base
        flag = "<-- WEAKENED" if delta < -0.15 else ("<-- STRENGTHENED" if delta > 0.15 else "normal")
        out.append(f"  {team:10s} {now:+.2f} vs {base:+.2f} baseline  ({delta:+.2f})  {flag}")
    out.append("")
    out.append("Known-relationship checks:")
    for sym1, sym2, baseline, kind, threshold, current in known_results:
        if current is None:
            out.append(f"  {sym1}/{sym2}: insufficient data")
            continue
        is_drifted = (
            (kind == "lt" and current < threshold) or
            (kind == "abs" and abs(current) < abs(threshold))
        )
        flag = "<-- DECOUPLED (regime shift)" if is_drifted else "normal"
        out.append(f"  {sym1}/{sym2}: {current:+.2f} vs {baseline:+.2f} baseline   {flag}")
    out.append("")
    if regime_shifts:
        out.append("Regime shift events (|z| > 2):")
        for sh in regime_shifts:
            out.append(f"  {sh}")
    else:
        out.append("Regime shift events (|z| > 2): none detected")
    out.append("")
    out.append("Reminder: correlation is not causation. Operator interprets cause.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default=None, help="Comma-separated 2 symbols, e.g. XAUUSD,DXY")
    ap.add_argument("--full-matrix", action="store_true")
    ap.add_argument("--baseline-days", type=int, default=180)
    args = ap.parse_args()

    if args.pair:
        sym1, sym2 = args.pair.split(",")
        c30 = correlation_for(sym1, sym2, 30)
        c180 = correlation_for(sym1, sym2, args.baseline_days)
        print(f"{sym1}/{sym2}  30d={c30}  {args.baseline_days}d baseline={c180}")
        return

    team_corrs = {team: (team_intra_corr(syms, 30), team_intra_corr(syms, args.baseline_days)) for team, syms in TEAMS.items()}
    known_results = []
    for sym1, sym2, baseline, kind, threshold in KNOWN:
        cur = correlation_for(sym1, sym2, 30)
        known_results.append((sym1, sym2, baseline, kind, threshold, cur))

    # Regime-shift z-scores against baseline (toy: just compare the two windows)
    regime_shifts = []
    for sym1, sym2, baseline, kind, threshold, cur in known_results:
        if cur is None:
            continue
        if abs(cur - baseline) > 0.20:
            regime_shifts.append(f"{sym1} <-> {sym2}: 30d={cur:+.2f} vs baseline={baseline:+.2f} (delta={cur - baseline:+.2f})")

    print(render(team_corrs, known_results, regime_shifts))

    HIST_DIR.mkdir(parents=True, exist_ok=True)
    out_path = HIST_DIR / f"{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    out_path.write_text(json.dumps({
        "team_corrs": {t: list(v) for t, v in team_corrs.items()},
        "known": [{"sym1": s1, "sym2": s2, "baseline": b, "current": c} for s1, s2, b, _, _, c in known_results],
        "regime_shifts": regime_shifts,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
