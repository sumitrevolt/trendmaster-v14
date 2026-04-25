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

Usage
-----
    python tools/walkforward_lab.py
    python tools/walkforward_lab.py --symbol XAUUSD
    python tools/walkforward_lab.py --symbol all --sl 1.5 --tp 3.0

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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--symbol", default="all", help="Single symbol or 'all' (default)")
    ap.add_argument("--sl", type=float, default=1.5, help="SL multiplier of ATR")
    ap.add_argument("--tp", type=float, default=3.0, help="TP multiplier of ATR")
    args = ap.parse_args()

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
