"""
portfolio_risk.py — VaR / CVaR / Expected Shortfall for TrendMaster v14.

Why this exists
---------------
The existing risk stack handles *position-level* sizing + daily-DD limits
but has no *portfolio-level* risk metric. An institutional-grade system
answers three questions at any moment:

  1. VaR(95) — "with 95% confidence, losses tomorrow will be ≤ $X"
  2. CVaR(95) — "if we're in the 5% tail, expected loss is $Y"
  3. Cornish-Fisher VaR — VaR corrected for skewness + kurtosis (fat tails)

This module provides all three from the brain's own `recent_results`
ledger. Pure numpy, no scipy dependency for the core path.

Reference: PyQuantNews VaR/CVaR guide, Interactive Brokers IBKR Campus
"Risk Metrics in Python", osquant.com/papers/conditional-value-at-risk.

Integration (opt-in)
--------------------
Enable via `PORTFOLIO_RISK.enabled=True` in `config/settings.py`. When
enabled, `tick_all` writes the latest VaR/CVaR to metrics (if METRICS
also on) and the `/var` Telegram command returns a one-shot snapshot.
No veto logic attached — this is an observability + alerting primitive.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("portfolio_risk")


@dataclass
class VaRResult:
    method:        str          # "historical" | "parametric" | "cornish_fisher"
    confidence:    float        # 0.95, 0.99, etc.
    var:           float        # absolute loss value (positive number)
    cvar:          float        # expected shortfall
    n_samples:     int
    mean:          float
    std:           float
    skew:          float
    kurt:          float
    reason:        str = ""

    def as_dict(self) -> dict:
        return {
            "method":     self.method,
            "confidence": self.confidence,
            "var":        round(self.var, 4),
            "cvar":       round(self.cvar, 4),
            "n_samples":  self.n_samples,
            "mean":       round(self.mean, 6),
            "std":        round(self.std, 6),
            "skew":       round(self.skew, 4),
            "kurt":       round(self.kurt, 4),
            "reason":     self.reason,
        }


def _extract_pnl(entry) -> float:
    """Local PnL normaliser — mirrors trade_tracker.pnl_of."""
    if entry is None:
        return 0.0
    if isinstance(entry, (int, float)):
        return float(entry)
    if isinstance(entry, dict):
        for k in ("pnl", "r_mult", "r"):
            v = entry.get(k)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
    return 0.0


def _moments(arr: np.ndarray) -> Tuple[float, float, float, float]:
    """Return mean, std, skew, excess_kurtosis. Pure-numpy impl."""
    n = len(arr)
    if n < 2:
        return (float(arr[0]) if n == 1 else 0.0), 0.0, 0.0, 0.0
    m = float(arr.mean())
    s = float(arr.std(ddof=1))
    if s == 0 or not np.isfinite(s):
        return m, 0.0, 0.0, 0.0
    z = (arr - m) / s
    skew = float((z ** 3).mean())
    kurt = float((z ** 4).mean() - 3.0)
    return m, s, skew, kurt


def historical_var(pnls: Iterable, confidence: float = 0.95) -> VaRResult:
    """Empirical VaR — the `(1-confidence)` quantile of the realised
    loss distribution. Simplest and most robust."""
    arr = np.array([_extract_pnl(x) for x in pnls], dtype=float)
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n < 10:
        return VaRResult("historical", confidence, 0.0, 0.0, n, 0.0, 0.0, 0.0, 0.0,
                         reason=f"insufficient samples ({n} < 10)")
    q = 1.0 - confidence
    var_val = -float(np.quantile(arr, q))  # positive loss number
    tail = arr[arr <= np.quantile(arr, q)]
    cvar_val = -float(tail.mean()) if len(tail) else var_val
    m, s, sk, kt = _moments(arr)
    return VaRResult("historical", confidence, max(0.0, var_val),
                     max(0.0, cvar_val), n, m, s, sk, kt)


def parametric_var(pnls: Iterable, confidence: float = 0.95) -> VaRResult:
    """Variance-covariance VaR — assumes P&L is normal. Fast, but
    under-estimates tail when the real distribution is fat-tailed."""
    # Inverse standard-normal CDF for common confidence levels (no scipy dep).
    Z = {0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.99: 2.3263, 0.995: 2.5758}
    z = Z.get(round(confidence, 3), 1.6449)
    arr = np.array([_extract_pnl(x) for x in pnls], dtype=float)
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n < 10:
        return VaRResult("parametric", confidence, 0.0, 0.0, n, 0.0, 0.0, 0.0, 0.0,
                         reason=f"insufficient samples ({n} < 10)")
    m, s, sk, kt = _moments(arr)
    var_val = max(0.0, z * s - m)
    # CVaR for a normal = φ(z) / (1-α) × σ − μ
    pdf_z = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    cvar_val = max(0.0, (pdf_z / (1.0 - confidence)) * s - m)
    return VaRResult("parametric", confidence, var_val, cvar_val, n, m, s, sk, kt)


def cornish_fisher_var(pnls: Iterable, confidence: float = 0.95) -> VaRResult:
    """VaR adjusted for skew and kurtosis via the Cornish-Fisher expansion.

        z_cf = z + (z²-1)·S/6 + (z³-3z)·K/24 − (2z³-5z)·S²/36

    Captures fat-tail risk without a full distribution fit. Reference:
    osquant.com/papers/conditional-value-at-risk.
    """
    Z = {0.90: 1.2816, 0.95: 1.6449, 0.975: 1.9600, 0.99: 2.3263}
    z = Z.get(round(confidence, 3), 1.6449)
    arr = np.array([_extract_pnl(x) for x in pnls], dtype=float)
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n < 30:
        return VaRResult("cornish_fisher", confidence, 0.0, 0.0, n, 0.0, 0.0, 0.0, 0.0,
                         reason=f"insufficient samples ({n} < 30)")
    m, s, sk, kt = _moments(arr)
    z_cf = (z
            + (z * z - 1.0) * sk / 6.0
            + (z ** 3 - 3.0 * z) * kt / 24.0
            - (2.0 * z ** 3 - 5.0 * z) * (sk ** 2) / 36.0)
    var_val = max(0.0, z_cf * s - m)
    # CF-adjusted CVaR uses the same correction on the φ(z)/α term —
    # approximate form, good enough for monitoring.
    pdf_z = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    cvar_val = max(0.0, (pdf_z / (1.0 - confidence)) * s * (1.0 + sk * z / 6.0) - m)
    return VaRResult("cornish_fisher", confidence, var_val, cvar_val, n, m, s, sk, kt)


def snapshot(pnls: Iterable, confidence: float = 0.95) -> dict:
    """Compute all three methods at once — handy for dashboards."""
    return {
        "historical":     historical_var(pnls, confidence).as_dict(),
        "parametric":     parametric_var(pnls, confidence).as_dict(),
        "cornish_fisher": cornish_fisher_var(pnls, confidence).as_dict(),
    }


__all__ = [
    "VaRResult", "historical_var", "parametric_var", "cornish_fisher_var",
    "snapshot",
]
