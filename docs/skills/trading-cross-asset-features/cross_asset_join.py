"""
Merge cached cross-asset macro features into a per-symbol H1 DataFrame.

Use from ai_trading_agents/trend_master_brain.py::build_features:

    from ai_trading_agents.cross_asset_join import attach_macros
    df = attach_macros(df, symbol)

Forward-fills within session, NaN over weekend gap, adds is_stale_<feat> flags.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
CACHE_DIR = REPO_ROOT / "data" / "cross_asset"


def _load(name: str) -> pd.DataFrame | None:
    p = CACHE_DIR / f"{name}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.sort_values("ts")


def _is_weekend(ts: pd.Series) -> pd.Series:
    # Mon=0..Sun=6; FX weekend gap roughly Fri 22:00 UTC -> Sun 22:00 UTC
    dow = ts.dt.dayofweek
    h = ts.dt.hour
    return ((dow == 4) & (h >= 22)) | (dow == 5) | ((dow == 6) & (h < 22))


def _merge_with_stale(price_df: pd.DataFrame, macro_df: pd.DataFrame, value_cols: list[str], prefix: str) -> pd.DataFrame:
    if macro_df is None or macro_df.empty:
        for v in value_cols:
            price_df[f"{prefix}_{v}"] = np.nan
            price_df[f"is_stale_{prefix}_{v}"] = 1
        return price_df
    macro_df = macro_df.set_index("ts")
    aligned = macro_df[value_cols].reindex(price_df["ts"], method="ffill")
    aligned.index = price_df.index
    weekend = _is_weekend(price_df["ts"]).values
    for v in value_cols:
        col_name = f"{prefix}_{v}"
        price_df[col_name] = aligned[v].values
        price_df.loc[weekend, col_name] = np.nan
        # Stale flag: 1 if value carried forward >2h, else 0
        # (simple heuristic - full impl would compare ts of last actual update)
        ages = price_df.groupby((aligned[v].notna() != aligned[v].notna().shift()).cumsum()).cumcount()
        price_df[f"is_stale_{col_name}"] = (ages > 2).astype(int)
    return price_df


def attach_macros(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Merge dxy/vix/us10y macro columns into df keyed on `ts`. Pure function."""
    if "ts" not in df.columns:
        raise ValueError("attach_macros requires a 'ts' column with UTC timestamps")
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = _merge_with_stale(df, _load("dxy_h1"), ["close", "ret_1h"], "dxy")
    df = _merge_with_stale(df, _load("vix_h1"), ["close", "z_30d"], "vix")
    df = _merge_with_stale(df, _load("us10y_h1"), ["yield", "d1d"], "us10y")
    # Cheap derived: gold-oil ratio z-score from your own CSVs (optional)
    return df


if __name__ == "__main__":
    # Smoke test: print column names that would be added
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    args = ap.parse_args()
    df = pd.DataFrame({"ts": pd.date_range("2026-04-20", periods=24, freq="H", tz="UTC")})
    out = attach_macros(df, args.symbol)
    print("Added columns:", [c for c in out.columns if c not in {"ts"}])
