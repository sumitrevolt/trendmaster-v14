"""Close ALL open MT5 positions immediately.

USER OPERATION: This script places real CLOSE orders. Sumit must run it.

Logic:
  1. Connect to MT5 (creds from config/.env)
  2. Get all open positions
  3. For each, send opposite-side market deal with FILLING_IOC
  4. Print result per position + summary
"""
import sys
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
load_dotenv(ROOT / "config" / ".env")
sys.path.insert(0, str(ROOT))

import MetaTrader5 as mt5

if not mt5.initialize(login=int(os.getenv("MT5_LOGIN")),
                     password=os.getenv("MT5_PASSWORD"),
                     server=os.getenv("MT5_SERVER")):
    print(f"FATAL: MT5 init failed: {mt5.last_error()}")
    sys.exit(1)

ai = mt5.account_info()
print(f"=== BEFORE ===")
print(f"  balance: ${ai.balance:.2f}  equity: ${ai.equity:.2f}  P/L: ${ai.equity - ai.balance:.2f}")

positions = mt5.positions_get() or []
print(f"\n=== CLOSING {len(positions)} POSITIONS ===")
ok, fail = 0, 0
for p in positions:
    # Pick correct close side + price
    close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(p.symbol)
    price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": p.symbol,
        "volume": p.volume,
        "type": close_type,
        "position": p.ticket,
        "price": price,
        "deviation": 30,
        "magic": p.magic,
        "comment": "Manual-CloseAll-2026-05-06",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res is None:
        print(f"  [FAIL] {p.symbol:8} ticket={p.ticket}: order_send returned None ({mt5.last_error()})")
        fail += 1
    elif res.retcode != mt5.TRADE_RETCODE_DONE:
        # Try ORDER_FILLING_FOK as fallback
        req["type_filling"] = mt5.ORDER_FILLING_FOK
        res2 = mt5.order_send(req)
        if res2 and res2.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"  [OK]   {p.symbol:8} ticket={p.ticket}  closed at {res2.price:.5f}  pnl=${p.profit:.2f}  (FOK)")
            ok += 1
        else:
            err = res2.comment if res2 else mt5.last_error()
            print(f"  [FAIL] {p.symbol:8} ticket={p.ticket}  retcode={res.retcode}  comment={res.comment}  fallback={err}")
            fail += 1
    else:
        print(f"  [OK]   {p.symbol:8} ticket={p.ticket}  closed at {res.price:.5f}  pnl=${p.profit:.2f}")
        ok += 1

ai2 = mt5.account_info()
print(f"\n=== AFTER ===")
print(f"  balance: ${ai2.balance:.2f}  equity: ${ai2.equity:.2f}  realized P/L change: ${ai2.balance - ai.balance:.2f}")
remain = mt5.positions_get() or []
print(f"  remaining open positions: {len(remain)}")
for r in remain:
    print(f"    - {r.symbol} ticket={r.ticket} pnl=${r.profit:.2f}")

print(f"\n=== SUMMARY: closed {ok}, failed {fail} ===")
mt5.shutdown()
sys.exit(0 if fail == 0 else 2)
