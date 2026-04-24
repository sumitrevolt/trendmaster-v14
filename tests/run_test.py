import MetaTrader5 as mt5
import sys, os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_out.txt")


def log(msg):
    print(msg, flush=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


# clear file
open(OUT, "w").close()

log("=" * 50)
log("MT5 TRADE TEST")
log("=" * 50)

# 1. init
ok = mt5.initialize()
log(f"mt5.initialize() = {ok}")
log(f"last_error = {mt5.last_error()}")

if not ok:
    log("FAILED: MT5 did not initialize. Is MetaTrader 5 open?")
    sys.exit(1)

# 2. account
acct = mt5.account_info()
if acct:
    log(f"Account: {acct.login} | Balance: {acct.balance} | Server: {acct.server}")
else:
    log(f"No account info: {mt5.last_error()}")

# 3. symbol
sym = mt5.symbol_info("XAUUSD")
if sym is None:
    mt5.symbol_select("XAUUSD", True)
    sym = mt5.symbol_info("XAUUSD")

if sym is None:
    log(f"FAILED: XAUUSD symbol not found: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

tick = mt5.symbol_info_tick("XAUUSD")
if tick is None:
    log(f"FAILED: No tick for XAUUSD: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

log(f"XAUUSD  bid={tick.bid}  ask={tick.ask}")

# 4. filling mode
fm = sym.filling_mode
if fm & 1:
    filling = mt5.ORDER_FILLING_FOK
elif fm & 2:
    filling = mt5.ORDER_FILLING_IOC
else:
    filling = mt5.ORDER_FILLING_RETURN
log(f"filling_mode flag={fm}  using={filling}")

# 5. place order
price = round(tick.ask, sym.digits)
sl = round(tick.ask - 5.0, sym.digits)
tp = round(tick.ask + 10.0, sym.digits)

request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": "XAUUSD",
    "volume": 0.01,
    "type": mt5.ORDER_TYPE_BUY,
    "price": price,
    "sl": sl,
    "tp": tp,
    "deviation": 20,
    "magic": 234001,
    "comment": "TEST_TRADE",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": filling,
}

log(f"Sending order: BUY 0.01 XAUUSD @ {price}  SL={sl}  TP={tp}")

result = mt5.order_send(request)

if result is None:
    log(f"FAILED: order_send returned None: {mt5.last_error()}")
else:
    log(f"retcode  = {result.retcode}")
    log(f"comment  = {result.comment}")
    log(f"ticket   = {result.order}")
    log(f"price    = {result.price}")
    log(f"volume   = {result.volume}")
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log("SUCCESS: TRADE PLACED!")
    else:
        log(f"FAILED: retcode {result.retcode}")

mt5.shutdown()
log("Done.")
