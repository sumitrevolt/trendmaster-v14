"""Find TV's actual delete-alert endpoint by trying many patterns + intercepting
network when user manually deletes."""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright, Request

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"

# Get one alert ID to test with
CAT_PATH = HERE / "alerts_categorized.json"
cat = json.loads(CAT_PATH.read_text(encoding="utf-8"))
TEST_ALERT_ID = cat["delete_candidates"][0]["alert_id"]
print(f"Testing with alert_id: {TEST_ALERT_ID}")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=True,
        viewport={"width": 1600, "height": 1000},
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(4)
    api = ctx.request

    hdrs = {
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/chart/",
        "Content-Type": "application/json",
    }

    # Try a TON of endpoint variants
    candidates = [
        # POST endpoints
        ("POST", "https://pricealerts.tradingview.com/delete_alerts", {"payload": {"alert_id": TEST_ALERT_ID}}),
        ("POST", "https://pricealerts.tradingview.com/disable_alert", {"payload": {"alert_id": TEST_ALERT_ID}}),
        ("POST", "https://pricealerts.tradingview.com/cancel_alert", {"payload": {"alert_id": TEST_ALERT_ID}}),
        ("POST", "https://pricealerts.tradingview.com/destroy_alert", {"payload": {"alert_id": TEST_ALERT_ID}}),
        ("POST", "https://pricealerts.tradingview.com/cleanup", {"payload": {"alert_id": TEST_ALERT_ID}}),
        ("POST", "https://pricealerts.tradingview.com/dispose_alert", {"payload": {"alert_id": TEST_ALERT_ID}}),
        ("POST", "https://pricealerts.tradingview.com/api/delete_alert", {"payload": {"alert_id": TEST_ALERT_ID}}),
        ("POST", "https://pricealerts.tradingview.com/api/v1/delete_alert", {"payload": {"alert_id": TEST_ALERT_ID}}),
        # GET endpoints
        ("GET", f"https://pricealerts.tradingview.com/delete_alert/{TEST_ALERT_ID}", None),
        ("GET", f"https://pricealerts.tradingview.com/cancel_alert/{TEST_ALERT_ID}", None),
        # DELETE method
        ("DELETE", f"https://pricealerts.tradingview.com/alert/{TEST_ALERT_ID}", None),
        ("DELETE", f"https://pricealerts.tradingview.com/alerts/{TEST_ALERT_ID}", None),
        # Alternate id field name
        ("POST", "https://pricealerts.tradingview.com/remove_alert", {"payload": {"id": TEST_ALERT_ID}}),
        # Try without payload wrapper
        ("POST", "https://pricealerts.tradingview.com/remove_alert", {"alert_id": TEST_ALERT_ID}),
        # Singular "alert"
        ("POST", "https://pricealerts.tradingview.com/alert/remove", {"payload": {"alert_id": TEST_ALERT_ID}}),
        # "stop"
        ("POST", "https://pricealerts.tradingview.com/stop_alert", {"payload": {"alert_id": TEST_ALERT_ID}}),
        ("POST", "https://pricealerts.tradingview.com/deactivate_alert", {"payload": {"alert_id": TEST_ALERT_ID}}),
    ]
    for method, url, body in candidates:
        try:
            if method == "POST":
                r = api.post(url, data=json.dumps(body), headers=hdrs, timeout=8000)
            elif method == "DELETE":
                r = api.delete(url, headers=hdrs, timeout=8000)
            else:
                r = api.get(url, headers=hdrs, timeout=8000)
            txt = r.text()[:180]
            short_url = url.replace("https://pricealerts.tradingview.com", "")
            indicator = "***" if ('"s":"ok"' in txt or "no_such_endpoint" not in txt) else "   "
            print(f"  {indicator} {method:6} {short_url:<50}  HTTP {r.status} -> {txt[:90]!r}")
        except Exception as e:
            print(f"      {method} {url[:60]}  ERR  {e}")
        time.sleep(0.2)

    ctx.close()
