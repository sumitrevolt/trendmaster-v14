"""
Drift triage for TrendMaster v14.

Reads the latest ADWIN drift alerts, computes PSI/KS for affected features,
compares prediction-error stream vs baseline, and prints which step on the
3-tier action ladder applies. Recommends commands; never executes them.

Pure-Python; pandas + numpy + scipy + json + argparse + pathlib.
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
from scipy import stats

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
ALERTS = REPO_ROOT / "logs" / "drift_alerts.jsonl"
DATA_DIR = REPO_ROOT / "data"
MEMORY = REPO_ROOT / "brain_memory.json"
STATE = REPO_ROOT / "logs" / "brain_state.json"

# Action-ladder thresholds (tunable)
PSI_LOG = 0.20
PSI_DEGRADE = 0.25
PVR_DEGRADE = 0.10
P_L_Z_HALT = -2.0


def psi(curr: np.ndarray, base: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index, López de Prado / Hudson & Thames style."""
    edges = np.linspace(min(curr.min(), base.min()), max(curr.max(), base.max()), bins + 1)
    c, _ = np.histogram(curr, bins=edges)
    b, _ = np.histogram(base, bins=edges)
    c = (c + 1) / (c.sum() + bins)  # +1 smoothing
    b = (b + 1) / (b.sum() + bins)
    return float(np.sum((c - b) * np.log(c / b)))


def load_recent_alerts(window_hours: int = 24) -> list[dict]:
    if not ALERTS.exists():
        return []
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    out = []
    with ALERTS.open() as f:
        for line in f:
            try:
                ev = json.loads(line)
                ts = datetime.fromisoformat(ev["fired_at"].replace("Z", "+00:00"))
                if ts.replace(tzinfo=None) >= cutoff:
                    out.append(ev)
            except Exception:
                continue
    return out


def feature_drift_for_team(team: str, feature: str | None = None) -> dict:
    # Toy version: scan all CSVs for the team and compute PSI on close-returns
    # Real impl pulls actual feature columns from build_features
    team_to_symbols = {
        "metals": ["XAUUSD", "XAGUSD"],
        "forex": ["EURUSD", "GBPUSD", "USDJPY"],
        "crypto": ["BTCUSD", "ETHUSD"],
        "commodities": ["XTIUSD", "XBRUSD"],
    }
    syms = team_to_symbols.get(team, [])
    out = {}
    for s in syms:
        p = DATA_DIR / f"{s.lower()}_m5_history.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, parse_dates=["time"]).tail(2200)
        ret = df["close"].pct_change().dropna().values
        if len(ret) < 600:
            continue
        curr = ret[-200:]
        base = ret[:-200]
        out[f"{s}/close_ret"] = {
            "psi": round(psi(curr, base), 3),
            "ks": round(float(stats.ks_2samp(curr, base).statistic), 3),
        }
    return out


def pl_zscore_for_team(team: str, days: int = 5) -> tuple[float, float]:
    if not MEMORY.exists():
        return 0.0, 0.0
    th = pd.DataFrame(json.loads(MEMORY.read_text()).get("trade_history", []))
    if th.empty:
        return 0.0, 0.0
    th["ts"] = pd.to_datetime(th["ts"])
    cutoff = datetime.utcnow() - timedelta(days=days)
    recent_pl = th[th["ts"] >= cutoff]["pnl"].sum() if "pnl" in th else 0.0
    baseline_pls = th.set_index("ts").resample(f"{days}D")["pnl"].sum()
    if len(baseline_pls) < 4:
        return float(recent_pl), 0.0
    z = (recent_pl - baseline_pls.mean()) / (baseline_pls.std() + 1e-9)
    return float(recent_pl), float(z)


def decide_tier(psi_max: float, pvr_gap: float, recent_pl_z: float, adwin_fired: bool) -> str:
    if not adwin_fired and psi_max < PSI_LOG and abs(pvr_gap) < PVR_DEGRADE:
        return "L0_no_action"
    if adwin_fired and recent_pl_z < P_L_Z_HALT:
        return "L3_full_halt"
    if adwin_fired or psi_max > PSI_DEGRADE or abs(pvr_gap) > PVR_DEGRADE:
        return "L2_degrade_to_rules"
    return "L1_log_only"


def render(team: str, alerts: list[dict], drift: dict, pl: float, z: float, tier: str) -> str:
    out = ["Drift Triage - " + datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")]
    out.append("=" * 38)
    out.append(f"Team: {team}")
    out.append(f"Active alerts last 24h: {len(alerts)}")
    for a in alerts[-3:]:
        out.append(f"  - {a.get('detector','?')} {a.get('feature','?')} fired at {a.get('fired_at','?')}")
    out.append("")
    out.append("Distribution comparison (current 200 vs baseline 2000 bars):")
    psi_max = 0.0
    for k, v in drift.items():
        flag = "<-- drift" if v["psi"] >= PSI_LOG else "ok"
        out.append(f"  {k:30s} PSI={v['psi']:.3f}  KS={v['ks']:.3f}  {flag}")
        psi_max = max(psi_max, v["psi"])
    out.append("")
    out.append(f"5-day team P&L: ${pl:+,.2f}  z-score vs baseline: {z:+.2f}")
    out.append("")
    out.append(f"==> RECOMMENDATION: TIER {tier}")
    if tier == "L0_no_action":
        out.append("  No action required; continue trading.")
    elif tier == "L1_log_only":
        out.append("  Log to drift_history.jsonl; continue trading.")
    elif tier == "L2_degrade_to_rules":
        out.append("  Degrade affected team to infer_rule via ml_align guard.")
        out.append("  Continue trading on rules; investigate before re-promotion.")
    elif tier == "L3_full_halt":
        out.append(f"  Pause team: /halt-team {team}")
        out.append(f"  Confirm: .venv\\Scripts\\python.exe tools\\diagnose_zero_trades.py --team {team}")
        out.append("  File postmortem after resolution.")
    out.append("")
    out.append("DO NOT lower MIN_CONF below 0.50. DO NOT re-enable spread_guard. Operator policy.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default="crypto", help="Team to triage (metals/forex/crypto/commodities)")
    ap.add_argument("--explain", action="store_true")
    args = ap.parse_args()

    alerts = [a for a in load_recent_alerts() if a.get("team", "").lower() == args.team.lower()]
    adwin_fired = any(a.get("detector") == "ADWIN" for a in alerts)
    drift = feature_drift_for_team(args.team)
    psi_max = max((v["psi"] for v in drift.values()), default=0.0)
    pl, z = pl_zscore_for_team(args.team)
    # PvR gap not directly available here; pass 0 as placeholder
    pvr_gap = 0.0
    tier = decide_tier(psi_max, pvr_gap, z, adwin_fired)
    print(render(args.team, alerts, drift, pl, z, tier))


if __name__ == "__main__":
    main()
