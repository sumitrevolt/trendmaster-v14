"""Close only the 2 unintended GBPUSD SELL positions opened by my test signal.

USER OPERATION: closes specific positions only. Sumit must run.
"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(r"C:\Users\Ratanshila\Documents\autmated trading\config\.env")
import MetaTrader5 as mt5

if not mt5.initialize(login=int(os.getenv("MT5_LOGIN")),
                     password=os.getenv("MT5_PASSWORD"),
                     server=os.getenv("MT5_SERVER")):
    print(f"FATAL: MT5 init failed: {mt5.last_error()}")
    sys.exit(1)

ai = mt5.account_info()
print(f"=== BEFORE ===")
print(f"  balance=${ai.balance:.2f}  equity=${ai.equity:.2f}")

positions = mt5.positions_get(symbol="GBPUSD") or []
print(f"\n=== GBPUSD positions to close: {len(positions)} ===")
for p in positions:
    age_min = (datetime.now().timestamp() - p.time) / 60
    print(f"  ticket={p.ticket}  {p.symbol} {('BUY' if p.type==0 else 'SELL')}  open={p.price_open:.5f}  cur={p.price_current:.5f}  pnl=${p.profit:.2f}  comment='{p.comment}'")

ok, fail = 0, 0
for p in positions:
    close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(p.symbol)
    price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
    req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume,
        "type": close_type, "position": p.ticket, "price": price, "deviation": 30,
        "magic": p.magic, "comment": "Manual-CloseGBPUSDOnly-2026-05-06",
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        # Try FOK
        req["type_filling"] = mt5.ORDER_FILLING_FOK
        res2 = mt5.order_send(req)
        if res2 and res2.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"  [OK FOK] ticket={p.ticket} closed at {res2.price:.5f} pnl=${p.profit:.2f}")
            ok += 1
        else:
            err = res.comment if res else mt5.last_error()
            print(f"  [FAIL] ticket={p.ticket}: {err}")
            fail += 1
    else:
        print(f"  [OK] ticket={p.ticket} closed at {res.price:.5f} pnl=${p.profit:.2f}")
        ok += 1

ai2 = mt5.account_info()
print(f"\n=== AFTER ===")
print(f"  balance=${ai2.balance:.2f}  equity=${ai2.equity:.2f}  realized change: ${ai2.balance - ai.balance:.2f}")
remain = mt5.positions_get() or []
print(f"  remaining open positions: {len(remain)}")
for r in remain:
    print(f"    {r.symbol} {('BUY' if r.type==0 else 'SELL')} pnl=${r.profit:.2f}")

print(f"\n[SUMMARY] closed {ok}, failed {fail}")
mt5.shutdown()
sys.exit(0 if fail == 0 else 2)
