"""
Six-metric model healthcheck for TrendMaster v14.

Computes per-team:
  1. conf_std_across_symbols
  2. ECE_weekly  (10-bin Expected Calibration Error on 7-day trades)
  3. prediction_entropy_mean
  4. PvR_gap_50tr
  5. feature_null_rate
  6. retrain_age_days

Pure-Python; uses pandas + numpy + lightgbm if a model file is present, but
degrades cleanly if any input is missing.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
MODELS_DIR = REPO_ROOT / "ai_trading_agents" / "ml_models"
STATE_PATH = REPO_ROOT / "logs" / "brain_state.json"
MEMORY_PATH = REPO_ROOT / "brain_memory.json"
HEALTH_DIR = REPO_ROOT / "logs" / "model_healthcheck"

TEAMS = {
    "metals": ["XAUUSD", "XAGUSD"],
    "forex": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURJPY"],
    "crypto": ["BTCUSD", "ETHUSD", "XRPUSD", "LTCUSD"],
    "commodities": ["XTIUSD", "XBRUSD", "XNGUSD", "XCUUSD", "XAUUSD"],
}

THRESHOLDS = {
    "conf_std": (0.08, 0.05),  # GREEN >, AMBER >=, else RED
    "ece":      (0.05, 0.10),  # GREEN <, AMBER <=, else RED
    "entropy_low": 0.4,
    "entropy_amber_low": 0.6,
    "entropy_amber_high": 1.0,
    "entropy_high": 1.05,
    "pvr": (0.05, 0.10),
    "null_rate": (0.01, 0.05),
    "retrain_days": (14, 28),
}


def color_two_sided(value, green_lo, amber_lo, amber_hi, red_hi):
    if green_lo <= value <= amber_hi:
        return "GREEN"
    if amber_lo <= value < green_lo or amber_hi < value <= red_hi:
        return "AMBER"
    return "RED"


def color_lt(value, green_max, amber_max):
    if value < green_max:
        return "GREEN"
    if value < amber_max:
        return "AMBER"
    return "RED"


def color_gt(value, green_min, amber_min):
    if value > green_min:
        return "GREEN"
    if value > amber_min:
        return "AMBER"
    return "RED"


def color_abs_lt(value, green_max, amber_max):
    return color_lt(abs(value), green_max, amber_max)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text())


def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return {}
    return json.loads(MEMORY_PATH.read_text())


def conf_std_for_team(state: dict, symbols: list[str]) -> tuple[float, int]:
    confs = []
    last_sig = state.get("last_signal_per_symbol", {})
    for s in symbols:
        sig = last_sig.get(s)
        if isinstance(sig, dict) and "conf" in sig:
            confs.append(float(sig["conf"]))
    if len(confs) < 2:
        return float("nan"), len(confs)
    return float(np.std(confs)), len(confs)


def entropy_for_team(state: dict, symbols: list[str]) -> tuple[float, int]:
    """3-class predicted entropy across last_signal_per_symbol."""
    ents = []
    last_sig = state.get("last_signal_per_symbol", {})
    for s in symbols:
        sig = last_sig.get(s)
        if isinstance(sig, dict) and "probs" in sig:
            probs = np.array(sig["probs"], dtype=float)
            probs = np.clip(probs, 1e-9, 1.0)
            probs = probs / probs.sum()
            ents.append(-float(np.sum(probs * np.log(probs))))
    if not ents:
        return float("nan"), 0
    return float(np.mean(ents)), len(ents)


def ece_and_pvr(memory: dict, symbols: list[str], days: int = 7, last_n: int = 50) -> tuple[float, float, int, int]:
    th = memory.get("trade_history", [])
    if not th:
        return float("nan"), float("nan"), 0, 0
    df = pd.DataFrame(th)
    if df.empty or "ts" not in df:
        return float("nan"), float("nan"), 0, 0
    df["ts"] = pd.to_datetime(df["ts"])
    df = df[df["symbol"].isin(symbols)]
    df["win"] = (df.get("pnl", pd.Series(0, index=df.index)) > 0).astype(int)
    cutoff = datetime.utcnow() - timedelta(days=days)
    weekly = df[df["ts"] >= cutoff].copy()
    weekly_n = len(weekly)
    # ECE
    ece = float("nan")
    if weekly_n >= 30 and "predicted_prob" in weekly.columns:
        bins = np.linspace(0, 1, 11)
        weekly["bin"] = np.digitize(weekly["predicted_prob"], bins) - 1
        ece_total = 0.0
        for b in range(10):
            sub = weekly[weekly["bin"] == b]
            if len(sub) == 0:
                continue
            avg_pred = sub["predicted_prob"].mean()
            avg_actual = sub["win"].mean()
            ece_total += (len(sub) / weekly_n) * abs(avg_pred - avg_actual)
        ece = float(ece_total)
    # PvR last 50
    last = df.tail(last_n)
    pvr = float("nan")
    if len(last) >= 10 and "predicted_prob" in last.columns:
        pvr = float(last["predicted_prob"].mean() - last["win"].mean())
    return ece, pvr, weekly_n, len(last)


def feature_null_rate(symbols: list[str]) -> float:
    rates = []
    for s in symbols:
        path = REPO_ROOT / "data" / f"{s.lower()}_m5_history.csv"
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path).tail(2000)
            rates.append(float(df.isna().mean().mean()))
        except Exception:
            continue
    return float(np.mean(rates)) if rates else float("nan")


def retrain_age_days(team: str) -> float:
    p = MODELS_DIR / f"{team}_model.lgb"
    if not p.exists():
        return float("nan")
    return (datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)).total_seconds() / 86400


def evaluate_team(team: str, symbols: list[str], state: dict, memory: dict) -> dict:
    conf_std, n_conf = conf_std_for_team(state, symbols)
    ent, n_ent = entropy_for_team(state, symbols)
    ece, pvr, n_week, n_last = ece_and_pvr(memory, symbols)
    nulls = feature_null_rate(symbols)
    age = retrain_age_days(team)

    flags = {
        "conf_std": color_gt(conf_std, *THRESHOLDS["conf_std"]) if not math.isnan(conf_std) else "INSUFFICIENT",
        "ece": (color_lt(ece, *THRESHOLDS["ece"]) if (not math.isnan(ece) and n_week >= 30) else "INSUFFICIENT"),
        "entropy": (color_two_sided(
            ent, THRESHOLDS["entropy_amber_low"], THRESHOLDS["entropy_low"],
            THRESHOLDS["entropy_amber_high"], THRESHOLDS["entropy_high"]
        ) if not math.isnan(ent) else "INSUFFICIENT"),
        "pvr": color_abs_lt(pvr, *THRESHOLDS["pvr"]) if (not math.isnan(pvr) and n_last >= 10) else "INSUFFICIENT",
        "null_rate": color_lt(nulls, *THRESHOLDS["null_rate"]) if not math.isnan(nulls) else "INSUFFICIENT",
        "retrain_age": color_lt(age, *THRESHOLDS["retrain_days"]) if not math.isnan(age) else "INSUFFICIENT",
    }

    if "RED" in flags.values():
        verdict = "RED"
    elif "AMBER" in flags.values():
        verdict = "AMBER"
    elif all(f in ("GREEN", "INSUFFICIENT") for f in flags.values()):
        verdict = "HEALTHY" if "GREEN" in flags.values() else "NO DATA"
    else:
        verdict = "UNKNOWN"

    return {
        "team": team,
        "metrics": {
            "conf_std": (round(conf_std, 4) if not math.isnan(conf_std) else None, flags["conf_std"], n_conf),
            "ece": (round(ece, 4) if not math.isnan(ece) else None, flags["ece"], n_week),
            "entropy": (round(ent, 3) if not math.isnan(ent) else None, flags["entropy"], n_ent),
            "pvr": (round(pvr, 4) if not math.isnan(pvr) else None, flags["pvr"], n_last),
            "null_rate": (round(nulls, 4) if not math.isnan(nulls) else None, flags["null_rate"], None),
            "retrain_age": (round(age, 1) if not math.isnan(age) else None, flags["retrain_age"], None),
        },
        "verdict": verdict,
    }


def render(results: list[dict], explain: bool) -> str:
    out = ["Model Healthcheck - " + datetime.now().strftime("%Y-%m-%d %H:%M local")]
    out.append("=" * 42)
    for r in results:
        out.append("")
        out.append(f"{r['team'].upper()} team")
        for k, (v, flag, n) in r["metrics"].items():
            extra = f"  (n={n})" if n is not None else ""
            out.append(f"  {k:25s} {str(v):<10s} {flag}{extra}")
        out.append(f"  Verdict: {r['verdict']}")
        if explain and r["verdict"] == "RED":
            out.append("    Action: degrade team to infer_rule via ml_align guard.")
            out.append("    Run tools/diagnose_zero_trades.py --team " + r["team"])
            out.append("    DO NOT lower MIN_CONF below 0.50 - operator policy.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default="all")
    ap.add_argument("--explain", action="store_true")
    args = ap.parse_args()

    state = load_state()
    memory = load_memory()
    teams = list(TEAMS.keys()) if args.team == "all" else [args.team]
    results = [evaluate_team(t, TEAMS[t], state, memory) for t in teams]

    print(render(results, args.explain))

    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    out_path = HEALTH_DIR / f"{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.json"
    out_path.write_text(json.dumps({"results": results, "ts": datetime.utcnow().isoformat()}, indent=2))


if __name__ == "__main__":
    main()
    _sys.exit(0)
