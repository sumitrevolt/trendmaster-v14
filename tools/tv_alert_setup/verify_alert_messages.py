"""Query TV list_alerts API and verify each Rocket Prime alert's message
field is actually 'RP|{{ticker}}|...|p0={{plot_0}}|...' template.

If TV stripped the override and reverted to indicator default (e.g.
'#### {{ticker}} ####'), we'll see it here.
"""
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
        if r.status != 200:
            print(f"[X] list_alerts returned {r.status} — session may be expired")
            return 2

        alerts = r.json().get("r", [])
        rp = []
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            if ((cond.get("series") or [{}])[0]).get("pine_id") != ROCKET_PRIME:
                continue
            sym_raw = a.get("symbol", "")
            try:
                full = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
            except Exception:
                full = sym_raw
            rp.append({
                "id": a.get("alert_id"),
                "symbol": full,
                "resolution": str(a.get("resolution", "")),
                "message": a.get("message", ""),
                "web_hook": a.get("web_hook", ""),
                "active": a.get("active", False),
            })

        print(f"\nFound {len(rp)} Rocket Prime alerts\n")
        good = 0
        bad = 0
        for x in sorted(rp, key=lambda r: (r["symbol"], r["resolution"])):
            msg = x["message"]
            has_plot = "{{plot_0}}" in msg or "{{plot_1}}" in msg
            mark = "OK" if has_plot else "BAD"
            if has_plot:
                good += 1
            else:
                bad += 1
            print(f"  [{mark}] {x['symbol']:<22} tf={x['resolution']:<3} active={x['active']}")
            print(f"        msg = {msg[:120]!r}")

        print()
        print(f"=== Summary: {good} alerts have plot template, {bad} do NOT ===")
        if bad > 0:
            print("\n!! Alerts WITHOUT plot template will fall back to indicator's")
            print("   built-in alert text, which is just '#### {{ticker}} ####'.")
            print("   Direction extraction at the receiver will FAIL.")
            print("   Workaround: use per-direction URL params (recreate with two")
            print("   alerts per pair-tf: one BUY-condition with ?direction=buy,")
            print("   one SELL-condition with ?direction=sell).")

        ctx.close()
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
