"""Add the auth secret to all Rocket Prime alert webhook URLs.

TV's webhook URL gets called as-is by TradingView. Receiver requires the
secret as query param or body field. Updating the webhook URL to include
?secret=... is the cleanest fix.
"""
from __future__ import annotations

import json
import os
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
CAPTURE_PATH = HERE / "capture_create_post.json"
ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"

# Read secret from config/.env
ROOT = HERE.parent.parent
ENV_PATH = ROOT / "config" / ".env"
SECRET = None
for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
    if line.startswith("TV_WEBHOOK_SECRET"):
        SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
if not SECRET:
    print("FATAL: TV_WEBHOOK_SECRET not in config/.env")
    sys.exit(1)

print(f"Using secret: {SECRET[:8]}...{SECRET[-8:]}")
NEW_URL = f"https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret={SECRET}"
print(f"New webhook URL pattern: {NEW_URL[:80]}...")

# TV's modify_alert endpoint takes a payload similar to create_alert
captures = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
cap = captures[0]
captured_url = cap["url"]
captured_headers = cap.get("headers") or {}

create_hdrs = {k: v for k, v in captured_headers.items()
               if k.lower() not in ("host", "content-length", "cookie", "connection",
                                     "accept-encoding")}
create_hdrs["Origin"] = "https://www.tradingview.com"
create_hdrs["Referer"] = "https://www.tradingview.com/"
create_hdrs["Content-Type"] = "text/plain;charset=UTF-8"

json_hdrs = {"Origin": "https://www.tradingview.com",
             "Referer": "https://www.tradingview.com/chart/",
             "Content-Type": "application/json"}

# Derive modify URL by replacing /create_alert with /modify_alert in the URL
# (TradingView API convention — uses ?action= or path replacement)
# We'll first try modify_alert path with same query string structure
modify_url = captured_url.replace("/create_alert", "/modify_alert")
print(f"Modify URL: {modify_url[:80]}...\n")


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(3)
        api = ctx.request

        # 1. List Rocket Prime alerts
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])

        targets = []
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            wh = a.get("web_hook") or ""
            if "secret=" in wh:
                continue  # already has secret
            targets.append(a)

        print(f"=== Found {len(targets)} Rocket Prime alerts needing secret ===")
        if not targets:
            print("All alerts already have secret. Nothing to do.")
            ctx.close()
            return 0

        # 2. For each alert, delete + recreate with new webhook URL
        # (modify_alert is undocumented; simpler to delete + recreate)
        success = 0
        failed = 0

        # Step 2a: collect IDs to delete + payloads to recreate
        to_delete = []
        recreate_payloads = []
        for a in targets:
            to_delete.append(a["alert_id"])
            # Build the payload exactly like the existing alert, but new web_hook
            payload = {k: v for k, v in a.items()
                       if k not in ("alert_id", "create_time", "fire_time",
                                     "last_fire_time", "last_fire_bar_time",
                                     "last_error", "last_stop_reason",
                                     "presentation_data", "mutable_study_data",
                                     "pro_symbol")}
            payload["web_hook"] = NEW_URL
            payload["expiration"] = (datetime_now_iso())
            recreate_payloads.append(payload)

        # Step 2b: delete in batch
        print(f"\n=== Step A: Delete {len(to_delete)} alerts ===")
        BATCH = 25
        for i in range(0, len(to_delete), BATCH):
            chunk = to_delete[i:i+BATCH]
            r = api.post("https://pricealerts.tradingview.com/delete_alerts",
                         data=json.dumps({"payload": {"alert_ids": chunk}}),
                         headers=json_hdrs, timeout=15_000)
            txt = r.text()
            ok = (r.status == 200 and '"s":"ok"' in txt)
            print(f"  delete batch ({len(chunk)}): {'OK' if ok else 'FAIL ' + txt[:100]}")
            time.sleep(0.4)

        # Step 2c: recreate with new URL
        print(f"\n=== Step B: Recreate {len(recreate_payloads)} alerts with secret URL ===")
        for i, payload in enumerate(recreate_payloads):
            body = {"payload": payload}
            try:
                r = api.post(captured_url, data=json.dumps(body), headers=create_hdrs, timeout=15_000)
                txt = r.text()[:200]
                if r.status == 200 and '"s":"ok"' in txt:
                    success += 1
                    aid = None
                    try:
                        aid = r.json().get("r", {}).get("alert_id")
                    except Exception:
                        pass
                    print(f"  [OK   {i+1}/{len(recreate_payloads)}] {payload.get('symbol','')[:60]} alert_id={aid}")
                else:
                    failed += 1
                    print(f"  [FAIL {i+1}/{len(recreate_payloads)}] {payload.get('symbol','')[:60]} {txt[:100]}")
            except Exception as e:
                failed += 1
                print(f"  [ERR  {i+1}/{len(recreate_payloads)}] {e}")
            time.sleep(0.4)

        print(f"\n=== Done. created={success} failed={failed} ===")

        # Verify
        print(f"\n=== Final verification ===")
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])
        with_secret = 0
        without = 0
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            wh = a.get("web_hook") or ""
            if "secret=" in wh:
                with_secret += 1
            else:
                without += 1
        print(f"  Rocket Prime alerts: {with_secret} with secret, {without} without")

        ctx.close()
    return 0


def datetime_now_iso():
    """Helper for fresh expiration."""
    from datetime import datetime, timezone, timedelta
    return (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


if __name__ == "__main__":
    sys.exit(main())
