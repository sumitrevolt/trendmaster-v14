"""Check TV account plan/entitlements with exported cookies."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE = HERE / "_browser_profile"
COOKIES_JSON = Path(sys.argv[1])

try:
    raw = json.loads(COOKIES_JSON.read_text(encoding="utf-8"))
except UnicodeDecodeError:
    raw = json.loads(COOKIES_JSON.read_text(encoding="utf-16"))
cookies = raw["data"]["cookies"]

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
    ctx.add_cookies(cookies)
    api = ctx.request
    hdrs = {"Referer": "https://www.tradingview.com/"}
    for url in ("https://www.tradingview.com/api/v1/users/current",
                "https://www.tradingview.com/accounts/current/",
                "https://www.tradingview.com/api/v1/subscriptions/"):
        try:
            r = api.get(url, headers=hdrs, timeout=30_000)
            txt = r.text()
            print(f"=== {url} -> {r.status}")
            print(txt[:900], "\n")
        except Exception as e:
            print(f"=== {url} ERR {e}")
    ctx.close()
