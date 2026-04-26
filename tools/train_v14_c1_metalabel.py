"""Phase C1: TrendMaster v14 meta-labelling head trainer.

Architecture (López de Prado AFML Ch.10)
-----------------------------------------
Primary classifier  : B3 model (3-class: SELL / NONE / BUY)
Meta-labeller       : binary act/skip (given B3 picked a direction, will it profit?)

Input to meta-model : 35 cols
  [0:3]   P_sell, P_none, P_buy  — B3 softmax probabilities
  [3:35]  V2 features (32 effective cols, same set used to train B3)

Labels (binary)
  1 = B3's chosen direction hit its TP barrier within HOLD_BARS
  0 = B3's chosen direction hit SL or timed out

Only rows where B3 predicts BUY or SELL are included in meta-training.
NONE rows are dropped because there is no "act" decision to label.

CV  : purged walk-forward 5-fold, same purge gap as B3 (HOLD_BARS)
Goal: OOF AUC >= ACT_AUC_THRESHOLD (0.55)
Out : ai_trading_agents/meta_label_model.lgb

Brain wiring
------------
After B3 gives (direction, conf):
  if direction != NONE and metalabel_enabled:
      feat_meta = [P_sell, P_none, P_buy] + V2_row   (35 cols)
      P_act = meta_model.predict(feat_meta)[0][1]
      if P_act < ACT_THRESHOLD:  direction = NONE  (skip)
      else: keep direction, confidence = conf * P_act  (product = joint prob)

Path discipline
---------------
File is in tools/ (not in junction) so .resolve() is safe.
"""

from __future__ import annotations

import json
import sys
import time

# Force UTF-8 stdout — Windows cp1252 can't handle arrows / em-dashes.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.sample_weights import avg_uniqueness  # noqa: E402  [Phase D1]
from ai_trading_agents.feature_cols_v2 import build_features_v2  # noqa: E402
from ai_trading_agents.trend_master_brain import FEATURE_COLS  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = ROOT / "data"
B3_MODEL_PATH = ROOT / "ai_trading_agents" / "trend_master_model.lgb"
OUT_META = ROOT / "ai_trading_agents" / "meta_label_model.lgb"
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

HOLD_BARS = 12  # must match B3
TP_MULT = 2.0  # must match B3
SL_MULT = 1.0  # must match B3
FOLDS = 5
PURGE = HOLD_BARS
SEED = 42

ACT_AUC_THRESHOLD = 0.55  # OOF AUC floor to deploy
ACT_THRESHOLD = 0.55  # runtime P_act gate (stored in model metadata)
MIN_SAMPLES = 200  # skip symbol if fewer act-rows after filtering


# ---------------------------------------------------------------------------
# Helpers (shared with B3 trainer)
# ---------------------------------------------------------------------------


def _resample_h1(path: Path) -> pd.DataFrame | None:
    """Load M5 CSV and resample to H1."""
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


def _triple_barrier_binary(df_h1: pd.DataFrame, b3_side: pd.Series) -> pd.Series:
    """Return binary label: 1 if B3's predicted direction hit TP, 0 otherwise.

    b3_side: Series of {-1=SELL, 0=NONE, +1=BUY} aligned to df_h1 index.
    Only non-zero b3_side rows are labelled; the rest are NaN (dropped later).
    """
    h, l, c = df_h1["high"], df_h1["low"], df_h1["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    out = pd.Series(np.nan, index=df_h1.index, dtype=float)
    closes = c.values
    highs = h.values
    lows = l.values
    a = atr.values
    sides = b3_side.reindex(df_h1.index, fill_value=0).values
    n = len(df_h1)
    for i in range(n - HOLD_BARS - 1):
        side = int(sides[i])
        if side == 0:
            continue
        if not np.isfinite(a[i]) or a[i] <= 0:
            continue
        entry = closes[i]
        if side == +1:  # BUY: TP = up, SL = down
            tp = entry + TP_MULT * a[i]
            sl = entry - SL_MULT * a[i]
            hit = 0
            for j in range(i + 1, i + 1 + HOLD_BARS):
                if lows[j] <= sl:
                    hit = 0
                    break
                if highs[j] >= tp:
                    hit = 1
                    break
        else:  # SELL: TP = down, SL = up
            tp = entry - TP_MULT * a[i]
            sl = entry + SL_MULT * a[i]
            hit = 0
            for j in range(i + 1, i + 1 + HOLD_BARS):
                if highs[j] >= sl:
                    hit = 0
                    break
                if lows[j] <= tp:
                    hit = 1
                    break
        out.iloc[i] = hit
    return out


def _purged_wf_cv_binary(
    X: np.ndarray,
    y: np.ndarray,
    feat_names: list[str],
    sample_weights: np.ndarray,  # [Phase D1] pre-computed uniqueness×class weights
    folds: int = FOLDS,
    purge: int = PURGE,
) -> dict[str, Any]:
    """Purged walk-forward CV for binary classifier. Returns OOF AUC.

    [Phase D1] sample_weights replaces per-fold class-weight computation.
    bagging_fraction disabled; uniqueness weights replace it.
    """
    n = len(X)
    fold_size = n // (folds + 1)
    aucs: list[float] = []
    all_probs: list[float] = []
    all_true: list[int] = []

    for k in range(folds):
        train_end = fold_size * (k + 1)
        test_start = train_end + purge
        test_end = test_start + fold_size
        if test_end > n:
            break
        X_tr, y_tr = X[:train_end], y[:train_end]
        X_te, y_te = X[test_start:test_end], y[test_start:test_end]
        if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
            continue

        w_tr = sample_weights[:train_end]  # [Phase D1] uniqueness×class weight slice

        d_tr = lgb.Dataset(X_tr, y_tr, weight=w_tr, feature_name=feat_names)
        d_va = lgb.Dataset(X_te, y_te, reference=d_tr, feature_name=feat_names)
        params = dict(
            objective="binary",
            metric="auc",
            learning_rate=0.05,
            num_leaves=31,
            min_data_in_leaf=60,
            feature_fraction=0.80,
            # [Phase D1] bagging_fraction removed; uniqueness weights replace it
            lambda_l2=1.0,
            verbosity=-1,
            seed=SEED,
        )
        m = lgb.train(
            params,
            d_tr,
            num_boost_round=600,
            valid_sets=[d_va],
            callbacks=[
                lgb.early_stopping(40, verbose=False),
                lgb.log_evaluation(period=-1),
            ],
        )
        prob_te = m.predict(X_te)
        auc = float(roc_auc_score(y_te, prob_te))
        aucs.append(auc)
        all_probs.extend(prob_te.tolist())
        all_true.extend(y_te.tolist())

    if not aucs:
        return {"oof_auc": 0.0, "folds": 0}

    oof_auc = float(roc_auc_score(all_true, all_probs)) if len(set(all_true)) > 1 else 0.0
    return {
        "oof_auc": oof_auc,
        "oof_auc_per_fold": [round(a, 4) for a in aucs],
        "folds": len(aucs),
        "n_act": int((np.array(all_true) == 1).sum()),
        "n_skip": int((np.array(all_true) == 0).sum()),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    t0 = time.time()
    print("=" * 65)
    print("Phase C1 -- TrendMaster v14 meta-label head trainer")
    print("  Primary model  : trend_master_model.lgb  (B3, 32 features)")
    print("  Meta features  : 3 B3 probs + 32 V2 cols = 35 total")
    print("  Meta labels    : TP-hit=1 vs SL/timeout=0 (per B3 direction)")
    print("  CV             : purged walk-forward 5-fold")
    print("=" * 65)

    # ------------------------------------------------------------------
    # Step 1: load B3 model
    # ------------------------------------------------------------------
    print("\n[1/5] Loading B3 primary model...")
    if not B3_MODEL_PATH.exists():
        print(f"  ERROR: {B3_MODEL_PATH} not found — run Phase B3 first.")
        return 1
    b3 = lgb.Booster(model_file=str(B3_MODEL_PATH))
    b3_feat_names = b3.feature_name()
    print(
        f"  B3 model: {len(b3_feat_names)} features, "
        f"mtime={datetime.fromtimestamp(B3_MODEL_PATH.stat().st_mtime, tz=timezone.utc).isoformat()}"
    )

    # ------------------------------------------------------------------
    # Step 2: fetch smart-money data (COT/EIA) once
    # ------------------------------------------------------------------
    print("\n[2/5] Fetching smart-money data (COT + EIA)...")
    try:
        from ai_trading_agents.cross_asset_join import fetch_cot_data, fetch_eia_data  # noqa: PLC0415

        cot_df = fetch_cot_data()
        print(f"  COT  : {len(cot_df)} weekly rows, cols={list(cot_df.columns)}")
    except Exception as e:
        print(f"  COT fetch failed ({e}); smart-money cols will be NaN")
        cot_df = None
    try:
        eia_df = fetch_eia_data()
        print(f"  EIA  : {len(eia_df)} rows")
    except Exception as e:
        print(f"  EIA fetch failed ({e}); ng_storage_delta_z will be NaN")
        eia_df = None

    # ------------------------------------------------------------------
    # Step 3: build meta-feature pool across all 19 symbols
    # ------------------------------------------------------------------
    print(f"\n[3/5] Building meta-feature pool ({len(ALL_SYMBOLS)} symbols)...")
    meta_rows: list[np.ndarray] = []
    meta_labels: list[int] = []
    uniq_weights: list[np.ndarray] = []  # [Phase D1]
    sym_stats: list[dict] = []

    for sym in ALL_SYMBOLS:
        csv_path = DATA_DIR / f"{sym.lower()}_m5_history.csv"
        if not csv_path.exists():
            print(f"  {sym:10s} SKIP -- CSV missing")
            continue

        h1 = _resample_h1(csv_path)
        if h1 is None or len(h1) < 200:
            print(f"  {sym:10s} SKIP -- too few H1 bars")
            continue

        # Build V2 features
        try:
            feat_df = build_features_v2(
                h1,
                symbol=sym,
                cot_df=cot_df,
                eia_df=eia_df,
                fill_na_smartmoney=True,
            )
        except Exception as e:
            print(f"  {sym:10s} SKIP -- build_features_v2 failed: {e}")
            continue

        # Align to B3's exact feature order, fill missing with 0
        aligned = feat_df.reindex(columns=b3_feat_names, fill_value=0.0)
        clean = aligned.dropna()
        if len(clean) < MIN_SAMPLES:
            print(f"  {sym:10s} SKIP -- only {len(clean)} clean rows")
            continue

        X_raw = clean.values.astype(np.float32)

        # Get B3 predictions on every row: shape (N, 3) = [P_sell, P_none, P_buy]
        b3_probs = b3.predict(X_raw)  # (N, 3)
        b3_sides_enc = b3_probs.argmax(axis=1)  # 0=SELL 1=NONE 2=BUY
        enc_to_side = {0: -1, 1: 0, 2: +1}
        b3_side_arr = np.array([enc_to_side[int(s)] for s in b3_sides_enc])
        b3_side_ser = pd.Series(b3_side_arr, index=clean.index)

        # Compute per-direction triple-barrier binary labels
        binary_labels = _triple_barrier_binary(h1, b3_side_ser)

        # Keep only rows where B3 picked BUY or SELL AND label is not NaN
        act_mask = b3_side_arr != 0
        aligned_idx = clean.index
        label_arr = binary_labels.reindex(aligned_idx).values

        combined_mask = act_mask & np.isfinite(label_arr)
        n_act = int(combined_mask.sum())
        if n_act < MIN_SAMPLES:
            print(f"  {sym:10s} SKIP -- only {n_act} act-rows after filtering")
            continue

        X_act = X_raw[combined_mask]  # (n_act, 32)
        probs_act = b3_probs[combined_mask]  # (n_act, 3)
        y_act = label_arr[combined_mask].astype(int)  # (n_act,)

        # Meta-feature: [P_sell, P_none, P_buy] + V2 raw = 35 cols
        X_meta = np.concatenate([probs_act, X_act], axis=1).astype(np.float32)

        tp_rate = float(y_act.mean())
        print(
            f"  {sym:10s} act_rows={n_act}  TP_rate={tp_rate:.1%}  "
            f"B3_buy={int((b3_side_arr[combined_mask] == +1).sum())}  "
            f"B3_sell={int((b3_side_arr[combined_mask] == -1).sum())}"
        )

        meta_rows.append(X_meta)
        meta_labels.extend(y_act.tolist())
        uniq_i = avg_uniqueness(n_act, HOLD_BARS)  # [Phase D1]
        uniq_weights.append(uniq_i)  # [Phase D1]
        sym_stats.append(
            {
                "symbol": sym,
                "n_act": n_act,
                "tp_rate": round(tp_rate, 4),
            }
        )

    if not meta_rows:
        print("\nERROR: no usable symbols -- aborting.")
        return 1

    X_all = np.vstack(meta_rows)
    y_all = np.array(meta_labels, dtype=int)
    meta_feat_names = ["b3_p_sell", "b3_p_none", "b3_p_buy"] + list(b3_feat_names)

    # [Phase D1] sequential-bootstrap sample weights: avg_uniqueness × balanced class weight
    uniq_all = np.concatenate(uniq_weights)
    pos_w = float((y_all == 0).sum()) / max(int((y_all == 1).sum()), 1)
    class_w_all = np.where(y_all == 1, pos_w, 1.0).astype(np.float64)
    sample_w_all = uniq_all * class_w_all

    print(f"\n  Total pool: {len(X_all):,} act-rows from {len(sym_stats)} symbols")
    print(f"  Meta features  : {len(meta_feat_names)} cols")
    print(f"  Overall TP rate: {y_all.mean():.1%}  (act={int(y_all.sum())}  skip={int((y_all == 0).sum())})")
    print(
        f"  Sample weight  : mean={sample_w_all.mean():.4f}  min={sample_w_all.min():.4f}  max={sample_w_all.max():.4f}"
    )  # [Phase D1]

    # ------------------------------------------------------------------
    # Step 4: purged walk-forward CV
    # ------------------------------------------------------------------
    print(f"\n[4/5] Purged walk-forward CV ({FOLDS} folds, purge={PURGE} bars)...")
    cv = _purged_wf_cv_binary(X_all, y_all, meta_feat_names, sample_weights=sample_w_all)  # [Phase D1]
    oof_auc = cv["oof_auc"]
    print(f"  OOF AUC   : {oof_auc:.4f}  (per fold: {cv.get('oof_auc_per_fold', '?')})")
    print(f"  Random baseline : 0.500  |  Target : >= {ACT_AUC_THRESHOLD}")
    print(f"  act(TP)={cv.get('n_act', '?')}  skip(SL/TO)={cv.get('n_skip', '?')}")

    if oof_auc < ACT_AUC_THRESHOLD:
        print(f"\n  HOLD: OOF AUC {oof_auc:.4f} < {ACT_AUC_THRESHOLD}")
        print("  Saving model for inspection. DO NOT wire into brain without further tuning.")
    else:
        print(f"\n  PROMOTE: OOF AUC {oof_auc:.4f} >= {ACT_AUC_THRESHOLD}")

    # ------------------------------------------------------------------
    # Step 5: full-fit on all data
    # ------------------------------------------------------------------
    print(f"\n[5/5] Full-fit on all {len(X_all):,} act-rows...")
    # [Phase D1] use sample_w_all (uniqueness × class weight) instead of flat class weights
    d_full = lgb.Dataset(X_all, y_all, weight=sample_w_all, feature_name=meta_feat_names)
    params_full = dict(
        objective="binary",
        metric="auc",
        learning_rate=0.03,
        num_leaves=31,
        min_data_in_leaf=60,
        feature_fraction=0.80,
        # [Phase D1] bagging_fraction/bagging_freq removed; uniqueness weights replace them
        lambda_l2=1.0,
        num_iterations=700,
        verbosity=-1,
        seed=SEED,
    )
    meta_model = lgb.train(params_full, d_full, num_boost_round=700)
    OUT_META.parent.mkdir(parents=True, exist_ok=True)
    meta_model.save_model(str(OUT_META))
    print(f"\n  Saved --> {OUT_META}")

    # Verify feature name round-trip
    loaded = lgb.Booster(model_file=str(OUT_META))
    match = loaded.feature_name() == meta_feat_names
    print(f"  Feature name round-trip: {'OK' if match else 'MISMATCH -- CHECK!'}")
    print(f"  Meta features: {loaded.feature_name()[:6]} ... ({len(loaded.feature_name())} total)")

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    runtime = int(time.time() - t0)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "phase": "C1",
        "generated": datetime.now(timezone.utc).isoformat(),
        "runtime_s": runtime,
        "b3_model": str(B3_MODEL_PATH),
        "b3_features": len(b3_feat_names),
        "meta_features": len(meta_feat_names),
        "symbols": len(sym_stats),
        "total_act_rows": int(len(X_all)),
        "overall_tp_rate": round(float(y_all.mean()), 4),
        "cv_folds": cv.get("folds", 0),
        "oof_auc": round(oof_auc, 4),
        "oof_auc_per_fold": cv.get("oof_auc_per_fold", []),
        "deploy_threshold": ACT_AUC_THRESHOLD,
        "verdict": "PROMOTE" if oof_auc >= ACT_AUC_THRESHOLD else "HOLD",
        "act_threshold": ACT_THRESHOLD,
        "per_symbol": sym_stats,
    }
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_json = REPORT_DIR / f"{ts}_c1_metalabel_report.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  Report --> {out_json}")
    print(f"  Runtime: {runtime}s")

    print("\n" + "=" * 65)
    if oof_auc >= ACT_AUC_THRESHOLD:
        print("PROMOTE -- to activate the meta-labeller:")
        print("  1. In config/settings.py set: metalabel_enabled = True")
        print("     (also set metalabel_act_threshold = 0.55)")
        print("  2. start_brain_clean.cmd")
        print("  3. .venv\\Scripts\\python.exe tools\\diagnose_zero_trades.py")
        print("     --> expect MODEL_OK, non-NONE directions with P_act filter active")
    else:
        print("HOLD -- OOF AUC below threshold. Consider:")
        print("  - More training data (wait 4+ weeks of live bars)")
        print("  - Per-team meta-models instead of pooled")
        print("  - Wider TP/SL asymmetry (TP=3x ATR) to improve signal clarity")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
