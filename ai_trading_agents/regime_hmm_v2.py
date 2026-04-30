"""Phase E scaffolding: Gaussian Mixture regime classifier (no new deps).

Why
---
Per ``CLAUDE.md`` "Open R&D priorities" #8, HMM-gated experts is a
post-D-phase target. The classical implementation needs ``hmmlearn``,
which is a new dependency — and the operator's invariant says
"Don't introduce new dependencies casually" (Defender attack surface,
recent quarantine incident).

This module gives us an HMM-equivalent without the new pip dep:

- A 3-component Gaussian Mixture from ``sklearn.mixture`` (already a
  transitive dep of LightGBM's stack) classifies (volatility, trend)
  into TREND / RANGE / VOLATILE-CHOP.
- The fitted assignments + per-state posteriors are exactly the inputs
  an HMM-gated expert wants. We're trading the time-correlation prior
  of an HMM for a memoryless GMM; in practice rolling features
  (vol_5m, atr_norm) carry most of the time structure anyway.

This module does **not** wire into the live brain. It is a feature
producer for the V3+ trainer (FEATURE_COLS_V3 = V2 + D2 + regime
posteriors) and for future gate logic. Promotion to the live infer
path requires explicit operator approval per CLAUDE.md.

Junction discipline
-------------------
This file lives inside the ``ai_trading_agents/`` junction. Use the
centralised path helper, not raw ``Path(__file__).parent.parent``.
See docs/POSTMORTEMS/2026-04-30_junction_trap_silent_state_drift.md.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

_log = logging.getLogger(__name__)

# Number of regime states. 3 = trend / range / volatile-chop is the
# operator-friendly choice; 4 splits trend into bull/bear, which is
# already captured by the v1 ``ema_stack`` feature.
N_REGIMES = 3

# Canonical regime feature columns.
REGIME_FEATURE_COLS: List[str] = [
    "regime_state",  # 0..N_REGIMES-1, hard assignment
    "regime_post_0",  # posterior P(state=0 | x)
    "regime_post_1",
    "regime_post_2",
]


def _build_regime_inputs(df: pd.DataFrame) -> pd.DataFrame:
    """Pick the inputs the GMM clusters on.

    These are intentionally short so the GMM converges fast and the
    states are interpretable: ATR (vol), abs ema_slope (trend
    strength), abs rsi - 50 (momentum centred at neutral).
    """
    feats = pd.DataFrame(index=df.index)

    if "atr" in df.columns and "close" in df.columns:
        feats["atr_norm"] = df["atr"] / df["close"].replace(0, np.nan)
    elif "atr" in df.columns:
        feats["atr_norm"] = df["atr"]
    else:
        feats["atr_norm"] = np.nan

    # Trend strength via ema_slope or fallback to close diff.
    if "ema_slope" in df.columns:
        feats["abs_trend"] = df["ema_slope"].abs()
    elif "close" in df.columns:
        feats["abs_trend"] = df["close"].diff().abs()
    else:
        feats["abs_trend"] = np.nan

    # Distance from RSI-50 (momentum magnitude).
    if "rsi" in df.columns:
        feats["abs_rsi_50"] = (df["rsi"] - 50.0).abs()
    else:
        feats["abs_rsi_50"] = np.nan

    return feats


def fit_regime_model(df: pd.DataFrame, n_components: int = N_REGIMES, random_state: int = 42):
    """Fit a GaussianMixture on the regime inputs from ``df``.

    Returns ``(model, scaler)`` — both fitted. ``model.predict_proba``
    + ``scaler.transform`` reproduce the same posteriors on new data.
    Uses sklearn's GaussianMixture and StandardScaler — already
    available via the LightGBM/sklearn dep stack.
    """
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler

    feats = _build_regime_inputs(df).dropna()
    if feats.empty:
        raise ValueError("regime inputs empty after dropna; check input columns")

    scaler = StandardScaler()
    x = scaler.fit_transform(feats.to_numpy())
    model = GaussianMixture(
        n_components=n_components,
        covariance_type="full",
        n_init=4,
        random_state=random_state,
        reg_covar=1e-4,  # numerical guard
    )
    model.fit(x)
    return model, scaler


def predict_regime(df: pd.DataFrame, model, scaler) -> pd.DataFrame:
    """Return a DataFrame with REGIME_FEATURE_COLS aligned to ``df.index``.

    Missing-input rows are NaN; the dropna→predict→reindex pattern keeps
    output indexable to the original frame.
    """
    feats = _build_regime_inputs(df)
    valid = feats.dropna()
    out = pd.DataFrame(np.nan, index=df.index, columns=REGIME_FEATURE_COLS)
    if valid.empty:
        return out

    x = scaler.transform(valid.to_numpy())
    posteriors = model.predict_proba(x)  # (n, n_components)
    states = posteriors.argmax(axis=1)

    sub = pd.DataFrame(index=valid.index)
    sub["regime_state"] = states.astype(np.float64)
    for k in range(posteriors.shape[1]):
        sub[f"regime_post_{k}"] = posteriors[:, k]
    # Pad missing posterior columns with NaN if model has fewer components.
    for col in REGIME_FEATURE_COLS:
        if col not in sub.columns:
            sub[col] = np.nan

    return sub.reindex(df.index)


def add_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """Convenience: fit + predict on the same frame in one call.

    For walk-forward training this is wrong (look-ahead bias — fitting on
    the same data we predict). The trainer must call ``fit_regime_model``
    on the train fold and ``predict_regime`` on the test fold separately.

    This convenience function exists for live-inference scenarios where
    the operator passes a long historical window and only consumes the
    most recent row's posteriors.
    """
    out = df.copy()
    try:
        model, scaler = fit_regime_model(df)
        regime_df = predict_regime(df, model, scaler)
    except Exception as exc:
        _log.warning("add_regime_features failed (%s); regime cols filled NaN", exc)
        for col in REGIME_FEATURE_COLS:
            out[col] = np.nan
        return out

    for col in REGIME_FEATURE_COLS:
        out[col] = regime_df[col]
    return out


__all__ = [
    "N_REGIMES",
    "REGIME_FEATURE_COLS",
    "fit_regime_model",
    "predict_regime",
    "add_regime_features",
]
