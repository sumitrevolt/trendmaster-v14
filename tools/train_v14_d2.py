"""Phase D2/D3: TrendMaster v14 retrainer with frac-diff + Hurst + macro features.

Extends the Phase B3 trainer to FEATURE_COLS_V3 = V2 (33) + D2 (4) +
D3 macro (3) = 40 cols. Same triple-barrier labels, same purged
walk-forward 5-fold CV, same sequential-bootstrap uniqueness weights.

Output is a CANDIDATE model at
``ai_trading_agents/trend_master_model_v3_d2.lgb`` — does NOT touch
the live ``trend_master_model.lgb`` file. Operator must explicitly
copy it after reviewing the OOF report.

Usage
-----
    .venv\\Scripts\\python.exe tools\\train_v14_d2.py

Comparison vs B3 baseline
-------------------------
B3 OOF acc on V2 (33 cols, 19 symbols, sequential-bootstrap, 78k
samples) = 0.3857. The D2 deploy threshold is bumped from 0.38 to
0.39 — a 1pp improvement is the minimum we'd need to justify the
extra feature complexity. Below threshold the trainer still saves
the model file for inspection but flags HOLD, not PROMOTE.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

# Force UTF-8 stdout so Unicode symbols don't blow up on cp1252 terminals.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.sample_weights import avg_uniqueness  # noqa: E402

from ai_trading_agents.feature_cols_v2 import SMARTMONEY_COLS  # noqa: E402
from ai_trading_agents.feature_cols_v3 import (  # noqa: E402
    FEATURE_COLS_V3,
    MACRO_COLS_V3,
    build_features_v3,
)
from ai_trading_agents.feature_eng_d2 import D2_FEATURE_COLS  # noqa: E402
from ai_trading_agents.trend_master_brain import FEATURE_COLS  # noqa: E402

DATA_DIR = ROOT / "data"
OUT_V3 = ROOT / "ai_trading_agents" / "trend_master_model_v3_d2.lgb"
REPORT_DIR = ROOT / "reports" / "training"

ALL_SYMBOLS = [
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
    "AUDJPY",
    "CADJPY",
    "EURGBP",
    "BTCUSD",
    "ETHUSD",
    "XTIUSD",
    "XBRUSD",
    "XNGUSD",
]

HOLD_BARS = 12
TP_MULT = 2.0
SL_MULT = 1.0
FOLDS = 5
PURGE = HOLD_BARS
SEED = 42

# Bumped from B3's 0.38 — D2 needs to BEAT V2 baseline to justify the
# feature complexity, not just match it.
DEPLOY_THRESHOLD = 0.39
B3_BASELINE = 0.3857  # for the report's delta-vs-baseline column
MIN_SAMPLES = 500


def _resample_h1(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"  [load error] {path.name}: {e}")
        return None
    df = df.rename(columns=str.lower)
    if "time" in df.columns:
        df = df.set_index(pd.to_datetime(df["time"], utc=True, errors="coerce"))
        df = df.drop(columns=["time"])
    elif not isinstance(df.index, pd.DatetimeIndex):
        for c in ("datetime", "date"):
            if c in df.columns:
                df = df.set_index(pd.to_datetime(df[c], utc=True, errors="coerce"))
                df = df.drop(columns=[c])
                break
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.sort_index()
    h1 = (
        df.resample("60min")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    return h1


def _triple_barrier_labels(df_h1: pd.DataFrame) -> pd.Series:
    h, l, c = df_h1["high"], df_h1["low"], df_h1["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    out = pd.Series(0, index=df_h1.index, dtype=int)
    closes = c.values
    highs = h.values
    lows = l.values
    a = atr.values
    n = len(df_h1)
    for i in range(n - HOLD_BARS - 1):
        if not np.isfinite(a[i]) or a[i] <= 0:
            continue
        entry = closes[i]
        tp_l, sl_l = entry + TP_MULT * a[i], entry - SL_MULT * a[i]
        tp_s, sl_s = entry - TP_MULT * a[i], entry + SL_MULT * a[i]
        long_hit = short_hit = 0
        for j in range(i + 1, i + 1 + HOLD_BARS):
            hi, lo = highs[j], lows[j]
            if not long_hit:
                if lo <= sl_l:
                    long_hit = -1
                elif hi >= tp_l:
                    long_hit = +1
            if not short_hit:
                if hi >= sl_s:
                    short_hit = -1
                elif lo <= tp_s:
                    short_hit = +1
            if long_hit and short_hit:
                break
        if long_hit == +1 and short_hit != +1:
            out.iloc[i] = +1
        elif short_hit == +1 and long_hit != +1:
            out.iloc[i] = -1
    return out


def _purged_wf_cv(
    X: np.ndarray,
    y: np.ndarray,
    feat_names: list[str],
    sample_weights: np.ndarray,
    folds: int = FOLDS,
    purge: int = PURGE,
) -> dict[str, Any]:
    n = len(X)
    fold_size = n // (folds + 1)
    accs: list[float] = []

    label_map = {-1: 0, 0: 1, 1: 2}
    y_enc = np.array([label_map[int(v)] for v in y], dtype=int)

    for k in range(folds):
        train_end = fold_size * (k + 1)
        test_start = train_end + purge
        test_end = test_start + fold_size
        if test_end > n:
            break
        X_tr, y_tr = X[:train_end], y_enc[:train_end]
        X_te, y_te = X[test_start:test_end], y_enc[test_start:test_end]
        if len(np.unique(y_tr)) < 2:
            continue

        w_tr = sample_weights[:train_end]
        d_tr = lgb.Dataset(X_tr, y_tr, weight=w_tr, feature_name=feat_names)
        d_va = lgb.Dataset(X_te, y_te, reference=d_tr, feature_name=feat_names)
        params = dict(
            objective="multiclass",
            num_class=3,
            metric="multi_logloss",
            learning_rate=0.05,
            num_leaves=63,
            min_data_in_leaf=80,
            feature_fraction=0.85,
            lambda_l2=0.5,
            verbosity=-1,
            seed=SEED,
        )
        m = lgb.train(
            params,
            d_tr,
            num_boost_round=800,
            valid_sets=[d_va],
            callbacks=[lgb.early_stopping(40, verbose=False), lgb.log_evaluation(period=-1)],
        )
        pred = m.predict(X_te).argmax(axis=1)
        accs.append(float((pred == y_te).mean()))

    if not accs:
        return {"oof_acc": 0.0, "folds": 0}
    return {
        "oof_acc": float(np.mean(accs)),
        "oof_acc_per_fold": [round(a, 4) for a in accs],
        "folds": len(accs),
    }


def main() -> None:
    t0 = time.perf_counter()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Phase D2/D3 — TrendMaster v14 retrain with frac-diff + Hurst + macro")
    print(f"  FEATURE_COLS_V3 : {len(FEATURE_COLS_V3)} cols")
    print(f"      V1 (rule)   : {len(list(FEATURE_COLS))}")
    print(f"      smartmoney  : {len(SMARTMONEY_COLS)}")
    print(f"      D2 frac+H   : {len(D2_FEATURE_COLS)}")
    print(f"      D3 macro    : {len(MACRO_COLS_V3)}")
    print(f"  Symbols         : {len(ALL_SYMBOLS)}")
    print(f"  Labels          : triple-barrier TP={TP_MULT}*ATR SL={SL_MULT}*ATR hold={HOLD_BARS}H1")
    print(f"  CV              : purged walk-forward {FOLDS}-fold")
    print(f"  Deploy floor    : {DEPLOY_THRESHOLD} (B3 baseline {B3_BASELINE})")
    print("=" * 70)

    # Step 1: fetch COT + EIA + macro once
    print("\n[1/4] Fetching cross-asset data (COT + EIA + macro)…")
    cot_df = eia_df = macro_df = None
    try:
        from ai_trading_agents.cross_asset_join import (
            fetch_cot_weekly,
            fetch_eia_ng_storage,
            fetch_macro_h1,
        )

        cot_df = fetch_cot_weekly()
        print(f"  COT  : {len(cot_df)} weekly rows")
    except Exception as e:
        print(f"  COT fetch failed ({e}); cols will be NaN")
    try:
        eia_df = fetch_eia_ng_storage()
        print(f"  EIA  : {len(eia_df)} weekly rows")
    except Exception as e:
        print(f"  EIA fetch failed ({e}); cols will be NaN")
    try:
        macro_df = fetch_macro_h1()
        print(f"  macro: {len(macro_df)} daily rows, cols={list(macro_df.columns)}")
    except Exception as e:
        print(f"  macro fetch failed ({e}); cols will be NaN")

    # Step 2: build feature + label pool
    print(f"\n[2/4] Building V3 feature pool ({len(ALL_SYMBOLS)} symbols)…")
    frames: list[pd.DataFrame] = []
    symbol_stats: dict[str, Any] = {}

    for sym in ALL_SYMBOLS:
        csv = DATA_DIR / f"{sym.lower()}_m5_history.csv"
        if not csv.exists():
            print(f"  {sym:10s} SKIP — CSV missing")
            symbol_stats[sym] = {"status": "csv_missing"}
            continue

        h1 = _resample_h1(csv)
        if h1 is None or len(h1) < 200:
            print(f"  {sym:10s} SKIP — too few H1 bars")
            symbol_stats[sym] = {"status": "too_few_bars"}
            continue

        try:
            feats = build_features_v3(
                h1,
                symbol=sym,
                cot_df=cot_df,
                eia_df=eia_df,
                macro_df=macro_df,
                fill_na_smartmoney=False,
                fill_na_macro=False,
            )
        except Exception as e:
            print(f"  {sym:10s} SKIP — feature build failed: {e}")
            symbol_stats[sym] = {"status": f"feat_error:{e}"}
            continue

        labels = _triple_barrier_labels(h1)
        feats["__label__"] = labels.reindex(feats.index).fillna(0).astype(int)
        feats["__sym__"] = sym
        feats = feats.iloc[: -HOLD_BARS - 2]
        feats = feats.dropna(subset=list(FEATURE_COLS) + ["__label__"])

        if len(feats) < MIN_SAMPLES:
            print(f"  {sym:10s} SKIP — only {len(feats)} clean samples")
            symbol_stats[sym] = {"status": "too_few_samples", "n": len(feats)}
            continue

        feats["__uniq__"] = avg_uniqueness(len(feats), HOLD_BARS)

        # Per-symbol effective col count for diagnostics
        smarts_active = sum(1 for c in SMARTMONEY_COLS if c in feats.columns and not feats[c].isna().all())
        d2_active = sum(1 for c in D2_FEATURE_COLS if c in feats.columns and not feats[c].isna().all())
        macro_active = sum(1 for c in MACRO_COLS_V3 if c in feats.columns and not feats[c].isna().all())

        dist = feats["__label__"].value_counts().sort_index().to_dict()
        frames.append(feats)
        print(
            f"  {sym:10s} clean={len(feats):5d}  labels={dist}"
            f"  sm={smarts_active}/{len(SMARTMONEY_COLS)}"
            f"  d2={d2_active}/{len(D2_FEATURE_COLS)}"
            f"  macro={macro_active}/{len(MACRO_COLS_V3)}"
        )
        symbol_stats[sym] = {
            "status": "ok",
            "h1_bars": len(h1),
            "clean_samples": len(feats),
            "label_dist": dist,
            "smartmoney_active": smarts_active,
            "d2_active": d2_active,
            "macro_active": macro_active,
        }

    if not frames:
        print("\nERROR: no usable symbols — aborting.")
        return

    pool = pd.concat(frames, ignore_index=False).sort_index()
    print(f"\n  Pool: {len(pool):,} samples from {len(frames)} symbols")

    # Effective feature cols from combined pool
    all_nan_pool = [c for c in FEATURE_COLS_V3 if c in pool.columns and pool[c].isna().all()]
    feat_cols = [c for c in FEATURE_COLS_V3 if c not in all_nan_pool]
    print(f"  Effective feature cols: {len(feat_cols)} (dropped {len(all_nan_pool)} all-NaN)")
    if all_nan_pool:
        print(f"  Dropped: {all_nan_pool}")

    label_map = {-1: 0, 0: 1, 1: 2}
    pool["__y__"] = pool["__label__"].map(label_map)
    pool = pool.dropna(subset=feat_cols + ["__y__"])

    X_all = pool[feat_cols].values.astype(np.float64)
    y_all = pool["__y__"].values.astype(int)
    y_raw = pool["__label__"].values.astype(int)
    uniq_all = pool["__uniq__"].values.astype(np.float64)

    print(f"\n  Final X shape: {X_all.shape}")
    print(f"  Label dist (0=SELL 1=NONE 2=BUY): {dict(zip(*np.unique(y_all, return_counts=True)))}")

    # Sequential-bootstrap × balanced class weights (same as B3 / D1)
    classes, counts = np.unique(y_all, return_counts=True)
    class_w_map = {int(c): float(len(y_all) / (3 * cnt)) for c, cnt in zip(classes, counts)}
    class_w_all = np.array([class_w_map.get(int(yy), 1.0) for yy in y_all])
    sample_w_all = uniq_all * class_w_all

    # Step 3: purged WF CV
    print(f"\n[3/4] Purged walk-forward CV ({FOLDS} folds, purge={PURGE} bars)…")
    cv = _purged_wf_cv(X_all, y_raw, feat_cols, sample_weights=sample_w_all)
    oof_acc = cv["oof_acc"]
    delta = oof_acc - B3_BASELINE
    print(f"  OOF accuracy : {oof_acc:.4f}  (per fold: {cv['oof_acc_per_fold']})")
    print(f"  vs B3 baseline ({B3_BASELINE:.4f}): Δ = {delta:+.4f}")
    print(f"  Threshold    : {DEPLOY_THRESHOLD}  →  {'PROMOTE' if oof_acc >= DEPLOY_THRESHOLD else 'HOLD'}")

    # Step 4: full-fit
    print(f"\n[4/4] Full-fit on all {len(X_all):,} samples…")
    d_full = lgb.Dataset(X_all, y_all, weight=sample_w_all, feature_name=feat_cols)
    params_full = dict(
        objective="multiclass",
        num_class=3,
        metric="multi_logloss",
        learning_rate=0.04,
        num_leaves=63,
        min_data_in_leaf=80,
        feature_fraction=0.85,
        lambda_l2=0.5,
        verbosity=-1,
        seed=SEED,
    )
    model = lgb.train(params_full, d_full, num_boost_round=960, callbacks=[lgb.log_evaluation(period=200)])

    model.save_model(str(OUT_V3))
    print(f"\n  Saved → {OUT_V3}")

    reloaded = lgb.Booster(model_file=str(OUT_V3))
    saved_feats = reloaded.feature_name()
    match = saved_feats == feat_cols
    print(f"  Feature name round-trip: {'OK' if match else 'MISMATCH'}")

    elapsed = time.perf_counter() - t0
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "D2_D3",
        "feature_set": "v3",
        "n_features": len(feat_cols),
        "dropped_cols": all_nan_pool,
        "n_symbols": len(frames),
        "n_samples_total": len(X_all),
        "cv": cv,
        "oof_acc": oof_acc,
        "b3_baseline": B3_BASELINE,
        "delta_vs_baseline": delta,
        "deploy_threshold": DEPLOY_THRESHOLD,
        "promote": oof_acc >= DEPLOY_THRESHOLD,
        "model_path": str(OUT_V3),
        "feature_name_roundtrip_ok": match,
        "runtime_sec": round(elapsed, 1),
        "symbol_stats": symbol_stats,
        "label_dist": {str(k): int(v) for k, v in zip(*np.unique(y_all, return_counts=True))},
    }
    out_json = REPORT_DIR / f"{stamp}_d2_training_report.json"
    out_json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n  Report → {out_json}")
    print(f"  Runtime: {elapsed:.0f}s")

    print("\n" + "=" * 70)
    if report["promote"]:
        print(f"PROMOTE  Δ = {delta:+.4f} vs B3 baseline.")
        print("To activate (operator decision required):")
        print(f"  1. Review {out_json}")
        print(f"  2. copy {OUT_V3.name} trend_master_model.lgb")
        print(f"  3. set smartmoney_features_enabled = True (covers v3 too)")
        print(f"  4. start_brain_clean.cmd && diagnose_zero_trades.py")
    else:
        print(f"HOLD  OOF {oof_acc:.4f} below threshold {DEPLOY_THRESHOLD}.")
        print(f"  Δ vs B3 baseline = {delta:+.4f}")
        print("  Either D2/D3 features didn't add edge OR data is too short.")
        print("  Model file saved for inspection; do NOT promote.")
    print("=" * 70)


if __name__ == "__main__":
    main()
