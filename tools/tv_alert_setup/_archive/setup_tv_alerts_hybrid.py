"""TradingView alert setup — Playwright (navigation) + pyautogui (clicks/typing).

Why hybrid: TV's "Message" field is a custom widget (Lexical-like editor) that
ignores Playwright's .fill() and .type() because they go through synthetic events
that the widget filters out. pyautogui sends REAL OS-level keyboard events that
the widget cannot distinguish from a human typing — same trick OpenClaw's
pc-control uses.

Flow per alert:
  1. Playwright navigates to chart for (symbol, TF)
  2. Playwright opens alert dialog via Alt+A
  3. Playwright finds element COORDINATES (URL field, message area, submit btn)
  4. pyautogui clicks at those coordinates and types the value
  5. Playwright clicks Submit button (this DOES work via Playwright)

Usage (after one-time playwright + pyautogui install):
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\setup_tv_alerts_hybrid.py --filter-symbol XAUUSD --filter-tf M5
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\setup_tv_alerts_hybrid.py --start-from 1   # all 75 remaining
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

import pyautogui
from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
CONFIG_PATH = HERE / "alerts_config.json"
DONE_PATH = HERE / "alerts_done.json"

# pyautogui safety: hard-fail if mouse goes to corner (operator panic-stop)
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05  # small inter-action pause

NAV_DELAY = 6.0      # chart load
DLG_DELAY = 3.0      # dialog open
FIELD_DELAY = 0.6    # between field operations


def _load_done() -> set[str]:
    if DONE_PATH.exists():
        try:
            return set(json.loads(DONE_PATH.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def _save_done(done: set[str]) -> None:
    DONE_PATH.write_text(json.dumps(sorted(done), indent=2), encoding="utf-8")


def _click_xy(x: int, y: int, *, delay: float = 0.2) -> None:
    """OS-level click via pyautogui."""
    pyautogui.moveTo(x, y, duration=delay)
    pyautogui.click()
    time.sleep(0.15)


def _type_text(text: str, *, interval: float = 0.005) -> None:
    """OS-level type via pyautogui (works on contenteditable, custom editors etc.)."""
    pyautogui.write(text, interval=interval)


def _select_all_and_delete() -> None:
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.15)


def _find_coords(page: Page, selector: str) -> tuple[int, int] | None:
    """Find an element via Playwright, return its center pixel coords on screen.

    Note: returns viewport-relative coords. Since the browser window is the
    foreground app (we ensure this) and we use viewport=full, coords map
    directly to screen pixels. Add browser-chrome offset if needed.
    """
    try:
        loc = page.locator(selector).first
        if loc.count() == 0:
            return None
        box = loc.bounding_box(timeout=2000)
        if not box:
            return None
        # Add browser chrome offset (title bar + tabs ~ 90px on a maximized window)
        # Playwright's bounding_box is relative to viewport; we need screen.
        # The launch_persistent_context with viewport={1600,1000} + start-maximized
        # places the viewport just below the chrome. Empirically chrome is ~85-95px tall.
        chrome_offset_y = 88
        x = int(box["x"] + box["width"] / 2)
        y = int(box["y"] + box["height"] / 2) + chrome_offset_y
        return (x, y)
    except Exception:
        return None


def _find_message_field_coords(page: Page, sym: str) -> tuple[int, int] | None:
    """Find the 'Message' field by locating the line containing the symbol +
    'Crossing'/condition keyword, since TV's message field shows that text by default."""
    target = page.evaluate(
        """(symbol) => {
            const all = document.querySelectorAll('div, span, p, textarea, input');
            let best = null;
            let bestArea = 1e9;
            const re = new RegExp('(' + symbol + '|Alert)\\\\b', 'i');
            for (const el of all) {
                const r = el.getBoundingClientRect();
                if (r.width < 40 || r.height < 14 || r.height > 80) continue;
                if (r.x < 100) continue;  // skip left sidebar
                const txt = (el.innerText || el.value || el.placeholder || '').trim();
                if (!txt || txt.length < 3 || txt.length > 220) continue;
                if (!re.test(txt)) continue;
                // The "Message" field is typically in the lower-middle of the dialog
                if (r.y < 400 || r.y > 850) continue;
                const area = r.width * r.height;
                if (area < bestArea) {
                    bestArea = area;
                    best = {x: r.x + r.width/2, y: r.y + r.height/2, text: txt.slice(0,50)};
                }
            }
            return best;
        }""",
        sym,
    )
    if not target:
        return None
    print(f"    [debug] message field text={target['text']!r} at ({int(target['x'])},{int(target['y'])})")
    return (int(target["x"]), int(target["y"]) + 88)  # chrome offset


def _expand_notifications(page: Page) -> None:
    """Open the Notifications sub-dialog by clicking the summary button.
    Uses Playwright force-click (NOT pyautogui) so it works even when the
    browser isn't the foreground OS window."""
    try:
        # Match button containing both 'Webhook' and 'Toasts' (the summary)
        btn = page.locator("button:has-text('Webhook'):has-text('Toasts')").first
        if btn.count() == 0:
            # Fallback: any button mentioning Notifications
            btn = page.locator("button:has-text('Notifications')").first
        if btn.count() == 0:
            print("    [warn] notifications summary button not found")
            return
        try:
            btn_text = btn.inner_text(timeout=1500)
        except Exception:
            btn_text = "?"
        btn.click(force=True, timeout=4000)
        print(f"    [ok] clicked notifications button {btn_text!r}")
        time.sleep(FIELD_DELAY * 2)
    except Exception as e:
        print(f"    [warn] notifications expand failed: {e!s:.100}")


def create_alert(page: Page, alert: dict) -> bool:
    print(f"\n=== {alert['id']} ===")
    print(f"  symbol: {alert['exchange']}:{alert['broker_symbol']}  TF: {alert['timeframe']}")

    # Step 1: navigate to chart
    chart_url = f"https://www.tradingview.com/chart/?symbol={alert['exchange']}%3A{alert['broker_symbol']}&interval={alert['tv_interval']}"
    page.goto(chart_url, wait_until="domcontentloaded", timeout=30_000)
    time.sleep(NAV_DELAY)

    # Step 2: open alert dialog. Use Playwright's keyboard (DevTools protocol)
    # NOT pyautogui — pyautogui sends to OS-focused window which may be Claude
    # Code or another foreground app. Playwright always targets the browser.
    page.bring_to_front()
    time.sleep(0.3)
    # Click on chart canvas to ensure keyboard focus is on the chart (not URL bar)
    page.evaluate("() => { document.querySelector('canvas')?.click(); }")
    time.sleep(0.3)
    page.keyboard.press("Alt+a")
    time.sleep(DLG_DELAY)

    # Step 3: ensure webhook URL is correct in the Notifications sub-dialog.
    # Workflow: clicking "App, Toasts, Email, Webhook..." opens a SEPARATE
    # sub-dialog (not inline expansion). We open it, verify/update URL, then
    # click the sub-dialog's "Apply" button to commit and close it.
    print("    [step] opening notifications sub-dialog")
    _expand_notifications(page)
    time.sleep(FIELD_DELAY * 2)

    # Verify URL field state (it should appear now)
    url_state = page.evaluate(
        """() => {
            const el = document.querySelector('#webhook-url');
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {visible: r.width > 50, value: el.value || ''};
        }"""
    )
    if url_state and url_state["visible"]:
        # If the value differs from desired, fix it.
        # Use Playwright .fill() (DOM-level), NOT pyautogui — pyautogui needs
        # browser foreground which can be stolen by Antigravity/other apps
        # mid-typing, leaving the URL truncated. .fill() is foreground-
        # independent (CDP) and atomic.
        if url_state["value"] != alert["webhook_url"]:
            print(f"    [info] updating URL: {url_state['value'][-60:]!r} -> {alert['webhook_url'][-60:]!r}")
            try:
                page.locator("#webhook-url").first.fill(alert["webhook_url"], timeout=4000)
                # Verify what actually got set
                time.sleep(0.3)
                got = page.evaluate("() => (document.querySelector('#webhook-url') || {}).value || ''")
                if got == alert["webhook_url"]:
                    print(f"    [ok] URL set & verified ({len(got)} chars)")
                else:
                    print(f"    [warn] URL mismatch after fill: got_len={len(got)} want_len={len(alert['webhook_url'])}")
                    print(f"           got: {got[-80:]!r}")
                time.sleep(FIELD_DELAY)
            except Exception as e:
                print(f"    [warn] URL .fill() failed: {e!s:.100}")
        else:
            print(f"    [ok] URL already correct ({len(url_state['value'])} chars)")
    else:
        print("  [warn] URL field not visible in sub-dialog")

    # Step 4: click "Apply" in the SUB-dialog (not Create — that's main dialog)
    # Use data-overflow-tooltip-text to differentiate: Apply has tooltip 'Apply',
    # Create has tooltip 'Create'.
    sub_applied = False
    apply_selector = (
        "[data-qa-id='submit'][data-overflow-tooltip-text='Apply'], "
        "button[type='submit']:has-text('Apply')"
    )
    try:
        # Sub-dialog Apply: text='Apply' AND inside the popup that just opened
        apply_btn = page.locator(apply_selector).first
        if apply_btn.count() > 0:
            apply_btn.click(force=True, timeout=3000)
            sub_applied = True
            print("    [ok] sub-dialog Apply clicked - notifications saved")
            # CRITICAL: wait for sub-dialog to actually close before proceeding.
            # If we don't wait, the next 'Create' search falls back to
            # button[type='submit'] and matches Apply (still visible).
            for _ in range(40):  # up to 8 seconds
                time.sleep(0.2)
                if page.locator(apply_selector).count() == 0:
                    break
            else:
                print("    [warn] Apply button still visible after wait")
            time.sleep(FIELD_DELAY)
    except Exception as e:
        print(f"    [warn] sub-dialog Apply click failed: {e!s:.80}")

    # Step 5: fill message body. Strategy:
    #   1. Use Playwright to find and CLICK the message-display element
    #      (which contains "<SYMBOL> Crossing <price>"). This focuses the editor.
    #   2. Use page.keyboard (DevTools-protocol) to Ctrl+A + Delete + type.
    #   This works because Playwright's keyboard.type() goes through the
    #   browser's input event machinery and IS accepted by TV's custom editor —
    #   the issue with .fill() is that fill bypasses keypress events. .type()
    #   with delay=10ms simulates real typing.
    msg_filled = False
    try:
        # Click the display element to focus the message editor under it
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
            alert["symbol"],
        )
        if target:
            # Clicking the message preview opens the "Edit message" SUB-DIALOG
            # (Cancel / Apply). We must type into it, then click ITS Apply.
            page.mouse.click(target["x"], target["y"])
            time.sleep(0.6)
            # Wait for Edit message sub-dialog to actually open (look for its
            # header "Edit message" OR a textarea/contenteditable)
            for _ in range(20):
                if page.locator("text=Edit message").count() > 0 or \
                   page.locator("textarea").count() > 0:
                    break
                time.sleep(0.15)
            page.keyboard.press("Control+a")
            time.sleep(0.1)
            page.keyboard.press("Delete")
            time.sleep(0.2)
            # CRITICAL: insertText (single 'input' event), NOT type().
            # type() fires keydown/keyup -> if focus shifts, TV chart hotkeys
            # ('s', '/' etc.) fire and the dialog dismisses.
            page.keyboard.insert_text(alert["message_body"])
            time.sleep(FIELD_DELAY)
            print(f"    [ok] message inserted via insertText")

            # Click the Edit message sub-dialog's Apply button.
            edit_apply_clicked = False
            try:
                # Apply button text is just 'Apply'; the notifications Apply
                # already closed, so the only visible Apply now is this one.
                edit_apply = page.locator(
                    "button[type='submit']:has-text('Apply'), "
                    "[data-qa-id='submit'][data-overflow-tooltip-text='Apply']"
                ).first
                if edit_apply.count() > 0:
                    edit_apply.click(force=True, timeout=3000)
                    edit_apply_clicked = True
                    print("    [ok] Edit message Apply clicked")
                    # Wait for Edit message sub-dialog to close
                    for _ in range(40):
                        time.sleep(0.2)
                        if page.locator("text=Edit message").count() == 0:
                            break
                    time.sleep(FIELD_DELAY)
            except Exception as e:
                print(f"    [warn] Edit message Apply click failed: {e!s:.80}")
            if not edit_apply_clicked:
                # Try Enter key as fallback (many TV dialogs accept Enter to confirm)
                try:
                    page.keyboard.press("Enter")
                    time.sleep(FIELD_DELAY)
                    print("    [ok] Edit message confirmed via Enter")
                except Exception:
                    pass
            msg_filled = True
        else:
            print(f"    [warn] message field locator returned None")
    except Exception as e:
        print(f"    [warn] message fill via keyboard failed: {e!s:.100}")
    # Fallback to pyautogui only if everything else failed (and only if browser
    # is foreground — focus_chromium first to maximize chances)
    if not msg_filled:
        try:
            import subprocess
            subprocess.run(
                [sys.executable, str(HERE / "focus_chromium.py")],
                capture_output=True, timeout=10,
            )
            time.sleep(0.5)
        except Exception:
            pass
        msg_coords = _find_message_field_coords(page, alert["symbol"])
        if msg_coords:
            _click_xy(*msg_coords)
            _select_all_and_delete()
            _type_text(alert["message_body"])
            time.sleep(FIELD_DELAY)
            print(f"    [ok] message typed via pyautogui fallback")
            msg_filled = True
        else:
            print("  [warn] message field not found at all")

    # Step 6: click MAIN dialog "Create" button (not sub-dialog Apply).
    # We REFUSE to click any button whose text is 'Apply' — that's the
    # sub-dialog leaking through. Only buttons literally labeled 'Create'
    # are accepted.
    create_selectors = [
        "[data-qa-id='submit'][data-overflow-tooltip-text='Create']",
        "button[type='submit'][data-overflow-tooltip-text='Create']",
        "button[type='submit']:has-text('Create')",
    ]
    create_btn = None
    btn_text = ""
    for sel in create_selectors:
        try:
            cand = page.locator(sel).first
            if cand.count() == 0:
                continue
            t = cand.inner_text(timeout=1000).strip()
            if "Create" in t and "Apply" not in t:
                create_btn = cand
                btn_text = t
                print(f"    [step] found Create via {sel!r} text={t!r}")
                break
        except Exception:
            continue
    if create_btn is None:
        # Defensive: scan all submit buttons, only accept Create-labeled
        try:
            all_submits = page.locator("button[type='submit']").all()
            for cand in all_submits:
                try:
                    t = cand.inner_text(timeout=500).strip()
                except Exception:
                    continue
                if "Create" in t and "Apply" not in t and cand.is_visible():
                    create_btn = cand
                    btn_text = t
                    print(f"    [step] found Create by scan, text={t!r}")
                    break
        except Exception:
            pass
    if create_btn is None:
        print("  [warn] Create button not found - SKIPPING (will not click Apply by mistake)")
        # Take a screenshot for postmortem
        try:
            page.screenshot(path=str(HERE / f"err_no_create_{alert['id']}.png"))
        except Exception:
            pass
        return False
    try:
        create_btn.click(timeout=4000, force=True)
        # Verify the dialog actually closed within ~6s — that's the real
        # success signal. If dialog stays open, alert was NOT saved.
        closed = False
        for _ in range(30):
            time.sleep(0.2)
            try:
                if page.locator("[data-qa-id='submit']:visible").count() == 0:
                    closed = True
                    break
            except Exception:
                pass
        if closed:
            print(f"  [ok] Create clicked, dialog closed - alert saved {btn_text!r}")
            time.sleep(FIELD_DELAY * 2)
            return True
        else:
            print(f"  [warn] Create clicked {btn_text!r} but dialog still open after 6s")
            return False
    except Exception as e:
        print(f"  [warn] Create click failed: {e!s:.100}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter-symbol", default=None)
    ap.add_argument("--filter-tf", default=None)
    ap.add_argument("--start-from", type=int, default=0)
    ap.add_argument("--max", type=int, default=None, help="cap on number to process")
    args = ap.parse_args()

    if not CONFIG_PATH.exists():
        print(f"FATAL: {CONFIG_PATH} missing"); return 1
    alerts = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if args.filter_symbol:
        alerts = [a for a in alerts if a["symbol"] == args.filter_symbol.upper()]
    if args.filter_tf:
        alerts = [a for a in alerts if a["timeframe"] == args.filter_tf.upper()]
    alerts = alerts[args.start_from:]
    if args.max:
        alerts = alerts[:args.max]

    done = _load_done()
    print(f"=== Hybrid Playwright+pyautogui setup: {len(alerts)} to process, {len(done)} already done ===")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1600, "height": 1000},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # Wait for any login if needed (3 sec poll, 60s max)
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(NAV_DELAY)
        cookies = ctx.cookies()
        if not any(c["name"] in ("sessionid", "sessionid_sign") for c in cookies):
            print(">>> No TV session cookie found. Log in to TV in the browser, then re-run.")
            ctx.close(); return 2
        print(">>> TV session OK; starting loop.")

        for i, alert in enumerate(alerts):
            if alert["id"] in done:
                print(f"[skip] {i+1}/{len(alerts)} {alert['id']}")
                continue
            try:
                ok = create_alert(page, alert)
                if ok:
                    done.add(alert["id"])
                    _save_done(done)
            except KeyboardInterrupt:
                print("\n[abort] user interrupted; resume with --start-from", args.start_from + i)
                break
            except Exception as e:
                print(f"  [ERR] {e}; continuing")

        ctx.close()
    print(f"\n=== Done. Total saved: {len(done)} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
