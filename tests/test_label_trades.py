"""Unit tests for tools/label_trades.py — no MT5, no lightgbm needed."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tools.label_trades import label


def _write_trades(path: Path) -> None:
    rows = [
        # BUY wins by 2R (entry=100 sl=99, close=102)
        {"open_time": "2026-04-01T10:00:00Z", "symbol": "XAUUSD",
         "type": "BUY", "open_price": 100, "sl": 99,
         "close_price": 102, "close_time": "2026-04-01T11:00:00Z"},
        # SELL loses — went against by 1R
        {"open_time": "2026-04-01T12:00:00Z", "symbol": "XAUUSD",
         "type": "SELL", "open_price": 100, "sl": 101,
         "close_price": 101, "close_time": "2026-04-01T13:00:00Z"},
        # BUY breakeven
        {"open_time": "2026-04-01T14:00:00Z", "symbol": "EURUSD",
         "type": "BUY", "open_price": 1.1, "sl": 1.09,
         "close_price": 1.1, "close_time": "2026-04-01T15:00:00Z"},
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def test_label_produces_per_symbol_files(tmp_path):
    trades = tmp_path / "trades.csv"
    _write_trades(trades)
    out_dir = tmp_path / "out"
    df = label(trades_csv=str(trades), out_dir=str(out_dir))
    assert set(df["symbol"]) == {"XAUUSD", "EURUSD"}
    xau = pd.read_csv(out_dir / "labels_xauusd.csv")
    assert set(xau["direction"]) == {"BUY", "SELL"}
    # BUY row: (102-100)/(100-99) = 2 → won_R
    buy = xau[xau["direction"] == "BUY"].iloc[0]
    assert buy["r_multiple"] == 2.0
    assert buy["won_R"] == 1
    # SELL row: close=101, entry=100 → move = -1, risk = |100-101| = 1 → R = -1
    sell = xau[xau["direction"] == "SELL"].iloc[0]
    assert sell["r_multiple"] == -1.0
    assert sell["won_R"] == 0


def test_label_missing_columns_raises(tmp_path):
    bad = tmp_path / "bad.csv"
    pd.DataFrame([{"open_time": "x", "symbol": "Y"}]).to_csv(bad, index=False)
    with pytest.raises(ValueError):
        label(trades_csv=str(bad), out_dir=str(tmp_path))
