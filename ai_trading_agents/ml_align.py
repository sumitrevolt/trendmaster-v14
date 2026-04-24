"""Feature-alignment helper for ML inference.

Extracted into its own module so it can be unit-tested without importing
the full brain (which pulls MetaTrader5 and other heavy deps at import
time).

Why this exists
---------------
On 2026-04-24 the top-level `trend_master_model.lgb` was retrained, and
after that every one of 18 diverse markets produced a confidence of
~0.344 +/- 0.005 and direction=NONE. That std across metals, forex,
crypto, and commodities is the signature of a LightGBM booster being
fed features in the wrong order (or under different names) from what it
was trained on. Without feature names on a numpy array, the booster
silently mixes up columns and outputs near-uniform probabilities.

`align_feature_row` uses `model.feature_name()` (LightGBM API, returns
the training-time feature order) to index the inference DataFrame, so
the model is always scored on the columns it was trained on, in the
order it was trained with -- regardless of whether the brain's local
FEATURE_COLS list drifted.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

import numpy as np
import pandas as pd


def trained_feature_names(model: Any) -> List[str]:
    """Best-effort extraction of training-time feature names.

    LightGBM Booster exposes `feature_name()` returning a list[str].
    Other libraries use `feature_names_in_` (sklearn >= 1.0) or
    `feature_name_` (lightgbm sklearn API). Returns [] if none are
    available.
    """
    # LightGBM Booster
    try:
        fn = getattr(model, "feature_name", None)
        if callable(fn):
            names = list(fn())
            if names:
                return [str(c) for c in names]
    except Exception:
        pass
    # sklearn / lightgbm sklearn-style
    for attr in ("feature_names_in_", "feature_name_"):
        try:
            names = getattr(model, attr, None)
            if names is not None:
                names = list(names)
                if names:
                    return [str(c) for c in names]
        except Exception:
            continue
    return []


def align_feature_row(
    x: pd.DataFrame,
    model: Any,
    fallback_cols: List[str],
) -> Tuple[Optional[np.ndarray], List[str], List[str]]:
    """Build a single-row feature array aligned to the model's trained order.

    Returns (feature_array, used_cols, missing_cols).

    - If the model exposes trained feature names, they are used to pick
      columns out of ``x`` in the right order.
    - Otherwise falls back to ``fallback_cols``.
    - If any required column is missing from ``x``, feature_array is
      None and ``missing_cols`` is populated; the caller should route
      to a rule-based fallback rather than feed zeros to the model.
    """
    trained_cols = trained_feature_names(model)
    cols = trained_cols if trained_cols else list(fallback_cols)
    if not cols:
        return None, [], []

    missing = [c for c in cols if c not in x.columns]
    if missing:
        return None, cols, missing

    row = x[cols].iloc[-1:].values
    return row, cols, []
