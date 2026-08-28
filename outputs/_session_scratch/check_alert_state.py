"""Check current TV alert state via API + recent signals."""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
PROFILE = ROOT / "tools" / "tv_alert_setup" / "_browser_profile"
ROCKET = "PUB;56f0fb74de7f4eed9325b987428b727e"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request

    r = api.post("https://pricealerts.tradingview.com/list_alerts",
                 data=json.dumps({"payload": {"limit": 5000}}),
                 headers={"Origin": "https://www.tradingview.com",
                          "Referer": "https://www.tradingview.com/chart/",
                          "Content-Type": "application/json"},
                 timeout=15_000)
    alerts = r.json().get("r", [])
    rp = []
    for a in alerts:
        cond = a.get("condition") or {}
        if cond.get("type") != "pine_alert":
            continue
        series = cond.get("series") or [{}]
        if series[0].get("pine_id") != ROCKET:
            continue
        sym_raw = a.get("symbol", "")
        try:
            full = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
        except Exception:
            full = sym_raw
        rp.append({
            "alert_id": a.get("alert_id"),
            "symbol": full,
            "resolution": a.get("resolution"),
            "active": a.get("active"),
            "name": a.get("name"),
            "last_fire_time": a.get("last_fire_time"),
            "last_error": a.get("last_error"),
            "last_stop_reason": a.get("last_stop_reason"),
            "expiration": a.get("expiration"),
            "web_hook_short": (a.get("web_hook") or "")[:80],
        })
    rp.sort(key=lambda x: (x["symbol"], x["resolution"]))
    print(f"=== ROCKET PRIME ALERTS: {len(rp)} ===\n")
    actives = sum(1 for x in rp if x["active"])
    inactives = len(rp) - actives
    print(f"  Active: {actives}   Inactive: {inactives}\n")
    print(f"  {'symbol':<24} {'res':<5} {'active':<7} {'last_fire':<22} {'last_stop':<14}")
    for x in rp:
        lf = x["last_fire_time"] or "-"
        ls = x["last_stop_reason"] or "-"
        print(f"  {x['symbol']:<24} {x['resolution']:<5} {str(x['active']):<7} {lf:<22} {ls:<14}")
        if x.get("last_error"):
            print(f"    └─ ERROR: {x['last_error']}")
    ctx.close()
