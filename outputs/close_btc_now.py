"""Close 2 wrong-direction BTC SELL positions immediately."""
import MetaTrader5 as mt5
import time
from datetime import datetime
from pathlib import Path

LOG = Path(r"C:\Users\Ratanshila\Documents\autmated trading\outputs\close_btc.log")
LOG.write_text(f"=== Close BTC SELL — {datetime.now()} ===\n", encoding="utf-8")

def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

if not mt5.initialize():
    log(f"MT5 init failed: {mt5.last_error()}")
    raise SystemExit(1)
log("MT5 connected")

positions = mt5.positions_get(symbol="BTCUSD") or []
log(f"Found {len(positions)} BTCUSD positions")

def detect_filling(symbol):
    info = mt5.symbol_info(symbol)
    if not info:
        return mt5.ORDER_FILLING_FOK
    fm = info.filling_mode
    if fm & 1: return mt5.ORDER_FILLING_FOK
    if fm & 2: return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN

for p in positions:
    if p.type != mt5.ORDER_TYPE_SELL:
        log(f"  ticket {p.ticket} not SELL, skipping")
        continue
    tick = mt5.symbol_info_tick(p.symbol)
    # Try all 3 filling modes
    closed_ok = False
    for fill_mode, name in [(detect_filling(p.symbol), "auto"),
                             (mt5.ORDER_FILLING_FOK, "FOK"),
                             (mt5.ORDER_FILLING_IOC, "IOC"),
                             (mt5.ORDER_FILLING_RETURN, "RETURN")]:
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": mt5.ORDER_TYPE_BUY,
            "position": p.ticket,
            "price": tick.ask,
            "deviation": 100,
            "magic": p.magic,
            "comment": "CLOSE-OCR-TF-BUG",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": fill_mode,
        }
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            log(f"  CLOSED ticket {p.ticket} @ {tick.ask:.2f} (was SELL @ {p.price_open:.2f}, PnL ${p.profit:+.2f}) [filling={name}]")
            closed_ok = True
            break
        else:
            rc = res.retcode if res else 'no-response'
            cm = res.comment if res else '?'
            log(f"    try filling={name}: rc={rc} {cm}")
    if not closed_ok:
        log(f"  FAIL ticket {p.ticket}: all filling modes rejected")

ai = mt5.account_info()
remaining = mt5.positions_get() or []
log(f"\nFinal: balance=${ai.balance:.2f} equity=${ai.equity:.2f} positions={len(remaining)}")
for r in remaining:
    d = "BUY" if r.type == 0 else "SELL"
    log(f"  {r.symbol} {d} {r.volume} @ {r.price_open:.5f} | PnL ${r.profit:+.2f}")
mt5.shutdown()
log("Done.")
