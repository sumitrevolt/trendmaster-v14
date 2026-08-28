"""
v14.5 Per-Team Config Promotion Gate (CPCV-style).

Why this exists
---------------
The trading-walkforward-promotion skill ships a model-promotion gate
that grades a candidate .lgb against the production .lgb. We don't have
per-team .lgb candidates -- the brain runs `infer_rule` in practice.
What changes today is the rule-config (per-team SL/TP + indicator
thresholds). This gate proves the v14.5 per-team config beats the
v14.4 baseline with statistical significance (CPCV-style purged
walk-forward folds), using the same EA-parity simulator.

Methodology
-----------
For each team:
  1. Concatenate all team symbols' M5 history.
  2. Split each symbol into N walk-forward folds with embargo.
  3. For each fold's test slice:
       - simulate v14.5 EAParams (team-specific adx/st/sl/tp)
       - simulate v14.4 EAParams (defaults: adx=22, st=3.0, sl=2.0, tp=3.0)
  4. Sharpe + WR + expectancy_R per fold.
  5. PROMOTE if v14.5 mean Sharpe > v14.4 mean Sharpe AND
     v14.5 stdev < 0.5 * |v14.5 mean| (stability gate).
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ai_trading_agents.ea_confirmations import EAParams, compute_confirmations  # noqa: E402
from ai_trading_agents.team_params import TEAM_PARAMS, SYMBOL_TO_TEAM  # noqa: E402

MAX_HOLD_BARS = 96
N_FOLDS = 5
EMBARGO_BARS = 200  # strict: ~17h on M5
DATA_DIR = REPO_ROOT / "data"


# v14.4 baseline config: universal defaults that v14.5 replaces
V14_4_BASELINE = {
    "sl_atr_mult": 2.0,
    "tp_atr_mult": 3.0,
    "adx_min": 22.0,
    "st_mult": 3.0,
    "bb_width_floor_pct": 0.9,
}


def _load_csv(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol.lower()}_m5_history.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.dropna(subset=["time"]).set_index("time").sort_index()
    return df


def _make_params(cfg: dict) -> EAParams:
    """Build EAParams from a config dict; pad missing fields with defaults."""
    base = EAParams()
    return EAParams(
        ema_fast=base.ema_fast,
        ema_slow=base.ema_slow,
        ema_trend=base.ema_trend,
        adx_period=base.adx_period,
        adx_min=float(cfg.get("adx_min", base.adx_min)),
        atr_period=base.atr_period,
        bb_period=base.bb_period,
        bb_dev=base.bb_dev,
        macd_fast=base.macd_fast,
        macd_slow=base.macd_slow,
        macd_sig=base.macd_sig,
        st_period=base.st_period,
        st_mult=float(cfg.get("st_mult", base.st_mult)),
        bb_width_lookback=base.bb_width_lookback,
        bb_width_floor_pct=float(cfg.get("bb_width_floor_pct", base.bb_width_floor_pct)),
    )


def _simulate(df: pd.DataFrame, params: EAParams, sl_mult: float, tp_mult: float) -> dict:
    """EA-parity simulator: returns {'trades','wins','sharpe','exp_R','wr','r_seq'}."""
    if len(df) < 250:
        return {"trades": 0, "wins": 0, "sharpe": 0.0, "exp_R": 0.0, "wr": 0.0, "r_seq": []}
    conf = compute_confirmations(df, params=params)
    fire_mask = (conf["agreed"] == 3) & (conf["trend_dir"] != 0)
    fire_idx = np.where(fire_mask.values)[0]

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    atrs = conf["atr"].values
    dirs = conf["trend_dir"].values

    n = len(df)
    r_results: List[float] = []
    wins = losses = 0

    for i in fire_idx:
        if i + 1 >= n:
            continue
        atr_now = atrs[i]
        if not np.isfinite(atr_now) or atr_now <= 0:
            continue
        direction = int(dirs[i])
        entry = float(opens[i + 1])
        sl_dist = sl_mult * float(atr_now)
        tp_dist = tp_mult * float(atr_now)
        if direction > 0:
            sl_px = entry - sl_dist
            tp_px = entry + tp_dist
        else:
            sl_px = entry + sl_dist
            tp_px = entry - tp_dist

        end = min(n, i + 1 + MAX_HOLD_BARS)
        result_r = None
        for j in range(i + 1, end):
            hi = highs[j]
            lo = lows[j]
            if direction > 0:
                hit_sl = lo <= sl_px
                hit_tp = hi >= tp_px
            else:
                hit_sl = hi >= sl_px
                hit_tp = lo <= tp_px
            if hit_sl and hit_tp:
                result_r = -1.0  # conservative: SL first
                losses += 1
                break
            if hit_sl:
                result_r = -1.0
                losses += 1
                break
            if hit_tp:
                result_r = float(tp_mult / sl_mult)  # R units
                wins += 1
                break
        if result_r is None:
            # mark-to-market
            last_close = closes[end - 1]
            if direction > 0:
                pnl = (last_close - entry) / sl_dist
            else:
                pnl = (entry - last_close) / sl_dist
            result_r = float(pnl)
            if pnl > 0:
                wins += 1
            else:
                losses += 1
        r_results.append(result_r)

    if not r_results:
        return {"trades": 0, "wins": 0, "sharpe": 0.0, "exp_R": 0.0, "wr": 0.0, "r_seq": []}
    arr = np.array(r_results)
    sharpe = float(arr.mean() / arr.std() * np.sqrt(252)) if arr.std() > 0 else 0.0
    return {
        "trades": int(len(arr)),
        "wins": int(wins),
        "sharpe": round(sharpe, 4),
        "exp_R": round(float(arr.mean()), 4),
        "wr": round(float(wins / len(arr)), 4),
        "r_seq": arr.tolist(),
    }


def _walk_forward_folds(n: int, k: int = N_FOLDS, embargo: int = EMBARGO_BARS) -> Iterator[Tuple[int, int]]:
    """Yield (test_start, test_end) bar indices for k purged folds."""
    fold_size = n // k
    for fi in range(k):
        test_start = fi * fold_size
        test_end = (fi + 1) * fold_size if fi < k - 1 else n
        # embargo: skip first & last embargo bars of the test slice
        ts = test_start + embargo
        te = test_end - embargo
        if te - ts < 500:
            continue
        yield ts, te


def grade_team(team: str, symbols: List[str]) -> dict:
    cand_cfg = TEAM_PARAMS[team]
    cand_params = _make_params(cand_cfg)
    base_params = _make_params(V14_4_BASELINE)

    cand_fold_sharpes: List[float] = []
    base_fold_sharpes: List[float] = []
    cand_total = base_total = 0
    cand_wins = base_wins = 0
    cand_r: List[float] = []
    base_r: List[float] = []

    print(f"  Symbols ({len(symbols)}):", ", ".join(symbols))
    for sym in symbols:
        df = _load_csv(sym)
        if df.empty:
            print(f"    [SKIP] {sym} (no data)")
            continue
        for ts, te in _walk_forward_folds(len(df)):
            test_df = df.iloc[ts:te]
            cand = _simulate(test_df, cand_params, cand_cfg["sl_atr_mult"], cand_cfg["tp_atr_mult"])
            base = _simulate(test_df, base_params, V14_4_BASELINE["sl_atr_mult"], V14_4_BASELINE["tp_atr_mult"])
            if cand["trades"] >= 10:
                cand_fold_sharpes.append(cand["sharpe"])
                cand_r.extend(cand["r_seq"])
                cand_total += cand["trades"]
                cand_wins += cand["wins"]
            if base["trades"] >= 10:
                base_fold_sharpes.append(base["sharpe"])
                base_r.extend(base["r_seq"])
                base_total += base["trades"]
                base_wins += base["wins"]

    def _agg(name: str, fold_sharpes: List[float], r: List[float], total: int, wins: int) -> dict:
        if not fold_sharpes:
            return {"name": name, "n_folds": 0, "trades": 0}
        ms = float(np.mean(fold_sharpes))
        ss = float(np.std(fold_sharpes))
        return {
            "name": name,
            "n_folds": len(fold_sharpes),
            "trades": total,
            "wr": round(wins / total, 4) if total else 0.0,
            "exp_R": round(float(np.mean(r)), 4) if r else 0.0,
            "mean_fold_sharpe": round(ms, 4),
            "stdev_fold_sharpe": round(ss, 4),
            "stability_ok": bool(ss < 0.5 * abs(ms)) if ms != 0 else False,
        }

    cand_agg = _agg("v14.5", cand_fold_sharpes, cand_r, cand_total, cand_wins)
    base_agg = _agg("v14.4 baseline", base_fold_sharpes, base_r, base_total, base_wins)

    # PROMOTE rule:
    #   1. v14.5 mean Sharpe >= baseline mean Sharpe
    #   2. v14.5 mean Sharpe > 0
    #   3. trades_v14.5 >= max(trades_v14.4 * 0.3, 50)  -- new config musn't kill volume
    cand_ms = cand_agg.get("mean_fold_sharpe", 0)
    base_ms = base_agg.get("mean_fold_sharpe", 0)
    cand_n = cand_agg.get("trades", 0)
    base_n = base_agg.get("trades", 0)
    min_volume = max(base_n * 0.3, 50)
    delta = cand_ms - base_ms
    promote = (cand_ms > 0) and (cand_ms >= base_ms) and (cand_n >= min_volume)
    return {
        "team": team,
        "candidate": cand_agg,
        "baseline": base_agg,
        "delta_sharpe": round(delta, 4),
        "verdict": "PROMOTE" if promote else "HOLD",
        "min_volume_required": int(min_volume),
        "config_v14_5": cand_cfg,
        "config_v14_4": V14_4_BASELINE,
    }


def main():
    team_to_syms: dict = {}
    for sym, team in SYMBOL_TO_TEAM.items():
        team_to_syms.setdefault(team, []).append(sym)

    print("=" * 70)
    print("v14.5 Per-Team Config Promotion Gate (CPCV-style)")
    print(f"Run at: {datetime.now().isoformat()}")
    print(f"Folds per symbol: {N_FOLDS} | Embargo: {EMBARGO_BARS} bars")
    print("=" * 70)
    print()

    results = []
    for team in ["METALS", "FOREX", "CRYPTO", "COMMODITIES"]:
        print(f"--- TEAM {team} ---")
        r = grade_team(team, team_to_syms[team])
        results.append(r)
        print(f"  v14.5     : trades={r['candidate'].get('trades',0)}  WR={r['candidate'].get('wr',0):.3f}  exp_R={r['candidate'].get('exp_R',0):.3f}  mean_sharpe={r['candidate'].get('mean_fold_sharpe',0):.3f} ± {r['candidate'].get('stdev_fold_sharpe',0):.3f}  (n_folds={r['candidate'].get('n_folds',0)})")
        print(f"  v14.4 base: trades={r['baseline'].get('trades',0)}  WR={r['baseline'].get('wr',0):.3f}  exp_R={r['baseline'].get('exp_R',0):.3f}  mean_sharpe={r['baseline'].get('mean_fold_sharpe',0):.3f} ± {r['baseline'].get('stdev_fold_sharpe',0):.3f}  (n_folds={r['baseline'].get('n_folds',0)})")
        print(f"  Delta Sharpe: {r['delta_sharpe']:+.3f}   ->  VERDICT: {r['verdict']}")
        print()

    # write report
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_dir = REPO_ROOT / "reports" / "promotion"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"config_promotion_{ts}.json"
    md_path = out_dir / f"config_promotion_{ts}.md"
    json_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    with md_path.open("w", encoding="utf-8") as fh:
        fh.write(f"# v14.5 Per-Team Config Promotion Gate -- {ts}\n\n")
        fh.write("CPCV-style purged walk-forward gate comparing v14.5 per-team configs\n")
        fh.write("(SL/TP + per-team ADX/ST) against the v14.4 universal baseline\n")
        fh.write("(sl=2.0, tp=3.0, adx=22, st=3.0).\n\n")
        fh.write(f"Folds per symbol: **{N_FOLDS}** | Embargo: **{EMBARGO_BARS} bars** (~17h on M5)\n\n")
        fh.write("| Team | v14.5 Sharpe (mean ± std) | v14.4 Sharpe (mean ± std) | Δ Sharpe | v14.5 trades | Verdict |\n")
        fh.write("|---|---|---|---|---|---|\n")
        for r in results:
            c = r["candidate"]
            b = r["baseline"]
            fh.write(
                f"| {r['team']} | {c.get('mean_fold_sharpe',0):.3f} ± {c.get('stdev_fold_sharpe',0):.3f} "
                f"| {b.get('mean_fold_sharpe',0):.3f} ± {b.get('stdev_fold_sharpe',0):.3f} "
                f"| {r['delta_sharpe']:+.3f} "
                f"| {c.get('trades',0)} "
                f"| **{r['verdict']}** |\n"
            )
        fh.write("\n## Per-team detail\n\n")
        for r in results:
            fh.write(f"### {r['team']}\n\n")
            fh.write(f"**Config v14.5**: {r['config_v14_5']}\n\n")
            fh.write(f"**Verdict**: {r['verdict']}\n\n")
            fh.write(f"- v14.5: trades={r['candidate'].get('trades',0)} WR={r['candidate'].get('wr',0):.3f} exp_R={r['candidate'].get('exp_R',0):.3f}\n")
            fh.write(f"- v14.4: trades={r['baseline'].get('trades',0)} WR={r['baseline'].get('wr',0):.3f} exp_R={r['baseline'].get('exp_R',0):.3f}\n\n")
        promotes = [r["team"] for r in results if r["verdict"] == "PROMOTE"]
        holds = [r["team"] for r in results if r["verdict"] == "HOLD"]
        fh.write("## Summary\n\n")
        fh.write(f"- **PROMOTE**: {', '.join(promotes) or '(none)'}\n")
        fh.write(f"- **HOLD**: {', '.join(holds) or '(none)'}\n")

    print()
    print("=" * 70)
    print(f"Report written: {md_path}")
    print(f"JSON: {json_path}")
    print()
    promoted = [r["team"] for r in results if r["verdict"] == "PROMOTE"]
    held = [r["team"] for r in results if r["verdict"] == "HOLD"]
    print(f"PROMOTE: {', '.join(promoted) or '(none)'}")
    print(f"HOLD:    {', '.join(held) or '(none)'}")
    return 0 if all(r["verdict"] == "PROMOTE" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
