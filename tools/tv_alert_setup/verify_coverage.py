"""Refresh inventory + show coverage matrix: which (symbol, TF) have Rocket Prime alerts."""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"

ROCKET_PRIME_PINE_ID = "PUB;56f0fb74de7f4eed9325b987428b727e"

SYMBOLS = ["XAUUSD","XAGUSD","EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD",
           "AUDUSD","NZDUSD","EURJPY","GBPJPY","AUDJPY","CADJPY","EURGBP",
           "BTCUSD","ETHUSD","XTIUSD","XBRUSD","XNGUSD"]
TF_MAP = {"M5": "5", "M15": "15", "H1": "60", "H4": "240"}
RES_TO_TF = {v: k for k, v in TF_MAP.items()}

def _exch(s):
    if s in ("BTCUSD","ETHUSD"): return "BINANCE"
    if s in ("XTIUSD","XBRUSD","XNGUSD"): return "TVC"
    return "OANDA"

def _broker(s):
    return {"XTIUSD":"USOIL","XBRUSD":"UKOIL","XNGUSD":"NATGASUSD"}.get(s,s)

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE_DIR), headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request
    hdrs = {"Origin":"https://www.tradingview.com",
            "Referer":"https://www.tradingview.com/chart/",
            "Content-Type":"application/json"}
    r = api.post("https://pricealerts.tradingview.com/list_alerts",
                 data=json.dumps({"payload":{"limit":5000}}),
                 headers=hdrs, timeout=15_000)
    if r.status != 200:
        print(f"FATAL list_alerts: HTTP {r.status}")
        sys.exit(1)
    alerts = r.json().get("r", [])
    ctx.close()

# Build map of (clean_symbol, resolution) -> True for Rocket Prime alerts
rp_present = set()
other_pine = []
for a in alerts:
    cond = a.get("condition") or {}
    if cond.get("type") != "pine_alert":
        continue
    series = cond.get("series") or [{}]
    pine_id = series[0].get("pine_id", "")
    sym_raw = a.get("symbol","")
    try:
        sym_obj = json.loads(sym_raw[1:]) if sym_raw.startswith("=") else {}
        sym = sym_obj.get("symbol","")
    except Exception:
        sym = sym_raw
    res = str(a.get("resolution",""))
    if pine_id == ROCKET_PRIME_PINE_ID:
        rp_present.add((sym, res))
    else:
        other_pine.append((sym, res, pine_id[:30]))

print(f"=== Total alerts in account: {len(alerts)} ===")
print(f"=== Rocket Prime alerts: {len(rp_present)} ===\n")

print(f"=== COVERAGE MATRIX (Rocket Prime: {ROCKET_PRIME_PINE_ID[:30]}...) ===\n")
print(f"  {'Symbol':<10}  M5  M15  H1   H4")
print(f"  {'------':<10} ---  ---  ---  ---")
total_have = 0
total_target = 0
missing = []
for sym in SYMBOLS:
    full_sym = f"{_exch(sym)}:{_broker(sym)}"
    row = []
    for tf, res in TF_MAP.items():
        total_target += 1
        if (full_sym, res) in rp_present:
            row.append(" ✓ ")
            total_have += 1
        else:
            row.append(" - ")
            missing.append(f"{sym} {tf}")
    print(f"  {sym:<10}  {row[0]}  {row[1]}  {row[2]}  {row[3]}")

print(f"\nCovered: {total_have} / {total_target} ({100*total_have/total_target:.0f}%)")
print(f"Missing: {len(missing)}")
if missing[:20]:
    print("First 20 missing:", missing[:20])

if other_pine:
    print(f"\n=== Pine alerts on OTHER indicators ({len(other_pine)}) ===")
    for s, r, pid in other_pine[:10]:
        tf = RES_TO_TF.get(r, r)
        print(f"  {s:<25} {tf:<4}  pine_id={pid!r}")
