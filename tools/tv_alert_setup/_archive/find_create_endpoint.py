"""Find TV's CREATE alert API endpoint by probing common patterns."""
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

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE_DIR), headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request
    hdrs = {"Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/chart/",
            "Content-Type": "application/json"}

    # Use a minimal-but-valid payload to test endpoint existence
    minimal_body = {"payload": {"symbol": "OANDA:EURUSD"}}

    candidates = [
        "create_alert", "create_alerts", "save_alert", "save_alerts",
        "add_alert", "add_alerts", "new_alert",
        "modify_alert", "manage_alert", "manage_create", "create",
        "alert/create", "alert/save", "alerts/create", "alerts/save",
    ]
    for ep in candidates:
        url = f"https://pricealerts.tradingview.com/{ep}"
        try:
            r = api.post(url, data=json.dumps(minimal_body), headers=hdrs, timeout=8000)
            txt = r.text()[:160]
            no_endpoint = "no_such_endpoint" in txt
            mark = "***" if not no_endpoint else "   "
            print(f"  {mark} POST /{ep:<25} HTTP {r.status} -> {txt[:120]!r}")
        except Exception as e:
            print(f"      POST /{ep}  ERR {e}")
        time.sleep(0.2)
    ctx.close()
