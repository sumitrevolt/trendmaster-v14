"""Delete the 3 leftover non-Rocket-Prime cross alerts via TV API."""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE = Path(r"C:\Users\Ratanshila\Documents\autmated trading\tools\tv_alert_setup\_browser_profile")
TARGETS = [4619979599, 4619964948, 4617178718]  # the 3 cross alerts

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request

    hdrs = {"Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/chart/",
            "Content-Type": "application/json"}

    rr = api.post("https://pricealerts.tradingview.com/delete_alerts",
                  data=json.dumps({"payload": {"alert_ids": TARGETS}}),
                  headers=hdrs, timeout=15_000)
    print(f"  delete: status={rr.status} body={rr.text()[:200]}")

    # Verify
    time.sleep(1)
    r = api.post("https://pricealerts.tradingview.com/list_alerts",
                 data=json.dumps({"payload": {"limit": 5000}}),
                 headers=hdrs, timeout=15_000)
    alerts = r.json().get("r", [])
    print(f"\n  AFTER: {len(alerts)} total alerts on account")
    rp = sum(1 for a in alerts if (a.get("condition") or {}).get("type") == "pine_alert")
    other = len(alerts) - rp
    print(f"  pine_alerts: {rp}  other: {other}")

    ctx.close()
