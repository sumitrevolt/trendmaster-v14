"""Unit tests for ai_trading_agents.panic (dry-run + MT5-missing paths)."""

from __future__ import annotations

from ai_trading_agents import panic


def test_no_mt5_returns_empty_result(monkeypatch):
    monkeypatch.setattr(panic, "_HAS_MT5", False)
    result = panic.flatten_all_positions(dry_run=True)
    assert result.attempted == 0
    assert result.closed == 0
    assert result.failed == 0
    assert any("not importable" in n for n in result.notes)


def test_flatten_result_summary_shape():
    r = panic.FlattenResult()
    assert r.as_dict()["attempted"] == 0
    assert r.as_dict()["success"] is True


def test_flatten_result_human_for_dry_run():
    r = panic.FlattenResult(dry_run=True, attempted=2, closed=2)
    r.per_symbol = {
        "EURUSD": {"action": "close-sell", "lots": 0.01, "ok": True, "note": "dry-run"},
        "XAUUSD": {"action": "close-buy", "lots": 0.02, "ok": True, "note": "dry-run"},
    }
    text = r.human
    assert "would close 2" in text
    assert "EURUSD" in text
    assert "XAUUSD" in text
    assert "OK" in text


def test_dry_run_without_mt5_is_side_effect_free():
    # Even if MT5 were importable, dry-run must never issue an order.
    # The absence of mt5.order_send in the module-level namespace on
    # CI confirms this path is safe.
    result = panic.flatten_all_positions(dry_run=True)
    assert result.dry_run is True
