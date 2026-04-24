"""
Walk-forward + purged CPCV validator for the CRYPTO per-team ML model.

Why this script exists
----------------------
`ai_trading_agents/ml_models/lgbm_CRYPTO.pkl` reports a 99.23% win rate on a
holdout split (259 samples, 257W / 2L). On a LightGBM classifier with 15
boolean features, n_estimators=200, and a label that is nearly single-class,
this is almost certainly overfit. Holdout splits are generous when sample
counts are small and labels are autocorrelated in time.

This validator re-evaluates the same training data under two more honest
strategies and compares out-of-fold performance against the reported
holdout baseline.

Strategies
----------
1. **walk_forward**  - sequential expanding-window CV. At step k, train on
   rows [0, i_k), test on rows [i_k, i_{k+1}). No purging; tests leakage
   over time by refusing to train on the future.

2. **cpcv**          - Combinatorial Purged CV with embargo (Lopez de Prado).
   Reuses the existing `tools/cpcv.py` implementation (already has 15 unit
   tests in tests/test_cpcv.py). Purges overlapping label windows and
   embargoes N bars around each test fold.

Both train a LightGBM classifier with the same hyperparameters as
`tools/train_per_team.py`.

Verdict logic
-------------
The model is flagged OVERFIT (not production-ready) if ANY of:
  - walk-forward mean AUC drops > 0.15 below holdout AUC
  - walk-forward mean win rate drops > 25 percentage points below holdout WR
  - cpcv mean AUC drops > 0.15 below holdout AUC

Usage
-----
    python tools/validate_crypto_ml.py
    python tools/validate_crypto_ml.py --team METALS --cv both
    python tools/validate_crypto_ml.py --team CRYPTO --cv walkforward --folds 5

Outputs
-------
    reports/ml_validation_<team>_<YYYY-MM-DD>.md   (human-readable)
    reports/ml_validation_<team>_<YYYY-MM-DD>.json (machine-readable)

Does NOT modify the live model, the registry, or brain state. Safe to run
while the brain is live.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent.parent

# Mirror of train_per_team.py feature list - keep in sync.
FEATURE_COLS: List[str] = [
    "trend_aligned",
    "liquidity_sweep",
    "structure_shift",
    "order_block",
    "fvg",
    "ema_aligned",
    "candle_pattern",
    "rsi_optimal",
    "rsi_divergence",
    "volume_spike",
    "good_volatility",
    "session_london",
    "session_ny",
    "session_overlap",
    "session_asian",
]

# Keep aligned with train_per_team.py hyperparams.
LGBM_PARAMS: Dict[str, Any] = dict(
    objective="binary",
    class_weight="balanced",
    n_estimators=200,
    learning_rate=0.05,
    num_leaves=15,
    max_depth=5,
    min_data_in_leaf=10,
    random_state=42,
    verbose=-1,
)

# Same team buckets as train_per_team.py.
TEAM_SYMBOLS = {
    "METALS": {"XAUUSD", "XAGUSD"},
    "FOREX": {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"},
    "CRYPTO": {"BTCUSD", "ETHUSD"},
    "COMMODITIES": {"XTIUSD", "XBRUSD", "XNGUSD"},
}

# Verdict thresholds (tunable).
AUC_DROP_BAD = 0.15  # absolute AUC drop that flags overfit
WR_DROP_BAD = 0.25  # 25 percentage points

# Minority-class floor. Below this, binary CV is largely meaningless
# (most folds will be single-class and AUC will be undefined). The
# CRYPTO model hit this: 257W / 2L on 259 trades -> minority=0.8%, so
# walk-forward AUC is computed over 1 of 5 folds and tells us nothing.
MIN_MINORITY_CLASS_FRAC = 0.10  # 10%


@dataclass
class FoldResult:
    fold: int
    n_train: int
    n_test: int
    train_auc: Optional[float]
    test_auc: Optional[float]
    test_acc: Optional[float]
    test_wr: Optional[float]
    notes: str = ""


@dataclass
class CVReport:
    strategy: str
    n_folds: int
    mean_auc: Optional[float]
    mean_wr: Optional[float]
    std_auc: Optional[float]
    std_wr: Optional[float]
    folds: List[FoldResult] = field(default_factory=list)
    error: Optional[str] = None


def load_trade_history(memory_path: Path) -> pd.DataFrame:
    """Load trade_history[] from logs/brain_memory.json."""
    if not memory_path.exists():
        raise FileNotFoundError(
            f"brain_memory.json not found at {memory_path}. Run the brain at least once to populate trade history."
        )
    data = json.loads(memory_path.read_text(encoding="utf-8"))
    trades = data.get("trade_history") or []
    if not trades:
        raise ValueError("trade_history[] is empty - no trades to validate on.")
    df = pd.DataFrame(trades)
    # Normalise the timestamp column.
    ts_col = "timestamp" if "timestamp" in df.columns else ("ts" if "ts" in df.columns else None)
    if ts_col is None:
        raise ValueError("No timestamp column found in trade records.")
    df["timestamp"] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def filter_team(df: pd.DataFrame, team: str) -> pd.DataFrame:
    symbols = TEAM_SYMBOLS.get(team.upper())
    if not symbols:
        raise ValueError(f"Unknown team: {team!r}. One of {list(TEAM_SYMBOLS)}.")
    if "symbol" not in df.columns:
        raise ValueError("'symbol' column missing from trade records.")
    mask = df["symbol"].isin(symbols)
    return df.loc[mask].reset_index(drop=True)


def extract_xy(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """Extract feature matrix X and label y."""
    if "features" in df.columns and df["features"].apply(lambda x: isinstance(x, dict)).any():
        # Features are a dict under 'features' column.
        feat_df = pd.json_normalize(df["features"])
    else:
        feat_df = df.copy()

    # Fill missing boolean features with 0 (matches train_per_team behaviour).
    X = pd.DataFrame({c: feat_df.get(c, 0) for c in FEATURE_COLS}).astype(int)

    if "is_win" in df.columns:
        y = df["is_win"].astype(int)
    elif "outcome" in df.columns:
        y = (df["outcome"].astype(str).str.lower() == "win").astype(int)
    else:
        raise ValueError("No label column ('is_win' or 'outcome') found.")
    return X, y.reset_index(drop=True)


def train_fold(
    X_tr: pd.DataFrame,
    y_tr: pd.Series,
    X_te: pd.DataFrame,
    y_te: pd.Series,
    fold: int,
) -> FoldResult:
    """Train one fold of LightGBM and score it."""
    try:
        import lightgbm as lgb
        from sklearn.metrics import accuracy_score, roc_auc_score
    except ImportError as e:
        return FoldResult(fold, len(X_tr), len(X_te), None, None, None, None, notes=f"missing dep: {e}")

    # Degenerate fold (single-class train or test) - LightGBM/roc_auc will fail.
    if y_tr.nunique() < 2:
        return FoldResult(fold, len(X_tr), len(X_te), None, None, None, None, notes="single-class training fold")
    if y_te.nunique() < 2:
        # Can still train, but AUC is undefined on test. Report accuracy only.
        clf = lgb.LGBMClassifier(**LGBM_PARAMS)
        clf.fit(X_tr, y_tr)
        pred = clf.predict(X_te)
        acc = float(accuracy_score(y_te, pred))
        wr = float(y_te.mean()) if len(y_te) else None
        return FoldResult(
            fold, len(X_tr), len(X_te), None, None, acc, wr, notes="single-class test fold (AUC undefined)"
        )

    clf = lgb.LGBMClassifier(**LGBM_PARAMS)
    clf.fit(X_tr, y_tr)

    train_auc = float(roc_auc_score(y_tr, clf.predict_proba(X_tr)[:, 1]))
    pred_proba = clf.predict_proba(X_te)[:, 1]
    test_auc = float(roc_auc_score(y_te, pred_proba))
    pred = (pred_proba >= 0.5).astype(int)
    test_acc = float(accuracy_score(y_te, pred))
    test_wr = float(y_te.mean())

    return FoldResult(fold, len(X_tr), len(X_te), train_auc, test_auc, test_acc, test_wr)


def walk_forward_cv(X: pd.DataFrame, y: pd.Series, n_folds: int = 5) -> CVReport:
    """Expanding-window walk-forward CV. Guaranteed no future leakage."""
    n = len(X)
    if n < (n_folds + 1) * 10:  # need at least ~10 samples per fold
        return CVReport(
            "walk_forward", n_folds, None, None, None, None, error=f"need >= {(n_folds + 1) * 10} samples, have {n}"
        )

    fold_size = n // (n_folds + 1)  # first chunk is initial train, rest are folds
    initial_train = fold_size
    folds: List[FoldResult] = []

    for k in range(n_folds):
        train_end = initial_train + k * fold_size
        test_end = train_end + fold_size if k < n_folds - 1 else n
        X_tr, y_tr = X.iloc[:train_end], y.iloc[:train_end]
        X_te, y_te = X.iloc[train_end:test_end], y.iloc[train_end:test_end]
        folds.append(train_fold(X_tr, y_tr, X_te, y_te, fold=k))

    aucs = [f.test_auc for f in folds if f.test_auc is not None]
    wrs = [f.test_wr for f in folds if f.test_wr is not None]
    return CVReport(
        strategy="walk_forward",
        n_folds=n_folds,
        mean_auc=float(np.mean(aucs)) if aucs else None,
        mean_wr=float(np.mean(wrs)) if wrs else None,
        std_auc=float(np.std(aucs)) if len(aucs) > 1 else None,
        std_wr=float(np.std(wrs)) if len(wrs) > 1 else None,
        folds=folds,
    )


def cpcv_validate(X: pd.DataFrame, y: pd.Series, n_groups: int = 6, n_test: int = 2, embargo_bars: int = 5) -> CVReport:
    """Combinatorial Purged CV via tools/cpcv.py (already unit-tested).

    Uses tools.cpcv.CPCVSplit (dataclass with fields: n_groups, n_test,
    label_times, label_horizon_bars, embargo_bars). label_times is left
    None here; purging falls back to label_horizon_bars (default 0 -> no
    purge). Embargo handles the boundary-leak concern on its own for a
    trade-level feature row dataset.
    """
    try:
        # tools/ on sys.path when run from repo root
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        from cpcv import CPCVSplit  # type: ignore
    except ImportError as e:
        return CVReport("cpcv", 0, None, None, None, None, error=f"cannot import cpcv: {e}")

    n = len(X)
    if n < n_groups * 10:
        return CVReport("cpcv", 0, None, None, None, None, error=f"need >= {n_groups * 10} samples, have {n}")

    try:
        splitter = CPCVSplit(n_groups=n_groups, n_test=n_test, embargo_bars=embargo_bars)
        folds: List[FoldResult] = []
        for k, (tr_idx, te_idx) in enumerate(splitter.split(X)):
            folds.append(
                train_fold(
                    X.iloc[tr_idx],
                    y.iloc[tr_idx],
                    X.iloc[te_idx],
                    y.iloc[te_idx],
                    fold=k,
                )
            )
    except Exception as e:  # pragma: no cover - defensive
        return CVReport("cpcv", 0, None, None, None, None, error=f"cpcv failure: {e}")

    aucs = [f.test_auc for f in folds if f.test_auc is not None]
    wrs = [f.test_wr for f in folds if f.test_wr is not None]
    return CVReport(
        strategy="cpcv",
        n_folds=len(folds),
        mean_auc=float(np.mean(aucs)) if aucs else None,
        mean_wr=float(np.mean(wrs)) if wrs else None,
        std_auc=float(np.std(aucs)) if len(aucs) > 1 else None,
        std_wr=float(np.std(wrs)) if len(wrs) > 1 else None,
        folds=folds,
    )


def load_holdout_baseline(team: str, registry_path: Path) -> Dict[str, Any]:
    """Read the registry entry for <team> and flatten the holdout metrics.

    Registry shape (from train_per_team.py):
        teams.<TEAM>.{
            n_samples, win_rate, wins, losses, trained_at,
            test_metrics: { accuracy, precision, recall, f1, auc_roc },
            train_metrics: { ... },
            hyperparams, feature_importance_top5, ...
        }

    Flatten into a single dict the rest of this script expects: we pull
    auc_roc -> test_auc and keep win_rate/n_samples/trained_at at the
    top level.
    """
    if not registry_path.exists():
        return {"error": f"registry not found at {registry_path}"}
    reg = json.loads(registry_path.read_text(encoding="utf-8"))
    teams = reg.get("teams") or reg
    entry = teams.get(team.upper()) if isinstance(teams, dict) else None
    if not entry:
        return {"error": f"no entry for team {team} in registry"}
    # Flatten nested metrics so verdict() can compare against CV results.
    flat = dict(entry)  # shallow copy
    tm = entry.get("test_metrics") or {}
    if "auc_roc" in tm and "test_auc" not in flat:
        flat["test_auc"] = tm["auc_roc"]
    if "accuracy" in tm and "test_acc" not in flat:
        flat["test_acc"] = tm["accuracy"]
    return flat


def verdict(
    holdout: Dict[str, Any],
    walk: CVReport,
    cpcv: CVReport,
    minority_frac: Optional[float] = None,
) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    holdout_auc = holdout.get("test_auc") or holdout.get("auc")
    holdout_wr = holdout.get("win_rate") or holdout.get("wr")

    # Class-balance gate: if the training label is too imbalanced to
    # meaningfully cross-validate, no amount of AUC comparison helps.
    # (CRYPTO hit this: 257W / 2L -> minority = 0.8%. 4 of 5 walk-forward
    # folds were single-class; the "OK" verdict was a false negative.)
    if minority_frac is not None and minority_frac < MIN_MINORITY_CLASS_FRAC:
        return "INSUFFICIENT_DATA - SEVERE CLASS IMBALANCE", [
            f"minority class is only {minority_frac * 100:.1f}% of samples "
            f"(threshold {MIN_MINORITY_CLASS_FRAC * 100:.0f}%); binary CV "
            f"degenerates - most folds are single-class and AUC is undefined",
            "remediation: collect more loss trades OR relabel target "
            "(e.g., profit-bucket instead of win/loss) before trusting this model",
        ]

    # Degenerate-fold share check: even if overall minority fraction is
    # above the floor, if >50% of CV folds ended up single-class the
    # mean AUC is unreliable. Flag explicitly.
    def _degenerate_share(r: CVReport) -> float:
        if not r.folds:
            return 0.0
        bad = sum(1 for f in r.folds if "single-class" in (f.notes or ""))
        return bad / len(r.folds)

    walk_bad = _degenerate_share(walk)
    cpcv_bad = _degenerate_share(cpcv)
    if walk_bad > 0.5 or cpcv_bad > 0.5:
        return "INCONCLUSIVE - DEGENERATE FOLDS", [
            f"degenerate folds: walk-forward {walk_bad * 100:.0f}%, "
            f"CPCV {cpcv_bad * 100:.0f}% single-class (CV unreliable)",
            "remediation: same as SEVERE CLASS IMBALANCE above",
        ]

    if holdout_auc is None:
        reasons.append("holdout AUC unavailable from registry - cannot compare")
    else:
        if walk.mean_auc is not None and (holdout_auc - walk.mean_auc) > AUC_DROP_BAD:
            reasons.append(
                f"walk-forward AUC dropped {holdout_auc - walk.mean_auc:.3f} ({holdout_auc:.3f} -> {walk.mean_auc:.3f})"
            )
        if cpcv.mean_auc is not None and (holdout_auc - cpcv.mean_auc) > AUC_DROP_BAD:
            reasons.append(
                f"CPCV AUC dropped {holdout_auc - cpcv.mean_auc:.3f} ({holdout_auc:.3f} -> {cpcv.mean_auc:.3f})"
            )

    if holdout_wr is not None and walk.mean_wr is not None:
        if (holdout_wr - walk.mean_wr) > WR_DROP_BAD:
            reasons.append(
                f"walk-forward WR dropped {(holdout_wr - walk.mean_wr) * 100:.1f} pp "
                f"({holdout_wr * 100:.1f}% -> {walk.mean_wr * 100:.1f}%)"
            )

    if reasons:
        return "OVERFIT - DO NOT DEPLOY", reasons
    if walk.mean_auc is None and cpcv.mean_auc is None:
        return "INCONCLUSIVE", ["no CV strategy produced usable metrics"]
    return "OK", ["walk-forward and CPCV metrics within tolerance of holdout baseline"]


def write_reports(
    team: str,
    holdout: Dict[str, Any],
    walk: CVReport,
    cpcv: CVReport,
    out_dir: Path,
    minority_frac: Optional[float] = None,
) -> Tuple[Path, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"ml_validation_{team}_{stamp}.json"
    md_path = out_dir / f"ml_validation_{team}_{stamp}.md"

    v, reasons = verdict(holdout, walk, cpcv, minority_frac=minority_frac)

    payload = {
        "team": team,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "holdout_baseline": holdout,
        "walk_forward": asdict(walk),
        "cpcv": asdict(cpcv),
        "verdict": v,
        "reasons": reasons,
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def pct(x: Optional[float]) -> str:
        return f"{x * 100:.1f}%" if x is not None else "-"

    def f3(x: Optional[float]) -> str:
        return f"{x:.3f}" if x is not None else "-"

    md = [
        f"# ML validation report - {team}",
        "",
        f"_Generated: {datetime.now(timezone.utc).isoformat()}_",
        "",
        f"## Verdict: **{v}**",
        "",
        *[f"- {r}" for r in reasons],
        "",
        "## Holdout baseline (from registry)",
        "",
        f"- n_samples: {holdout.get('n_samples', '-')}",
        f"- win_rate:  {pct(holdout.get('win_rate'))}",
        f"- test_auc:  {f3(holdout.get('test_auc'))}",
        f"- trained_at: {holdout.get('trained_at', '-')}",
        "",
        "## Walk-forward (expanding window)",
        "",
        f"- folds:    {walk.n_folds}",
        f"- mean AUC: {f3(walk.mean_auc)} (std {f3(walk.std_auc)})",
        f"- mean WR:  {pct(walk.mean_wr)} (std {pct(walk.std_wr)})",
        f"- error:    {walk.error or '-'}",
        "",
        "### Per-fold",
        "",
        "| fold | n_train | n_test | train_auc | test_auc | test_acc | test_wr | notes |",
        "|-----:|--------:|-------:|----------:|---------:|---------:|--------:|:------|",
    ]
    for f in walk.folds:
        md.append(
            f"| {f.fold} | {f.n_train} | {f.n_test} | {f3(f.train_auc)} | "
            f"{f3(f.test_auc)} | {f3(f.test_acc)} | {pct(f.test_wr)} | {f.notes} |"
        )

    md += [
        "",
        "## CPCV (combinatorial purged CV, embargo=5)",
        "",
        f"- folds:    {cpcv.n_folds}",
        f"- mean AUC: {f3(cpcv.mean_auc)} (std {f3(cpcv.std_auc)})",
        f"- mean WR:  {pct(cpcv.mean_wr)} (std {pct(cpcv.std_wr)})",
        f"- error:    {cpcv.error or '-'}",
    ]
    md_path.write_text("\n".join(md), encoding="utf-8")
    return md_path, json_path


TEAMS_ORDER = ["METALS", "FOREX", "CRYPTO", "COMMODITIES"]


def _run_for_team(team: str, args) -> Tuple[int, str]:
    """Validate one team. Returns (exit_code, verdict_label).

    exit_code: 0 = OK, 1 = OVERFIT / INCONCLUSIVE, 2 = error loading data.
    verdict_label is "OK" / "OVERFIT" / "INCONCLUSIVE" / "ERROR".
    """
    try:
        df = load_trade_history(Path(args.memory))
        df = filter_team(df, team)
    except Exception as e:
        print(f"[ERROR] {team}: loading trades: {e}")
        return 2, "ERROR"

    print(f"[info] team={team}  rows={len(df)}")

    # No trades for this team means no model to validate. Skip cleanly
    # instead of crashing the --team all loop on an empty dataframe.
    if len(df) == 0:
        print(f"[info] {team}: no trades in history, skipping validation")
        return 0, "SKIPPED"

    if len(df) < 30:
        print(f"[WARN] {team}: only {len(df)} rows - metrics will be very noisy.")

    try:
        X, y = extract_xy(df)

        # Minority-class proportion: gates verdict when target is
        # effectively single-class (e.g., CRYPTO's 2 losses in 259 trades).
        minority_frac: Optional[float] = None
        if len(y) > 0:
            p = float(y.mean())
            minority_frac = min(p, 1.0 - p)
            print(f"[info] {team}: minority class fraction = {minority_frac * 100:.1f}%")

        walk = (
            walk_forward_cv(X, y, n_folds=args.folds)
            if args.cv in ("walkforward", "both")
            else CVReport("walk_forward", 0, None, None, None, None, error="skipped")
        )

        cpcv = (
            cpcv_validate(X, y)
            if args.cv in ("cpcv", "both")
            else CVReport("cpcv", 0, None, None, None, None, error="skipped")
        )

        holdout = load_holdout_baseline(team, Path(args.registry))
        md_path, json_path = write_reports(team, holdout, walk, cpcv, Path(args.out), minority_frac=minority_frac)
        v, reasons = verdict(holdout, walk, cpcv, minority_frac=minority_frac)
    except Exception as e:
        # Don't let one team's failure kill the loop when --team all.
        print(f"[ERROR] {team}: validation crashed: {e}")
        return 2, "ERROR"

    print(f"[done] {team}: verdict={v}")
    for r in reasons:
        print(f"       - {r}")
    print(f"[done] wrote {md_path}")
    print(f"[done] wrote {json_path}")

    if v == "OK":
        return 0, "OK"
    if v.startswith("INSUFFICIENT"):
        return 1, "INSUFFICIENT"
    if v.startswith("INCONCLUSIVE"):
        return 1, "INCONCLUSIVE"
    return 1, "OVERFIT"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--team", default="CRYPTO", help="Team to validate; 'all' to iterate every team (default: CRYPTO)")
    ap.add_argument("--cv", choices=["walkforward", "cpcv", "both"], default="both")
    ap.add_argument("--folds", type=int, default=5, help="walk-forward fold count (default: 5)")
    ap.add_argument("--memory", default=str(REPO_ROOT / "logs" / "brain_memory.json"))
    ap.add_argument("--registry", default=str(REPO_ROOT / "ai_trading_agents" / "ml_models" / "registry.json"))
    ap.add_argument("--out", default=str(REPO_ROOT / "reports"))
    args = ap.parse_args()

    teams = TEAMS_ORDER if args.team.lower() == "all" else [args.team.upper()]

    summary: List[Tuple[str, int, str]] = []
    for t in teams:
        if len(teams) > 1:
            print(f"\n{'=' * 20} {t} {'=' * 20}")
        code, label = _run_for_team(t, args)
        summary.append((t, code, label))

    if len(teams) > 1:
        print("\n=== summary ===")
        for t, code, label in summary:
            print(f"  {t:12s}  {label}  (exit={code})")

    # Worst-case exit: ERROR (2) dominates OVERFIT (1) dominates OK (0).
    return max(code for _, code, _ in summary)


if __name__ == "__main__":
    raise SystemExit(main())
