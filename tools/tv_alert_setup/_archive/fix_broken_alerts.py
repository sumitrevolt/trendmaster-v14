"""Surgical fix for broken alerts:
  1. Delete 3 alerts with DEAD trycloudflare URLs (causing TV delivery errors).
  2. Delete 21 alerts with NO webhook URL (wasting quota, never deliver).
  Total deleted: 24 alerts → frees ~24 quota slots.

Then can run replay_pine_alerts.py to fill missing (symbol, TF) combos.
"""
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
GOOD_URL = "https://shadow-cosmos-unending.ngrok-free.dev/tv-signal"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE_DIR), headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request
    hdrs = {"Origin":"https://www.tradingview.com","Referer":"https://www.tradingview.com/chart/","Content-Type":"application/json"}

    # Get current alerts
    r = api.post("https://pricealerts.tradingview.com/list_alerts",
                 data=json.dumps({"payload":{"limit":5000}}), headers=hdrs, timeout=15_000)
    alerts = r.json().get("r", [])
    print(f"Total alerts before cleanup: {len(alerts)}")

    delete_ids = []
    for a in alerts:
        web_hook = a.get("web_hook") or ""
        if not web_hook:
            delete_ids.append(a["alert_id"])
        elif GOOD_URL not in web_hook:
            delete_ids.append(a["alert_id"])

    print(f"\nWill delete {len(delete_ids)} broken alerts (no-webhook + dead-url)")

    if delete_ids:
        # Batch delete (works up to ~25 per call)
        BATCH = 25
        deleted = 0
        for i in range(0, len(delete_ids), BATCH):
            chunk = delete_ids[i:i+BATCH]
            body = {"payload": {"alert_ids": chunk}}
            r = api.post("https://pricealerts.tradingview.com/delete_alerts",
                         data=json.dumps(body), headers=hdrs, timeout=15_000)
            txt = r.text()
            if r.status == 200 and '"s":"ok"' in txt:
                deleted += len(chunk)
                print(f"  [batch ok] deleted {len(chunk)} ids")
            else:
                print(f"  [batch FAIL] {txt[:200]}")
            time.sleep(0.4)
        print(f"\nDeleted {deleted} alerts")

    # Verify
    time.sleep(1)
    r = api.post("https://pricealerts.tradingview.com/list_alerts",
                 data=json.dumps({"payload":{"limit":5000}}), headers=hdrs, timeout=15_000)
    alerts2 = r.json().get("r", [])
    print(f"\nTotal alerts after cleanup: {len(alerts2)}")

    ctx.close()
