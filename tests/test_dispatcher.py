"""Integration-ish tests for ai_trading_agents/multi_market_dispatcher.py.

These tests stub MT5 completely — they only hit the offline path
(CSV in data/) + the pure-Python agent bus.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ai_trading_agents import multi_market_dispatcher as D


@pytest.fixture
def tiny_csv(tmp_path: Path, monkeypatch) -> Path:
    """Write a synthetic M5 csv and point the dispatcher at it."""
    n = 1500
    ts = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    import numpy as np

    rng = np.random.default_rng(1)
    close = 100 + np.cumsum(rng.normal(0.05, 0.2, size=n))
    df = pd.DataFrame(
        {
            "time": ts,
            "open": close - 0.05,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": rng.integers(100, 1000, size=n),
        }
    )
    out = tmp_path / "testsym_m5_history.csv"
    df.to_csv(out, index=False)

    def _patched_path(symbol: str) -> Path:
        return out

    monkeypatch.setattr(D, "_csv_path", _patched_path)
    monkeypatch.setattr(D, "_HAS_MT5", False)
    return out


def test_scan_once_returns_entry_per_symbol(tiny_csv):
    res = D.scan_once(symbols=["TESTSYM"], min_votes=3)
    assert list(res.keys()) == ["TESTSYM"]
    entry = res["TESTSYM"]
    for key in ("direction", "confidence", "votes", "risk", "team", "agent_summary"):
        assert key in entry
    assert entry["direction"] in ("BUY", "SELL", "NONE")


def test_scan_once_missing_data_marks_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "_csv_path", lambda sym: tmp_path / "does_not_exist.csv")
    monkeypatch.setattr(D, "_HAS_MT5", False)
    res = D.scan_once(symbols=["ZZZZZZ"], min_votes=3)
    assert res["ZZZZZZ"]["direction"] == "NONE"
    assert res["ZZZZZZ"]["risk"]["reason"] == "no data"
