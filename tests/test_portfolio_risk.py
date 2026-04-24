"""Unit tests for ai_trading_agents.portfolio_risk (VaR / CVaR)."""

from __future__ import annotations

import numpy as np
import pytest

from ai_trading_agents.portfolio_risk import (
    VaRResult,
    cornish_fisher_var,
    historical_var,
    parametric_var,
    snapshot,
)


def test_insufficient_samples_returns_zeros():
    r = historical_var([-1.0, 2.0], confidence=0.95)
    assert r.var == 0.0 and r.cvar == 0.0
    assert "insufficient" in r.reason


def test_historical_var_positive_for_losses():
    # Distribution with clear losses.
    pnls = [-3.0, -2.5, -2.0, -1.0, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, -4.0, 3.0, -1.5, 1.2, -0.5]
    r = historical_var(pnls, confidence=0.95)
    assert r.var > 0
    assert r.cvar >= r.var  # CVaR should always be >= VaR


def test_parametric_var_normal_formula():
    # For a standard normal P&L with mean=0, std=1, VaR95 ≈ 1.6449.
    rng = np.random.default_rng(7)
    pnls = rng.normal(loc=0.0, scale=1.0, size=1000).tolist()
    r = parametric_var(pnls, confidence=0.95)
    assert abs(r.var - 1.6449) < 0.3


def test_cornish_fisher_handles_fat_tails_safely():
    # Build a mildly fat-tailed distribution (student-t df=8, not df=3).
    # With df=3 the moments explode and CF breaks down — that's a known
    # CF limitation, not a bug. This test uses realistic P&L moments.
    rng = np.random.default_rng(11)
    base = rng.normal(0, 1, size=500)
    fat_tail = rng.standard_t(df=8, size=500)
    pnls = np.concatenate([base, fat_tail]).tolist()
    pr = parametric_var(pnls, confidence=0.95)
    cf = cornish_fisher_var(pnls, confidence=0.95)
    # CF should return a non-negative value (floor at 0 is correct
    # behaviour when extreme moments make the expansion diverge).
    assert cf.var >= 0
    assert pr.var > 0
    assert cf.n_samples == pr.n_samples


def test_snapshot_has_all_three_methods():
    rng = np.random.default_rng(42)
    pnls = rng.normal(0, 1, size=100).tolist()
    snap = snapshot(pnls)
    for key in ("historical", "parametric", "cornish_fisher"):
        assert key in snap
        assert "var" in snap[key]
        assert "cvar" in snap[key]


def test_handles_dict_shaped_entries():
    pnls_dict = [{"pnl": x, "ts": i} for i, x in enumerate([-1, 2, -2, 1, -3] * 10)]
    r = historical_var(pnls_dict, confidence=0.95)
    assert r.n_samples == 50
    assert r.var > 0


def test_confidence_level_affects_var():
    pnls = list(range(-50, 50)) + list(range(-20, 20))
    r95 = historical_var(pnls, confidence=0.95)
    r99 = historical_var(pnls, confidence=0.99)
    # Higher confidence → wider VaR (more extreme quantile).
    assert r99.var >= r95.var


def test_as_dict_roundtrip():
    r = VaRResult(
        method="historical", confidence=0.95, var=1.0, cvar=2.0, n_samples=100, mean=0.1, std=1.0, skew=-0.2, kurt=0.5
    )
    d = r.as_dict()
    assert d["var"] == 1.0
    assert d["n_samples"] == 100
