"""List TV alerts using fresh cookies exported from TradingView Desktop (CDP)."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE = HERE / "_browser_profile"
COOKIES_JSON = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\Users\Ratanshila\AppData\Local\Temp\opencode\cookies_raw.txt")

try:
    raw = json.loads(COOKIES_JSON.read_text(encoding="utf-8"))
except UnicodeDecodeError:
    raw = json.loads(COOKIES_JSON.read_text(encoding="utf-16"))
cookies = raw["data"]["cookies"]

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
    ctx.add_cookies(cookies)
    api = ctx.request
    hdrs = {"Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/chart/",
            "Content-Type": "application/json"}
    r = api.post("https://pricealerts.tradingview.com/list_alerts",
                 data=json.dumps({"payload": {"limit": 5000}}), headers=hdrs, timeout=45_000)
    print(f"HTTP {r.status}")
    obj = r.json()
    if obj.get("s") != "ok":
        print("API error:", json.dumps(obj)[:300])
    alerts = obj.get("r") or []
    print(f"total alerts: {len(alerts)}")
    if alerts:
        print("SAMPLE ALERT JSON:")
        print(json.dumps(alerts[0], indent=2)[:2500])
    for a in alerts:
        sym = a.get("symbol", "?")
        wh = a.get("web_hook") or a.get("webhook") or ""
        print(f"  id={a.get('alert_id')} | res={a.get('resolution')} | {sym} | {wh[:90]}")
    ctx.close()
