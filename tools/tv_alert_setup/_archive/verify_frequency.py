"""List all Rocket Prime alerts and show their frequency setting."""
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
ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"
TF_LABEL = {"1": "M1", "5": "M5", "15": "M15", "30": "M30", "60": "H1", "240": "H4"}


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
        alerts = r.json().get("r", [])
        rp = []
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            sym_raw = a.get("symbol", "")
            try:
                full = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
            except Exception:
                full = sym_raw
            rp.append((full, str(a.get("resolution", "")), cond.get("frequency", "?")))
        rp.sort()
        print(f"Total Rocket Prime alerts: {len(rp)}")
        print(f"{'Symbol':<28} {'TF':<5} {'Frequency'}")
        print("-" * 60)
        all_instant = True
        for fs, res, freq in rp:
            mark = "OK" if freq == "all" else "BAR-CLOSE"
            if freq != "all":
                all_instant = False
            print(f"{fs:<28} {TF_LABEL.get(res, res):<5} {freq:<22} {mark}")
        print("-" * 60)
        print(f"{'ALL INSTANT' if all_instant else 'NOT ALL INSTANT YET'}")
        ctx.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
