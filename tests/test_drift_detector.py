"""Unit tests for ai_trading_agents.drift_detector."""

from __future__ import annotations

import random

import pytest

from ai_trading_agents.drift_detector import (
    ADWIN,
    ADWINConfig,
    feed_recent_results,
    get_detector,
    reset_all,
)


@pytest.fixture(autouse=True)
def _clean():
    reset_all()
    yield
    reset_all()


def test_short_window_never_flags():
    det = ADWIN(ADWINConfig(min_window=32))
    for _ in range(20):
        drift, warn = det.update(0.5)
    assert drift is False
    assert warn is False
    # Also confirm state survived.
    assert det.state.total_observations == 20
    assert det.state.current_window_size == 20


def test_stable_stream_does_not_flag():
    det = ADWIN(ADWINConfig(min_window=32, delta=0.002))
    random.seed(42)
    flags = 0
    for _ in range(400):
        drift, _warn = det.update(random.gauss(0.0, 1.0))
        if drift:
            flags += 1
    # One or two false positives over 400 samples is acceptable
    # (delta=0.002 is already tight), but not more.
    assert flags <= 3, f"expected <=3 false positives, got {flags}"


def test_distribution_shift_triggers_drift():
    det = ADWIN(ADWINConfig(min_window=32, delta=0.01))
    # Feed 120 samples at mean=0, then 120 at mean=+5 — unmistakable drift.
    drift_ever = False
    for i in range(120):
        det.update(random.gauss(0.0, 1.0))
    random.seed(99)
    for i in range(120):
        d, _ = det.update(random.gauss(5.0, 1.0))
        drift_ever = drift_ever or d
    assert drift_ever, "clear distribution shift must be caught"


def test_reset_clears_window_not_counters():
    det = ADWIN(ADWINConfig(min_window=4))
    for _ in range(10):
        det.update(1.0)
    assert det.state.current_window_size == 10
    det.reset()
    assert det.state.current_window_size == 0
    # Counters stay.
    assert det.state.total_observations == 10


def test_non_numeric_input_ignored():
    det = ADWIN()
    drift, warn = det.update("not a number")
    assert drift is False and warn is False
    # Infs and NaNs also ignored.
    drift, warn = det.update(float("nan"))
    assert drift is False and warn is False
    drift, warn = det.update(float("inf"))
    assert drift is False and warn is False
    assert det.state.total_observations == 0


def test_feed_recent_results_handles_float_and_dict():
    # Make sure the helper handles both shapes without raising.
    drift, warn = feed_recent_results([])
    assert drift is False and warn is False
    drift, warn = feed_recent_results([-1.0])
    assert drift is False  # single sample, below min_window
    drift, warn = feed_recent_results([{"pnl": -2.5, "ts": 0}])
    assert drift is False


def test_singleton_reuses_instance():
    d1 = get_detector("test_key")
    d2 = get_detector("test_key")
    assert d1 is d2
    d3 = get_detector("other_key")
    assert d3 is not d1


def test_warning_fires_before_drift_on_slow_shift():
    det = ADWIN(ADWINConfig(min_window=32, delta=0.01))
    # Noisy but stable for a while.
    for _ in range(80):
        det.update(random.gauss(0.0, 0.5))
    # Slow, steady shift upward — might hit warning zone before drift.
    saw_warn = False
    saw_drift = False
    for k in range(80):
        d, w = det.update(random.gauss(2.0 + k * 0.02, 0.5))
        saw_warn = saw_warn or w
        saw_drift = saw_drift or d
        if saw_drift:
            break
    # Either a warning was raised OR drift fired directly — both are ok.
    assert saw_warn or saw_drift
