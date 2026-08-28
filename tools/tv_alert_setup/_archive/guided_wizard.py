"""Guided collaborative TV alert setup wizard.

Division of labor:
  Script (me)               You (user)
  --------                  --------
  - Navigate to chart       - Click message field
  - Open alert dialog       - Press Ctrl+A then Ctrl+V (paste pre-loaded JSON)
  - Copy JSON to clipboard  - Click "Create" button at bottom-right
  - Show clear instructions - Press Enter in this terminal to advance

Each alert: ~15 seconds of manual work (one click, two keystrokes, one click).
76 alerts: ~20 minutes total.

Resume-friendly: alerts_done.json tracks progress; restart picks up where left off.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pyperclip
from playwright.sync_api import sync_playwright, Page

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
CONFIG_PATH = HERE / "alerts_config.json"
DONE_PATH = HERE / "alerts_done.json"


def _load_done() -> set[str]:
    if DONE_PATH.exists():
        try:
            return set(json.loads(DONE_PATH.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def _save_done(done: set[str]) -> None:
    DONE_PATH.write_text(json.dumps(sorted(done), indent=2), encoding="utf-8")


def _focus_chromium_window() -> None:
    """Bring the Playwright Chromium ('Chrome for Testing') to foreground."""
    try:
        import pygetwindow as gw
        for w in gw.getAllWindows():
            if w.title and "Chrome for Testing" in w.title:
                if w.isMinimized:
                    w.restore()
                w.activate()
                return
    except Exception:
        pass


def _open_alert_dialog(page: Page) -> bool:
    """Open the new-alert dialog. Click on chart canvas first to ensure
    keyboard focus is on the chart (not URL bar), then send Alt+A."""
    try:
        page.bring_to_front()
        # Click on chart canvas (center of the page) to focus
        page.evaluate("() => document.querySelector('canvas')?.click()")
        time.sleep(0.3)
        page.keyboard.press("Alt+a")
        time.sleep(2.5)
        # Verify dialog opened by checking for the message field's default text
        return page.locator("button[type='submit']").count() > 0
    except Exception as e:
        print(f"  [warn] open_alert_dialog: {e}")
        return False


def _check_notifications_via_api(page: Page, expected_url: str) -> bool:
    """Open the notifications sub-dialog, verify webhook URL is correct,
    click Apply to commit and close. Returns True if URL was already right."""
    # Open notifications sub-dialog
    btn = page.locator("button:has-text('Webhook'):has-text('Toasts')").first
    if btn.count() == 0:
        btn = page.locator("button:has-text('Webhook')").first
    if btn.count() == 0:
        return False
    btn.click(force=True, timeout=3000)
    time.sleep(1.5)

    # Check URL value
    url_state = page.evaluate(
        """() => {
            const el = document.querySelector('#webhook-url');
            return el ? el.value : null;
        }"""
    )
    correct = url_state == expected_url

    # Click sub-dialog Apply to close it
    apply_btn = page.locator("button[type='submit']:has-text('Apply')").first
    if apply_btn.count() > 0:
        apply_btn.click(force=True, timeout=3000)
        time.sleep(1.0)
    return correct


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter-symbol", default=None)
    ap.add_argument("--filter-tf", default=None)
    ap.add_argument("--start-from", type=int, default=0)
    args = ap.parse_args()

    if not CONFIG_PATH.exists():
        print(f"FATAL: {CONFIG_PATH} missing"); return 1
    alerts = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if args.filter_symbol:
        alerts = [a for a in alerts if a["symbol"] == args.filter_symbol.upper()]
    if args.filter_tf:
        alerts = [a for a in alerts if a["timeframe"] == args.filter_tf.upper()]
    alerts = alerts[args.start_from:]

    done = _load_done()
    print()
    print("=" * 70)
    print("  GUIDED TV ALERT WIZARD")
    print("=" * 70)
    print(f"  Total to process: {len(alerts)}")
    print(f"  Already done:     {len(done)}")
    print(f"  Remaining:        {sum(1 for a in alerts if a['id'] not in done)}")
    print("=" * 70)
    print()
    print("HOW IT WORKS:")
    print("  1. I'll navigate the browser to each (symbol, timeframe) chart")
    print("  2. I'll open the alert dialog and copy the correct JSON to clipboard")
    print("  3. YOU do these 4 things in the browser:")
    print("       a) Click on the 'Message' line that shows '<SYMBOL> Crossing X.XX'")
    print("       b) Press Ctrl+A (selects the default text)")
    print("       c) Press Ctrl+V (pastes my JSON from clipboard)")
    print("       d) Click 'Create' button (bottom-right of dialog)")
    print("  4. Press Enter in THIS terminal to move to the next alert")
    print("  5. Type 's' + Enter to skip the current alert")
    print("  6. Type 'q' + Enter to quit (resume later with --start-from N)")
    print()
    print("Press Enter when ready to begin (browser will open).")
    input("> ")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1600, "height": 1000},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(4)

        cookies = ctx.cookies()
        if not any(c["name"] in ("sessionid", "sessionid_sign") for c in cookies):
            print("\n[!] You're not logged into TradingView in this browser.")
            print("    Sign in now, then press Enter to continue.")
            input("> ")

        for i, alert in enumerate(alerts):
            if alert["id"] in done:
                print(f"[skip] {i+1}/{len(alerts)} {alert['id']} (already done)")
                continue

            print()
            print("─" * 70)
            print(f"  [{i+1}/{len(alerts)}]  {alert['symbol']:<8}  {alert['timeframe']}  ({alert['exchange']}:{alert['broker_symbol']})")
            print("─" * 70)

            # Navigate to chart
            chart_url = f"https://www.tradingview.com/chart/?symbol={alert['exchange']}%3A{alert['broker_symbol']}&interval={alert['tv_interval']}"
            print(f"  -> navigating ...")
            page.goto(chart_url, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(5)

            # Open dialog
            print(f"  -> opening alert dialog (Alt+A) ...")
            opened = _open_alert_dialog(page)
            if not opened:
                print("  [!] dialog did not open — try pressing Alt+A in the browser yourself")

            # Verify webhook URL once (per session is enough, but cheap to recheck)
            print(f"  -> verifying webhook URL ...")
            try:
                _check_notifications_via_api(page, alert["webhook_url"])
            except Exception:
                pass

            # Copy JSON to clipboard
            pyperclip.copy(alert["message_body"])
            print()
            print(f"  ✓ JSON copied to clipboard ({len(alert['message_body'])} chars)")
            print()
            print("  >>> NOW IN THE BROWSER, DO:")
            print("       1. Click on the 'Message' field (line showing")
            print(f"          '{alert['symbol']} Crossing X.XXX' or similar)")
            print("       2. Press Ctrl+A  (selects all default text)")
            print("       3. Press Ctrl+V  (pastes the correct JSON)")
            print("       4. Click 'Create' button (bottom-right of dialog)")
            print()
            print("  Then come back here and press Enter for next alert.")
            print("  ('s' + Enter = skip this one, 'q' + Enter = quit and save)")
            print()
            try:
                response = input("  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n  Aborted.")
                break
            if response == "q":
                print("  Quitting per user request.")
                break
            if response == "s":
                print(f"  [skip] {alert['id']}")
                continue
            done.add(alert["id"])
            _save_done(done)
            print(f"  ✓ marked {alert['id']} done ({len(done)} total)")

        ctx.close()

    print()
    print(f"=== Wizard finished. {len(done)} alerts marked done in alerts_done.json ===")
    print(f"=== To resume: run again with --start-from {args.start_from + i + 1} (or no flag) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
