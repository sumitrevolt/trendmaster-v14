"""Dump raw list_alerts response to understand state."""
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
PROFILE = HERE / "_browser_profile"


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(3)
        api = ctx.request

        json_hdrs = {"Origin": "https://www.tradingview.com",
                     "Referer": "https://www.tradingview.com/chart/",
                     "Content-Type": "application/json"}

        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        print(f"HTTP status: {r.status}")
        try:
            data = r.json()
            print(f"Top-level keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            alerts = data.get("r", []) if isinstance(data, dict) else []
            print(f"Total alerts in 'r': {len(alerts)}")
            type_counts = {}
            pine_id_counts = {}
            for a in alerts:
                cond = a.get("condition") or {}
                t = cond.get("type", "?")
                type_counts[t] = type_counts.get(t, 0) + 1
                if t == "pine_alert":
                    series = cond.get("series") or [{}]
                    pid = series[0].get("pine_id", "?")
                    pine_id_counts[pid] = pine_id_counts.get(pid, 0) + 1
            print(f"Type breakdown: {type_counts}")
            print(f"Pine_id breakdown: {pine_id_counts}")
            if alerts:
                print(f"\nFirst alert sample:\n{json.dumps(alerts[0], indent=2)[:1500]}")
        except Exception as e:
            print(f"json parse failed: {e}")
            print(f"Raw text (first 500): {r.text()[:500]}")
        ctx.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
