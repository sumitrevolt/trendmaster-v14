"""Unit tests for tools.slippage_model."""
from __future__ import annotations

import pytest

from tools.slippage_model import CostModel, DEFAULT_OCTAFX_PROFILE, Fill


def test_buy_pays_above_mid():
    m = CostModel(style="spread_linear")
    f = m.fill("EURUSD", "buy", 1.1000, lots=0.01)
    assert f.filled_price > 1.1000
    assert f.total_cost_usd >= 0.0


def test_sell_hits_below_mid():
    m = CostModel(style="spread_linear")
    f = m.fill("EURUSD", "sell", 1.1000, lots=0.01)
    assert f.filled_price < 1.1000


def test_flat_style_uses_fixed_cost():
    m = CostModel(style="flat", flat_cost_usd=0.50, slippage_pips=0.0)
    f = m.fill("EURUSD", "buy", 1.1000, lots=0.01)
    assert f.spread_cost_usd == pytest.approx(0.50)


def test_p95_spread_is_larger_than_median():
    m = CostModel(style="spread_linear", slippage_pips=0.0)
    med = m.fill("XAUUSD", "buy", 2000.0, lots=0.01, use_p95_spread=False)
    p95 = m.fill("XAUUSD", "buy", 2000.0, lots=0.01, use_p95_spread=True)
    assert p95.spread_cost_usd > med.spread_cost_usd


def test_commission_applied_per_lot():
    # Synthetic profile with explicit commission.
    profile = dict(DEFAULT_OCTAFX_PROFILE)
    profile["EURUSD"] = dict(profile["EURUSD"], commission_per_lot=7.0)
    m = CostModel(profile=profile, style="spread_linear", slippage_pips=0.0)
    f = m.fill("EURUSD", "buy", 1.1000, lots=0.5)
    assert f.commission_usd == pytest.approx(3.5)   # 7 * 0.5


def test_sqrt_impact_scales_with_lots():
    m = CostModel(style="sqrt_impact", impact_k=0.1, slippage_pips=0.0)
    f1 = m.fill("XAUUSD", "buy", 2000.0, lots=0.01)
    f4 = m.fill("XAUUSD", "buy", 2000.0, lots=0.04)
    # 4x lots → sqrt-4 = 2x impact contribution on top of linear spread.
    assert f4.spread_cost_usd > f1.spread_cost_usd


def test_fill_as_dict_has_expected_keys():
    m = CostModel(style="flat")
    f = m.fill("EURUSD", "buy", 1.1000, lots=0.01)
    d = f.as_dict()
    for k in ("side", "requested_price", "filled_price", "lots",
              "spread_cost_usd", "commission_usd", "slippage_usd",
              "total_cost_usd"):
        assert k in d


def test_unknown_symbol_falls_back_to_defaults():
    m = CostModel(style="spread_linear")
    # Shouldn't raise — should use default spread_pips_median=2.0.
    f = m.fill("FOOBAR", "buy", 100.0, lots=0.01)
    assert f.filled_price >= 100.0
    assert f.lots == pytest.approx(0.01)
