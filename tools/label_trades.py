"""
tools/label_trades.py — convert logs/trades.csv into R-multiple labels.

Why
---
FINAL_UPGRADE_REPORT.md flagged forward-return labelling as the reason
M5 ML didn't beat baseline. The right labels are the system's own trade
outcomes: did the setup the EA took actually pay out ≥ 1R?

Input columns expected in logs/trades.csv (standard MT5 history export)
-----------------------------------------------------------------------
    open_time, symbol, type (BUY/SELL), open_price, sl, tp,
    close_time, close_price, profit, ...

Output
------
    data/labels_{symbol}.csv with columns:
        time, symbol, direction, entry, sl, tp, r_multiple, won_R

`won_R = 1` when realized R >= 1 (a "good setup"), else 0.
This is the binary target for the "should I take this setup?" classifier
in tools/retrain_from_trades.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


REQUIRED = ["open_time", "symbol", "type", "open_price", "sl", "close_price"]


def label(trades_csv: Optional[str] = None,
          out_dir: Optional[str] = None,
          symbol_filter: Optional[str] = None) -> pd.DataFrame:
    path = Path(trades_csv) if trades_csv else _ROOT / "logs" / "trades.csv"
    if not path.exists():
        raise FileNotFoundError(f"No trades csv at {path}")
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"trades csv missing columns: {missing}")

    df["open_time"] = pd.to_datetime(df["open_time"], utc=True, errors="coerce")
    df = df.dropna(subset=["open_time"]).copy()
    df["direction"] = df["type"].str.upper().str.strip()
    df = df[df["direction"].isin(["BUY", "SELL"])]
    if symbol_filter:
        df = df[df["symbol"] == symbol_filter]

    # R = (close - entry) / |entry - sl|, flipped for shorts
    risk = (df["open_price"] - df["sl"]).abs()
    risk = risk.where(risk > 0)   # avoid /0
    move = df["close_price"] - df["open_price"]
    move = move.where(df["direction"] == "BUY", -move)
    df["r_multiple"] = (move / risk).round(3)
    df["won_R"] = (df["r_multiple"] >= 1.0).astype(int)

    out_root = Path(out_dir) if out_dir else _ROOT / "data"
    out_root.mkdir(parents=True, exist_ok=True)
    keep = ["open_time", "symbol", "direction", "open_price", "sl",
            "close_price", "r_multiple", "won_R"]
    for sym, g in df.groupby("symbol"):
        out = out_root / f"labels_{sym.lower()}.csv"
        g[keep].rename(columns={"open_time": "time",
                                "open_price": "entry"}).to_csv(out, index=False)
        print(f"wrote {out} — {len(g)} trades, won_R rate "
              f"{g['won_R'].mean():.2%}")
    return df[keep]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--trades", default=None)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--symbol", default=None)
    a = p.parse_args()
    label(a.trades, a.out_dir, a.symbol)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
