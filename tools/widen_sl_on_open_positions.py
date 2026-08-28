"""Widen SL on all currently-open positions.

For each open position:
  - Compute new SL = entry_price ± (2.5 × ATR_H1)
  - Compute new TP = entry_price ± (5.0 × ATR_H1)  [1:2 RR]
  - Send TRADE_ACTION_SLTP modify request

Skips positions that already have wider SL than our minimum.
"""
from __future__ import annotations
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import MetaTrader5 as mt5

MIN_SL_ATR = 2.5
MIN_TP_ATR = 5.0


def get_atr_h1(symbol, period=14):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, period + 1)
    if rates is None or len(rates) < period + 1:
        return None
    trs = []
    for i in range(1, len(rates)):
        h, l, pc = rates[i]["high"], rates[i]["low"], rates[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else None


def main():
    if not mt5.initialize():
        print(f"mt5.initialize failed: {mt5.last_error()}")
        return 1
    pos = mt5.positions_get() or []
    print(f"=== Widening SL on {len(pos)} open positions ===")
    print(f"Policy: SL >= {MIN_SL_ATR}× ATR(H1), TP >= {MIN_TP_ATR}× ATR(H1)\n")

    success = 0
    skipped = 0
    failed = 0
    for p in sorted(pos, key=lambda x: x.symbol):
        info = mt5.symbol_info(p.symbol)
        if not info:
            print(f"  [skip] {p.symbol}: no symbol_info")
            skipped += 1
            continue
        atr = get_atr_h1(p.symbol)
        if not atr or atr <= 0:
            print(f"  [skip] {p.symbol}: no ATR")
            skipped += 1
            continue

        is_buy = p.type == mt5.ORDER_TYPE_BUY
        entry = p.price_open
        new_sl_dist = MIN_SL_ATR * atr
        new_tp_dist = MIN_TP_ATR * atr

        # Respect broker stops level
        stops_level = max(info.trade_stops_level, getattr(info, "freeze_level", 0))
        min_dist = stops_level * info.point * 2.0
        if new_sl_dist < min_dist:
            new_sl_dist = min_dist
        if new_tp_dist < min_dist:
            new_tp_dist = min_dist

        if is_buy:
            new_sl = entry - new_sl_dist
            new_tp = entry + new_tp_dist
        else:
            new_sl = entry + new_sl_dist
            new_tp = entry - new_tp_dist

        new_sl = round(new_sl, info.digits)
        new_tp = round(new_tp, info.digits)

        # Compare to current SL — only widen, never tighten
        cur_sl = p.sl
        if cur_sl > 0:
            cur_dist = abs(entry - cur_sl)
            if cur_dist >= new_sl_dist * 0.95:
                print(f"  [skip] {p.symbol} {('BUY' if is_buy else 'SELL'):<4}: "
                      f"current SL already wide ({cur_dist:.5f} >= {new_sl_dist:.5f})")
                skipped += 1
                continue

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": p.ticket,
            "symbol": p.symbol,
            "sl": new_sl,
            "tp": new_tp,
            "magic": p.magic,
        }
        res = mt5.order_send(request)
        if res is None:
            print(f"  [ERR ] {p.symbol}: order_send None — {mt5.last_error()}")
            failed += 1
            continue
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            old_sl_str = f"{cur_sl:.5f}" if cur_sl > 0 else "(none)"
            print(f"  [OK  ] {p.symbol} {('BUY' if is_buy else 'SELL'):<4}: "
                  f"SL {old_sl_str} -> {new_sl:.5f}  (dist {new_sl_dist:.5f}, {MIN_SL_ATR}× ATR={atr:.5f})  "
                  f"TP -> {new_tp:.5f}")
            success += 1
        else:
            print(f"  [FAIL] {p.symbol}: ret={res.retcode} {res.comment}")
            failed += 1

    print(f"\n=== Done. widened={success}  skipped={skipped}  failed={failed} ===")
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
