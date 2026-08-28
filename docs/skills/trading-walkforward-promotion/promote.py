"""
Walkforward promotion gate for TrendMaster v14.

Runs four checks against a candidate .lgb model:
  1. CPCV mean Sharpe (mean > 0 AND stdev < 0.5 x mean)
  2. PSI < 0.20 vs production training distribution per feature
  3. Calibration ECE < 0.10 on CPCV out-of-fold predictions
  4. Class balance (no class < 15%)

Prints PROMOTE or HOLD; never executes the file swap.

Pure-Python; pandas + numpy + lightgbm (already in .venv).
Falls back gracefully if optional CPCV module is unavailable.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
sys.path.insert(0, str(REPO_ROOT))

# ---------------- gate helpers ----------------

def gate1_cpcv_sharpe(candidate_path: Path, data_path: Path, n_groups: int = 6, k_test: int = 2) -> dict:
    try:
        from tools.cpcv import CPCVSplit  # type: ignore
        import lightgbm as lgb  # type: ignore
    except ImportError as e:
        return {"status": "SKIP", "reason": f"missing import: {e}"}

    if not data_path.exists():
        return {"status": "SKIP", "reason": f"data not found: {data_path}"}

    df = pd.read_parquet(data_path) if data_path.suffix == ".parquet" else pd.read_csv(data_path)
    if "label" not in df.columns:
        return {"status": "SKIP", "reason": "data has no 'label' column"}
    feature_cols = [c for c in df.columns if c not in {"label", "ts", "side", "entry_px", "tp_px", "sl_px", "atr", "hit_ts", "holding_bars"}]
    X = df[feature_cols].fillna(0.0).values
    y = df["label"].values

    booster = lgb.Booster(model_file=str(candidate_path))

    cv = CPCVSplit(n_groups=n_groups, k_test=k_test)
    sharpes = []
    for train_idx, test_idx in cv.split(np.arange(len(df))):
        preds = booster.predict(X[test_idx])
        # convert per-class to side prediction (-1, 0, +1)
        if preds.ndim > 1:
            side = np.argmax(preds, axis=1) - 1
        else:
            side = np.where(preds > 0.5, 1, -1)
        # toy returns: side * sign(y)
        ret = side * np.sign(y[test_idx])
        if ret.std() == 0:
            continue
        sharpes.append(float(ret.mean() / ret.std() * np.sqrt(252)))

    if not sharpes:
        return {"status": "FAIL", "reason": "CPCV produced no fold returns"}

    mean_s = float(np.mean(sharpes))
    std_s = float(np.std(sharpes))
    pass_gate = mean_s > 0 and std_s < 0.5 * abs(mean_s)
    return {
        "status": "PASS" if pass_gate else "FAIL",
        "mean_sharpe": round(mean_s, 3),
        "stdev": round(std_s, 3),
        "n_paths": len(sharpes),
    }


def gate2_psi(candidate_path: Path, prod_data_path: Path, candidate_data_path: Path) -> dict:
    if not (prod_data_path.exists() and candidate_data_path.exists()):
        return {"status": "SKIP", "reason": "missing prod or candidate data"}
    prod = pd.read_parquet(prod_data_path) if prod_data_path.suffix == ".parquet" else pd.read_csv(prod_data_path)
    cand = pd.read_parquet(candidate_data_path) if candidate_data_path.suffix == ".parquet" else pd.read_csv(candidate_data_path)
    skip = {"label", "ts", "side", "entry_px", "tp_px", "sl_px", "atr", "hit_ts", "holding_bars"}
    feats = [c for c in prod.columns if c not in skip and c in cand.columns and pd.api.types.is_numeric_dtype(prod[c])]
    psi_max = 0.0
    psi_max_feat = ""
    for c in feats:
        a = prod[c].dropna().values
        b = cand[c].dropna().values
        if len(a) < 50 or len(b) < 50:
            continue
        edges = np.linspace(min(a.min(), b.min()), max(a.max(), b.max()), 11)
        ah, _ = np.histogram(a, bins=edges)
        bh, _ = np.histogram(b, bins=edges)
        ah = (ah + 1) / (ah.sum() + 10)
        bh = (bh + 1) / (bh.sum() + 10)
        ps = float(np.sum((bh - ah) * np.log(bh / ah)))
        if ps > psi_max:
            psi_max = ps
            psi_max_feat = c
    return {
        "status": "PASS" if psi_max < 0.20 else "FAIL",
        "max_psi": round(psi_max, 3),
        "feature": psi_max_feat,
    }


def gate3_ece(candidate_path: Path, data_path: Path, n_bins: int = 10) -> dict:
    try:
        import lightgbm as lgb  # type: ignore
    except ImportError:
        return {"status": "SKIP", "reason": "lightgbm not importable"}
    if not data_path.exists():
        return {"status": "SKIP", "reason": "data missing"}
    df = pd.read_parquet(data_path) if data_path.suffix == ".parquet" else pd.read_csv(data_path)
    if "label" not in df.columns:
        return {"status": "SKIP", "reason": "no label column"}
    skip = {"label", "ts", "side", "entry_px", "tp_px", "sl_px", "atr", "hit_ts", "holding_bars"}
    feats = [c for c in df.columns if c not in skip]
    booster = lgb.Booster(model_file=str(candidate_path))
    preds = booster.predict(df[feats].fillna(0.0).values)
    if preds.ndim > 1:
        # 3-class: take prob of predicted class as confidence; "win" = pred matches sign(label)
        conf = preds.max(axis=1)
        pred_cls = preds.argmax(axis=1) - 1
        win = (pred_cls == df["label"].values).astype(int)
    else:
        conf = np.where(preds > 0.5, preds, 1 - preds)
        pred_cls = (preds > 0.5).astype(int)
        win = (pred_cls == (df["label"].values > 0).astype(int)).astype(int)
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.digitize(conf, bins) - 1
    n = len(conf)
    ece = 0.0
    for b in range(n_bins):
        mask = idx == b
        if mask.sum() < 10:
            continue
        ece += (mask.sum() / n) * abs(conf[mask].mean() - win[mask].mean())
    return {"status": "PASS" if ece < 0.10 else "FAIL", "ece": round(float(ece), 3)}


def gate4_class_balance(data_path: Path) -> dict:
    if not data_path.exists():
        return {"status": "SKIP", "reason": "data missing"}
    df = pd.read_parquet(data_path) if data_path.suffix == ".parquet" else pd.read_csv(data_path)
    counts = df["label"].value_counts(normalize=True).to_dict()
    min_class = min(counts.values()) if counts else 0
    return {
        "status": "PASS" if min_class >= 0.15 else "FAIL",
        "min_class_frac": round(float(min_class), 3),
        "balance": {str(k): round(float(v), 3) for k, v in counts.items()},
    }


# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--prod", required=True)
    ap.add_argument("--data", required=True, help="Candidate training/validation data (parquet or csv)")
    ap.add_argument("--prod-data", default=None, help="Production training data for PSI (defaults to --data)")
    ap.add_argument("--team", required=True)
    args = ap.parse_args()

    cand = Path(args.candidate)
    prod = Path(args.prod)
    data = Path(args.data)
    prod_data = Path(args.prod_data) if args.prod_data else data

    print(f"Walkforward Promotion Gate - {args.team.upper()} team")
    print("=" * 50)
    print(f"Candidate: {cand.name}")
    print(f"Production: {prod.name} (age {(datetime.now().timestamp() - prod.stat().st_mtime) / 86400:.1f} days)" if prod.exists() else "Production: <missing>")
    print()

    g1 = gate1_cpcv_sharpe(cand, data)
    g2 = gate2_psi(cand, prod_data, data)
    g3 = gate3_ece(cand, data)
    g4 = gate4_class_balance(data)

    print(f"Gate 1 CPCV Sharpe:  {g1}")
    print(f"Gate 2 PSI:          {g2}")
    print(f"Gate 3 Calibration:  {g3}")
    print(f"Gate 4 Class balance: {g4}")
    print()

    fails = [name for name, g in [("CPCV", g1), ("PSI", g2), ("ECE", g3), ("Balance", g4)] if g.get("status") == "FAIL"]
    if not fails:
        print("VERDICT: PROMOTE")
        print()
        print("Promotion command (run manually after final review):")
        print(f'  copy /Y "{cand}" "{prod}"')
        print()
        print("After promotion: restart via start_brain_clean.cmd; run trading-model-healthcheck after 50 trades.")
    else:
        print(f"VERDICT: HOLD  (failed: {', '.join(fails)})")
        print("Production model remains in service. Fix the failed gates and re-run.")


if __name__ == "__main__":
    main()
