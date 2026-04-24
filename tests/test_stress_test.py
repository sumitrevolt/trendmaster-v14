"""Unit tests for tools.stress_test."""
from __future__ import annotations

import pytest

from tools.stress_test import (
    StressReport,
    black_monday,
    flash_crash,
    gap_risk,
    mt5_outage,
    order_shuffle,
    run_all,
    spread_spike,
)


# Synthetic "live" PnL history — net positive, some losses.
_POSITIVE_HISTORY = [2.0, -1.0, 3.0, 1.5, -0.5, 2.5, -2.0, 1.0, 4.0, -1.5]


def test_flash_crash_detects_harm():
    r = flash_crash(_POSITIVE_HISTORY, shock=-50.0)
    assert r.name == "flash_crash"
    assert r.pnl_delta < 0
    assert 0.0 <= r.score <= 100.0


def test_order_shuffle_reports_worst_dd():
    r = order_shuffle(_POSITIVE_HISTORY, iters=200)
    assert r.name == "order_shuffle"
    assert r.max_dd_delta <= 0  # worst shuffle DD ≤ observed DD


def test_spread_spike_reduces_pnl():
    r = spread_spike(_POSITIVE_HISTORY)
    assert r.pnl_delta <= 0


def test_mt5_outage_drops_trades():
    r = mt5_outage(_POSITIVE_HISTORY, missed_fraction=0.5)
    assert r.name == "mt5_outage"
    assert r.pnl_delta <= 0


def test_gap_risk_injects_losses():
    r = gap_risk(_POSITIVE_HISTORY, gap_size=-20.0, freq=3)
    assert r.pnl_delta < 0


def test_black_monday_is_destructive():
    r = black_monday(_POSITIVE_HISTORY, shock_pct=-0.20)
    assert r.pnl_delta < 0


def test_run_all_produces_report():
    report = run_all(_POSITIVE_HISTORY)
    assert isinstance(report, StressReport)
    assert len(report.scenarios) >= 4
    assert 0.0 <= report.robustness_score <= 100.0
    text = report.human()
    assert "Robustness score" in text


def test_report_as_dict_serializable():
    import json
    report = run_all(_POSITIVE_HISTORY)
    d = report.as_dict()
    # Must be JSON-round-trippable.
    json.loads(json.dumps(d))
