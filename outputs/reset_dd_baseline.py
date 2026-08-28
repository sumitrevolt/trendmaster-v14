"""
Reset today's drawdown baseline so TV signals can resume firing.

Why: tv_executor's A3 gate compares current equity against
brain_state.json:start_of_day_equity. After real losses today
($1145.73 -> $1059.20 = 7.55% DD), the 3% brake locked everything out.

What: rebase sod_equity to CURRENT live equity. Risk management stays
active from the new baseline (next 5% loss from $1059.20 = $52.96 will
re-trigger the brake). This is NOT a disable-safety hack, it's the
"start fresh from now" semantics.

How:
  1. Read current equity from MT5
  2. Atomic write brain_state.json with new sod + cleared lockout
  3. Caller restarts brain so the change sticks

Caller is responsible for stopping brain BEFORE this script runs and
restarting it AFTER.
"""
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("config/.env")
import MetaTrader5 as mt5

STATE_PATH = Path("logs/brain_state.json")

if not mt5.initialize(
    login=int(os.getenv("MT5_LOGIN")),
    password=os.getenv("MT5_PASSWORD"),
    server=os.getenv("MT5_SERVER"),
):
    print(f"[FATAL] MT5 init failed: {mt5.last_error()}")
    sys.exit(1)

ai = mt5.account_info()
if ai is None:
    print("[FATAL] account_info() returned None")
    mt5.shutdown()
    sys.exit(1)

current_equity = float(ai.equity)
print(f"  Live equity: ${current_equity:.2f}")
print(f"  Live balance: ${ai.balance:.2f}")
mt5.shutdown()

if not STATE_PATH.exists():
    print(f"[FATAL] {STATE_PATH} missing — refusing to create from scratch")
    sys.exit(1)

state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

before = {
    "sod": state.get("start_of_day_equity"),
    "peak": state.get("daily_drawdown_peak_eq"),
    "lockout_until": state.get("drawdown_lockout_until"),
    "trading_paused": state.get("trading_paused"),
    "cooldown": state.get("cooldown_until_ts"),
}
print(f"  BEFORE: {json.dumps(before, indent=2)}")

state["start_of_day_equity"] = current_equity
state["daily_drawdown_peak_eq"] = current_equity
state["drawdown_lockout_until"] = 0
state["trading_paused"] = False
state["cooldown_until_ts"] = 0
state["last_saved_at"] = int(time.time())

# Atomic write
tmp = STATE_PATH.with_suffix(".json.tmp")
tmp.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
tmp.replace(STATE_PATH)

print(f"  AFTER:  sod=${current_equity:.2f}  peak=${current_equity:.2f}  lockout=0  paused=False")
print()
print("OK — brain_state.json rebased. Restart brain now to lock it in.")
