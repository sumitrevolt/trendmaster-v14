"""Phase B2: Feature set v2 — v1 (25 cols) + smart-money cross-asset (8 cols) = 33 cols.

This module is the single source of truth for the V2 feature contract.
It imports the v1 builder (trend_master_brain.build_features) and the Phase B1
cross-asset harness (cross_asset_join.align_to_h1), stitches them together,
and exports the canonical V2 definitions used by:

  - tools/walkforward_lab.py   (``--feature-set v2``)
  - TrendMasterBrain.tick_once  (when CFG.smartmoney_features_enabled = True)
  - tools/train_v14_better.py   (Phase B3 retraining)

Smart-money columns (8 total):
    GC_spec_delta_z    -- COMEX Gold non-commercial net z-score (52-week)
    SI_spec_delta_z    -- COMEX Silver non-commercial net z-score
    6E_spec_delta_z    -- CME EUR/USD FX futures non-commercial net z-score
    6J_spec_delta_z    -- CME JPY FX futures non-commercial net z-score
    6C_spec_delta_z    -- CME CAD FX futures non-commercial net z-score
    CL_spec_delta_z    -- NYMEX Light Sweet Crude non-commercial net z-score
    BTC_spec_delta_z   -- CME Bitcoin non-commercial net z-score
    ng_storage_delta_z -- EIA weekly NG storage delta z-score (52-week)

Junction discipline
-------------------
This file lives inside ai_trading_agents/ (the NTFS junction). We use
``Path(__file__).parent.parent`` (NEVER ``.resolve()``) for project root,
because ``.resolve()`` follows the junction to C:\\ and breaks every config
lookup. See CLAUDE.md, "Don't" #1.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ai_trading_agents import cross_asset_join
from ai_trading_agents.trend_master_brain import FEATURE_COLS, build_features

# Junction-safe -- DO NOT use .resolve() here.
PROJECT_ROOT = Path(__file__).parent.parent
_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Symbol -> COT contract code mapping
# ---------------------------------------------------------------------------
# MT5 broker symbol -> CFTC legacy-fut contract code.
# Rationale from Phase A2 correlation study
# (reports/influencer_correlation_phaseA2_2026-04-26.md):
#   GC / SI  -> direct futures for XAUUSD / XAGUSD (EDGE-class verdicts).
#   6E       -> EUR FX futures; also USD-strength proxy for CHF/GBP pairs.
#   6J       -> JPY futures; covers all JPY-cross pairs.
#   6C       -> CAD futures for USDCAD.
#   CL       -> WTI light-sweet crude for XTIUSD and XBRUSD.
#   BTC      -> CME BTC futures; crypto sentiment proxy for ETHUSD too.
#   AUD/NZD  -> GC (both have documented gold-price correlation).
#   XNGUSD   -> CL (NG legacy-fut history is thin; EIA ng_storage_delta_z
#               supplements as the more robust NG fundamental signal).
SYMBOL_COT_MAP: dict[str, str] = {
    "XAUUSD": "GC",
    "XAGUSD": "SI",
    "EURUSD": "6E",
    "GBPUSD": "6E",  # GBP treated as EUR proxy (high EUR/GBP correlation)
    "USDCHF": "6E",  # CHF anti-dollar, same structural driver as EUR
    "EURGBP": "6E",
    "EURJPY": "6E",
    "USDJPY": "6J",
    "GBPJPY": "6J",
    "AUDJPY": "6J",
    "CADJPY": "6J",
    "USDCAD": "6C",
    "AUDUSD": "GC",  # AUD/gold documented correlation
    "NZDUSD": "GC",  # NZD/gold documented (weaker) correlation
    "XTIUSD": "CL",
    "XBRUSD": "CL",
    "XNGUSD": "CL",  # CL nearest available; EIA NG supplements
    "BTCUSD": "BTC",
    "ETHUSD": "BTC",  # ETH uses BTC as sentiment proxy
}

# ---------------------------------------------------------------------------
# Feature column constants
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# V2 feature builder
# ---------------------------------------------------------------------------


def build_features_v2(
    df_h1: pd.DataFrame,
    *,
    symbol: str | None = None,
    cot_df: pd.DataFrame | None = None,
    eia_df: pd.DataFrame | None = None,
    fill_na_smartmoney: bool = False,
) -> pd.DataFrame:
    """Build V2 feature matrix: V1 (25 cols) + smart-money cross-asset (8 cols).

    Cache-aware: cross_asset_join uses cached parquet under data/external/. If
    cache is empty/stale and no network is available, the joined columns will
    be all-NaN. With fill_na_smartmoney=False (default) the walkforward can
    measure the data-availability gap; with True the live brain fills 0.0 to
    prevent dropna() from killing all rows.

    Parameters
    ----------
    df_h1 : pd.DataFrame
        H1 OHLCV frame with a DatetimeIndex (tz-aware UTC preferred). Not
        mutated -- a new frame is returned.
    symbol : str | None
        MT5 symbol for log messages only. All 8 smart-money cols are always
        appended (FEATURE_COLS_V2 = 33 cols, fixed width regardless of symbol).
    cot_df, eia_df : pd.DataFrame | None
        Pre-fetched frames for tests / offline use. None = fetch live.
    fill_na_smartmoney : bool
        When True, entirely-NaN smart-money cols (EIA key missing, network
        down) are filled with 0.0 for live inference. Default False.

    Returns
    -------
    pd.DataFrame
        Frame with all V1 feature columns plus the 8 smart-money columns.
        Rows where any V1 column is NaN are NOT dropped here.
    """
    _sym_tag = f" {symbol}" if symbol else ""

    # Build V1 features first.
    base = build_features(df_h1)

    # Enrich the base frame with publish-lag-aware COT + EIA values.
    try:
        enriched = cross_asset_join.align_to_h1(
            base,
            include_smartmoney=True,
            cot_df=cot_df,
            eia_df=eia_df,
        )
    except Exception as exc:
        _log.warning(
            "[B2%s] align_to_h1 failed (%s); smart-money cols will be NaN",
            _sym_tag,
            exc,
        )
        enriched = base.copy()
        for col in SMARTMONEY_COLS:
            if col not in enriched.columns:
                enriched[col] = np.nan

    # Ensure all expected smart-money cols are present (guards against a
    # partial fetch where e.g. only COT succeeded but EIA key was absent).
    sm_hits = 0
    for col in SMARTMONEY_COLS:
        if col not in enriched.columns:
            enriched[col] = np.nan
        if not enriched[col].isna().all():
            sm_hits += 1

    # Optional 0-fill for all-NaN cols in live inference mode.
    if fill_na_smartmoney:
        for col in SMARTMONEY_COLS:
            if enriched[col].isna().all():
                enriched[col] = 0.0

    _log.info(
        "[B2%s] build_features_v2: %d/%d smartmoney cols have data (fill_na=%s)",
        _sym_tag,
        sm_hits,
        len(SMARTMONEY_COLS),
        fill_na_smartmoney,
    )
    return enriched


__all__ = [
    "SYMBOL_COT_MAP",
    "FEATURE_COLS_V2",
    "SMARTMONEY_COLS",
    "build_features_v2",
    "PROJECT_ROOT",
]
