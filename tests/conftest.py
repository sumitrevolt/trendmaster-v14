"""pytest bootstrap — put the project root on sys.path and expose fixtures."""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Legacy scripts (run_test.py, test_chat.py, test_trade.py) call sys.exit()
# at module level and are not pytest-compatible. Skip them during collection.
collect_ignore_glob = [
    "run_test.py",
    "test_chat.py",
    "test_trade.py",
]


def _synthetic_ohlcv(n=800, start=100.0, drift=0.02, vol=0.5, seed=7):
    rng = np.random.default_rng(seed)
    steps = rng.normal(drift, vol, size=n)
    close = np.cumsum(steps) + start
    high = close + rng.uniform(0.05, 0.5, size=n)
    low = close - rng.uniform(0.05, 0.5, size=n)
    open_ = close - rng.normal(0, 0.1, size=n)
    volume = rng.integers(100, 1000, size=n)
    ts = pd.date_range(datetime(2026, 1, 1, tzinfo=timezone.utc), periods=n, freq="5min")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=ts,
    )


def _resample(df, minutes):
    return (
        df.resample(f"{minutes}min")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )


@pytest.fixture
def bullish_frames():
    df5 = _synthetic_ohlcv(n=1500, drift=0.08, vol=0.3, seed=11)
    return {"M30": _resample(df5, 30), "H1": _resample(df5, 60), "H4": _resample(df5, 240)}


@pytest.fixture
def sideways_frames():
    df5 = _synthetic_ohlcv(n=1500, drift=0.0, vol=0.4, seed=3)
    return {"M30": _resample(df5, 30), "H1": _resample(df5, 60), "H4": _resample(df5, 240)}
