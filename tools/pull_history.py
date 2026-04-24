"""
tools/pull_history.py — pull M5 OHLCV for every pair in TRADING_PAIRS.

Closes the data-pipeline gap: the final upgrade report only has xauusd,
but config/settings.py lists 20+ pairs. This script makes the history
pull routine (just run it) and symmetric across pairs.

Writes to data/{symbol_lower}_m5_history.csv, which the backtester and
retrainer both read from by default.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import settings  # noqa: E402

logger = logging.getLogger("pull_history")


def pull_all(bars: int = 50_000, symbols: list[str] | None = None) -> int:
    try:
        import MetaTrader5 as mt5  # type: ignore
        import pandas as pd
    except ImportError as e:
        logger.error("MetaTrader5/pandas not installed: %s", e)
        return 2

    if not mt5.initialize():
        logger.error("mt5.initialize() failed: %s", mt5.last_error())
        return 3

    out_dir = _ROOT / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    symbols = symbols or settings.TRADING_PAIRS
    ok = fail = 0
    for sym in symbols:
        mt5.symbol_select(sym, True)
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, bars)
        if rates is None or len(rates) == 0:
            logger.warning("no data for %s: %s", sym, mt5.last_error())
            fail += 1
            continue
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        out = out_dir / f"{sym.lower()}_m5_history.csv"
        cols = [c for c in ("time", "open", "high", "low", "close", "tick_volume") if c in df.columns]
        df[cols].rename(columns={"tick_volume": "volume"}).to_csv(out, index=False)
        logger.info("[%s] %d bars → %s", sym, len(df), out.name)
        ok += 1

    mt5.shutdown()
    logger.info("done — ok=%d fail=%d", ok, fail)
    return 0 if fail == 0 else 1


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--bars", type=int, default=50_000)
    p.add_argument("--symbols", nargs="*", default=None)
    a = p.parse_args()
    return pull_all(bars=a.bars, symbols=a.symbols)


if __name__ == "__main__":
    raise SystemExit(main())
