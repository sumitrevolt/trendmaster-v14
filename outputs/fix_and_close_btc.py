"""Emergency:
1. Restart webhook to load chart_scrape_ocr TF fix
2. Close 2 wrong-direction BTC SELL positions (chart shows BUY)
"""
import psutil
import subprocess
import time
import MetaTrader5 as mt5
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOG = ROOT / "outputs" / "fix_and_close_btc.log"
LOG.write_text(f"=== Fix + close BTC — {datetime.now()} ===\n", encoding="utf-8")

def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

# Step 1: kill + respawn webhook silently
log("--- Step 1: restart webhook ---")
DETACHED = 0x00000008
NO_WINDOW = 0x08000000
killed = []
for p in psutil.process_iter(['pid', 'cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        if "tv_webhook_receiver" in cmd:
            p.kill()
            killed.append(p.info['pid'])
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
log(f"Killed {len(killed)} webhook PIDs: {killed}")
time.sleep(2)

pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
proc = subprocess.Popen(
    [str(pythonw), "-m", "ai_trading_agents.tv_webhook_receiver"],
    cwd=str(ROOT),
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    creationflags=DETACHED | NO_WINDOW, close_fds=True,
)
log(f"Spawned new webhook PID {proc.pid}")
time.sleep(3)

# Step 2: close BTC SELL positions
log("\n--- Step 2: close wrong-direction BTC SELL positions ---")
if not mt5.initialize():
    log(f"MT5 init failed: {mt5.last_error()}")
    raise SystemExit(1)

positions = mt5.positions_get(symbol="BTCUSD") or []
log(f"Found {len(positions)} open BTCUSD positions")

closed_count = 0
for p in positions:
    if p.type != mt5.ORDER_TYPE_SELL:
        log(f"  PID {p.ticket}: not a SELL ({p.type}), skipping")
        continue
    info = mt5.symbol_info(p.symbol)
    tick = mt5.symbol_info_tick(p.symbol)
    if not info or not tick:
        log(f"  PID {p.ticket}: no symbol info, skipping")
        continue
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": p.symbol,
        "volume": p.volume,
        "type": mt5.ORDER_TYPE_BUY,  # opposite to close SELL
        "position": p.ticket,
        "price": tick.ask,
        "deviation": 50,
        "magic": p.magic,
        "comment": "AUTO-CLOSE-WRONG-DIR-OCR-BUG",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(request)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        closed_count += 1
        log(f"  ✓ CLOSED ticket {p.ticket} @ {tick.ask:.2f} (was SELL @ {p.price_open:.2f}, PnL ${p.profit:+.2f})")
    else:
        log(f"  ✗ FAILED to close ticket {p.ticket}: {res.comment if res else 'no response'}")

log(f"\nClosed {closed_count}/{len(positions)} BTC SELL positions.")

ai = mt5.account_info()
log(f"\nFinal account: balance=${ai.balance:.2f} equity=${ai.equity:.2f} positions={len(mt5.positions_get() or [])}")
mt5.shutdown()
log("Done.")
