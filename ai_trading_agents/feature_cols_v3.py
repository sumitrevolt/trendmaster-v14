"""Phase D2/D3: Feature set v3 — V2 (33) + D2 (4) + D3 macro (3) = 40 cols.

This module is the single source of truth for the V3 feature contract.
It composes:

  - V2 (FEATURE_COLS_V2 = V1 + smartmoney): 33 cols
  - D2 (frac-diff + Hurst):                  4 cols
  - D3 macro (DXY/VIX/US10Y z-score):        3 cols

V3 is consumed by ``tools/train_v14_d2.py`` and (after operator
promotion) by the live brain via a future ``smartmoney_d2_enabled``
config flag. It does NOT replace V2 — both feature sets coexist so
older models keep working.

Junction discipline
-------------------
This file lives inside the ai_trading_agents/ junction.
Use ``ai_trading_agents._paths.project_root()``.
See docs/POSTMORTEMS/2026-04-30_junction_trap_silent_state_drift.md.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from ai_trading_agents import cross_asset_join
from ai_trading_agents._paths import project_root
from ai_trading_agents.feature_cols_v2 import (
    FEATURE_COLS_V2,
    SMARTMONEY_COLS,
    build_features_v2,
)
from ai_trading_agents.feature_eng_d2 import (
    D2_FEATURE_COLS,
    add_d2_features,
)
from ai_trading_agents.trend_master_brain import FEATURE_COLS

PROJECT_ROOT = project_root()
_log = logging.getLogger(__name__)

# Phase D3 macro columns. These are 60-day z-scores of daily closes,
# forward-filled onto the H1 index with a +21h NYC-close publish lag.
MACRO_COLS_V3: List[str] = [
    "DXY_close_z",
    "VIX_close_z",
    "US10Y_close_z",
]

# V3 feature contract: V2 + D2 + D3 macro = 40 cols total.
FEATURE_COLS_V3: List[str] = list(FEATURE_COLS_V2) + list(D2_FEATURE_COLS) + list(MACRO_COLS_V3)


def build_features_v3(
    df_h1: pd.DataFrame,
    *,
    symbol: str | None = None,
    cot_df: pd.DataFrame | None = None,
    eia_df: pd.DataFrame | None = None,
    macro_df: pd.DataFrame | None = None,
    fill_na_smartmoney: bool = False,
    fill_na_macro: bool = False,
) -> pd.DataFrame:
    """Build V3 feature matrix: V2 (33) + D2 (4) + D3 macro (3).

    Parameters
    ----------
    df_h1 : pd.DataFrame
        H1 OHLCV frame. Same contract as ``build_features_v2``.
    symbol : str | None
        For log messages only.
    cot_df, eia_df : pd.DataFrame | None
        Pre-fetched smartmoney frames (passed through to
        ``build_features_v2``).
    macro_df : pd.DataFrame | None
        Pre-fetched macro frame from ``cross_asset_join.fetch_macro_h1``.
        If None, the trainer is expected to fetch once and pass to all
        symbols (same pattern as cot/eia).
    fill_na_smartmoney : bool
        Forward to V2 builder.
    fill_na_macro : bool
        When True, all-NaN macro cols are filled with 0.0 for live
        inference. Default False (keep NaN so the trainer can drop
        them or measure availability).

    Returns
    -------
    pd.DataFrame
        Frame with all V2 cols + 4 D2 cols + 3 macro cols (40 total).
    """
    _sym_tag = f" {symbol}" if symbol else ""

    # Step 1: V2 (V1 + smartmoney) base.
    v2 = build_features_v2(
        df_h1,
        symbol=symbol,
        cot_df=cot_df,
        eia_df=eia_df,
        fill_na_smartmoney=fill_na_smartmoney,
    )

    # Step 2: D2 (frac-diff + Hurst). Uses the close column from the
    # original OHLCV frame (V2 doesn't preserve raw close — we read
    # from df_h1 to be safe).
    if "close" in df_h1.columns:
        d2 = add_d2_features(df_h1[["close"]])
        for col in D2_FEATURE_COLS:
            v2[col] = d2[col].reindex(v2.index)
    else:
        for col in D2_FEATURE_COLS:
            v2[col] = np.nan

    # Step 3: D3 macro. If macro_df is None, attempt to fetch (cheap
    # via in-memory cache). Failures degrade gracefully to all-NaN.
    if macro_df is None:
        try:
            macro_df = cross_asset_join._cached_fetch("macro_h1", cross_asset_join.fetch_macro_h1)
        except Exception as exc:
            if not cross_asset_join._macro_unavailable_warned[0]:
                _log.info(
                    "[V3%s] macro features unavailable (%s); cols filled NaN",
                    _sym_tag,
                    exc,
                )
                cross_asset_join._macro_unavailable_warned[0] = True
            macro_df = None

    if macro_df is not None and not macro_df.empty:
        try:
            aligned = cross_asset_join.macro_align_h1(v2.index, macro_df)
            for col in MACRO_COLS_V3:
                v2[col] = aligned[col].reindex(v2.index) if col in aligned.columns else np.nan
        except Exception as exc:
            _log.warning("[V3%s] macro_align_h1 failed (%s); macro NaN", _sym_tag, exc)
            for col in MACRO_COLS_V3:
                v2[col] = np.nan
    else:
        for col in MACRO_COLS_V3:
            v2[col] = np.nan

    if fill_na_macro:
        for col in MACRO_COLS_V3:
            if v2[col].isna().all():
                v2[col] = 0.0

    return v2


__all__ = [
    "FEATURE_COLS_V3",
    "MACRO_COLS_V3",
    "build_features_v3",
    "PROJECT_ROOT",
]
