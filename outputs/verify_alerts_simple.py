"""Simple verify — count alerts + check first URL."""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE = Path(r"C:\Users\Ratanshila\Documents\autmated trading\tools\tv_alert_setup\_browser_profile")
ROCKET = "PUB;56f0fb74de7f4eed9325b987428b727e"

# Retry up to 3 times on ECONNRESET
for attempt in range(3):
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            pg.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
            time.sleep(4)
            r = ctx.request.post(
                "https://pricealerts.tradingview.com/list_alerts",
                data=json.dumps({"payload": {"limit": 5000}}),
                headers={"Origin": "https://www.tradingview.com",
                         "Referer": "https://www.tradingview.com/chart/",
                         "Content-Type": "application/json"},
                timeout=20_000,
            )
            alerts = r.json().get("r", [])
            rp = [a for a in alerts
                  if (a.get("condition") or {}).get("type") == "pine_alert"
                  and ((a.get("condition") or {}).get("series") or [{}])[0].get("pine_id") == ROCKET]
            tf_urls = sum(1 for a in rp if "tf=" in (a.get("web_hook") or ""))
            sym_urls = sum(1 for a in rp if "symbol=" in (a.get("web_hook") or ""))
            act = sum(1 for a in rp if a.get("active"))
            print(f"  Total Rocket Prime: {len(rp)}")
            print(f"  Active: {act}/{len(rp)}")
            print(f"  URLs with symbol= : {sym_urls}/{len(rp)}")
            print(f"  URLs with tf=     : {tf_urls}/{len(rp)}")
            if rp:
                print(f"  Sample URL: {rp[0].get('web_hook')[:140]}")
            ctx.close()
        break
    except Exception as e:
        print(f"  attempt {attempt+1} failed: {e}")
        time.sleep(3)
