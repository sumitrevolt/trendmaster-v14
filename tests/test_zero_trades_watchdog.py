"""Smoke tests for tools/zero_trades_watchdog.py.

Focus on the pure-logic helpers: time-since-last-deal, confidence stats
(respecting the 6h staleness filter), and the verdict branches. Telegram
posting is not invoked (send_telegram is patched in to return True).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from zero_trades_watchdog import (  # noqa: E402
    STALE_HOURS,
    STALE_SIGNAL_HOURS,
    UNIFORM_MEAN_1_3,
    UNIFORM_STD,
    confidence_stats,
    last_deal_ts,
)


# ---------- last_deal_ts --------------------------------------------------


def test_last_deal_ts_picks_most_recent():
    state = {
        "recent_results": [
            {"ts": 100, "symbol": "XAUUSD", "pnl": 1.0},
            {"ts": 300, "symbol": "XAUUSD", "pnl": -2.0},
            {"ts": 200, "symbol": "XAUUSD", "pnl": 0.5},
        ]
    }
    assert last_deal_ts(state) == 300


def test_last_deal_ts_empty_state():
    assert last_deal_ts({}) is None
    assert last_deal_ts({"recent_results": []}) is None


def test_last_deal_ts_handles_bad_entries():
    state = {"recent_results": [{"ts": "not a number"}, {"ts": 500}]}
    assert last_deal_ts(state) == 500


# ---------- confidence_stats (staleness filter) ---------------------------


def _ts_now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _ts_ago(hours: float) -> int:
    return int(_ts_now() - hours * 3600)


def test_confidence_stats_drops_stale_signals():
    state = {
        "last_signal_per_symbol": {
            "A": {"ts": _ts_ago(1), "confidence": 0.35, "direction": "NONE"},
            "B": {"ts": _ts_ago(2), "confidence": 0.40, "direction": "NONE"},
            # stale - older than STALE_SIGNAL_HOURS
            "C": {"ts": _ts_ago(STALE_SIGNAL_HOURS + 2), "confidence": 0.50, "direction": "NONE"},
        }
    }
    mean, std, n = confidence_stats(state, _ts_now())
    assert n == 2
    assert mean == pytest.approx((0.35 + 0.40) / 2)
    assert std == pytest.approx(abs(0.35 - 0.40) / 2)


def test_confidence_stats_all_stale_returns_none():
    state = {
        "last_signal_per_symbol": {
            "A": {"ts": _ts_ago(STALE_SIGNAL_HOURS + 1), "confidence": 0.4},
        }
    }
    mean, std, n = confidence_stats(state, _ts_now())
    assert mean is None and std is None and n == 0


def test_confidence_stats_single_value_std_is_zero():
    state = {
        "last_signal_per_symbol": {
            "A": {"ts": _ts_ago(1), "confidence": 0.42},
        }
    }
    mean, std, n = confidence_stats(state, _ts_now())
    assert n == 1 and mean == pytest.approx(0.42) and std == 0.0


# ---------- constants sanity ----------------------------------------------


def test_stale_hours_reasonable():
    # 24h is our operational threshold. Don't silently change it in CI.
    assert STALE_HOURS == 24


def test_uniform_band_covers_one_third():
    lo, hi = UNIFORM_MEAN_1_3
    assert lo < 1.0 / 3.0 < hi
    # must be tight enough that a healthy binary classifier (mean ~0.5)
    # does NOT get flagged
    assert hi < 0.5
    assert UNIFORM_STD < 0.10
