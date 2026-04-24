"""
MT5 DIRECT TRADE TEST
======================
Run this script FIRST to confirm MT5 trading works.
It places ONE real 0.01 lot XAUUSD BUY trade.

Usage:
    python test_trade.py

If this works → your MT5 connection is fine, restart main bot.
If this fails → check the error message shown.
"""

import sys
import os

# ── Load credentials from .env ───────────────────────────────────────
try:
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
except Exception as e:
    print(f"Warning: could not load .env: {e}")

LOGIN = int(os.getenv("MT5_LOGIN", "0"))
PASSWORD = os.getenv("MT5_PASSWORD", "")
SERVER = os.getenv("MT5_SERVER", "OctaFX-Demo")

print(f"\n{'=' * 55}")
print(f"  MT5 DIRECT TRADE TEST")
print(f"  Account : {LOGIN}")
print(f"  Server  : {SERVER}")
print(f"{'=' * 55}\n")

# ── Import MT5 ───────────────────────────────────────────────────────
try:
    import MetaTrader5 as mt5
except ImportError:
    print("❌  MetaTrader5 package NOT installed.")
    print("    Run:  pip install MetaTrader5")
    sys.exit(1)

# ── Initialize ───────────────────────────────────────────────────────
print("Step 1 — Initializing MT5...")
if not mt5.initialize(login=LOGIN, password=PASSWORD, server=SERVER):
    print(f"❌  mt5.initialize() FAILED: {mt5.last_error()}")
    print("    Make sure MetaTrader 5 terminal is OPEN and logged in.")
    sys.exit(1)

acct = mt5.account_info()
if acct:
    print(f"✅  Connected — Account: {acct.login} | Balance: {acct.balance:.2f} {acct.currency}")
else:
    print(f"⚠️  Connected but cannot read account info: {mt5.last_error()}")

# ── Check symbol ─────────────────────────────────────────────────────
SYMBOL = "XAUUSD"
print(f"\nStep 2 — Checking symbol {SYMBOL}...")

sym = mt5.symbol_info(SYMBOL)
if sym is None:
    print(f"❌  Symbol {SYMBOL} not found. Trying to add it...")
    if not mt5.symbol_select(SYMBOL, True):
        print(f"❌  Cannot select {SYMBOL}: {mt5.last_error()}")
        print("    Open MT5 → right-click Market Watch → Show All → find XAUUSD")
        mt5.shutdown()
        sys.exit(1)
    sym = mt5.symbol_info(SYMBOL)

if sym is None:
    print(f"❌  Still no symbol info: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

if not sym.visible:
    mt5.symbol_select(SYMBOL, True)

tick = mt5.symbol_info_tick(SYMBOL)
if tick is None:
    print(f"❌  No tick data for {SYMBOL}: {mt5.last_error()}")
    print("    Market may be closed or symbol not available on this broker.")
    mt5.shutdown()
    sys.exit(1)

print(f"✅  {SYMBOL} — Bid: {tick.bid} | Ask: {tick.ask} | Spread: {round(tick.ask - tick.bid, 2)}")

# ── Build order ───────────────────────────────────────────────────────
print(f"\nStep 3 — Placing 0.01 lot BUY order on {SYMBOL}...")

digits = sym.digits
price = tick.ask
sl = round(price - 5.0, digits)  # SL = 5 dollars below entry
tp = round(price + 10.0, digits)  # TP = 10 dollars above entry
lots = 0.01

# Filling mode
fm = sym.filling_mode
if fm & 1:
    filling = mt5.ORDER_FILLING_FOK
elif fm & 2:
    filling = mt5.ORDER_FILLING_IOC
else:
    filling = mt5.ORDER_FILLING_RETURN

request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": SYMBOL,
    "volume": lots,
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

print(f"  Order: BUY {lots}L @ {price} | SL: {sl} | TP: {tp}")

result = mt5.order_send(request)

if result is None:
    print(f"\n❌  order_send returned None: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

print(f"\n  MT5 retcode: {result.retcode} — {result.comment}")

if result.retcode == mt5.TRADE_RETCODE_DONE:
    print(f"\n✅  TRADE PLACED SUCCESSFULLY!")
    print(f"    Ticket : #{result.order}")
    print(f"    Price  : {result.price}")
    print(f"    Volume : {result.volume}")
    print(f"\n  → MT5 live trading is WORKING.")
    print(f"  → Restart the main bot (START_TRADING.bat) to apply code fixes.")
else:
    print(f"\n❌  TRADE FAILED — retcode {result.retcode}: {result.comment}")
    # Common error codes
    errors = {
        10004: "Requote — price changed, try again",
        10006: "Request rejected",
        10007: "Request cancelled by trader",
        10010: "Only part of the request was completed",
        10013: "Invalid request",
        10014: "Invalid volume",
        10015: "Invalid price",
        10016: "Invalid stops (SL/TP too close to price)",
        10017: "Trading disabled",
        10018: "Market closed",
        10019: "Insufficient funds",
        10031: "No connection to trade server",
        10032: "Operation allowed only for live accounts",
        10033: "Too many pending orders",
        10034: "Trade volume limit reached",
    }
    hint = errors.get(result.retcode, "Unknown error")
    print(f"    Hint: {hint}")

mt5.shutdown()
print(f"\n{'=' * 55}\n")
