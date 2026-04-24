"""
Smoke test for tools.backtest.run_ea_parity_backtest.

Generates 1000 bars of synthetic bullish OHLCV M5 data, calls the new
EA-parity backtest, and prints the result dict. Exits non-zero if the
backtest raises or produces a malformed dict.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.backtest import run_ea_parity_backtest  # noqa: E402


def make_bullish_ohlcv(n: int = 1000, seed: int = 7) -> pd.DataFrame:
    """1000 bars of M5 bullish-trend OHLCV with realistic intrabar wicks."""
    rng = np.random.default_rng(seed)
    # Persistent positive drift + noise so EMAs stack bullishly and
    # MACD/SuperTrend agree often enough to fire the gate.
    drift = 0.4
    noise = rng.normal(loc=0.0, scale=1.0, size=n)
    closes = 2000.0 + np.cumsum(noise + drift)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    # Wick sizes ~ 0.5 of typical bar move.
    wick = np.abs(rng.normal(loc=0.0, scale=0.6, size=n))
    highs = np.maximum(opens, closes) + wick
    lows  = np.minimum(opens, closes) - wick
    vol = rng.integers(100, 1000, size=n).astype(float)
    idx = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": vol,
    }, index=idx)


def main() -> int:
    df = make_bullish_ohlcv()
    print(f"Generated {len(df)} synthetic M5 bars; "
          f"close range {df['close'].min():.2f} -> {df['close'].max():.2f}")
    result = run_ea_parity_backtest(df)
    print("run_ea_parity_backtest result:")
    for k, v in result.items():
        print(f"  {k:<14}= {v}")

    # Sanity: required keys present, types sane.
    required = {"trades", "wins", "losses",
                "expectancy_R", "win_rate", "gross_R", "sharpe_proxy"}
    missing = required - set(result.keys())
    if missing:
        print(f"FAIL: missing keys {missing}")
        return 2
    if result["trades"] < 0:
        print("FAIL: negative trade count")
        return 2
    print("OK: smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
