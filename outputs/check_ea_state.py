"""Why didn't EA trade the 23:05 signals?"""
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv("config/.env")
import MetaTrader5 as mt5

mt5.initialize(login=int(os.getenv("MT5_LOGIN")),
               password=os.getenv("MT5_PASSWORD"),
               server=os.getenv("MT5_SERVER"))

# Terminal info — autotrading on?
ti = mt5.terminal_info()
print(f"=== MT5 TERMINAL INFO ===")
print(f"  trade_allowed:    {ti.trade_allowed}        (FALSE = AutoTrading button OFF)")
print(f"  expert_enabled:   {ti.tradeapi_disabled is False}")
print(f"  connected:        {ti.connected}")
print(f"  community_account:{ti.community_account}")

# Account state
ai = mt5.account_info()
print(f"\n=== ACCOUNT ===")
print(f"  trade_allowed:    {ai.trade_allowed}        (account trade permission)")
print(f"  trade_expert:     {ai.trade_expert}        (expert can trade)")
print(f"  margin_mode:      {ai.margin_mode}")

# Current spread on the 5 pairs
print(f"\n=== CURRENT SPREADS (23:00 IST = late session) ===")
for sym in ["XAUUSD", "EURUSD", "USDJPY", "GBPUSD", "BTCUSD"]:
    si = mt5.symbol_info(sym)
    if si is None:
        print(f"  {sym}: NOT VISIBLE")
        continue
    if not si.visible:
        mt5.symbol_select(sym, True)
        si = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if tick:
        spread_pts = (tick.ask - tick.bid) / si.point
        print(f"  {sym:8} bid={tick.bid:.5f} ask={tick.ask:.5f} spread={spread_pts:.0f} pts")

# Recent deals (any in last hour?)
print(f"\n=== DEALS LAST 60 MIN ===")
end = datetime.now()
start = end - timedelta(hours=1)
deals = mt5.history_deals_get(start, end) or []
print(f"  count: {len(deals)}")
for d in deals[-10:]:
    print(f"  {datetime.fromtimestamp(d.time).strftime('%H:%M:%S')} {d.symbol:8} {('BUY' if d.type==0 else 'SELL'):4} entry={d.entry} vol={d.volume} price={d.price:.5f} comment='{d.comment}'")

# Recent ORDERS (incl rejected)
print(f"\n=== ORDERS LAST 60 MIN ===")
orders = mt5.history_orders_get(start, end) or []
print(f"  count: {len(orders)}")
for o in orders[-10:]:
    state_name = {
        0: "STARTED", 1: "PLACED", 2: "CANCELED", 3: "PARTIAL",
        4: "FILLED", 5: "REJECTED", 6: "EXPIRED", 7: "REQUEST_ADD",
        8: "REQUEST_MODIFY", 9: "REQUEST_CANCEL"
    }.get(o.state, f"state{o.state}")
    print(f"  {datetime.fromtimestamp(o.time_setup).strftime('%H:%M:%S')} {o.symbol:8} type={o.type} state={state_name} vol={o.volume_initial} price={o.price_open:.5f} comment='{o.comment}'")

mt5.shutdown()
