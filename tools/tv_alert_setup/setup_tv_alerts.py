"""TradingView alert setup automation via Playwright.

Iterates through alerts_config.json and creates each alert in TradingView.
By default runs in SEMI-AUTO mode: opens the alert dialog, fills the
fields, then PAUSES so you can click "Create" yourself. This is safer
than full-auto because TV's anti-bot detection treats rapid clicks as
suspicious and may rate-limit your account.

Why a separate browser profile:
  We use Playwright's `launch_persistent_context` with a dedicated
  profile under `_browser_profile/`. First run, you log into TradingView
  manually; the cookies persist there. Subsequent runs auto-login.
  Your real Chrome profile is NEVER touched.

Usage:
    pip install playwright
    playwright install chromium

    # 1. Generate alerts_config.json (only once, or after changing TFs/symbols)
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\generate_alerts_config.py --strategy-mode

    # 2. Run the setup. First time only — log in when the browser opens.
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\setup_tv_alerts.py

    # Resume from a specific index after interruption:
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\setup_tv_alerts.py --start-from 24

    # Dry-run: don't open dialogs, just print what would happen
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\setup_tv_alerts.py --dry-run

    # Auto-confirm (skip pause; click Create programmatically). HIGH RISK.
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\setup_tv_alerts.py --auto-confirm

Checkpoint:
    `alerts_done.json` tracks IDs already saved. If the script crashes,
    re-run; it skips done entries automatically.

Caveats:
    * TradingView's UI selectors change frequently. If the script breaks
      on a specific step, edit the corresponding `_step_*` function.
    * Anti-bot: keep the default 4-6s delays. If TV starts showing CAPTCHAs,
      stop and wait an hour.
    * The "Condition" dropdown selection depends on which indicator(s) you
      have on the chart. The script doesn't auto-select an indicator;
      you'll do that once when prompted at startup.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout
except ImportError:
    print("FATAL: playwright not installed.\n"
          "  pip install playwright\n"
          "  playwright install chromium")
    sys.exit(2)

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "alerts_config.json"
DONE_PATH = HERE / "alerts_done.json"
PROFILE_DIR = HERE / "_browser_profile"

DEFAULT_DELAY_S = 4.0   # between major actions
SHORT_DELAY_S = 1.0     # between minor actions
PAUSE_FOR_LOGIN_S = 0   # 0 means wait for Enter; positive int = wait that many seconds


# ─────────────────────── checkpoint helpers ───────────────────────
def _load_done() -> set[str]:
    if DONE_PATH.exists():
        try:
            return set(json.loads(DONE_PATH.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def _save_done(done: set[str]) -> None:
    DONE_PATH.write_text(json.dumps(sorted(done), indent=2), encoding="utf-8")


# ─────────────────────── per-step helpers ───────────────────────
def _wait(page: Page, s: float) -> None:
    page.wait_for_timeout(int(s * 1000))


def _navigate_to_chart(page: Page, alert: dict) -> None:
    """Open the chart for this symbol on its broker exchange."""
    exch = alert["exchange"]
    sym = alert["broker_symbol"]
    interval = alert["tv_interval"]
    url = f"https://www.tradingview.com/chart/?symbol={exch}%3A{sym}&interval={interval}"
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    _wait(page, DEFAULT_DELAY_S)


def _open_alert_dialog(page: Page) -> None:
    """Alt+A is TradingView's keyboard shortcut for "Create alert"."""
    page.keyboard.press("Alt+a")
    _wait(page, DEFAULT_DELAY_S)


def _fill_webhook_section(page: Page, alert: dict) -> None:
    """Expand Notifications, ensure Webhook checked, fill URL + message body.

    TradingView 2025+ dialog structure (verified 2026-05-04):
      - Notifications row collapsed by default, shows summary like
        'App, Toasts, Email, Webhook, Sound, Plain text'
      - Click that button to expand the notifications panel
      - Inside: 6 checkboxes (App, Toasts, Email, Webhook, Sound, Plain text)
      - Webhook URL: id='webhook-url'
      - Message body: contenteditable div (NOT textarea anymore)
      - Submit: button[type='submit'] with text 'Create' or 'Apply'
    """
    # Step 1: Expand Notifications panel by clicking the summary button.
    # The summary button text contains "Webhook" (among other methods).
    try:
        page.locator("button:has-text('App, Toasts')").first.click(timeout=4000)
        _wait(page, SHORT_DELAY_S * 1.5)
    except PWTimeout:
        # Try a more lenient match
        try:
            page.locator("button").filter(has_text="Webhook").first.click(timeout=3000)
            _wait(page, SHORT_DELAY_S * 1.5)
        except PWTimeout:
            print("  [warn] could not expand notifications panel - assuming already expanded")

    # Step 2: Ensure Webhook checkbox is checked. There are 6 checkboxes in
    # the notifications panel at the same x-coordinate (~580). The 4th is Webhook.
    # We use position-based selection since labels lack stable selectors.
    try:
        # Find checkboxes inside the dialog
        checkboxes = page.locator("input[type='checkbox']")
        n = checkboxes.count()
        if n >= 4:
            # Iterate to find the 4th VISIBLE checkbox (Webhook)
            visible_idx = 0
            for i in range(n):
                cb = checkboxes.nth(i)
                if cb.is_visible(timeout=500):
                    if visible_idx == 3:  # 0-indexed, 4th = Webhook
                        if not cb.is_checked():
                            cb.check(timeout=2000)
                        break
                    visible_idx += 1
    except Exception as e:
        print(f"  [warn] checkbox selection failed: {e}")

    _wait(page, SHORT_DELAY_S)

    # Step 3: Fill webhook URL — clear any pre-existing value first
    try:
        url_input = page.locator("#webhook-url")
        url_input.click(timeout=4000)
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        url_input.fill(alert["webhook_url"], timeout=4000)
    except (PWTimeout, Exception) as e:
        print(f"  [warn] webhook URL fill failed: {e}")

    _wait(page, SHORT_DELAY_S)

    # Step 4: Fill message body.
    # FORMAT B short-circuit: invite-only indicators (Rocket Prime, Goldbach, etc.)
    # emit their own "Buy Observation @ price" / "Sell Observation @ price" text via
    # alert() calls. The receiver parses direction from that text. If we Control+A
    # Delete the message field, we wipe the indicator's text and the receiver gets
    # an empty body -> can't determine BUY/SELL. So when format=="B" or message_body
    # is empty, leave the message field strictly alone.
    if alert.get("format") == "B" or not alert.get("message_body"):
        print("  [ok] Format B: leaving message field untouched (indicator alert() text passes through)")
        return

    # TradingView's "Message" field is positioned BELOW the webhook URL input
    # and is a custom widget (no stable selector). Reliable approach:
    # find an element whose text matches the default condition message
    # ("<SYMBOL> Crossing <price>") OR look for a "Message" label and grab
    # the next sibling editable area. Final fallback: Tab from URL field.
    msg_filled = False

    # Strategy A: locator by data-name/aria-label conventions used by TV editors
    msg_selectors = [
        "[data-name='message']",
        "[aria-label='Message']",
        "[aria-label*='message']",
        "div.tv-control-field__body[contenteditable='true']",
        "div[contenteditable='true']",
        "div[contenteditable='plaintext-only']",
        "textarea[name='message']",
        "textarea",
    ]
    for sel in msg_selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            if not loc.is_visible(timeout=500):
                continue
            loc.click(timeout=2000)
            _wait(page, SHORT_DELAY_S * 0.5)
            # Select all + delete (works for contenteditable + textarea + input)
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            _wait(page, SHORT_DELAY_S * 0.3)
            # Type via keyboard (works for both contenteditable and inputs)
            page.keyboard.type(alert["message_body"], delay=2)
            msg_filled = True
            print(f"  [ok] message filled via selector {sel!r}")
            break
        except Exception:
            continue

    # Strategy B: locate message by SEARCHING for an element near the URL
    # field whose text matches the default condition pattern
    # ("<SYMBOL> Crossing <price>") — that's the message field's current value.
    if not msg_filled:
        try:
            sym = alert["symbol"]
            # Find any element whose visible text contains "<SYMBOL> Crossing"
            # (TV's default condition-derived message), or just any text that
            # looks like a condition-message (contains "Crossing" or the symbol).
            target = page.evaluate(
                """(symbol) => {
                    // Walk ALL text-bearing elements; find smallest one matching pattern
                    const all = document.querySelectorAll('div, span, p');
                    let best = null;
                    let bestLen = 9999;
                    const pattern = new RegExp(symbol + '\\\\s+(Crossing|crossing|>|<)', 'i');
                    for (const el of all) {
                        const r = el.getBoundingClientRect();
                        if (r.width === 0 || r.height === 0) continue;
                        const txt = (el.innerText || '').trim();
                        if (txt.length < 5 || txt.length > 200) continue;
                        if (!pattern.test(txt)) continue;
                        // Prefer the smallest matching element (deepest in DOM)
                        if (txt.length < bestLen) {
                            bestLen = txt.length;
                            best = {
                                x: Math.round(r.x + r.width/2),
                                y: Math.round(r.y + r.height/2),
                                text: txt.slice(0, 60),
                                ce: el.getAttribute('contenteditable') || '',
                                tag: el.tagName,
                            };
                        }
                    }
                    return best;
                }""",
                sym,
            )
            if target:
                print(f"  [debug] found message-like element: {target['tag']} ce={target['ce']!r} text={target['text']!r} at ({target['x']},{target['y']})")
                # Click on the message text to focus the editor
                page.mouse.click(target["x"], target["y"])
                _wait(page, SHORT_DELAY_S * 0.5)
                page.keyboard.press("Control+a")
                page.keyboard.press("Delete")
                _wait(page, SHORT_DELAY_S * 0.3)
                page.keyboard.type(alert["message_body"], delay=2)
                msg_filled = True
                print(f"  [ok] message filled via text-pattern match")
            else:
                print(f"  [warn] no element matching '<SYMBOL> Crossing ...' pattern found")
        except Exception as e:
            print(f"  [warn] text-pattern message strategy failed: {e}")

    if not msg_filled:
        print(f"  [warn] no message field selector matched - message will use TV default (alert WILL NOT route correctly)")


def _fill_alert_name(page: Page, alert: dict) -> None:
    try:
        page.locator("input[name='name'], input[placeholder*='name']").first.fill(
            alert["name"], timeout=4000)
    except PWTimeout:
        pass


# ─────────────────────── main loop ───────────────────────
def create_alert(page: Page, alert: dict, dry_run: bool, auto_confirm: bool) -> bool:
    """Returns True if alert was saved, False if user skipped/cancelled."""
    print(f"\n=== {alert['id']} ===")
    print(f"  symbol: {alert['exchange']}:{alert['broker_symbol']} ({alert['symbol']})")
    print(f"  TF:     {alert['timeframe']} (TV interval={alert['tv_interval']})")

    if dry_run:
        print("  [dry-run] skipping actual UI work")
        return True

    _navigate_to_chart(page, alert)
    _open_alert_dialog(page)
    _fill_alert_name(page, alert)
    _fill_webhook_section(page, alert)

    if auto_confirm:
        # TV uses "Create" for new alerts, "Apply" when editing existing.
        # Both are button[type='submit'] inside the dialog.
        try:
            submit_btn = page.locator("button[type='submit']").first
            if submit_btn.count() == 0:
                # Fallback by text
                for txt in ("Create", "Apply", "Save"):
                    try:
                        page.locator(f"button:has-text('{txt}')").first.click(timeout=2000)
                        print(f"  [auto] clicked {txt!r}")
                        _wait(page, DEFAULT_DELAY_S)
                        return True
                    except PWTimeout:
                        continue
                print("  [warn] no submit button found")
                return False
            btn_text = submit_btn.inner_text(timeout=2000)
            submit_btn.click(timeout=5000)
            _wait(page, DEFAULT_DELAY_S)
            print(f"  [auto] clicked submit button ({btn_text!r})")
            return True
        except PWTimeout:
            print("  [warn] submit button not clickable - manual save needed")
            return False

    # Semi-auto: pause for user to verify + save manually
    print("  >>> VERIFY the alert dialog, click 'Create' yourself, then press Enter here.")
    print("      (or type 's' + Enter to skip this one, or 'q' + Enter to quit)")
    response = input("  > ").strip().lower()
    if response == "q":
        print("Quitting on user request.")
        return None  # signals quit
    if response == "s":
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would happen, don't open dialogs.")
    ap.add_argument("--auto-confirm", action="store_true",
                    help="Click 'Create' programmatically (HIGH RISK; default is to pause).")
    ap.add_argument("--start-from", type=int, default=0,
                    help="Skip the first N entries (useful for resume).")
    ap.add_argument("--filter-symbol", default=None, help="Only process this symbol.")
    ap.add_argument("--filter-tf", default=None, help="Only process this timeframe.")
    args = ap.parse_args()

    if not CONFIG_PATH.exists():
        print(f"FATAL: {CONFIG_PATH} missing. Run generate_alerts_config.py first.")
        return 1
    alerts = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if args.filter_symbol:
        alerts = [a for a in alerts if a["symbol"] == args.filter_symbol.upper()]
    if args.filter_tf:
        alerts = [a for a in alerts if a["timeframe"] == args.filter_tf.upper()]
    alerts = alerts[args.start_from:]

    done = _load_done()
    print(f"=== TV alert setup ({len(alerts)} to process, {len(done)} already done) ===")
    print(f"    Profile dir: {PROFILE_DIR}")
    print(f"    Mode: {'AUTO-CONFIRM' if args.auto_confirm else 'SEMI-AUTO (pause for Save)'}")
    if args.dry_run:
        print("    DRY RUN — no UI actions")

    if args.dry_run:
        for a in alerts:
            print(f"  - {a['id']:<25}  -> {a['name']}")
        return 0

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1600, "height": 1000},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # First-run login gate — POLL-based instead of input(), so the script can
        # be driven via Desktop Commander / detached terminals without stdin.
        # Detection: TV's logged-in state shows a user-menu button in the top-right
        # header. We poll for that or for any cookie that survives login.
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        login_timeout_s = int(__import__("os").environ.get("TV_LOGIN_TIMEOUT_S", "300"))
        print(f"\n>>> Waiting up to {login_timeout_s}s for TradingView login in the browser window.")
        print(">>> Sign in (if needed) AND add your indicator(s) to the chart.")
        print(">>> Script auto-detects when TV session is active.")
        login_deadline = time.time() + login_timeout_s
        login_start = time.time()
        last_diag_at = 0.0
        while time.time() < login_deadline:
            try:
                cookies = ctx.cookies()
                # TradingView session cookie names — sessionid is the primary
                cookie_names = {c["name"] for c in cookies}
                has_session = bool(cookie_names & {"sessionid", "sessionid_sign", "tv_ecuid"})
                # Diagnostic dump every 30s so user can see what's missing
                now = time.time()
                if now - last_diag_at > 30:
                    print(f">>> [poll @ {int(now - login_start)}s] cookies present: "
                          f"{sorted(cookie_names)[:6]}... (have_session={has_session})")
                    last_diag_at = now
                if has_session:
                    print(f">>> [OK] TV session cookie detected after {int(now - login_start)}s; proceeding.")
                    break
            except Exception as e:
                print(f">>> [poll error] {e}")
            _wait(page, 3)
        else:
            print(">>> [WARN] Login not detected within timeout - proceeding anyway. "
                  "Alert dialogs may fail if not logged in.")

        for i, alert in enumerate(alerts):
            if alert["id"] in done:
                print(f"[skip] {i+1}/{len(alerts)} {alert['id']} (already done)")
                continue

            try:
                result = create_alert(page, alert, args.dry_run, args.auto_confirm)
            except KeyboardInterrupt:
                print("\nInterrupted by user. Resume with --start-from", args.start_from + i)
                break
            except Exception as e:
                print(f"  [ERROR] {e}")
                # Non-interactive in --auto-confirm mode (DC-driven runs have no stdin)
                if args.auto_confirm:
                    print("  [auto] continuing to next alert (--auto-confirm set)")
                    continue
                response = input("  Continue with next alert? (y/N): ").strip().lower()
                if response != "y":
                    break
                continue

            if result is None:  # user typed 'q'
                break
            if result:
                done.add(alert["id"])
                _save_done(done)
                print(f"  [saved] {alert['id']} ({len(done)} total)")

        ctx.close()

    print(f"\n=== Done. {len(done)} alerts marked complete in {DONE_PATH.name} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
