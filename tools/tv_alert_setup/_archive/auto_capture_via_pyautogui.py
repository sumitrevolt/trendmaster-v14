"""Drive the TV alert dialog via pyautogui to create ANY alert (default cross
condition is fine). Goal: capture TV's /create_alert POST so we can replay it.

Strategy:
  1. Reuse running Playwright Chromium with chart loaded
  2. Bring window to front via pygetwindow
  3. Send Alt+A keystroke via Playwright (DevTools, reliable)
  4. Wait for dialog
  5. Send Enter (Create button has focus / submit on enter)
  6. OR use pyautogui to click Create button at known coords (~957,877)
  7. Network capture (already attached) saves the POST
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

import pyautogui
import pygetwindow as gw
from playwright.sync_api import sync_playwright, Request

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
CAPTURE_PATH = HERE / "capture_create_post.json"

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

# Use a NEVER-existing combo so dialog opens fresh + cross condition default works
SYMBOL_URL = "https://www.tradingview.com/chart/?symbol=OANDA%3AUSDCHF&interval=15"

captured = []


def _focus_chrome() -> bool:
    try:
        for w in gw.getAllWindows():
            if w.title and "Chrome for Testing" in w.title:
                if w.isMinimized:
                    w.restore()
                w.activate()
                time.sleep(0.5)
                return True
    except Exception:
        pass
    return False


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
            if req.method == "POST" and "create_alert" in req.url and "tradingview.com" in req.url:
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
                }
                captured.append(rec)
                print(f"\n*** CAPTURED *** POST {req.url}")
                if body:
                    print(f"   body[:400]: {body[:400]!r}")
        page.on("request", on_request)

        print("Navigating to chart...")
        page.goto(SYMBOL_URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(8)
        print("Bringing chrome to front...")
        _focus_chrome()
        page.bring_to_front()
        # Click chart canvas to ensure keyboard focus
        try:
            page.evaluate("() => document.querySelector('canvas')?.click()")
        except Exception:
            pass
        time.sleep(0.5)

        print("Opening alert dialog (Alt+A via Playwright)...")
        page.keyboard.press("Alt+a")
        time.sleep(3)

        # Verify dialog opened by checking for submit button presence
        submit_count = page.locator("[data-qa-id='submit']").count()
        print(f"  Submit buttons visible: {submit_count}")
        if submit_count == 0:
            print("  Dialog didn't open, retrying with pyautogui Alt+A...")
            _focus_chrome()
            page.bring_to_front()
            time.sleep(0.5)
            pyautogui.hotkey("alt", "a")
            time.sleep(3)
            submit_count = page.locator("[data-qa-id='submit']").count()
            print(f"  After pyautogui Alt+A — submit buttons: {submit_count}")

        # Use page.expect_request to BLOCK until the create_alert POST fires.
        # This is the proper way — the POST happens asynchronously after Create
        # click, and we must not exit before it's captured.
        print("Setting up POST wait (will block until create_alert POST fires)...")
        try:
            with page.expect_request(
                lambda req: req.method == "POST" and "create_alert" in req.url,
                timeout=30_000,
            ) as req_info:
                # Click Create button INSIDE the wait context
                print("Clicking Create button (force-click via Playwright)...")
                create_btn = page.locator(
                    "[data-qa-id='submit'][data-overflow-tooltip-text='Create']"
                ).first
                if create_btn.count() == 0:
                    create_btn = page.locator("button[type='submit']:has-text('Create')").first
                if create_btn.count() == 0:
                    create_btn = page.locator("[data-qa-id='submit']").first
                if create_btn.count() > 0:
                    create_btn.click(force=True, timeout=5000)
                    print("  Create clicked, waiting for POST...")
                else:
                    print("  [warn] no Create button found")
            req = req_info.value
            print(f"\n*** POST FIRED *** {req.url}")
            try:
                body = req.post_data
            except Exception:
                body = None
            captured.append({
                "method": req.method,
                "url": req.url,
                "headers": dict(req.headers),
                "post_data": body,
                "ts": time.time(),
            })
            print(f"   body[:400]: {(body or '')[:400]!r}")
            time.sleep(2)
        except Exception as e:
            print(f"  expect_request failed: {e}")
            time.sleep(5)  # fallback wait — maybe captured via event handler

        if captured:
            CAPTURE_PATH.write_text(json.dumps(captured, indent=2, default=str), encoding="utf-8")
            print(f"\n✓ Captured {len(captured)} POST(s) -> {CAPTURE_PATH}")
        else:
            print("\n[!] Nothing captured.")
            print("    Possibilities:")
            print("    - Dialog didn't open (Alt+A failed)")
            print("    - Submit button click landed on wrong button")
            print("    - TV used a different endpoint")

        try:
            ctx.close()
        except Exception:
            pass
    return 0 if captured else 1


if __name__ == "__main__":
    sys.exit(main())
