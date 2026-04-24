"""Smoke test for tools/backtest.py on synthetic data."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tools.backtest import run_backtest, BacktestReport


@pytest.fixture
def trendy_csv(tmp_path: Path) -> Path:
    n = 2500
    ts = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    rng = np.random.default_rng(2)
    close = 100 + np.cumsum(rng.normal(0.08, 0.3, size=n))
    df = pd.DataFrame({
        "time": ts,
        "open":  close - 0.05,
        "high":  close + 0.4,
        "low":   close - 0.4,
        "close": close,
        "volume": rng.integers(100, 1000, size=n),
    })
    out = tmp_path / "trendy.csv"
    df.to_csv(out, index=False)
    return out


def test_backtest_runs_and_reports(trendy_csv):
    rep = run_backtest("TRENDY", csv_path=str(trendy_csv),
                       warmup_bars=400, stride=24, hold_bars=12)
    assert isinstance(rep, BacktestReport)
    rep.compute()
    assert rep.bars_scanned > 0
    # Every trade must end in a resolved state
    for t in rep.trades:
        assert t.outcome in ("win", "loss", "timeout")


def test_backtest_missing_csv_raises():
    with pytest.raises(FileNotFoundError):
        run_backtest("NOPE", csv_path="/nonexistent/path.csv")
