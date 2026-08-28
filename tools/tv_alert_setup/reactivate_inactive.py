"""Re-activate any deactivated Rocket Prime alerts."""
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
PROFILE = HERE / "_browser_profile"
ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(3)
        api = ctx.request

        json_hdrs = {"Origin": "https://www.tradingview.com",
                     "Referer": "https://www.tradingview.com/chart/",
                     "Content-Type": "application/json"}

        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])

        inactive_rp = []
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            if ((cond.get("series") or [{}])[0]).get("pine_id") != ROCKET_PRIME:
                continue
            if not a.get("active", False):
                inactive_rp.append(a["alert_id"])

        if not inactive_rp:
            print("[OK] All Rocket Prime alerts are active. Nothing to do.")
            ctx.close()
            return 0

        print(f"Found {len(inactive_rp)} inactive RP alerts. Re-activating...")
        for aid in inactive_rp:
            try:
                rr = api.post("https://pricealerts.tradingview.com/restart_alerts",
                              data=json.dumps({"payload": {"alert_ids": [aid]}}),
                              headers=json_hdrs, timeout=15_000)
                ok = rr.status == 200 and '"s":"ok"' in rr.text()
                print(f"  alert {aid}: {'OK' if ok else 'FAIL ' + rr.text()[:140]}")
            except Exception as e:
                print(f"  alert {aid}: ERR {e}")
            time.sleep(0.3)

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
