"""Phase C2: TrendMaster v14 per-team meta-labelling heads trainer.

Architecture (López de Prado AFML Ch.10, per-group variant)
------------------------------------------------------------
Primary classifier  : B3 model (3-class: SELL / NONE / BUY)
Meta-labellers      : 4 × binary act/skip, one per trading team

Teams and symbols
  METALS      : XAUUSD, XAGUSD
  FOREX       : GBPJPY, USDCAD, USDCHF, EURUSD, GBPUSD, AUDUSD,
                USDJPY, NZDUSD, EURJPY, AUDJPY, CADJPY, EURGBP
  CRYPTO      : BTCUSD, ETHUSD
  COMMODITIES : XTIUSD, XBRUSD, XNGUSD

Motivation
  C1 (global head) was trained on all 19 symbols (TP rate 84.5%).
  Team TP rates differ significantly:
    CRYPTO      87-88%  (BTCUSD 87.4%, ETHUSD 88.3%)
    COMMODITIES 85-88%  (XBRUSD 88.3%, XNGUSD 88.0%, XTIUSD 85.1%)
    METALS      83-86%  (XAGUSD 85.9%, XAUUSD 83.4%)
    FOREX       80-85%  (EURGBP 85.3%, GBPUSD 84.7%, USDCAD 85.0%,
                         CADJPY 80.4%, USDJPY 81.0%)
  A pooled head learns the average; a per-team head captures the
  team-specific TP geometry, improving precision on extreme teams.

Input / output
  Same 35-col meta-feature schema as C1:
    [0:3]  P_sell, P_none, P_buy  (B3 softmax probabilities)
    [3:35] V2 features (32 effective cols)
  Output: ai_trading_agents/meta_label_model_{TEAM}.lgb  (× 4)

Brain wiring (after this commit)
  When metalabel_perteam_enabled=True, infer_ml() routes each symbol
  to its team's head. Falls back to global C1 model if a team model
  is not loaded. When both metalabel_enabled and
  metalabel_perteam_enabled are True, per-team takes precedence.

Path discipline
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

from ai_trading_agents.feature_cols_v2 import build_features_v2  # noqa: E402
from tools.sample_weights import avg_uniqueness  # noqa: E402  [Phase D1]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = ROOT / "data"
B3_MODEL_PATH = ROOT / "ai_trading_agents" / "trend_master_model.lgb"
MODEL_DIR = ROOT / "ai_trading_agents"
REPORT_DIR = ROOT / "reports" / "training"

TEAMS: dict[str, list[str]] = {
    "METALS": ["XAUUSD", "XAGUSD"],
    "FOREX": [
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
    ],
    "CRYPTO": ["BTCUSD", "ETHUSD"],
    "COMMODITIES": ["XTIUSD", "XBRUSD", "XNGUSD"],
}

HOLD_BARS = 12  # must match B3
TP_MULT = 2.0  # must match B3
SL_MULT = 1.0  # must match B3
FOLDS = 5
PURGE = HOLD_BARS
SEED = 42

ACT_AUC_THRESHOLD = 0.55  # OOF AUC floor to deploy
MIN_SAMPLES = 150  # minimum act-rows per symbol (lower than C1 — smaller teams)
MIN_TEAM_SAMPLES = 400  # minimum total act-rows per team to train


# ---------------------------------------------------------------------------
# Helpers (identical to C1)
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
    """Return binary label: 1 if B3's predicted direction hit TP, 0 otherwise."""
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
        if side == +1:
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
        else:
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
            min_data_in_leaf=40,  # slightly lower than C1 — smaller per-team sets
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
# Per-symbol data builder (returns (X_meta, y) for one symbol)
# ---------------------------------------------------------------------------


def _build_symbol_meta(
    sym: str,
    b3: lgb.Booster,
    b3_feat_names: list[str],
    cot_df: pd.DataFrame | None,
    eia_df: pd.DataFrame | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Build 35-col meta-feature matrix + binary labels + uniqueness for one symbol.

    Returns (X_meta, y, uniq) or None if the symbol is unusable.
    [Phase D1] uniq = avg_uniqueness(n_act, HOLD_BARS) — used for sample weighting.
    """
    csv_path = DATA_DIR / f"{sym.lower()}_m5_history.csv"
    if not csv_path.exists():
        print(f"    {sym:10s} SKIP -- CSV missing")
        return None

    h1 = _resample_h1(csv_path)
    if h1 is None or len(h1) < 200:
        print(f"    {sym:10s} SKIP -- too few H1 bars")
        return None

    try:
        feat_df = build_features_v2(
            h1,
            symbol=sym,
            cot_df=cot_df,
            eia_df=eia_df,
            fill_na_smartmoney=True,
        )
    except Exception as e:
        print(f"    {sym:10s} SKIP -- build_features_v2 failed: {e}")
        return None

    aligned = feat_df.reindex(columns=b3_feat_names, fill_value=0.0)
    clean = aligned.dropna()
    if len(clean) < MIN_SAMPLES:
        print(f"    {sym:10s} SKIP -- only {len(clean)} clean rows")
        return None

    X_raw = clean.values.astype(np.float32)
    b3_probs = b3.predict(X_raw)  # (N, 3)
    b3_sides_enc = b3_probs.argmax(axis=1)
    enc_to_side = {0: -1, 1: 0, 2: +1}
    b3_side_arr = np.array([enc_to_side[int(s)] for s in b3_sides_enc])
    b3_side_ser = pd.Series(b3_side_arr, index=clean.index)

    binary_labels = _triple_barrier_binary(h1, b3_side_ser)
    act_mask = b3_side_arr != 0
    label_arr = binary_labels.reindex(clean.index).values
    combined_mask = act_mask & np.isfinite(label_arr)
    n_act = int(combined_mask.sum())

    if n_act < MIN_SAMPLES:
        print(f"    {sym:10s} SKIP -- only {n_act} act-rows after filtering")
        return None

    X_act = X_raw[combined_mask]
    probs_act = b3_probs[combined_mask]
    y_act = label_arr[combined_mask].astype(int)
    X_meta = np.concatenate([probs_act, X_act], axis=1).astype(np.float32)

    tp_rate = float(y_act.mean())
    print(
        f"    {sym:10s} act_rows={n_act}  TP_rate={tp_rate:.1%}  "
        f"B3_buy={int((b3_side_arr[combined_mask] == +1).sum())}  "
        f"B3_sell={int((b3_side_arr[combined_mask] == -1).sum())}"
    )
    uniq = avg_uniqueness(n_act, HOLD_BARS)  # [Phase D1]
    return X_meta, y_act, uniq


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    t0 = time.time()
    print("=" * 65)
    print("Phase C2 -- TrendMaster v14 per-team meta-label trainer")
    print("  Primary model  : trend_master_model.lgb  (B3, 32 features)")
    print("  Meta features  : 3 B3 probs + 32 V2 cols = 35 total")
    print("  Teams          : METALS / FOREX / CRYPTO / COMMODITIES")
    print("  CV             : purged walk-forward 5-fold per team")
    print("=" * 65)

    # ------------------------------------------------------------------
    # Step 1: load B3 model
    # ------------------------------------------------------------------
    print("\n[1/4] Loading B3 primary model...")
    if not B3_MODEL_PATH.exists():
        print(f"  ERROR: {B3_MODEL_PATH} not found -- run Phase B3 first.")
        return 1
    b3 = lgb.Booster(model_file=str(B3_MODEL_PATH))
    b3_feat_names = b3.feature_name()
    meta_feat_names = ["b3_p_sell", "b3_p_none", "b3_p_buy"] + list(b3_feat_names)
    print(
        f"  B3 model: {len(b3_feat_names)} features, "
        f"mtime={datetime.fromtimestamp(B3_MODEL_PATH.stat().st_mtime, tz=timezone.utc).isoformat()}"
    )

    # ------------------------------------------------------------------
    # Step 2: fetch smart-money data once (shared across all teams)
    # ------------------------------------------------------------------
    print("\n[2/4] Fetching smart-money data (COT + EIA)...")
    try:
        from ai_trading_agents.cross_asset_join import fetch_cot_data, fetch_eia_data  # noqa: PLC0415

        cot_df = fetch_cot_data()
        print(f"  COT  : {len(cot_df)} weekly rows")
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
    # Step 3: train one model per team
    # ------------------------------------------------------------------
    print("\n[3/4] Training per-team meta-label models...")
    team_results: list[dict] = []
    all_promoted = True

    for team_name, symbols in TEAMS.items():
        print(f"\n  === {team_name} ({len(symbols)} symbols) ===")

        # Collect meta-features for all symbols in this team
        team_rows: list[np.ndarray] = []
        team_labels: list[int] = []
        team_uniq: list[np.ndarray] = []  # [Phase D1]
        sym_stats: list[dict] = []

        for sym in symbols:
            result = _build_symbol_meta(sym, b3, b3_feat_names, cot_df, eia_df)
            if result is None:
                continue
            X_meta, y_act, uniq = result  # [Phase D1] unpack uniqueness
            team_rows.append(X_meta)
            team_labels.extend(y_act.tolist())
            team_uniq.append(uniq)  # [Phase D1]
            sym_stats.append(
                {
                    "symbol": sym,
                    "n_act": len(y_act),
                    "tp_rate": round(float(y_act.mean()), 4),
                }
            )

        if not team_rows or sum(d["n_act"] for d in sym_stats) < MIN_TEAM_SAMPLES:
            print(
                f"  {team_name}: SKIP -- insufficient data "
                f"({sum(d['n_act'] for d in sym_stats) if sym_stats else 0} act-rows < {MIN_TEAM_SAMPLES})"
            )
            team_results.append(
                {
                    "team": team_name,
                    "symbols": sym_stats,
                    "verdict": "SKIP",
                    "oof_auc": None,
                    "model_path": None,
                }
            )
            all_promoted = False
            continue

        X_team = np.vstack(team_rows)
        y_team = np.array(team_labels, dtype=int)
        team_tp = float(y_team.mean())

        # [Phase D1] sequential-bootstrap sample weights: avg_uniqueness × balanced class weight
        uniq_team = np.concatenate(team_uniq)
        pos_w_team = float((y_team == 0).sum()) / max(int((y_team == 1).sum()), 1)
        class_w_team = np.where(y_team == 1, pos_w_team, 1.0).astype(np.float64)
        sample_w_team = uniq_team * class_w_team

        print(f"  {team_name}: {len(X_team):,} act-rows  overall TP={team_tp:.1%}  features={len(meta_feat_names)}")
        print(
            f"  Sample weight  : mean={sample_w_team.mean():.4f}  min={sample_w_team.min():.4f}  max={sample_w_team.max():.4f}"
        )  # [Phase D1]

        # Purged walk-forward CV
        cv = _purged_wf_cv_binary(X_team, y_team, meta_feat_names, sample_weights=sample_w_team)  # [Phase D1]
        oof_auc = cv["oof_auc"]
        verdict = "PROMOTE" if oof_auc >= ACT_AUC_THRESHOLD else "HOLD"
        if verdict == "HOLD":
            all_promoted = False
        print(f"  {team_name} OOF AUC: {oof_auc:.4f}  (per fold: {cv.get('oof_auc_per_fold', '?')})  --> {verdict}")
        print(f"  act(TP)={cv.get('n_act', '?')}  skip(SL/TO)={cv.get('n_skip', '?')}")

        # Full fit — [Phase D1] use sample_w_team (uniqueness × class weight)
        d_full = lgb.Dataset(X_team, y_team, weight=sample_w_team, feature_name=meta_feat_names)
        params_full = dict(
            objective="binary",
            metric="auc",
            learning_rate=0.03,
            num_leaves=31,
            min_data_in_leaf=40,
            feature_fraction=0.80,
            # [Phase D1] bagging_fraction/bagging_freq removed; uniqueness weights replace them
            lambda_l2=1.0,
            num_iterations=700,
            verbosity=-1,
            seed=SEED,
        )
        team_model = lgb.train(params_full, d_full, num_boost_round=700)

        out_path = MODEL_DIR / f"meta_label_model_{team_name}.lgb"
        team_model.save_model(str(out_path))

        # Verify round-trip
        loaded = lgb.Booster(model_file=str(out_path))
        rt_ok = loaded.feature_name() == meta_feat_names
        print(f"  Saved --> {out_path}  feature round-trip: {'OK' if rt_ok else 'MISMATCH'}")

        team_results.append(
            {
                "team": team_name,
                "symbols": sym_stats,
                "n_act_total": int(len(X_team)),
                "team_tp_rate": round(team_tp, 4),
                "oof_auc": round(oof_auc, 4),
                "oof_auc_per_fold": cv.get("oof_auc_per_fold", []),
                "cv_folds": cv.get("folds", 0),
                "cv_n_act": cv.get("n_act", 0),
                "cv_n_skip": cv.get("n_skip", 0),
                "verdict": verdict,
                "model_path": str(out_path),
            }
        )

    # ------------------------------------------------------------------
    # Step 4: summary + report
    # ------------------------------------------------------------------
    print("\n[4/4] Summary")
    print("-" * 55)
    for tr in team_results:
        auc_str = f"{tr['oof_auc']:.4f}" if tr.get("oof_auc") else "N/A"
        n_str = f"{tr.get('n_act_total', 0):,}" if tr.get("n_act_total") else "0"
        print(f"  {tr['team']:12s}  act={n_str:>6s}  OOF_AUC={auc_str}  {tr['verdict']}")
    print("-" * 55)

    runtime = int(time.time() - t0)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report = {
        "phase": "C2",
        "generated": datetime.now(timezone.utc).isoformat(),
        "runtime_s": runtime,
        "b3_model": str(B3_MODEL_PATH),
        "b3_features": len(b3_feat_names),
        "meta_features": len(meta_feat_names),
        "act_auc_threshold": ACT_AUC_THRESHOLD,
        "teams": team_results,
    }
    out_json = REPORT_DIR / f"{ts}_c2_metalabel_perteam_report.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n  Report --> {out_json}")
    print(f"  Runtime: {runtime}s")

    print("\n" + "=" * 65)
    promoted_teams = [tr["team"] for tr in team_results if tr.get("verdict") == "PROMOTE"]
    held_teams = [tr["team"] for tr in team_results if tr.get("verdict") in ("HOLD", "SKIP")]
    print(f"PROMOTED: {promoted_teams}")
    if held_teams:
        print(f"HOLD/SKIP: {held_teams}")
    if promoted_teams:
        print("\nTo activate per-team meta-labelling:")
        print("  1. In config/settings.py set: metalabel_perteam_enabled = True")
        print("     (keep metalabel_enabled = True as the global fallback)")
        print("  2. start_brain_clean.cmd")
        print("  3. .venv\\Scripts\\python.exe tools\\diagnose_zero_trades.py")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
