"""More aggressive probing for TV create_alert API."""
from __future__ import annotations
import copy
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
TEMPLATE = json.loads((HERE / "pine_alert_template.json").read_text(encoding="utf-8"))

# Build the alert payload identical to template structure
target = copy.deepcopy(TEMPLATE)
target["resolution"] = "60"
target["condition"]["resolution"] = "60"
for c in target.get("conditions", []):
    c["resolution"] = "60"
for k in ("alert_id", "create_time", "last_fire_time", "last_fire_bar_time",
          "last_error", "last_stop_reason"):
    target.pop(k, None)
exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
target["expiration"] = exp
target["expiration_policy"] = {"time": exp, "policy": "fixed_date"}
target["name"] = "PROBE: Rocket Prime XAUUSD H1"

# also check schema variations
DATA_BASE = {
    "symbol": target["symbol"],
    "resolution": target["resolution"],
    "expiration": target["expiration"],
    "expiration_policy": target["expiration_policy"],
    "kinds": ["regular"],
    "type": "indicator",
    "active": True,
    "auto_deactivate": False,
    "email": True,
    "popup": True,
    "mobile_push": True,
    "sms_over_email": True,
    "sound_file": "alert/3_notes_reverb",
    "sound_duration": 30,
    "message": "",
    "name": target["name"],
    "web_hook": "https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?symbol=XAUUSD",
    "complexity": "complex",
    "cross_interval": False,
    "condition": target["condition"],
    "conditions": target["conditions"],
}

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE_DIR), headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request
    hdrs = {"Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/chart/",
            "Content-Type": "application/json"}

    # Try various endpoints + envelopes
    tests = [
        ("create_alert with payload + minimal envelope",
         "create_alert",
         {"payload": DATA_BASE}),
        ("create_indicator_alert",
         "create_indicator_alert",
         {"payload": DATA_BASE}),
        ("create_alert + alert wrapper",
         "create_alert",
         {"payload": {"alert": DATA_BASE, "kind": "regular"}}),
        ("manage/save_alert",
         "manage/save_alert",
         {"payload": DATA_BASE}),
        ("api/save_alert",
         "api/save_alert",
         {"payload": DATA_BASE}),
        ("modify_alert",
         "modify_alert",
         {"payload": DATA_BASE}),
        ("create_alert with snake_kinds",
         "create_alert",
         {"payload": {**DATA_BASE, "kind": "regular"}}),
    ]
    for label, ep, body in tests:
        url = f"https://pricealerts.tradingview.com/{ep}"
        try:
            r = api.post(url, data=json.dumps(body), headers=hdrs, timeout=10000)
            txt = r.text()[:500]
            ok = '"s":"ok"' in txt
            mark = "*** OK ***" if ok else "         "
            print(f"\n{mark} {label}")
            print(f"  POST {url}")
            print(f"  HTTP {r.status} body: {txt[:300]}")
        except Exception as e:
            print(f"\nERR {label}: {e}")
        time.sleep(0.4)
    ctx.close()
