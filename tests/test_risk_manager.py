"""Unit tests for ai_trading_agents/risk_manager.py."""

from __future__ import annotations

import pytest

from ai_trading_agents.risk_manager import (
    Position,
    RiskConfig,
    RiskState,
    check_risk,
    size_position,
    team_of,
)


def test_team_of_known_symbols():
    assert team_of("XAUUSD") == "METALS"
    assert team_of("EURUSD") == "FOREX"
    assert team_of("BTCUSD") == "CRYPTO"
    assert team_of("XTIUSD") == "COMMODITIES"
    assert team_of("UNKNOWN") == "OTHER"


def test_size_position_scales_with_equity():
    cfg = RiskConfig(risk_per_trade_pct=1.0)
    small = size_position(equity=1_000, risk_pct=1.0, sl_distance_price=10, pip_value_per_lot=1.0, cfg=cfg)
    big = size_position(equity=10_000, risk_pct=1.0, sl_distance_price=10, pip_value_per_lot=1.0, cfg=cfg)
    assert big > small
    assert small >= cfg.min_lot


def test_size_position_caps_at_max_lot():
    cfg = RiskConfig(max_lot=2.0)
    lots = size_position(equity=1_000_000, risk_pct=5.0, sl_distance_price=1, pip_value_per_lot=1.0, cfg=cfg)
    assert lots == cfg.max_lot


def test_size_position_bad_inputs_zero():
    assert size_position(0, 1, 1, 1) == 0
    assert size_position(1000, 1, 0, 1) == 0
    assert size_position(1000, 1, 1, 0) == 0


def test_daily_loss_stop_blocks_trade():
    state = RiskState(equity=900, start_of_day=1000, open_positions=[])
    cfg = RiskConfig(max_daily_loss_pct=5.0)
    d = check_risk("EURUSD", "BUY", 0.1, state, cfg)
    assert not d.allow
    assert "daily loss stop" in d.reason


def test_global_concurrency_blocks_trade():
    state = RiskState(
        equity=1000, start_of_day=1000, open_positions=[Position(f"EURUSD", "BUY", 0.1, 1.0, 0.9, 1.2)] * 6
    )
    cfg = RiskConfig(max_open_total=6)
    d = check_risk("GBPUSD", "BUY", 0.1, state, cfg)
    assert not d.allow
    assert "max open total" in d.reason


def test_team_cap_blocks():
    opens = [
        Position("EURUSD", "BUY", 0.1, 1, 0.9, 1.1),
        Position("GBPUSD", "BUY", 0.1, 1, 0.9, 1.1),
        Position("AUDUSD", "BUY", 0.1, 1, 0.9, 1.1),
    ]
    state = RiskState(equity=1000, start_of_day=1000, open_positions=opens)
    cfg = RiskConfig(max_open_per_team=3, max_open_total=10)
    d = check_risk("NZDUSD", "BUY", 0.1, state, cfg)
    assert not d.allow
    assert "team FOREX" in d.reason


def test_correlation_cap_blocks_stacked_longs():
    opens = [Position("EURUSD", "BUY", 0.1, 1, 0.9, 1.1), Position("GBPUSD", "BUY", 0.1, 1, 0.9, 1.1)]
    state = RiskState(equity=1000, start_of_day=1000, open_positions=opens)
    cfg = RiskConfig(max_corr_same_dir=2, max_open_total=10, max_open_per_team=10)
    d = check_risk("AUDUSD", "BUY", 0.1, state, cfg)
    assert not d.allow
    assert "correlation cap" in d.reason


def test_happy_path_allows_trade():
    state = RiskState(equity=1000, start_of_day=1000, open_positions=[])
    d = check_risk("XAUUSD", "BUY", 0.05, state, RiskConfig())
    assert d.allow
    assert d.lots == 0.05


# ---------- new (2026-04-22) profitability gates ----------
def test_daily_profit_lock_blocks_after_target():
    state = RiskState(equity=1025, start_of_day=1000, open_positions=[])
    cfg = RiskConfig(daily_profit_target_pct=2.0)
    d = check_risk("EURUSD", "BUY", 0.1, state, cfg)
    assert not d.allow
    assert "profit lock" in d.reason


def test_daily_profit_lock_allows_below_target():
    state = RiskState(equity=1010, start_of_day=1000, open_positions=[])
    cfg = RiskConfig(daily_profit_target_pct=2.0)
    d = check_risk("EURUSD", "BUY", 0.1, state, cfg)
    assert d.allow


def test_loss_streak_blocks_after_n_losses():
    # [audit-fix 2026-04-23] Use 1% drawdown so daily_loss_stop (5% default) doesn't
    # fire first — we want to exercise the loss-streak path specifically.
    state = RiskState(equity=990, start_of_day=1000, open_positions=[], recent_results=[-1, -2, -3])
    cfg = RiskConfig(max_consec_losses=3)
    d = check_risk("EURUSD", "BUY", 0.1, state, cfg)
    assert not d.allow
    assert "loss streak" in d.reason


def test_cooldown_active_blocks():
    state = RiskState(equity=1000, start_of_day=1000, open_positions=[], cooldown_active=True)
    d = check_risk("EURUSD", "BUY", 0.1, state, RiskConfig())
    assert not d.allow
    assert "cooldown" in d.reason
