"""Test multiple payload envelope shapes for create_alert."""
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

# Build a target alert spec
target = copy.deepcopy(TEMPLATE)
target["symbol"] = '={"symbol":"OANDA:XAUUSD","adjustment":"splits","session":"regular","currency-id":"USD"}'
target["pro_symbol"] = target["symbol"]
target["resolution"] = "60"  # H1
target["condition"]["resolution"] = "60"
for c in target.get("conditions", []):
    c["resolution"] = "60"
for k in ("alert_id", "create_time", "last_fire_time", "last_fire_bar_time",
          "last_error", "last_stop_reason"):
    target.pop(k, None)
exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
target["expiration"] = exp
target["expiration_policy"] = {"time": exp, "policy": "fixed_date"}
target["name"] = "TEST Rocket Prime: XAUUSD H1"
target["web_hook"] = "https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?symbol=XAUUSD"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE_DIR), headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request
    hdrs = {"Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/chart/",
            "Content-Type": "application/json"}

    # Different envelope shapes to try
    envelopes = [
        ("flat", target),
        ("payload-wrap", {"payload": target}),
        ("alert-key", {"alert": target}),
        ("payload+kind", {"payload": {"alert": target, "kind": "regular"}}),
    ]
    for name, body in envelopes:
        try:
            r = api.post("https://pricealerts.tradingview.com/create_alert",
                          data=json.dumps(body), headers=hdrs, timeout=10000)
            txt = r.text()[:400]
            ok = '"s":"ok"' in txt
            mark = "*** OK ***" if ok else "         "
            print(f"  {mark} envelope={name:<20}  HTTP {r.status} -> {txt[:200]!r}")
            if ok:
                print(f"\nWORKING ENVELOPE: {name}")
                print("Body shape:", json.dumps({k: ('...' if isinstance(v, (dict, list)) else v) for k, v in body.items()}))
                break
        except Exception as e:
            print(f"  ERR  envelope={name}: {e}")
        time.sleep(0.4)
    ctx.close()
