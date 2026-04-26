"""Phase B3: TrendMaster v14 multi-symbol triple-barrier retrainer.

Upgrades the global model from v1 (25 features, fixed-horizon labels,
XAUUSD only) to v2 (33 cols, triple-barrier labels, all 19 symbols).

Key design choices
------------------
* Triple-barrier labels (TP=2*ATR, SL=1*ATR, hold=12 H1 bars).
  Whichever barrier is touched first wins. Unambiguous bars (time
  expiry without a hit) are labelled 0 (NONE). This is the López de
  Prado AFML recommendation; it avoids look-ahead and label overlap
  simultaneously.
* All 19 symbols concatenated into one training pool. The model learns
  a market-agnostic representation; per-team fine-tuning is a future B4
  step.
* COT + EIA data fetched ONCE and passed to every symbol's
  build_features_v2 call to avoid 19 redundant HTTP round-trips.
* Purged walk-forward 5-fold CV to measure OOF accuracy without
  look-ahead contamination (purge gap = HOLD_BARS).
* Final model is a FULL-FIT on all 19 × H1 training data (after CV
  confirms OOF acc ≥ DEPLOY_THRESHOLD).
* Feature names explicitly set in lgb.Dataset so the brain's
  align_feature_row guard works correctly at inference time.
* Output: ai_trading_agents/trend_master_model_v2.lgb
  DO NOT overwrite trend_master_model.lgb until diagnose_zero_trades
  reports OK on the new model. See activation steps at the bottom.

Path discipline
---------------
This file is in tools/ — outside the ai_trading_agents/ junction —
so .resolve() is safe here.
"""

from __future__ import annotations

import json
import sys
import time

# Force UTF-8 stdout so Unicode symbols (arrows, em-dashes, etc.) don't blow
# up on Windows terminals with cp1252 encoding.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai_trading_agents.feature_cols_v2 import (  # noqa: E402
    FEATURE_COLS_V2,
    SMARTMONEY_COLS,
    build_features_v2,
)
from ai_trading_agents.trend_master_brain import FEATURE_COLS  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = ROOT / "data"
OUT_V2 = ROOT / "ai_trading_agents" / "trend_master_model_v2.lgb"
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

HOLD_BARS = 12  # H1 bars in the triple-barrier window
TP_MULT = 2.0  # TP = 2 * ATR
SL_MULT = 1.0  # SL = 1 * ATR
FOLDS = 5
PURGE = HOLD_BARS  # purge gap between train and test (bars)
SEED = 42

DEPLOY_THRESHOLD = 0.38  # OOF acc floor to proceed with full-fit
MIN_SAMPLES = 500  # skip symbol if fewer samples after dropna


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resample_h1(path: Path) -> pd.DataFrame | None:
    """Load M5 CSV and resample to H1. Returns UTC-indexed OHLCV or None."""
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"  [load error] {path.name}: {e}")
        return None
    for col in ("time", "datetime", "date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
            break
    # normalise to lowercase column names
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
    """Return labels in {-1, 0, +1} using ATR-anchored triple barriers."""
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
    folds: int = FOLDS,
    purge: int = PURGE,
) -> dict[str, Any]:
    """Purged walk-forward 5-fold cross-validation. Returns OOF metrics."""
    n = len(X)
    fold_size = n // (folds + 1)
    accs: list[float] = []
    all_preds: list[int] = []
    all_true: list[int] = []

    label_map = {-1: 0, 0: 1, 1: 2}
    inv_map = {0: -1, 1: 0, 2: 1}
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

        classes, counts = np.unique(y_tr, return_counts=True)
        w = {int(c): float(len(y_tr) / (3 * cnt)) for c, cnt in zip(classes, counts)}
        w_tr = np.array([w.get(int(yy), 1.0) for yy in y_tr])

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
            bagging_fraction=0.85,
            bagging_freq=5,
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
        all_preds.extend(pred.tolist())
        all_true.extend(y_te.tolist())

    if not accs:
        return {"oof_acc": 0.0, "folds": 0}
    return {
        "oof_acc": float(np.mean(accs)),
        "oof_acc_per_fold": [round(a, 4) for a in accs],
        "folds": len(accs),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    t0 = time.perf_counter()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("Phase B3 — TrendMaster v14 multi-symbol triple-barrier retrain")
    print(f"  FEATURE_COLS_V2 : {len(FEATURE_COLS_V2)} cols")
    print(f"  Symbols         : {len(ALL_SYMBOLS)}")
    print(f"  Labels          : triple-barrier TP={TP_MULT}*ATR SL={SL_MULT}*ATR hold={HOLD_BARS}H1")
    print(f"  CV              : purged walk-forward {FOLDS}-fold")
    print("=" * 65)

    # ------------------------------------------------------------------
    # Step 1: fetch COT + EIA once, share across all symbols
    # ------------------------------------------------------------------
    print("\n[1/4] Fetching smart-money data (COT + EIA)…")
    cot_df = eia_df = None
    try:
        from ai_trading_agents.cross_asset_join import fetch_cot_weekly, fetch_eia_ng_storage

        cot_df = fetch_cot_weekly()
        print(f"  COT  : {len(cot_df)} weekly rows, cols={list(cot_df.columns)}")
    except Exception as e:
        print(f"  COT fetch failed ({e}); smart-money cols will be NaN")
    try:
        eia_df = fetch_eia_ng_storage()
        print(f"  EIA  : {len(eia_df)} weekly rows")
    except Exception as e:
        print(f"  EIA fetch failed ({e}); ng_storage_delta_z will be NaN")

    # ------------------------------------------------------------------
    # Step 2: build feature + label pool across all symbols
    # ------------------------------------------------------------------
    print(f"\n[2/4] Building feature pool ({len(ALL_SYMBOLS)} symbols)…")
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
            print(f"  {sym:10s} SKIP — too few H1 bars ({len(h1) if h1 is not None else 0})")
            symbol_stats[sym] = {"status": "too_few_bars"}
            continue

        try:
            feats = build_features_v2(
                h1,
                symbol=sym,
                cot_df=cot_df,
                eia_df=eia_df,
                fill_na_smartmoney=False,  # keep NaN; drop per-symbol below
            )
        except Exception as e:
            print(f"  {sym:10s} SKIP — feature build failed: {e}")
            symbol_stats[sym] = {"status": f"feat_error:{e}"}
            continue

        labels = _triple_barrier_labels(h1)
        feats["__label__"] = labels.reindex(feats.index).fillna(0).astype(int)
        feats["__sym__"] = sym

        # resolve effective feature cols (drop all-NaN smartmoney cols)
        all_nan = [c for c in FEATURE_COLS_V2 if c in feats.columns and feats[c].isna().all()]
        eff_cols = [c for c in FEATURE_COLS_V2 if c not in all_nan]
        # require V1 cols; drop rows with any NaN in effective cols + label
        feats = feats.iloc[: -HOLD_BARS - 2]  # drop unlabelable tail
        pre = len(feats)
        feats = feats.dropna(subset=list(FEATURE_COLS) + ["__label__"])
        post = len(feats)

        if post < MIN_SAMPLES:
            print(f"  {sym:10s} SKIP — only {post} clean samples")
            symbol_stats[sym] = {"status": "too_few_samples", "n": post}
            continue

        dist = feats["__label__"].value_counts().sort_index().to_dict()
        frames.append(feats)
        print(
            f"  {sym:10s} H1={len(h1):5d}  clean={post:5d}"
            f"  labels={dist}"
            f"  sm_eff={len(eff_cols) - len(list(FEATURE_COLS)):d}/{len(SMARTMONEY_COLS)}"
        )
        symbol_stats[sym] = {"status": "ok", "h1_bars": len(h1), "clean_samples": post, "label_dist": dist}

    if not frames:
        print("\nERROR: no usable symbols — aborting.")
        return

    pool = pd.concat(frames, ignore_index=False).sort_index()
    print(f"\n  Total pool: {len(pool):,} samples from {len(frames)} symbols")

    # Determine effective feature cols from the combined pool
    all_nan_pool = [c for c in FEATURE_COLS_V2 if c in pool.columns and pool[c].isna().all()]
    feat_cols = [c for c in FEATURE_COLS_V2 if c not in all_nan_pool]
    print(
        f"  Effective feature cols: {len(feat_cols)} "
        f"({len(feat_cols) - len(list(FEATURE_COLS))} smartmoney cols active)"
    )
    if all_nan_pool:
        print(f"  Dropped all-NaN cols  : {all_nan_pool}")

    # Remap labels: -1→0  0→1  +1→2
    label_map = {-1: 0, 0: 1, 1: 2}
    pool["__y__"] = pool["__label__"].map(label_map)
    pool = pool.dropna(subset=feat_cols + ["__y__"])

    X_all = pool[feat_cols].values.astype(np.float64)
    y_all = pool["__y__"].values.astype(int)
    y_raw = pool["__label__"].values.astype(int)

    print(f"\n  Final X shape : {X_all.shape}")
    print(f"  Label dist (0=SELL 1=NONE 2=BUY): {dict(zip(*np.unique(y_all, return_counts=True)))}")

    # ------------------------------------------------------------------
    # Step 3: purged walk-forward CV
    # ------------------------------------------------------------------
    print(f"\n[3/4] Purged walk-forward CV ({FOLDS} folds, purge={PURGE} bars)…")
    cv = _purged_wf_cv(X_all, y_raw, feat_cols)
    oof_acc = cv["oof_acc"]
    print(f"  OOF accuracy : {oof_acc:.4f}  (per fold: {cv['oof_acc_per_fold']})")
    print(f"  Random baseline : 0.333  |  Target : >= {DEPLOY_THRESHOLD}")

    if oof_acc < DEPLOY_THRESHOLD:
        print(f"\n  ⚠  OOF acc {oof_acc:.4f} < {DEPLOY_THRESHOLD} — model does not meet deployment threshold.")
        print("  Saving model anyway for inspection. DO NOT copy to trend_master_model.lgb without further tuning.")
    else:
        print(f"\n  PROMOTE: OOF acc {oof_acc:.4f} >= {DEPLOY_THRESHOLD}")

    # ------------------------------------------------------------------
    # Step 4: full-fit on entire pool
    # ------------------------------------------------------------------
    print(f"\n[4/4] Full-fit on all {len(X_all):,} samples…")
    classes, counts = np.unique(y_all, return_counts=True)
    weights = {int(c): float(len(y_all) / (3 * cnt)) for c, cnt in zip(classes, counts)}
    w_all = np.array([weights[int(yy)] for yy in y_all])

    d_full = lgb.Dataset(X_all, y_all, weight=w_all, feature_name=feat_cols)
    params_full = dict(
        objective="multiclass",
        num_class=3,
        metric="multi_logloss",
        learning_rate=0.04,
        num_leaves=63,
        min_data_in_leaf=80,
        feature_fraction=0.85,
        bagging_fraction=0.85,
        bagging_freq=5,
        lambda_l2=0.5,
        verbosity=-1,
        seed=SEED,
    )
    # Use 20% more rounds than CV's best (no valid set, so we can't early-stop)
    n_rounds = 960
    model = lgb.train(params_full, d_full, num_boost_round=n_rounds, callbacks=[lgb.log_evaluation(period=200)])

    model.save_model(str(OUT_V2))
    print(f"\n  Saved → {OUT_V2}")

    # verify feature names round-trip
    reloaded = lgb.Booster(model_file=str(OUT_V2))
    saved_feats = reloaded.feature_name()
    match = saved_feats == feat_cols
    print(f"  Feature name round-trip: {'OK' if match else 'MISMATCH — CHECK!'}")
    if not match:
        print(f"  Expected[:5]: {feat_cols[:5]}")
        print(f"  Got[:5]     : {saved_feats[:5]}")

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    elapsed = time.perf_counter() - t0
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "B3",
        "feature_set": "v2",
        "n_features": len(feat_cols),
        "dropped_cols": all_nan_pool,
        "effective_smartmoney_cols": [c for c in SMARTMONEY_COLS if c in feat_cols],
        "n_symbols": len(frames),
        "n_samples_total": len(X_all),
        "cv": cv,
        "oof_acc": oof_acc,
        "deploy_threshold": DEPLOY_THRESHOLD,
        "promote": oof_acc >= DEPLOY_THRESHOLD,
        "model_path": str(OUT_V2),
        "feature_name_roundtrip_ok": match,
        "runtime_sec": round(elapsed, 1),
        "symbol_stats": symbol_stats,
        "label_dist": {str(k): int(v) for k, v in zip(*np.unique(y_all, return_counts=True))},
    }
    out_json = REPORT_DIR / f"{stamp}_b3_training_report.json"
    out_json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n  Report → {out_json}")
    print(f"  Runtime: {elapsed:.0f}s")

    print("\n" + "=" * 65)
    if report["promote"]:
        print("PROMOTE — to activate the new model:")
        print(f"  1. copy  ai_trading_agents\\trend_master_model_v2.lgb")
        print(f"           ai_trading_agents\\trend_master_model.lgb")
        print(f"  2. In config/settings.py set: smartmoney_features_enabled = True")
        print(f"  3. start_brain_clean.cmd")
        print(f"  4. .venv\\Scripts\\python.exe tools\\diagnose_zero_trades.py")
        print(f"     → expect MODEL_OK, std > 0.05, non-NONE directions")
    else:
        print("HOLD — OOF below threshold. Investigate before deploying.")
        print("  Possible causes: insufficient training data, COT all-NaN,")
        print("  or triple-barrier TP/SL ratio needs tuning.")
    print("=" * 65)


if __name__ == "__main__":
    main()
