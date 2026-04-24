"""Unit tests for ai_trading_agents.metrics."""

from __future__ import annotations

import re

import pytest

from ai_trading_agents import metrics as m


def _fresh_registry():
    # Reset the module-level singleton so tests don't leak counts
    # between each other.
    m._REGISTRY = m.MetricsRegistry()
    # Re-bind the pre-declared handles so imports inside tests still
    # point at the fresh registry.
    m.tick_latency = m._REGISTRY.histogram(
        "trendmaster_tick_latency_seconds",
        "test",
        labelnames=("symbol",),
    )
    m.signal_writes = m._REGISTRY.counter(
        "trendmaster_signal_writes_total",
        "test",
        labelnames=("symbol", "direction"),
    )
    m.veto_total = m._REGISTRY.counter(
        "trendmaster_veto_total",
        "test",
        labelnames=("symbol", "reason"),
    )


@pytest.fixture(autouse=True)
def _fresh():
    _fresh_registry()
    yield


def test_counter_increments():
    m.signal_writes.labels(symbol="XAUUSD", direction="BUY").inc()
    m.signal_writes.labels(symbol="XAUUSD", direction="BUY").inc(2)
    m.signal_writes.labels(symbol="XAUUSD", direction="SELL").inc()
    text = m.render_text()
    assert "trendmaster_signal_writes_total" in text
    # XAUUSD-BUY should be 3, XAUUSD-SELL should be 1.
    buy_line = [
        l
        for l in text.splitlines()
        if "trendmaster_signal_writes_total" in l and 'symbol="XAUUSD"' in l and 'direction="BUY"' in l
    ]
    assert len(buy_line) == 1
    assert buy_line[0].endswith(" 3")


def test_histogram_emits_buckets_sum_count():
    for v in (0.002, 0.01, 0.12, 0.8):
        m.tick_latency.labels(symbol="EURUSD").observe(v)
    text = m.render_text()
    # Required metric types appear.
    assert "trendmaster_tick_latency_seconds_bucket" in text
    assert "trendmaster_tick_latency_seconds_sum" in text
    assert "trendmaster_tick_latency_seconds_count" in text
    # Count matches observations.
    count_line = [l for l in text.splitlines() if l.startswith("trendmaster_tick_latency_seconds_count")]
    assert any(l.endswith(" 4") for l in count_line)


def test_uptime_always_present():
    text = m.render_text()
    assert "trendmaster_uptime_seconds" in text


def test_label_escaping():
    # A reason string with quotes shouldn't break the text format.
    m.veto_total.labels(symbol="XAUUSD", reason='needs "review"').inc()
    text = m.render_text()
    # The rendered line must be a valid Prometheus label value
    # (quotes escaped as \").
    assert r"\"review\"" in text


def test_render_is_deterministic_shape():
    m.signal_writes.labels(symbol="XAUUSD", direction="BUY").inc()
    text = m.render_text()
    # HELP/TYPE/metric triples appear for every declared metric.
    hits = re.findall(
        r"^# HELP\s+(\S+)\s+.*\n# TYPE\s+\1\s+(counter|gauge|histogram)",
        text,
        flags=re.MULTILINE,
    )
    assert len(hits) >= 2  # at least uptime + signal_writes


def test_nan_inf_ignored_in_histogram():
    m.tick_latency.labels(symbol="XAUUSD").observe(float("nan"))
    m.tick_latency.labels(symbol="XAUUSD").observe(float("inf"))
    m.tick_latency.labels(symbol="XAUUSD").observe(0.05)
    text = m.render_text()
    lines = [l for l in text.splitlines() if l.startswith("trendmaster_tick_latency_seconds_count")]
    assert any(l.endswith(" 1") for l in lines)
