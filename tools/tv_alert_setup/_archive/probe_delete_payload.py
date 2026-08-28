"""Find correct payload for /delete_alerts."""
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
CAT = json.loads((HERE / "alerts_categorized.json").read_text(encoding="utf-8"))
TEST_ID = CAT["delete_candidates"][0]["alert_id"]
URL = "https://pricealerts.tradingview.com/delete_alerts"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE_DIR), headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request
    hdrs = {"Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/chart/",
            "Content-Type": "application/json"}

    payloads = [
        {"payload": {"alert_ids": [TEST_ID]}},
        {"payload": {"ids": [TEST_ID]}},
        {"payload": {"alerts": [TEST_ID]}},
        {"alert_ids": [TEST_ID]},
        {"ids": [TEST_ID]},
        {"payload": {"alert_id": TEST_ID, "kind": "regular"}},
        {"payload": {"alerts_ids": [TEST_ID]}},
        {"payload": [TEST_ID]},
        [TEST_ID],
        {"payload": {"alert_id": str(TEST_ID)}},  # str instead of int
        {"alert_id": TEST_ID, "kind": "regular"},
    ]
    for body in payloads:
        try:
            r = api.post(URL, data=json.dumps(body), headers=hdrs, timeout=8000)
            txt = r.text()[:240]
            ok = '"s":"ok"' in txt
            mark = "*** OK ***" if ok else "         "
            print(f"  {mark}  body={json.dumps(body)[:60]:<60}  HTTP {r.status} -> {txt[:140]!r}")
            if ok:
                print("\nSUCCESS PAYLOAD FOUND. Stopping further probes.")
                break
        except Exception as e:
            print(f"  ERR  {body}: {e}")
        time.sleep(0.3)
    ctx.close()
