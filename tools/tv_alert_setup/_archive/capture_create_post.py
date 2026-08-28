"""Open Playwright Chromium with network capture. User manually creates ONE
Rocket Prime alert. Script captures the EXACT /create_alert POST request
(URL, headers, body) so we can replay it for missing combos.

Steps:
  1. Browser opens to a chart for a symbol you DON'T already have an alert on.
  2. Press Alt+A → alert dialog opens
  3. Configure:
     - Condition: Rocket Prime Engine → Any alert() function call
     - Notifications: Webhook URL → https://shadow-cosmos-unending.ngrok-free.dev/tv-signal
     - Click Create
  4. Script captures the POST and saves to capture_create_post.json
  5. Close browser to finish.
"""
from __future__ import annotations
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright, Request

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
CAPTURE_PATH = HERE / "capture_create_post.json"

# Suggest a missing combo so user creates it (we don't already have it)
SUGGESTED_URL = "https://www.tradingview.com/chart/?symbol=OANDA%3AUSDCHF&interval=15"

captured = []

def main() -> int:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1600, "height": 1000},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_request(req: Request) -> None:
            try:
                if (
                    req.method == "POST"
                    and "tradingview.com" in req.url
                    and "create_alert" in req.url
                ):
                    body = None
                    try:
                        body = req.post_data
                    except Exception:
                        pass
                    rec = {
                        "method": req.method,
                        "url": req.url,
                        "headers": dict(req.headers),
                        "post_data": body,
                        "ts": time.time(),
                        "captured_at": datetime.now(timezone.utc).isoformat(),
                    }
                    captured.append(rec)
                    print(f"\n*** CAPTURED *** POST {req.url}")
                    if body:
                        print(f"   body[:400]: {body[:400]!r}")
            except Exception as e:
                print(f"  capture err: {e}")

        page.on("request", on_request)

        print("=" * 70)
        print("  CAPTURE MODE")
        print("=" * 70)
        print()
        print("Browser opening to USDCHF M15 chart (you don't have this one yet).")
        print()
        print("STEPS in the browser window:")
        print("  1. Add Rocket Prime indicator to the chart (if not already there)")
        print("  2. Press Alt+A to open alert dialog")
        print("  3. Configure:")
        print("     - Condition: Rocket Prime Engine → 'Any alert() function call'")
        print("     - Notifications: enable 'Webhook URL'")
        print("     - Webhook URL: https://shadow-cosmos-unending.ngrok-free.dev/tv-signal")
        print("     - Message: leave default (Pine controls it)")
        print("  4. Click 'Create' button")
        print("  5. Close the browser window when done")
        print()
        print("Waiting for capture...")
        page.goto(SUGGESTED_URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(8)

        # Wait until browser closes
        try:
            while True:
                time.sleep(2)
                try:
                    if not ctx.pages:
                        print("\n>>> Browser closed.")
                        break
                except Exception:
                    print("\n>>> Browser context gone.")
                    break
        except KeyboardInterrupt:
            print("\nInterrupted.")

        if captured:
            CAPTURE_PATH.write_text(json.dumps(captured, indent=2, default=str), encoding="utf-8")
            print(f"\n✓ Captured {len(captured)} create_alert POST(s) -> {CAPTURE_PATH}")
        else:
            print("\n[!] No /create_alert POST captured.")
            print("    Either (a) you didn't click Create, or")
            print("    (b) TV uses a different endpoint for this kind of alert.")

        try:
            ctx.close()
        except Exception:
            pass
    return 0 if captured else 1


if __name__ == "__main__":
    sys.exit(main())
