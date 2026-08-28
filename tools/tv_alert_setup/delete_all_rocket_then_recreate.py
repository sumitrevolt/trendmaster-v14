"""Delete ALL existing Rocket Prime alerts, then run recreate_top5_instant.py."""
from __future__ import annotations
import json
import subprocess
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
ROOT = HERE.parent.parent
PY = ROOT / ".venv/Scripts/python.exe"


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
        rp_ids = []
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            rp_ids.append(a["alert_id"])
        print(f"Deleting {len(rp_ids)} Rocket Prime alerts…", flush=True)
        if rp_ids:
            BATCH = 25
            for i in range(0, len(rp_ids), BATCH):
                chunk = rp_ids[i:i + BATCH]
                rr = api.post("https://pricealerts.tradingview.com/delete_alerts",
                              data=json.dumps({"payload": {"alert_ids": chunk}}),
                              headers=json_hdrs, timeout=15_000)
                ok = rr.status == 200 and '"s":"ok"' in rr.text()
                print(f"  delete batch ({len(chunk)}): {'OK' if ok else 'FAIL ' + rr.text()[:120]}", flush=True)
        ctx.close()
    time.sleep(2)
    print("\nNow running recreate_top5_instant.py with INSTANT_FREQ=None…", flush=True)
    print("=" * 70, flush=True)
    p2 = subprocess.run([str(PY), str(HERE / "recreate_top5_instant.py")],
                        capture_output=True, text=True, timeout=240,
                        creationflags=0x08000000)
    print(p2.stdout, flush=True)
    if p2.stderr:
        print("STDERR:", p2.stderr, flush=True)
    return p2.returncode


if __name__ == "__main__":
    sys.exit(main() or 0)
