"""Per-symbol walk-forward R&D harness.

Iterates every historical CSV in `data/` and runs the EA-parity walk-
forward (`run_ea_parity_backtest`) to produce a per-symbol edge report.
Sorted by expectancy_R; symbols with negative or near-zero edge are
flagged so we know where the rule-based (or ML) brain genuinely has
signal vs where it doesn't.

Why this exists
---------------
After the 2026-04-24 incident the brain runs on rules, but we have
never measured per-symbol edge across the full 50,000-bar history.
The R&D loop needs a number-driven view: where does the strategy
work, where does it lose, and what changed since the last run.

Output
------
Writes:
  - reports/walkforward/<UTC-DATE>.md  (human-readable per-symbol table)
  - reports/walkforward/<UTC-DATE>.json  (machine-readable, for the
    nightly diff against the previous run)

Phase B2-research mode (--feature-set v1|v2)
--------------------------------------------
When ``--feature-set`` is set, the tool switches off the EA-parity
backtest and instead runs a purged walk-forward LightGBM classifier
per symbol, using either FEATURE_COLS (v1, 25 cols) or FEATURE_COLS_V2
(v2, 33 cols including 7 COT spec_delta_z + 1 EIA NG storage_delta_z).
Outputs go to ``reports/walkforward/2026-04-26_<feature_set>_<symbol>.json``
and ``reports/walkforward/2026-04-26_<feature_set>_all.json`` plus a
matching ``.md``. Same folds, hyper-params, seed, and sample selection
across v1 and v2 -- the ONLY difference is the feature set.

Usage
-----
    python tools/walkforward_lab.py
    python tools/walkforward_lab.py --symbol XAUUSD
    python tools/walkforward_lab.py --symbol all --sl 1.5 --tp 3.0
    python tools/walkforward_lab.py --symbol all --feature-set v1 --seed 42
    python tools/walkforward_lab.py --symbol all --feature-set v2 --seed 42

Read-only against historical CSVs. Safe to run while the brain is live.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = REPO_ROOT / "reports" / "walkforward"

# Same team mapping as elsewhere in the project.
TEAMS: Dict[str, str] = {
    "XAUUSD": "METALS",
    "XAGUSD": "METALS",
    "GBPJPY": "FOREX",
    "USDCAD": "FOREX",
    "USDCHF": "FOREX",
    "EURUSD": "FOREX",
    "GBPUSD": "FOREX",
    "AUDUSD": "FOREX",
    "USDJPY": "FOREX",
    "NZDUSD": "FOREX",
    "EURJPY": "FOREX",
    "AUDJPY": "FOREX",
    "CADJPY": "FOREX",
    "EURGBP": "FOREX",
    "BTCUSD": "CRYPTO",
    "ETHUSD": "CRYPTO",
    "XTIUSD": "COMMODITIES",
    "XBRUSD": "COMMODITIES",
    "XNGUSD": "COMMODITIES",
}


@dataclass
class SymbolResult:
    symbol: str
    team: str
    rows: int = 0
    bars_scanned: int = 0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    expectancy_R: float = 0.0
    gross_R: float = 0.0
    sharpe_proxy: float = 0.0
    error: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    @property
    def has_edge(self) -> bool:
        return self.error is None and self.trades >= 30 and self.expectancy_R > 0.05


def _csv_path(symbol: str) -> Path:
    return REPO_ROOT / "data" / f"{symbol.lower()}_m5_history.csv"


def _load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ("time", "datetime", "date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
            break
    return df


def run_one_symbol(symbol: str, sl_atr_mult: float, tp_atr_mult: float) -> SymbolResult:
    team = TEAMS.get(symbol.upper(), "UNKNOWN")
    res = SymbolResult(symbol=symbol.upper(), team=team)
    csv = _csv_path(symbol)
    if not csv.exists():
        res.error = f"CSV missing: {csv.name}"
        return res
    try:
        df = _load_csv(csv)
        res.rows = len(df)
    except Exception as e:
        res.error = f"load failed: {e}"
        return res
    try:
        from tools.backtest import run_ea_parity_backtest  # type: ignore
    except Exception as e:
        res.error = f"import run_ea_parity_backtest failed: {e}"
        return res
    try:
        out = run_ea_parity_backtest(df, sl_atr_mult=sl_atr_mult, tp_atr_mult=tp_atr_mult)
    except Exception as e:
        res.error = f"backtest crashed: {e}"
        res.notes.append(traceback.format_exc(limit=3))
        return res

    res.bars_scanned = int(out.get("bars_scanned", 0) or 0)
    res.trades = int(out.get("trades", 0) or 0)
    res.wins = int(out.get("wins", 0) or 0)
    res.losses = int(out.get("losses", 0) or 0)
    res.win_rate = float(out.get("win_rate", 0.0) or 0.0)
    res.expectancy_R = float(out.get("expectancy_R", 0.0) or 0.0)
    res.gross_R = float(out.get("gross_R", 0.0) or 0.0)
    res.sharpe_proxy = float(out.get("sharpe_proxy", 0.0) or 0.0)

    if res.trades == 0:
        res.notes.append("zero trades over full history")
    if res.trades > 0 and res.trades < 30:
        res.notes.append(f"only {res.trades} trades - statistical noise dominates")
    if res.expectancy_R < 0:
        res.notes.append("negative expectancy - rule has anti-edge here")
    if 0 <= res.expectancy_R <= 0.05:
        res.notes.append("near-zero expectancy - no edge")

    return res


def render_markdown(results: List[SymbolResult], sl: float, tp: float) -> str:
    stamp = datetime.now(timezone.utc).isoformat()
    sorted_res = sorted(results, key=lambda r: (r.error is not None, -r.expectancy_R))

    has_edge = [r for r in sorted_res if r.has_edge]
    no_edge = [r for r in sorted_res if r.error is None and not r.has_edge]
    errored = [r for r in sorted_res if r.error is not None]

    md = [
        f"# Walk-forward R&D — per-symbol edge report",
        "",
        f"_Generated: {stamp}_",
        f"_Backtest params: SL = {sl}*ATR, TP = {tp}*ATR_",
        "",
        f"**Coverage:** {len(results)} symbols. "
        f"{len(has_edge)} with edge, {len(no_edge)} without, {len(errored)} errored.",
        "",
    ]

    def _table(rs: List[SymbolResult]) -> List[str]:
        rows = [
            "| symbol | team | trades | WR | expectancy_R | gross_R | sharpe | notes |",
            "|--------|------|-------:|---:|-------------:|--------:|-------:|:------|",
        ]
        for r in rs:
            wr = f"{r.win_rate * 100:.1f}%" if r.trades else "-"
            rows.append(
                f"| {r.symbol} | {r.team} | {r.trades} | {wr} | "
                f"{r.expectancy_R:+.3f} | {r.gross_R:+.2f} | "
                f"{r.sharpe_proxy:.2f} | {'; '.join(r.notes) or '-'} |"
            )
        return rows

    md += ["## Symbols with edge (expectancy_R > 0.05 and trades >= 30)", ""]
    md += _table(has_edge) if has_edge else ["_(none)_"]
    md += ["", "## Symbols WITHOUT edge", ""]
    md += _table(no_edge) if no_edge else ["_(none)_"]
    if errored:
        md += ["", "## Errored", ""]
        for r in errored:
            md.append(f"- **{r.symbol}** ({r.team}): {r.error}")

    md += [
        "",
        "## How to read this",
        "",
        "- **expectancy_R > 0.05** = positive edge after costs (rough cut). Add to live trading rotation.",
        "- **expectancy_R near 0** = no signal — either tighten gates or rotate the symbol off the live list.",
        "- **expectancy_R < 0** = anti-edge — rule disagrees with reality. "
        "Investigate before changing thresholds; could be data alignment.",
        "- **trades < 30** = numbers are noise; look at rolling regime instead.",
    ]
    return "\n".join(md) + "\n"


# ---------------------------------------------------------------------------
# Phase B2-research: ML walk-forward with selectable FEATURE_COLS
#
# This block is fully additive -- the EA-parity path above (run_one_symbol /
# render_markdown) is unchanged. The ML mode is only entered when
# --feature-set is passed on the CLI.

ML_HOLD_BARS = 12  # 12 M5 bars = 1 H1 forward window
ML_TP_R = 2.0  # +1 label
ML_SL_R = 1.0  # -1 label
ML_FOLDS = 5
ML_TRAIN_FRAC = 0.8  # used only as a sanity floor; folds drive the split
ML_PURGE_BARS = ML_HOLD_BARS  # purge the overlap between train and test


@dataclass
class MLSymbolResult:
    symbol: str
    team: str
    feature_set: str
    rows: int = 0
    n_features: int = 0
    n_samples: int = 0
    n_trades: int = 0
    win_rate: float = 0.0
    expectancy_R: float = 0.0
    max_dd: float = 0.0
    oos_acc: float = 0.0
    oos_acc_per_fold: List[float] = field(default_factory=list)
    nan_drop_rows: int = 0
    smartmoney_all_nan: bool = False
    error: Optional[str] = None
    notes: List[str] = field(default_factory=list)


def _resample_h1_for_ml(df: pd.DataFrame) -> pd.DataFrame:
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
    return (
        df.resample("60min")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )


def _label_triple_barrier(df_h1: pd.DataFrame) -> pd.Series:
    """Return labels in {-1, 0, +1} for each bar based on which barrier
    is touched first within ML_HOLD_BARS forward bars. ATR-anchored.
    """
    h, l, c = df_h1["high"], df_h1["low"], df_h1["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    out = pd.Series(0, index=df_h1.index, dtype=int)
    closes = c.values
    highs = df_h1["high"].values
    lows = df_h1["low"].values
    a = atr.values
    n = len(df_h1)
    for i in range(n - ML_HOLD_BARS - 1):
        if not np.isfinite(a[i]) or a[i] <= 0:
            continue
        entry = closes[i]
        tp_long = entry + ML_TP_R * a[i]
        sl_long = entry - ML_SL_R * a[i]
        tp_short = entry - ML_TP_R * a[i]
        sl_short = entry + ML_SL_R * a[i]
        long_hit = 0
        short_hit = 0
        for j in range(i + 1, i + 1 + ML_HOLD_BARS):
            hi, lo = highs[j], lows[j]
            if long_hit == 0:
                if lo <= sl_long:
                    long_hit = -1
                elif hi >= tp_long:
                    long_hit = +1
            if short_hit == 0:
                if hi >= sl_short:
                    short_hit = -1
                elif lo <= tp_short:
                    short_hit = +1
            if long_hit and short_hit:
                break
        # Aggregate: +1 if long won and short didn't, -1 reverse, 0 ambiguous
        if long_hit == +1 and short_hit != +1:
            out.iloc[i] = +1
        elif short_hit == +1 and long_hit != +1:
            out.iloc[i] = -1
    return out


def _run_ml_walkforward(
    symbol: str,
    feature_set: str,
    seed: int,
    folds: int,
) -> MLSymbolResult:
    """Train+eval LightGBM 3-class with purged walk-forward folds."""
    team = TEAMS.get(symbol.upper(), "UNKNOWN")
    res = MLSymbolResult(symbol=symbol.upper(), team=team, feature_set=feature_set)

    csv = _csv_path(symbol)
    if not csv.exists():
        res.error = f"CSV missing: {csv.name}"
        return res
    try:
        df_m5 = _load_csv(csv)
        res.rows = len(df_m5)
    except Exception as e:
        res.error = f"load failed: {e}"
        return res

    try:
        df_h1 = _resample_h1_for_ml(df_m5)
    except Exception as e:
        res.error = f"resample failed: {e}"
        return res

    # Choose feature builder + columns
    try:
        if feature_set == "v1":
            from ai_trading_agents.trend_master_brain import FEATURE_COLS, build_features

            feat_cols: List[str] = list(FEATURE_COLS)
            feats_df = build_features(df_h1)
        elif feature_set == "v2":
            from ai_trading_agents.feature_cols_v2 import (
                FEATURE_COLS_V2,
                SMARTMONEY_COLS,
                build_features_v2,
            )

            feat_cols = list(FEATURE_COLS_V2)
            try:
                feats_df = build_features_v2(df_h1)
            except Exception as e:
                # Cross-asset fetch may fail offline. Fall back: build v1 then add NaN columns.
                from ai_trading_agents.trend_master_brain import build_features

                feats_df = build_features(df_h1).copy()
                for c in SMARTMONEY_COLS:
                    feats_df[c] = np.nan
                res.notes.append(f"smartmoney fetch unavailable ({e}); columns are NaN")
            sm_present = [c for c in SMARTMONEY_COLS if c in feats_df.columns]
            if sm_present:
                res.smartmoney_all_nan = bool(feats_df[sm_present].isna().all().all())
        else:
            res.error = f"unknown feature_set: {feature_set}"
            return res
    except Exception as e:
        res.error = f"feature build failed: {e}"
        return res

    res.n_features = len(feat_cols)

    # Labels (triple-barrier on H1 close-to-close).
    try:
        y_full = _label_triple_barrier(df_h1)
    except Exception as e:
        res.error = f"label failed: {e}"
        return res

    df_join = feats_df.copy()
    df_join["__y__"] = y_full.reindex(df_join.index).fillna(0).astype(int)
    df_join = df_join.iloc[: -ML_HOLD_BARS - 2]  # drop the unlabelable tail

    missing = [c for c in feat_cols if c not in df_join.columns]
    if missing:
        res.error = f"missing feature columns: {missing[:5]}"
        return res

    # Drop all-NaN columns from feat_cols (e.g. EIA NG when EIA_API_KEY isn't
    # set -- the cross-asset module surfaces ng_storage_delta_z as a NaN
    # column to keep the schema stable, but dropna(subset=feat_cols) would
    # then wipe every row). Note the dropped columns in result so the report
    # makes the data-availability gap explicit instead of silent.
    all_nan_cols = [c for c in feat_cols if df_join[c].isna().all()]
    if all_nan_cols:
        res.notes.append(f"dropped all-NaN columns: {all_nan_cols}")
        feat_cols = [c for c in feat_cols if c not in all_nan_cols]
        if not feat_cols:
            res.error = "all feature columns are NaN"
            return res
        res.n_features = len(feat_cols)

    pre = len(df_join)
    df_join = df_join.dropna(subset=feat_cols + ["__y__"])
    res.nan_drop_rows = pre - len(df_join)
    res.n_samples = len(df_join)

    if res.n_samples < 200:
        res.error = f"too few samples after dropna ({res.n_samples})"
        return res

    # Map labels to 0/1/2 for LightGBM multiclass.
    y_raw = df_join["__y__"].values
    label_map = {-1: 0, 0: 1, 1: 2}
    inv_label_map = {v: k for k, v in label_map.items()}
    y_enc = np.array([label_map[int(v)] for v in y_raw], dtype=int)
    X = df_join[feat_cols].values.astype(np.float64)

    try:
        import lightgbm as lgb  # type: ignore
    except Exception as e:
        res.error = f"lightgbm import failed: {e}"
        return res

    n = len(X)
    fold_size = n // (folds + 1)
    if fold_size < 50:
        res.error = f"folds too small (fold_size={fold_size})"
        return res

    accs: List[float] = []
    oos_signal: List[int] = []  # -1/0/+1
    oos_idx_list: List[int] = []

    for k in range(folds):
        train_end = fold_size * (k + 1)
        test_start = train_end + ML_PURGE_BARS  # purge gap
        test_end = test_start + fold_size
        if test_end > n:
            break
        X_tr = X[:train_end]
        y_tr = y_enc[:train_end]
        X_te = X[test_start:test_end]
        y_te = y_enc[test_start:test_end]

        if len(np.unique(y_tr)) < 2:
            continue

        model = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=3,
            n_estimators=120,
            learning_rate=0.05,
            num_leaves=31,
            min_data_in_leaf=20,
            feature_fraction=0.9,
            bagging_fraction=0.9,
            bagging_freq=5,
            random_state=seed,
            verbosity=-1,
            deterministic=True,
        )
        model.fit(X_tr, y_tr)
        pred = model.predict(X_te)
        accs.append(float((pred == y_te).mean()))
        for j, p in enumerate(pred):
            oos_signal.append(inv_label_map[int(p)])
            oos_idx_list.append(test_start + j)

    if not accs:
        res.error = "no usable folds"
        return res

    res.oos_acc_per_fold = [round(a, 4) for a in accs]
    res.oos_acc = float(np.mean(accs))

    # Trade economics: take an OOS prediction whenever signal != 0; outcome is the
    # corresponding triple-barrier label (already in y_raw at that index).
    trades_R: List[float] = []
    for sig, idx in zip(oos_signal, oos_idx_list):
        if sig == 0:
            continue
        # Look up triple-barrier label at that bar; if it matches the side,
        # +ML_TP_R, if it's the opposite side, -ML_SL_R, if it was 0, mark
        # to last close in R-units (approximate -- count as 0 since we
        # don't have a clean MTM here, conservative).
        actual = int(y_raw[idx])
        if actual == sig:
            trades_R.append(+ML_TP_R)
        elif actual == -sig:
            trades_R.append(-ML_SL_R)
        else:
            trades_R.append(0.0)

    res.n_trades = len(trades_R)
    if trades_R:
        wins = sum(1 for r in trades_R if r > 0)
        res.win_rate = wins / len(trades_R)
        res.expectancy_R = float(np.mean(trades_R))
        # Equity curve max drawdown in R units
        eq = np.cumsum(trades_R)
        peak = np.maximum.accumulate(eq)
        dd = peak - eq
        res.max_dd = float(dd.max()) if len(dd) else 0.0

    return res


def _summarise_ml_results(results: List[MLSymbolResult]) -> Dict[str, Any]:
    by_team: Dict[str, List[MLSymbolResult]] = {}
    for r in results:
        by_team.setdefault(r.team, []).append(r)
    team_aggs: Dict[str, Any] = {}
    ok = [r for r in results if r.error is None]
    for team, rs in by_team.items():
        ok_team = [r for r in rs if r.error is None]
        if not ok_team:
            team_aggs[team] = {"n": 0, "mean_expR": None, "mean_oos_acc": None}
            continue
        team_aggs[team] = {
            "n": len(ok_team),
            "mean_expR": float(np.mean([r.expectancy_R for r in ok_team])),
            "mean_oos_acc": float(np.mean([r.oos_acc for r in ok_team])),
            "mean_WR": float(np.mean([r.win_rate for r in ok_team])),
            "mean_trades": float(np.mean([r.n_trades for r in ok_team])),
        }
    overall = {
        "n_ok": len(ok),
        "n_err": len([r for r in results if r.error is not None]),
        "mean_expR": float(np.mean([r.expectancy_R for r in ok])) if ok else None,
        "mean_oos_acc": float(np.mean([r.oos_acc for r in ok])) if ok else None,
    }
    return {"per_team": team_aggs, "overall": overall}


def _ml_main(args: argparse.Namespace) -> int:
    targets = list(TEAMS.keys()) if args.symbol.lower() == "all" else [args.symbol.upper()]
    feature_set = args.feature_set
    seed = args.seed
    folds = args.folds

    print(f"[ml-mode] feature_set={feature_set} seed={seed} folds={folds} symbols={len(targets)}")
    t0 = datetime.now(timezone.utc)

    results: List[MLSymbolResult] = []
    for sym in targets:
        print(f"[ml] {sym} ...", end=" ", flush=True)
        r = _run_ml_walkforward(sym, feature_set, seed, folds)
        if r.error:
            print(f"ERROR: {r.error}")
        else:
            print(
                f"n={r.n_samples} feats={r.n_features} trades={r.n_trades} "
                f"WR={r.win_rate * 100:.1f}% expR={r.expectancy_R:+.3f} "
                f"acc={r.oos_acc:.3f}"
            )
        results.append(r)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    aggregate = _summarise_ml_results(results)
    runtime_sec = (datetime.now(timezone.utc) - t0).total_seconds()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feature_set": feature_set,
        "seed": seed,
        "folds": folds,
        "runtime_sec": round(runtime_sec, 2),
        "aggregate": aggregate,
        "results": [asdict(r) for r in results],
    }
    json_all = OUT_DIR / f"{stamp}_{feature_set}_all.json"
    json_all.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    # Also one tiny per-symbol json for downstream diff tools.
    for r in results:
        per = OUT_DIR / f"{stamp}_{feature_set}_{r.symbol}.json"
        per.write_text(json.dumps(asdict(r), indent=2, default=str), encoding="utf-8")

    md_lines = [
        f"# Walk-forward ML R&D ({feature_set}, seed={seed})",
        "",
        f"_Generated: {datetime.now(timezone.utc).isoformat()}_  ",
        f"_Runtime: {runtime_sec:.1f}s_",
        "",
        "| symbol | team | feats | n_samples | trades | WR% | expR | maxDD | oos_acc |",
        "|--------|------|-----:|----------:|-------:|----:|-----:|------:|--------:|",
    ]
    for r in results:
        if r.error:
            md_lines.append(f"| {r.symbol} | {r.team} | - | - | - | - | - | - | ERR: {r.error} |")
        else:
            md_lines.append(
                f"| {r.symbol} | {r.team} | {r.n_features} | {r.n_samples} | "
                f"{r.n_trades} | {r.win_rate * 100:.1f} | {r.expectancy_R:+.3f} | "
                f"{r.max_dd:.2f} | {r.oos_acc:.3f} |"
            )
    md_path = OUT_DIR / f"{stamp}_{feature_set}_all.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"\n[done] wrote {json_all}")
    print(f"[done] wrote {md_path}")
    print(f"[done] wrote {len(results)} per-symbol json files")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--symbol", default="all", help="Single symbol or 'all' (default)")
    ap.add_argument("--sl", type=float, default=1.5, help="SL multiplier of ATR")
    ap.add_argument("--tp", type=float, default=3.0, help="TP multiplier of ATR")
    ap.add_argument(
        "--feature-set",
        choices=("v1", "v2"),
        default=None,
        help="If set, run ML walk-forward in v1 or v2 mode (Phase B2-research) "
        "instead of the default EA-parity backtest.",
    )
    ap.add_argument("--seed", type=int, default=42, help="Random seed for ML mode (default 42)")
    ap.add_argument("--folds", type=int, default=ML_FOLDS, help="ML walk-forward fold count")
    args = ap.parse_args()

    if args.feature_set is not None:
        return _ml_main(args)

    targets = list(TEAMS.keys()) if args.symbol.lower() == "all" else [args.symbol.upper()]

    results: List[SymbolResult] = []
    for sym in targets:
        print(f"[run] {sym} ...", end=" ", flush=True)
        r = run_one_symbol(sym, args.sl, args.tp)
        if r.error:
            print(f"ERROR: {r.error}")
        else:
            print(
                f"trades={r.trades}  WR={r.win_rate * 100:.1f}%  "
                f"exp_R={r.expectancy_R:+.3f}  sharpe={r.sharpe_proxy:.2f}"
            )
        results.append(r)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    md_path = OUT_DIR / f"{stamp}.md"
    json_path = OUT_DIR / f"{stamp}.json"

    md_path.write_text(render_markdown(results, args.sl, args.tp), encoding="utf-8")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "params": {"sl_atr_mult": args.sl, "tp_atr_mult": args.tp},
        "results": [asdict(r) for r in results],
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"\n[done] wrote {md_path}")
    print(f"[done] wrote {json_path}")

    # Exit code: 0 if any symbol shows edge, 1 if every symbol is flat / negative
    any_edge = any(r.has_edge for r in results)
    return 0 if any_edge else 1


if __name__ == "__main__":
    raise SystemExit(main())
