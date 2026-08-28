"""Dump ALL MT5 permission flags."""
import MetaTrader5 as mt5

mt5.initialize()
ti = mt5.terminal_info()
ai = mt5.account_info()
print("=== terminal_info ===")
fields = [
    "build", "connected", "dlls_allowed", "trade_allowed",
    "tradeapi_disabled", "email_enabled", "ftp_enabled",
    "notifications_enabled", "mqid", "ping_last",
    "community_account", "community_connection",
]
for f in fields:
    try:
        print(f"  {f}: {getattr(ti, f)}")
    except AttributeError:
        print(f"  {f}: <not present>")
print()
print("=== account_info trade flags ===")
for f in ["trade_allowed", "trade_expert"]:
    print(f"  {f}: {getattr(ai, f, None)}")
print()

# Try a tiny test order to see the precise rejection code
print("=== order_send dry-run check ===")
sym = "EURUSD"
tick = mt5.symbol_info_tick(sym)
if tick:
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": 0.01,
        "type": mt5.ORDER_TYPE_BUY,
        "price": tick.ask,
        "deviation": 20,
        "magic": 999,
        "comment": "perm_test",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    # Use order_check, NOT order_send — this validates without placing
    res = mt5.order_check(request)
    print(f"  order_check retcode: {res.retcode if res else None}")
    print(f"  comment: {res.comment if res else None}")
    if res and res.retcode != 0:
        print(f"  margin_free: {res.margin_free}")
        print(f"  margin_level: {res.margin_level}")

mt5.shutdown()
