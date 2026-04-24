"""Unit tests for ai_trading_agents.ab_test."""

from __future__ import annotations

import pytest

from ai_trading_agents.ab_test import (
    ABTester,
    ShadowRecord,
    Variant,
    two_proportion_z,
    welch_t,
)


def _variant_bump_conf(symbol, direction, confidence, features):
    return direction, min(1.0, confidence + 0.05)


def _variant_flip_sell_to_none(symbol, direction, confidence, features):
    return ("NONE" if direction == "SELL" else direction), confidence


def test_register_and_tick_records_divergence():
    t = ABTester()
    t.register("bump", _variant_bump_conf)
    t.tick("EURUSD", "BUY", 0.70, {})
    s = t.summary()
    assert "bump" in s
    assert s["bump"]["total_ticks"] == 1
    assert s["bump"]["diverged"] == 1


def test_no_divergence_when_variant_returns_same():
    def same(symbol, direction, confidence, features):
        return direction, confidence

    t = ABTester()
    t.register("identity", same)
    t.tick("EURUSD", "BUY", 0.70, {})
    s = t.summary()
    assert s["identity"]["diverged"] == 0


def test_variant_failure_is_caught():
    def broken(symbol, direction, confidence, features):
        raise ValueError("boom")

    t = ABTester()
    t.register("broken", broken)
    # Should not raise.
    t.tick("EURUSD", "BUY", 0.70, {})
    s = t.summary()
    assert s["broken"]["diverged"] == 0  # error falls back to identity


def test_multiple_variants_independent():
    t = ABTester()
    t.register("bump", _variant_bump_conf)
    t.register("flip", _variant_flip_sell_to_none)
    t.tick("XAUUSD", "SELL", 0.60, {})
    s = t.summary()
    assert s["bump"]["total_ticks"] == 1
    assert s["flip"]["total_ticks"] == 1


def test_two_proportion_z_zero_when_equal():
    assert two_proportion_z(50, 100, 50, 100) == 0.0


def test_two_proportion_z_positive_when_a_better():
    z = two_proportion_z(wins_a=70, n_a=100, wins_b=50, n_b=100)
    # ~2.89 standard error units — highly significant.
    assert z > 2.0


def test_welch_t_zero_on_equal_means():
    a = [1, 2, 3, 4, 5]
    b = [1, 2, 3, 4, 5]
    assert welch_t(a, b) == 0.0


def test_welch_t_captures_mean_shift():
    a = [1.0, 1.1, 0.9, 1.0, 1.05] * 10
    b = [2.0, 2.1, 1.9, 2.0, 2.05] * 10
    t = welch_t(a, b)
    assert t < -2.0  # a has smaller mean, large |t|


def test_shadow_record_as_dict():
    rec = ShadowRecord(
        ts=1,
        symbol="X",
        variant="v",
        live_direction="BUY",
        live_confidence=0.5,
        shadow_direction="SELL",
        shadow_confidence=0.4,
        diverged=True,
    )
    d = rec.as_dict()
    assert d["variant"] == "v"
    assert d["diverged"] is True
