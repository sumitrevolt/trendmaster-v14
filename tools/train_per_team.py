"""
Per-team ML trainer for TrendMaster v14.

Purpose
-------
The brain currently uses a single LightGBM classifier trained on XAUUSD and
applies it to all 19 symbols across 4 teams. This trainer builds one model
per team so FOREX pairs (for example) aren't graded through a gold-trained
lens.

Source of truth
---------------
    logs/brain_memory.json  ->  trade_history[]

Each trade provides 15 boolean features plus an `is_win` label. Trades are
bucketed by team using the mapping in ai_trading_agents/risk_manager.py.

Outputs
-------
    ai_trading_agents/ml_models/lgbm_<team>.pkl       (joblib-serialized)
    ai_trading_agents/ml_models/registry.json         (paths + metrics)
    reports/ML_TRAINING_REPORT.md                     (human readable)

This script does NOT wire the models into trend_master_brain.py. Integration
is a separate step that should wait until every team has >=300 closed trades.
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
BRAIN_MEMORY = ROOT / "logs" / "brain_memory.json"
MODELS_DIR = ROOT / "ai_trading_agents" / "ml_models"
REGISTRY_PATH = MODELS_DIR / "registry.json"
REPORT_PATH = ROOT / "reports" / "ML_TRAINING_REPORT.md"

MODELS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# team mapping (kept in sync with ai_trading_agents/risk_manager.py)
# ---------------------------------------------------------------------------
TEAM_METALS = {"XAUUSD", "XAGUSD"}
TEAM_FOREX = {
    "GBPJPY", "USDCAD", "USDCHF", "EURUSD", "GBPUSD",
    "AUDUSD", "USDJPY", "NZDUSD", "EURJPY", "EURGBP",
    "AUDJPY", "CADJPY",
}
TEAM_CRYPTO = {"BTCUSD", "ETHUSD"}
TEAM_COMMODITIES = {"XTIUSD", "XBRUSD", "XNGUSD"}

TEAMS = ["METALS", "FOREX", "CRYPTO", "COMMODITIES"]
MIN_TRADES = 50


def team_of(symbol: str) -> str | None:
    if symbol in TEAM_METALS:
        return "METALS"
    if symbol in TEAM_FOREX:
        return "FOREX"
    if symbol in TEAM_CRYPTO:
        return "CRYPTO"
    if symbol in TEAM_COMMODITIES:
        return "COMMODITIES"
    return None


FEATURE_COLS = [
    "trend_aligned", "liquidity_sweep", "structure_shift", "order_block",
    "fvg", "ema_aligned", "candle_pattern", "rsi_optimal", "rsi_divergence",
    "volume_spike", "good_volatility", "session_london", "session_ny",
    "session_overlap", "session_asian",
]


# ---------------------------------------------------------------------------
# load + bucket
# ---------------------------------------------------------------------------
def load_trades() -> list[dict]:
    with BRAIN_MEMORY.open("r", encoding="utf-8") as fh:
        mem = json.load(fh)
    trades = mem.get("trade_history", []) or []
    print(f"[load] {len(trades)} trades in brain_memory.json")
    return trades


def bucket_by_team(trades: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {t: [] for t in TEAMS}
    skipped = 0
    for t in trades:
        sym = t.get("symbol", "")
        team = team_of(sym)
        if team is None:
            skipped += 1
            continue
        # must have all features + is_win label
        feats = t.get("features") or {}
        if "is_win" not in t or not all(k in feats for k in FEATURE_COLS):
            skipped += 1
            continue
        buckets[team].append(t)
    # sort each bucket by timestamp so 80/20 is a true time-based split
    for team, lst in buckets.items():
        lst.sort(key=lambda r: r.get("timestamp", ""))
    print(
        "[bucket] "
        + "  ".join(f"{team}={len(buckets[team])}" for team in TEAMS)
        + f"  skipped={skipped}"
    )
    return buckets


# ---------------------------------------------------------------------------
# training
# ---------------------------------------------------------------------------
# [enhancement 2026-04-23] Session features frequently dominate feature
# importance because they alias the session_window gate. --drop-session-
# features removes them so the model has to learn real technical alpha.
_SESSION_FEATURES = {"session_london", "session_ny", "session_overlap", "session_asian"}


def train_team(team: str, rows: list[dict], *,
               cv_mode: str = "holdout",
               drop_session_features: bool = False) -> dict[str, Any]:
    """Train a single team's LightGBM model. Returns metadata dict.

    Parameters
    ----------
    cv_mode : "holdout" | "cpcv"
        "holdout" — legacy time-based 80/20 split (default, unchanged).
        "cpcv"    — Combinatorial Purged CV with embargo (tools/cpcv.py).
                    Produces out-of-fold metrics that don't over-state
                    edge on time-series data. Recommended for any live-
                    promotion decision.
    drop_session_features : bool
        When True, removes session_london/ny/overlap/asian before fit.
        Forces the model to learn something besides session aliasing.
    """
    import numpy as np
    import joblib
    import lightgbm as lgb
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        roc_auc_score,
    )

    n = len(rows)
    print(f"\n[{team}] training with N={n} trades (cv={cv_mode} "
          f"drop_session={drop_session_features})")

    feature_cols = [c for c in FEATURE_COLS
                    if not (drop_session_features and c in _SESSION_FEATURES)]
    X = np.array(
        [[1 if r["features"][c] else 0 for c in feature_cols] for r in rows],
        dtype=np.float32,
    )
    y = np.array([1 if r["is_win"] else 0 for r in rows], dtype=np.int32)

    wins = int(y.sum())
    losses = int(n - wins)
    win_rate = wins / n if n else 0.0
    print(f"[{team}] class balance: {wins}W / {losses}L ({win_rate:.1%} win)")

    if cv_mode == "cpcv":
        # Out-of-fold pooled metrics — trustworthy estimate of live edge.
        try:
            from tools.cpcv import CPCVSplit
        except Exception as e:
            print(f"[{team}] CPCV import failed ({e}); falling back to holdout")
            cv_mode = "holdout"

    if cv_mode == "cpcv":
        cv = CPCVSplit(n_groups=6, n_test=2, embargo_bars=5)
        oof_true: list[int] = []
        oof_pred: list[int] = []
        oof_prob: list[float] = []
        for tr_idx, te_idx in cv.split(X, y):
            m = lgb.LGBMClassifier(
                objective="binary", class_weight="balanced",
                n_estimators=200, learning_rate=0.05, num_leaves=15,
                max_depth=5, min_data_in_leaf=10,
                verbosity=-1, random_state=42,
            )
            m.fit(X[tr_idx], y[tr_idx])
            pr = m.predict_proba(X[te_idx])[:, 1]
            pd_ = (pr >= 0.5).astype(int)
            oof_true.extend(y[te_idx].tolist())
            oof_pred.extend(pd_.tolist())
            oof_prob.extend(pr.tolist())
        # Refit on full data for inference.
        X_tr, y_tr = X, y
        X_te = np.asarray([])
        y_te = np.asarray([])
        cpcv_metrics = {
            "accuracy":  float(accuracy_score(oof_true, oof_pred)),
            "precision": float(precision_score(oof_true, oof_pred, zero_division=0)),
            "recall":    float(recall_score(oof_true, oof_pred, zero_division=0)),
            "f1":        float(f1_score(oof_true, oof_pred, zero_division=0)),
            "auc_roc":   (float(roc_auc_score(oof_true, oof_prob))
                          if len(set(oof_true)) == 2 else None),
            "n_folds":   cv.get_n_splits(),
        }
        print(f"[{team}] CPCV out-of-fold: {cpcv_metrics}")
    else:
        cpcv_metrics = None
        cut = int(n * 0.8)
        X_tr, y_tr = X[:cut], y[:cut]
        X_te, y_te = X[cut:], y[cut:]
        print(f"[{team}] split: train={len(X_tr)}  test={len(X_te)}")

    model = lgb.LGBMClassifier(
        objective="binary",
        class_weight="balanced",
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=15,
        max_depth=5,
        min_data_in_leaf=10,
        verbosity=-1,
        random_state=42,
    )
    model.fit(X_tr, y_tr)

    def _metrics(Xs, ys):
        pred = model.predict(Xs)
        out = {
            "accuracy": float(accuracy_score(ys, pred)),
            "precision": float(
                precision_score(ys, pred, zero_division=0)
            ),
            "recall": float(recall_score(ys, pred, zero_division=0)),
            "f1": float(f1_score(ys, pred, zero_division=0)),
            "auc_roc": None,
        }
        # AUC only defined when both classes present in ys
        if len(set(ys.tolist())) == 2:
            try:
                proba = model.predict_proba(Xs)[:, 1]
                out["auc_roc"] = float(roc_auc_score(ys, proba))
            except Exception as exc:  # pragma: no cover
                print(f"[{team}] AUC computation failed: {exc}")
        return out

    train_metrics = _metrics(X_tr, y_tr)
    test_metrics = _metrics(X_te, y_te) if len(X_te) else None

    # feature importance
    importances = model.booster_.feature_importance(importance_type="gain")
    fi_pairs = sorted(
        zip(feature_cols, importances.tolist()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    top5 = [{"feature": f, "gain": float(g)} for f, g in fi_pairs[:5]]

    # persist
    model_path = MODELS_DIR / f"lgbm_{team}.pkl"
    joblib.dump(
        {
            "model": model,
            "feature_cols": feature_cols,
            "team": team,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "n_samples": n,
            "cv_mode": cv_mode,
            "dropped_session_features": bool(drop_session_features),
        },
        model_path,
    )
    print(f"[{team}] saved -> {model_path}")
    print(f"[{team}] train: {train_metrics}")
    print(f"[{team}] test : {test_metrics}")
    print(f"[{team}] top features: {[p['feature'] for p in top5]}")

    return {
        "team": team,
        "status": "trained",
        "n_samples": n,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "model_path": str(model_path.relative_to(ROOT)).replace("\\", "/"),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "cv_mode": cv_mode,
        "cpcv_metrics": cpcv_metrics,
        "dropped_session_features": bool(drop_session_features),
        "feature_cols_used": feature_cols,
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "feature_importance_top5": top5,
        "feature_importance_all": [
            {"feature": f, "gain": float(g)} for f, g in fi_pairs
        ],
        "hyperparams": {
            "objective": "binary",
            "class_weight": "balanced",
            "n_estimators": 200,
            "learning_rate": 0.05,
            "num_leaves": 15,
            "max_depth": 5,
            "min_data_in_leaf": 10,
        },
    }


def stub_team(team: str, n: int) -> dict[str, Any]:
    print(
        f"\n[{team}] INSUFFICIENT DATA (N={n} < {MIN_TRADES}) - emitting stub"
    )
    return {
        "team": team,
        "status": "insufficient_data",
        "n_samples": n,
        "model_path": None,
        "note": f"insufficient data - will train when N >= {MIN_TRADES}",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def _fmt(v: Any, digits: int = 4) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def write_report(results: list[dict[str, Any]]) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []
    lines.append("# TrendMaster v14 - Per-Team ML Training Report")
    lines.append("")
    lines.append(f"Generated: {now}")
    lines.append("")
    lines.append(
        "Source: `logs/brain_memory.json` -> `trade_history[]` "
        "(bucketed by team using `risk_manager.team_of`)."
    )
    lines.append("")

    # summary table
    lines.append("## Summary")
    lines.append("")
    lines.append(
        "| Team | Status | N | Wins | Losses | Win% | "
        "Train Acc | Test Acc | Precision | Recall | F1 | AUC |"
    )
    lines.append(
        "|------|--------|---|------|--------|------|"
        "-----------|----------|-----------|--------|----|-----|"
    )
    for r in results:
        if r["status"] != "trained":
            lines.append(
                f"| {r['team']} | {r['status']} | {r.get('n_samples', 0)} "
                f"| - | - | - | - | - | - | - | - | - |"
            )
            continue
        tr, te = r["train_metrics"], r["test_metrics"] or {}
        lines.append(
            f"| {r['team']} | trained | {r['n_samples']} "
            f"| {r['wins']} | {r['losses']} | {r['win_rate']*100:.1f}% "
            f"| {_fmt(tr.get('accuracy'))} "
            f"| {_fmt(te.get('accuracy'))} "
            f"| {_fmt(te.get('precision'))} "
            f"| {_fmt(te.get('recall'))} "
            f"| {_fmt(te.get('f1'))} "
            f"| {_fmt(te.get('auc_roc'))} |"
        )
    lines.append("")

    # per-team details
    for r in results:
        lines.append(f"## {r['team']}")
        lines.append("")
        if r["status"] != "trained":
            lines.append(
                f"- Status: **{r['status']}**  "
                f"(N={r.get('n_samples', 0)}, "
                f"min required={MIN_TRADES})"
            )
            lines.append(f"- {r.get('note', '')}")
            lines.append("")
            continue

        lines.append(f"- Samples: {r['n_samples']} "
                     f"({r['wins']}W / {r['losses']}L, "
                     f"win rate {r['win_rate']*100:.1f}%)")
        lines.append(f"- Model: `{r['model_path']}`")
        lines.append(f"- Trained at: {r['trained_at']}")
        lines.append("")
        lines.append("**Metrics**")
        lines.append("")
        lines.append("| Split | Accuracy | Precision | Recall | F1 | AUC-ROC |")
        lines.append("|-------|----------|-----------|--------|----|---------|")
        tr = r["train_metrics"]
        lines.append(
            f"| train | {_fmt(tr['accuracy'])} | {_fmt(tr['precision'])} "
            f"| {_fmt(tr['recall'])} | {_fmt(tr['f1'])} "
            f"| {_fmt(tr['auc_roc'])} |"
        )
        if r["test_metrics"]:
            te = r["test_metrics"]
            lines.append(
                f"| test  | {_fmt(te['accuracy'])} "
                f"| {_fmt(te['precision'])} | {_fmt(te['recall'])} "
                f"| {_fmt(te['f1'])} | {_fmt(te['auc_roc'])} |"
            )
        lines.append("")
        lines.append("**Top 5 features (LightGBM gain)**")
        lines.append("")
        for i, p in enumerate(r["feature_importance_top5"], 1):
            lines.append(f"{i}. `{p['feature']}` - gain {p['gain']:.2f}")
        lines.append("")

    # caveats
    lines.append("## Honest caveats")
    lines.append("")
    lines.append(
        "- **One day of data.** All 500 trades in `brain_memory.json` are "
        "stamped 2026-03-08. There is no regime diversity - no high-vol "
        "news day, no holiday tape, no weekend crypto flush - so the "
        "models only know one market mood."
    )
    lines.append(
        "- **Class imbalance.** Overall split is ~429W / 71L "
        "(~85% win rate). `class_weight='balanced'` helps but a model "
        "that predicts WIN on everything already scores ~85% accuracy - "
        "look at precision/recall/AUC rather than accuracy."
    )
    lines.append(
        "- **Only 2 of 4 teams have any data.** METALS (XAUUSD) and "
        "CRYPTO (ETHUSD) are represented. FOREX and COMMODITIES have "
        "zero trades in memory; their models are stubs."
    )
    lines.append(
        "- **No out-of-sample window.** The 80/20 split is time-based "
        "but all 500 trades fall on the same calendar day, so the 'test' "
        "slice is effectively the last ~90 minutes of the same session "
        "as training. That is not a real OOS test."
    )
    lines.append(
        "- **Single-symbol-per-team coverage.** METALS has XAUUSD only "
        "(no XAGUSD); CRYPTO has ETHUSD only (no BTCUSD). A model "
        "trained on one symbol still generalizes cross-symbol on faith."
    )
    lines.append(
        "- **15 boolean features only.** No price/ATR/spread context. "
        "The model can't distinguish 'trend_aligned during London "
        "on a 0.05% ATR day' from 'trend_aligned during a news spike'."
    )
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    lines.append(
        "**Do NOT wire these into `trend_master_brain.py` yet.** Keep the "
        "current single-model fallback in production."
    )
    lines.append("")
    lines.append(
        "Gates to hit before switching the brain to per-team models:"
    )
    lines.append("")
    lines.append(
        "1. At least **300 closed trades per team** covering **>=10 "
        "distinct trading days** (ideally spanning a news week)."
    )
    lines.append(
        "2. Each team's test-slice AUC-ROC stably above 0.60 on a "
        "held-out **calendar** window (not an intra-day tail)."
    )
    lines.append(
        "3. Cross-symbol coverage inside each team (e.g. both XAUUSD and "
        "XAGUSD for METALS; both BTCUSD and ETHUSD for CRYPTO)."
    )
    lines.append(
        "4. A second validation pass via `tools/ea_parity` backtest "
        "showing the per-team model does not degrade EA-parity "
        "expectancy vs the current single model."
    )
    lines.append("")
    lines.append(
        "Until those gates are met, these artifacts exist so the "
        "pipeline is testable and so we can iterate quickly once the "
        "trade-feedback loop accumulates real data. Treat today's "
        "metrics as plumbing proof, not signal."
    )
    lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[report] wrote {REPORT_PATH}")


def write_registry(results: list[dict[str, Any]]) -> None:
    reg = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "logs/brain_memory.json",
        "feature_cols": FEATURE_COLS,
        "min_trades_to_train": MIN_TRADES,
        "teams": {},
    }
    for r in results:
        entry: dict[str, Any] = {
            "status": r["status"],
            "n_samples": r.get("n_samples", 0),
            "model_path": r.get("model_path"),
        }
        if r["status"] == "trained":
            entry.update(
                {
                    "trained_at": r["trained_at"],
                    "wins": r["wins"],
                    "losses": r["losses"],
                    "win_rate": r["win_rate"],
                    "train_metrics": r["train_metrics"],
                    "test_metrics": r["test_metrics"],
                    "hyperparams": r["hyperparams"],
                    "feature_importance_top5": r["feature_importance_top5"],
                }
            )
        else:
            entry["note"] = r.get("note", "")
            entry["recorded_at"] = r.get("recorded_at")
        reg["teams"][r["team"]] = entry

    REGISTRY_PATH.write_text(
        json.dumps(reg, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    print(f"[registry] wrote {REGISTRY_PATH}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    # [enhancement 2026-04-23] CLI flags for CPCV + session-feature drop.
    import argparse
    p = argparse.ArgumentParser(
        prog="train_per_team",
        description="Per-team LightGBM trainer with optional CPCV.",
    )
    p.add_argument("--cv", choices=("holdout", "cpcv"), default="holdout",
                   help="Cross-validation mode: 'holdout' (legacy 80/20) or "
                        "'cpcv' (Combinatorial Purged CV with embargo). "
                        "Use cpcv for honest out-of-fold metrics.")
    p.add_argument("--drop-session-features", action="store_true",
                   help="Drop session_london/ny/overlap/asian features before fit. "
                        "Prevents the model from re-learning the session_window gate.")
    args = p.parse_args()

    print(f"[env] python {sys.version.split()[0]}")
    print(f"[env] ROOT={ROOT}")
    print(f"[env] cv_mode={args.cv}  drop_session_features={args.drop_session_features}")

    if not BRAIN_MEMORY.exists():
        print(f"[fatal] missing {BRAIN_MEMORY}")
        return 2

    trades = load_trades()
    buckets = bucket_by_team(trades)

    results: list[dict[str, Any]] = []
    for team in TEAMS:
        rows = buckets[team]
        if len(rows) >= MIN_TRADES:
            try:
                results.append(train_team(
                    team, rows,
                    cv_mode=args.cv,
                    drop_session_features=args.drop_session_features,
                ))
            except Exception as exc:
                print(f"[{team}] TRAIN FAILED: {exc}")
                results.append(
                    {
                        "team": team,
                        "status": f"error: {exc!r}",
                        "n_samples": len(rows),
                        "model_path": None,
                    }
                )
        else:
            results.append(stub_team(team, len(rows)))

    write_registry(results)
    write_report(results)

    trained = [r for r in results if r["status"] == "trained"]
    print(f"\n[done] trained {len(trained)}/{len(results)} teams")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
