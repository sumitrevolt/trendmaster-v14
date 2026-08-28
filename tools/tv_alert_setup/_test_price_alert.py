"""Probe: can this account create a SIMPLE price alert (non-pine)?"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

COOKIES = Path(sys.argv[1])
PROFILE = Path(__file__).resolve().parent / "_browser_profile"

try:
    raw = json.loads(COOKIES.read_text(encoding="utf-8"))
except UnicodeDecodeError:
    raw = json.loads(COOKIES.read_text(encoding="utf-16"))
cookies = raw["data"]["cookies"]

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
    ctx.add_cookies(cookies)
    api = ctx.request
    hdrs = {"Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/chart/",
            "Content-Type": "text/plain;charset=UTF-8"}
    symbol_field = "=" + json.dumps(
        {"currency-id": "USD", "session": "regular", "symbol": "OANDA:XAUUSD"},
        separators=(",", ":"))
    payload = {
        "symbol": symbol_field,
        "resolution": "5",
        "expiration": "2026-09-21T00:00:00.000Z",
        "auto_deactivate": True,
        "conditions": [{"type": "cross", "series": [{"type": "price", "value": "4500"}],
                        "operation": "down"}],
        "message": "TEST price alert - ignore",
        "name": None,
        "email": True,
        "popup": False,
        "mobile_push": False,
        "sms_over_email": False,
        "sound_file": "",
        "sound_duration": 0,
        "active": True,
        "ignore_warnings": True,
    }
    r = api.post("https://pricealerts.tradingview.com/create_alert",
                 data=json.dumps({"payload": payload}), headers=hdrs, timeout=30_000)
    print(r.status, r.text()[:300])
    # cleanup if created
    try:
        aid = r.json().get("r", {}).get("alert_id")
        if aid:
            jh = {"Origin": hdrs["Origin"], "Referer": hdrs["Referer"],
                  "Content-Type": "application/json"}
            d = api.post("https://pricealerts.tradingview.com/delete_alerts",
                         data=json.dumps({"payload": {"alert_ids": [aid]}}),
                         headers=jh, timeout=30_000)
            print("cleanup:", d.status, d.text()[:60])
    except Exception as e:
        print("cleanup skipped:", e)
    ctx.close()
