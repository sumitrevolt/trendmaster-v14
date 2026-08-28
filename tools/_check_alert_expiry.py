"""Quick check: how many days until each Rocket Prime alert expires."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

PROFILE = Path("tools/tv_alert_setup/_browser_profile")
ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    api = ctx.request
    r = api.post(
        "https://pricealerts.tradingview.com/list_alerts",
        data=json.dumps({"payload": {"limit": 5000}}),
        headers={
            "Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/chart/",
            "Content-Type": "application/json",
        },
        timeout=15000,
    )
    alerts = r.json().get("r", [])
    ctx.close()

now = datetime.now(timezone.utc)
rp = []
for a in alerts:
    cond = a.get("condition") or {}
    if cond.get("type") != "pine_alert":
        continue
    s = (cond.get("series") or [{}])[0].get("pine_id")
    if s != ROCKET_PRIME:
        continue
    sym_raw = a.get("symbol", "")
    try:
        sym = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
    except Exception:
        sym = sym_raw
    try:
        exp = datetime.fromisoformat(a.get("expiration", "").replace("Z", "+00:00"))
        d = (exp - now).total_seconds() / 86400
    except Exception:
        d = None
    rp.append((sym, d))

rp.sort(key=lambda x: x[1] if x[1] is not None else 999)
print(f"Total Rocket Prime alerts: {len(rp)}\n")
print(f"{'Symbol':<22}  Days until expiry")
print("-" * 45)
for sym, d in rp:
    print(f"{sym:<22}  {d:.1f}d" if d is not None else f"{sym:<22}  unknown")
print()
soonest = rp[0][1] if rp and rp[0][1] is not None else 999
print(f"Soonest expiry: {soonest:.1f} days")
print(f"Renewer threshold: 10 days  ->  trigger renewal in ~{max(0, soonest - 10):.1f} days")
