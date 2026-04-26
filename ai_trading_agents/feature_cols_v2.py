"""FEATURE_COLS_V2 -- research-only candidate feature set (Phase B2-research).

This module is NEVER imported by trend_master_brain.py. It exists solely so
tools/walkforward_lab.py can run a controlled v1-vs-v2 comparison without
touching the live FEATURE_COLS list.

If the comparison report concludes PROMOTE, a separate Phase B2-deploy commit
will (a) merge FEATURE_COLS_V2 into the canonical FEATURE_COLS in
trend_master_brain.py, (b) retrain trend_master_model.lgb, (c) update
ml_align.py with the new feature contract.

Junction discipline
-------------------
This file lives inside ai_trading_agents/ (the NTFS junction). We use
``Path(__file__).parent.parent`` (NEVER ``.resolve()``) for project root,
because ``.resolve()`` follows the junction to C:\\ and breaks every config
lookup. See CLAUDE.md, "Don't" #1.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ai_trading_agents import cross_asset_join
from ai_trading_agents.trend_master_brain import FEATURE_COLS, build_features

# Junction-safe -- DO NOT use .resolve() here.
PROJECT_ROOT = Path(__file__).parent.parent

# 7 CFTC COT spec_delta_z + 1 EIA NG storage_delta_z, in the same order as
# cross_asset_join.DEFAULT_COT_CONTRACTS (GC, SI, 6E, 6J, 6C, CL, BTC).
SMARTMONEY_COLS: list[str] = [
    "GC_spec_delta_z",
    "SI_spec_delta_z",
    "6E_spec_delta_z",
    "6J_spec_delta_z",
    "6C_spec_delta_z",
    "CL_spec_delta_z",
    "BTC_spec_delta_z",
    "ng_storage_delta_z",
]
FEATURE_COLS_V2: list[str] = list(FEATURE_COLS) + SMARTMONEY_COLS


def build_features_v2(df_h1: pd.DataFrame) -> pd.DataFrame:
    """Build v1 features then forward-fill smart-money columns onto the H1 frame.

    Cache-aware: cross_asset_join uses cached parquet under data/external/. If
    cache is empty/stale and no network is available, the joined columns will
    be all-NaN and the walkforward will dropna() them out. This is a designed
    failure mode -- the fact gets surfaced in the comparison report.

    Parameters
    ----------
    df_h1 : pd.DataFrame
        H1 OHLCV frame with a DatetimeIndex (tz-aware UTC preferred). Not
        mutated -- a new frame is returned.

    Returns
    -------
    pd.DataFrame
        Frame with all v1 feature columns plus the 8 smart-money columns
        listed in SMARTMONEY_COLS. Rows where any smart-money column is
        NaN are NOT dropped here -- callers (e.g. walkforward training)
        should dropna(subset=FEATURE_COLS_V2) before fitting.
    """
    base = build_features(df_h1)
    enriched = cross_asset_join.align_to_h1(base, include_smartmoney=True)
    return enriched


__all__ = [
    "FEATURE_COLS_V2",
    "SMARTMONEY_COLS",
    "build_features_v2",
    "PROJECT_ROOT",
]
