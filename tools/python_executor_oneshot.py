"""One-shot test: scan signal files once, attempt one order, exit.
Used to verify the executor works before launching the looping version."""
from __future__ import annotations
import sys
sys.path.insert(0, ".")

# Reuse all logic from the main executor
from tools.python_signal_executor import (
    init_mt5, find_signal_dir, load_signal, signal_is_fresh, place_order,
    SYMBOLS, log,
)
import MetaTrader5 as mt5


def main():
    if not init_mt5():
        return 1
    sig_dir = find_signal_dir()
    if not sig_dir:
        log.error("no signal dir")
        return 1
    log.info("ONE-SHOT scan in %s", sig_dir)
    placed = 0
    for symbol in SYMBOLS:
        fname = "trendmaster_signals.json" if symbol == "XAUUSD" else f"trendmaster_signals_{symbol}.json"
        path = sig_dir / fname
        if not path.exists():
            continue
        sig = load_signal(path)
        if not sig:
            continue
        fresh = signal_is_fresh(sig)
        log.info("  %s: dir=%s conf=%s fresh=%s ts=%s",
                 symbol, sig.get("direction"), sig.get("confidence"), fresh, sig.get("ts"))
        if not fresh:
            continue
        if place_order(symbol, sig):
            placed += 1
    log.info("one-shot done: placed=%d", placed)
    pos = mt5.positions_get()
    if pos:
        log.info("open positions now:")
        for p in pos:
            log.info("  %s %s lots=%.2f profit=%.2f", p.symbol,
                     "BUY" if p.type == 0 else "SELL", p.volume, p.profit)
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
