"""One-shot orchestrator: delete every existing TV alert, then create the 20
fresh Rocket Prime alerts in alerts_config.json -- in a single browser session.

This avoids opening the browser twice and avoids re-logging in. Uses the
persistent profile under _browser_profile/ (same as setup_tv_alerts.py).

Flow:
  1. Open Playwright Chromium with persistent profile.
  2. Wait for TV session cookie (5 min default).
  3. >>> PROMPT operator: confirm Rocket Prime Engine indicator is on the
         active chart, then press Enter.
  4. Delete every existing alert via delete_all_alerts.main_inline.
  5. Run the create loop from setup_tv_alerts.create_alert across all 20
     entries in alerts_config.json.
  6. Close browser. Print summary.

Usage:
  .venv\\Scripts\\python.exe tools\\tv_alert_setup\\reset_and_create.py
  .venv\\Scripts\\python.exe tools\\tv_alert_setup\\reset_and_create.py --auto-confirm
  .venv\\Scripts\\python.exe tools\\tv_alert_setup\\reset_and_create.py --skip-delete

If anything blows up mid-create, re-run setup_tv_alerts.py directly --
checkpoint file alerts_done.json tracks IDs already saved.
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
    print("FATAL: playwright not installed.")
    sys.exit(2)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Reuse helpers from sibling scripts (we imported the modules so checkpoint stays consistent)
import setup_tv_alerts as create_mod      # noqa: E402
import delete_all_alerts as delete_mod    # noqa: E402

CONFIG_PATH = HERE / "alerts_config.json"
DONE_PATH = HERE / "alerts_done.json"
PROFILE_DIR = HERE / "_browser_profile"

LOGIN_TIMEOUT_S = 300


def _wait(page: Page, s: float) -> None:
    page.wait_for_timeout(int(s * 1000))


def _clear_checkpoint() -> None:
    if DONE_PATH.exists():
        DONE_PATH.unlink()
        print(f"  [info] cleared old checkpoint {DONE_PATH.name}")


def _wait_for_login(ctx, page: Page) -> bool:
    print(f"\n>>> Waiting up to {LOGIN_TIMEOUT_S}s for TradingView session cookie.")
    print(">>> If this is your first run, log in to TradingView in the open browser window.")
    deadline = time.time() + LOGIN_TIMEOUT_S
    last_diag = 0.0
    start = time.time()
    while time.time() < deadline:
        try:
            cookies = ctx.cookies()
            names = {c["name"] for c in cookies}
            if names & {"sessionid", "sessionid_sign", "tv_ecuid"}:
                print(f">>> [OK] session detected after {int(time.time()-start)}s")
                return True
            now = time.time()
            if now - last_diag > 30:
                print(f">>> [poll @ {int(now-start)}s] cookies={sorted(names)[:5]}")
                last_diag = now
        except Exception as e:
            print(f">>> [poll error] {e}")
        _wait(page, 3)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto-confirm", action="store_true",
                    help="Click 'Create' programmatically instead of pausing for the operator.")
    ap.add_argument("--skip-delete", action="store_true",
                    help="Skip the bulk-delete phase; only run the create loop.")
    ap.add_argument("--skip-create", action="store_true",
                    help="Only run the bulk-delete phase.")
    args = ap.parse_args()

    if not CONFIG_PATH.exists():
        print(f"FATAL: {CONFIG_PATH} missing. Run generate_alerts_format_b.py first.")
        return 1

    alerts = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    print(f"=== reset_and_create: {len(alerts)} alerts loaded from config ===")

    if not args.skip_create:
        _clear_checkpoint()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1600, "height": 1000},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)

        if not _wait_for_login(ctx, page):
            print(">>> [WARN] login not detected; proceeding anyway")

        # ---- DELETE PHASE ----
        if not args.skip_delete:
            print("\n=== PHASE 1/2: deleting existing TradingView alerts ===")
            page.goto("https://www.tradingview.com/chart/?aside=alerts",
                      wait_until="domcontentloaded", timeout=30_000)
            _wait(page, 4.0)
            page.keyboard.press("Alt+a")
            _wait(page, 2.0)

            rows_before = delete_mod._count_alert_rows(page)
            print(f"  [info] {rows_before} existing alerts detected")

            if rows_before > 0:
                if delete_mod._try_remove_all(page):
                    _wait(page, 3.0)
                remaining = delete_mod._count_alert_rows(page)
                print(f"  [info] after bulk-remove: {remaining} remain")
                if remaining > 0:
                    removed = delete_mod._delete_row_by_row(page)
                    print(f"  [info] row-by-row deleted: {removed}")

                final = delete_mod._count_alert_rows(page)
                if final > 0:
                    print(f"  [WARN] {final} alerts still remain. Delete them manually in the visible browser, then press Enter.")
                    try:
                        input("  > ")
                    except EOFError:
                        pass
                else:
                    print("  [OK] all existing alerts removed")
            else:
                print("  [OK] no existing alerts to delete")

        if args.skip_create:
            ctx.close()
            return 0

        # ---- ROCKET PRIME INDICATOR CONFIRMATION ----
        print("\n>>> Before creating alerts: open ONE chart (any symbol) and add the")
        print(">>> 'Rocket Prime Engine (Normal)' indicator to it. The setup script")
        print(">>> needs the indicator's 'Any alert() function call' condition")
        print(">>> available in the Create Alert dialog.")
        print(">>> Press Enter when ready.")
        try:
            input("  > ")
        except (EOFError, KeyboardInterrupt):
            print(">>> no stdin; sleeping 30s and continuing")
            _wait(page, 30_000)

        # ---- CREATE PHASE ----
        print("\n=== PHASE 2/2: creating 20 fresh alerts ===")
        done = create_mod._load_done()
        for i, alert in enumerate(alerts):
            if alert["id"] in done:
                print(f"[skip] {i+1}/{len(alerts)} {alert['id']} (already done)")
                continue
            print(f"\n[create] {i+1}/{len(alerts)} {alert['id']}")
            try:
                result = create_mod.create_alert(page, alert,
                                                 dry_run=False,
                                                 auto_confirm=args.auto_confirm)
            except KeyboardInterrupt:
                print(f"\nInterrupted. Resume with: setup_tv_alerts.py --start-from {i}")
                break
            except Exception as e:
                print(f"  [ERROR] {e}")
                if args.auto_confirm:
                    continue
                response = input("  Continue with next alert? (y/N): ").strip().lower()
                if response != "y":
                    break
                continue

            if result is None:    # 'q' from operator
                break
            if result:
                done.add(alert["id"])
                create_mod._save_done(done)
                print(f"  [saved] {alert['id']} (cumulative={len(done)})")

        ctx.close()

    print(f"\n=== summary: {len(create_mod._load_done())}/{len(alerts)} alerts saved ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
