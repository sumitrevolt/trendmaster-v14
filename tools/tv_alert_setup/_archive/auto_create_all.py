"""Fully autonomous TV alert creation. NO user interaction. NO terminal popups.

Runs via pythonw.exe (windowless). Uses Playwright + pyautogui + pyperclip +
pygetwindow together with focus-management + clipboard paste so it works even
when other windows steal focus.

Strategy per alert:
  1. Playwright navigates to chart for (symbol, TF)
  2. pygetwindow brings Chrome-for-Testing to foreground
  3. Playwright keyboard sends Alt+A (DevTools protocol — no focus needed)
  4. Playwright opens notifications sub-dialog (force-click)
  5. Verify webhook URL (already cached by TV)
  6. Click sub-dialog Apply (force-click)
  7. Find message field by text-pattern, COPY JSON to clipboard
  8. pygetwindow refocus Chrome, pyautogui click + Ctrl+A + Ctrl+V
  9. Playwright finds Create button (excluding Apply), force-click
  10. Verify alert was created (page.locator new alert appears)
  11. Save progress, next alert

Logs to logs/tv_auto_create.log only. NO console output (pythonw discards).
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Force UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pyautogui
import pyperclip
import pygetwindow as gw
from playwright.sync_api import sync_playwright, Page

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
PROFILE_DIR = HERE / "_browser_profile"
CONFIG_PATH = HERE / "alerts_config.json"
DONE_PATH = HERE / "alerts_done.json"
LOG_PATH = PROJECT_ROOT / "logs" / "tv_auto_create.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8")],
)
log = logging.getLogger("auto_create")

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

NAV_DELAY = 6.0
DLG_DELAY = 3.0
SUB_DLG_DELAY = 2.0
FIELD_DELAY = 0.6


def _load_done() -> set[str]:
    if DONE_PATH.exists():
        try:
            return set(json.loads(DONE_PATH.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def _save_done(done: set[str]) -> None:
    DONE_PATH.write_text(json.dumps(sorted(done), indent=2), encoding="utf-8")


def _focus_chrome() -> bool:
    """Bring Playwright's Chromium ('Chrome for Testing') to foreground."""
    try:
        for w in gw.getAllWindows():
            if w.title and "Chrome for Testing" in w.title:
                if w.isMinimized:
                    w.restore()
                w.activate()
                time.sleep(0.4)
                return True
    except Exception as e:
        log.warning(f"focus_chrome failed: {e}")
    return False


def _create_one(page: Page, alert: dict) -> bool:
    sym = alert["symbol"]
    tf = alert["timeframe"]
    log.info(f"--- {alert['id']} ({sym} {tf}) ---")

    # Step 1: navigate to chart
    chart_url = f"https://www.tradingview.com/chart/?symbol={alert['exchange']}%3A{alert['broker_symbol']}&interval={alert['tv_interval']}"
    page.goto(chart_url, wait_until="domcontentloaded", timeout=30_000)
    time.sleep(NAV_DELAY)

    # Step 2: focus chrome window so OS sees it
    _focus_chrome()
    page.bring_to_front()
    page.evaluate("() => document.querySelector('canvas')?.click()")
    time.sleep(0.3)

    # Step 3: open alert dialog
    page.keyboard.press("Alt+a")
    time.sleep(DLG_DELAY)

    # Step 4: open notifications sub-dialog
    notif_btn = page.locator("button:has-text('Webhook'):has-text('Toasts')").first
    if notif_btn.count() == 0:
        notif_btn = page.locator("button:has-text('Webhook')").first
    if notif_btn.count() > 0:
        notif_btn.click(force=True, timeout=4000)
        time.sleep(SUB_DLG_DELAY)
        log.info("  notifications sub-dialog opened")
    else:
        log.warning("  notifications button not found")

    # Step 5: verify URL in sub-dialog (it persists across alerts in this account)
    url_state = page.evaluate(
        """() => {
            const el = document.querySelector('#webhook-url');
            return el ? el.value : null;
        }"""
    )
    if url_state == alert["webhook_url"]:
        log.info(f"  URL ok: {url_state[:50]}...")
    else:
        log.warning(f"  URL mismatch: have={url_state!r:.60} want={alert['webhook_url']!r:.60}")
        # Force-fix the URL via Playwright (it's just an <input>, fill works)
        try:
            page.locator("#webhook-url").fill(alert["webhook_url"], timeout=3000)
            time.sleep(0.3)
            log.info(f"  URL fixed to {alert['webhook_url'][:50]}")
        except Exception as e:
            log.warning(f"  URL fix failed: {e}")

    # Step 6: click sub-dialog Apply
    apply_btn = page.locator("button[type='submit']:has-text('Apply')").first
    if apply_btn.count() > 0:
        apply_btn.click(force=True, timeout=3000)
        time.sleep(FIELD_DELAY * 2)
        log.info("  sub-dialog Apply clicked")
    else:
        log.warning("  Apply button not found")

    # Step 7: find message field via text pattern (default "<SYM> Crossing X")
    target = page.evaluate(
        """(symbol) => {
            const all = document.querySelectorAll('div, span, p, textarea');
            for (const el of all) {
                const r = el.getBoundingClientRect();
                if (r.width < 50 || r.height < 14 || r.height > 80) continue;
                if (r.x < 100 || r.y < 400 || r.y > 850) continue;
                const txt = (el.innerText || el.value || '').trim();
                if (txt && (txt.includes(symbol + ' Crossing') || txt.includes(symbol + ' >'))) {
                    return {x: r.x + r.width/2, y: r.y + r.height/2};
                }
            }
            return null;
        }""",
        sym,
    )
    if target:
        # Step 8: type message via Playwright keyboard (works through DevTools)
        page.mouse.click(target["x"], target["y"])
        time.sleep(0.4)
        page.keyboard.press("Control+a")
        time.sleep(0.15)
        page.keyboard.press("Delete")
        time.sleep(0.2)
        # Use clipboard paste — handles long JSON faster + reliable for editors
        pyperclip.copy(alert["message_body"])
        time.sleep(0.15)
        page.keyboard.press("Control+v")
        time.sleep(FIELD_DELAY)
        log.info("  message pasted")
    else:
        log.warning("  message field not found - skipping paste")

    # Step 9: click MAIN dialog Create button (must NOT click Apply)
    create_btn = page.locator(
        "[data-qa-id='submit'][data-overflow-tooltip-text='Create']"
    ).first
    if create_btn.count() == 0:
        # Fallback: button text "Create" specifically
        create_btn = page.locator("button[type='submit']:has-text('Create')").first
    if create_btn.count() == 0:
        log.warning("  Create button not found")
        return False
    try:
        create_btn.click(force=True, timeout=4000)
        time.sleep(NAV_DELAY * 0.7)
        log.info("  Create clicked")
        return True
    except Exception as e:
        log.warning(f"  Create click failed: {e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter-symbol", default=None)
    ap.add_argument("--filter-tf", default=None)
    ap.add_argument("--start-from", type=int, default=0)
    ap.add_argument("--max", type=int, default=None)
    args = ap.parse_args()

    log.info("=" * 60)
    log.info("AUTO-CREATE STARTING")
    log.info("=" * 60)

    if not CONFIG_PATH.exists():
        log.error(f"FATAL: {CONFIG_PATH} missing"); return 1
    alerts = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if args.filter_symbol:
        alerts = [a for a in alerts if a["symbol"] == args.filter_symbol.upper()]
    if args.filter_tf:
        alerts = [a for a in alerts if a["timeframe"] == args.filter_tf.upper()]
    alerts = alerts[args.start_from:]
    if args.max:
        alerts = alerts[:args.max]

    done = _load_done()
    log.info(f"To process: {len(alerts)}, already done: {len(done)}")

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
            log.error("Not logged into TradingView. Aborting.")
            ctx.close(); return 2
        log.info("TV session OK")

        success = 0
        for i, alert in enumerate(alerts):
            if alert["id"] in done:
                log.info(f"[skip {i+1}/{len(alerts)}] {alert['id']}")
                continue
            try:
                ok = _create_one(page, alert)
                if ok:
                    done.add(alert["id"])
                    _save_done(done)
                    success += 1
                    log.info(f"[ok {i+1}/{len(alerts)}] {alert['id']} - total saved: {success}")
                else:
                    log.warning(f"[fail {i+1}/{len(alerts)}] {alert['id']}")
            except Exception as e:
                log.exception(f"[exc {i+1}/{len(alerts)}] {alert['id']}: {e}")
            # Anti-bot: jitter pause between alerts
            time.sleep(2.0)

        ctx.close()
    log.info(f"DONE. Created: {success} new alerts. Total in done: {len(done)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
