"""Find which Rocket Prime alert is inactive + reactivate via TV API."""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE = Path(r"C:\Users\Ratanshila\Documents\autmated trading\tools\tv_alert_setup\_browser_profile")
ROCKET = "PUB;56f0fb74de7f4eed9325b987428b727e"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request

    json_hdrs = {"Origin": "https://www.tradingview.com",
                 "Referer": "https://www.tradingview.com/chart/",
                 "Content-Type": "application/json"}

    r = api.post("https://pricealerts.tradingview.com/list_alerts",
                 data=json.dumps({"payload": {"limit": 5000}}), headers=json_hdrs, timeout=15_000)
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
        rp.append({"id": a["alert_id"], "sym": full, "res": a["resolution"],
                   "active": a["active"], "last_stop": a.get("last_stop_reason"),
                   "last_error": a.get("last_error"), "name": a.get("name")})

    inactive = [a for a in rp if not a["active"]]
    print(f"=== {len(rp)} total Rocket Prime alerts; {len(inactive)} INACTIVE ===")
    for a in inactive:
        print(f"  INACTIVE: id={a['id']}  {a['sym']:<25} res={a['res']:<5}  stop={a['last_stop']}  err={a['last_error']}  name={a['name']}")

    if not inactive:
        print("All alerts already active.")
    else:
        # Try /restart_alerts to reactivate
        ids = [a["id"] for a in inactive]
        print(f"\n=== restart_alerts on {ids} ===")
        rr = api.post("https://pricealerts.tradingview.com/restart_alerts",
                      data=json.dumps({"payload": {"alert_ids": ids}}),
                      headers=json_hdrs, timeout=15_000)
        print(f"  status={rr.status}  body={rr.text()[:300]}")

    # Re-list to verify
    time.sleep(2)
    r2 = api.post("https://pricealerts.tradingview.com/list_alerts",
                  data=json.dumps({"payload": {"limit": 5000}}), headers=json_hdrs, timeout=15_000)
    alerts2 = r2.json().get("r", [])
    rp2 = [a for a in alerts2
           if (a.get("condition") or {}).get("type") == "pine_alert"
           and (((a.get("condition") or {}).get("series") or [{}])[0].get("pine_id")) == ROCKET]
    actives = sum(1 for a in rp2 if a["active"])
    print(f"\n=== AFTER: {len(rp2)} total, {actives} active, {len(rp2)-actives} inactive ===")

    ctx.close()
