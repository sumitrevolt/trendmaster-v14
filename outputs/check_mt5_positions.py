"""Check MT5 for open positions + recent trades to see if test signals triggered real trades."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, r"C:\Users\Ratanshila\Documents\autmated trading")
from dotenv import load_dotenv
import os
load_dotenv(r"C:\Users\Ratanshila\Documents\autmated trading\config\.env")

import MetaTrader5 as mt5

if not mt5.initialize(login=int(os.getenv("MT5_LOGIN")),
                     password=os.getenv("MT5_PASSWORD"),
                     server=os.getenv("MT5_SERVER")):
    print(f"FATAL: MT5 init failed: {mt5.last_error()}")
    sys.exit(1)

ai = mt5.account_info()
print(f"=== ACCOUNT ===")
print(f"  login:    {ai.login}")
print(f"  balance:  ${ai.balance:.2f}")
print(f"  equity:   ${ai.equity:.2f}")
print(f"  margin:   ${ai.margin:.2f}")
print(f"  free:     ${ai.margin_free:.2f}")
print(f"  P/L:      ${ai.equity - ai.balance:.2f}")

print(f"\n=== OPEN POSITIONS ===")
positions = mt5.positions_get() or []
print(f"  count: {len(positions)}")
for p in positions:
    age_min = (datetime.now().timestamp() - p.time) / 60
    print(f"  ticket={p.ticket}  {p.symbol:8} {('BUY' if p.type==0 else 'SELL'):4} vol={p.volume}  open={p.price_open:.5f}  cur={p.price_current:.5f}  pnl=${p.profit:.2f}  sl={p.sl:.5f}  tp={p.tp:.5f}  age={age_min:.1f}min  comment='{p.comment}'")

print(f"\n=== DEALS LAST 30 MIN ===")
end = datetime.now()
start = end - timedelta(minutes=30)
deals = mt5.history_deals_get(start, end) or []
print(f"  count: {len(deals)}")
for d in deals:
    print(f"  ticket={d.ticket}  {d.symbol:8} {('BUY' if d.type==0 else 'SELL'):4} vol={d.volume}  price={d.price:.5f}  pnl=${d.profit:.2f}  time={datetime.fromtimestamp(d.time).isoformat(timespec='seconds')}  comment='{d.comment}'")

print(f"\n=== ORDERS LAST 30 MIN ===")
orders = mt5.history_orders_get(start, end) or []
print(f"  count: {len(orders)}")
for o in orders:
    print(f"  ticket={o.ticket}  {o.symbol:8} type={o.type} state={o.state} vol={o.volume_initial}  price={o.price_open:.5f}  time={datetime.fromtimestamp(o.time_setup).isoformat(timespec='seconds')}  comment='{o.comment}'")

mt5.shutdown()
