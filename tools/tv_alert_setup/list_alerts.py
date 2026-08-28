"""Use Playwright to read TV's alerts list — see what we've actually created."""
from __future__ import annotations
import sys
import time
import json
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=True,
        viewport={"width": 1600, "height": 1000},
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(5)

    # Hit TV's alert-list API directly using the established session
    api = ctx.request
    candidates = [
        "https://pricealerts.tradingview.com/list_alerts",
        "https://pricealerts.tradingview.com/list_alerts_by_type",
        "https://pricealerts.tradingview.com/manage/list",
    ]
    for url in candidates:
        try:
            r = api.post(url, data="{}", headers={"Content-Type": "application/json"}, timeout=8000)
            print(f"\n=== {url} -> HTTP {r.status} ===")
            txt = r.text()
            try:
                obj = json.loads(txt)
                print(json.dumps(obj, indent=2)[:3000])
            except Exception:
                print(txt[:1500])
        except Exception as e:
            print(f"\n{url} -> ERR {e}")

    ctx.close()
