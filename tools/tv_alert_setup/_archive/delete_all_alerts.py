"""Delete every TradingView alert in the logged-in session.

Uses the SAME Playwright profile as setup_tv_alerts.py so login persists.

Strategy:
  1. Navigate to https://www.tradingview.com/alerts/ (the dedicated alerts page;
     more stable than the in-chart side panel).
  2. Wait for the alert rows to render.
  3. Open the kebab/menu and pick "Remove all" -> "Yes" if available.
  4. Fallback: iterate row-by-row, hover -> delete.
  5. Verify list is empty before exiting.

Safe to run multiple times -- if no alerts exist, exits cleanly.

Usage:
  .venv\\Scripts\\python.exe tools\\tv_alert_setup\\delete_all_alerts.py
  .venv\\Scripts\\python.exe tools\\tv_alert_setup\\delete_all_alerts.py --dry-run
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout
except ImportError:
    print("FATAL: playwright not installed. pip install playwright && playwright install chromium")
    sys.exit(2)

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"

LOGIN_TIMEOUT_S = 300
ROW_DELETE_DELAY_S = 1.5     # gap between delete clicks (anti-bot)
PANEL_WAIT_S = 4.0


def _wait(page: Page, s: float) -> None:
    page.wait_for_timeout(int(s * 1000))


def _wait_for_login(ctx, page: Page) -> bool:
    print(f">>> Waiting up to {LOGIN_TIMEOUT_S}s for TradingView session cookie...")
    deadline = time.time() + LOGIN_TIMEOUT_S
    last_diag = 0.0
    start = time.time()
    while time.time() < deadline:
        try:
            cookies = ctx.cookies()
            names = {c["name"] for c in cookies}
            has_session = bool(names & {"sessionid", "sessionid_sign", "tv_ecuid"})
            now = time.time()
            if now - last_diag > 30:
                print(f">>> [poll @ {int(now-start)}s] cookies={sorted(names)[:5]} session={has_session}")
                last_diag = now
            if has_session:
                print(f">>> [OK] session detected after {int(now-start)}s")
                return True
        except Exception as e:
            print(f">>> [poll error] {e}")
        _wait(page, 3)
    print(">>> [WARN] login not detected within timeout")
    return False


def _count_alert_rows(page: Page) -> int:
    """Best-effort row counter for the alerts panel.

    Verified 2026-05-06: TV uses dynamically-hashed class names of the form
    'firstItem-RsFlttSS symbolName-RsFlttSS' for each alert row. The hash
    suffix changes between TV deploys, so we match by the prefix substring.
    """
    selectors = [
        "div[class*='firstItem-'][class*='symbolName-']",  # primary (2026-05+)
        "div[class*='symbolName-']",
        "[data-name='alert-item']",
        "div[class*='alertItem']",
    ]
    for sel in selectors:
        try:
            n = page.locator(sel).count()
            if n > 0:
                return n
        except Exception:
            continue
    return 0


def _try_remove_all(page: Page) -> bool:
    """Try to invoke the alerts panel 'Remove all' shortcut.

    The TV alerts widget (widgetbar-widget-alerts) has a header with a kebab
    menu that contains 'Remove all'. We probe several common locations.
    """
    # Scope kebab search to the alerts widget container so we don't grab
    # other panels' menus.
    panel_root = "div.widgetbar-widget-alerts, [class*='widgetbar-widget-alerts']"
    kebab_selectors = [
        f"{panel_root} button[aria-label*='More' i]",
        f"{panel_root} button[aria-label*='menu' i]",
        f"{panel_root} button[data-name*='menu']",
        f"{panel_root} button:has(span[class*='Icon'])",  # last-resort
    ]
    opened = False
    for sel in kebab_selectors:
        try:
            loc = page.locator(sel).last  # rightmost button is usually the kebab
            if loc.count() == 0 or not loc.is_visible(timeout=500):
                continue
            loc.click(timeout=2000)
            _wait(page, 1.0)
            print(f"  [info] opened panel menu via {sel!r}")
            opened = True
            break
        except Exception:
            continue
    if not opened:
        print("  [info] could not locate alerts panel kebab menu")
        return False

    remove_selectors = [
        "div[role='menuitem']:has-text('Remove all')",
        "div[role='menuitem']:has-text('Delete all')",
        "[role='menuitem']:has-text('Remove')",
        "span:has-text('Remove all')",
        "span:has-text('Delete all')",
    ]
    for sel in remove_selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0 or not loc.is_visible(timeout=500):
                continue
            loc.click(timeout=2000)
            _wait(page, 1.0)
            print(f"  [info] clicked '{sel}'")
            for confirm_sel in ("button:has-text('Yes, remove all')",
                                "button:has-text('Yes')", "button:has-text('Remove')",
                                "button:has-text('Delete')", "button:has-text('Confirm')"):
                try:
                    cb = page.locator(confirm_sel).first
                    if cb.count() and cb.is_visible(timeout=500):
                        cb.click(timeout=2000)
                        print(f"  [info] confirmed via {confirm_sel}")
                        _wait(page, 2.5)
                        return True
                except Exception:
                    continue
            return True
        except Exception:
            continue
    print("  [info] no 'Remove all' menu item found")
    return False


_ROW_SEL = "div[class*='firstItem-'][class*='symbolName-']"


def _delete_row_by_row(page: Page, max_rounds: int = 60) -> int:
    """Iterate alert rows, right-click each + pick Remove. TV's row hover-actions
    weren't reliable in 2026-05; right-click context menu is more stable."""
    deleted = 0
    for round_idx in range(max_rounds):
        rows_before = _count_alert_rows(page)
        if rows_before == 0:
            break

        clicked_delete = False
        try:
            row = page.locator(_ROW_SEL).first
            if row.count() == 0:
                print(f"  [warn] round {round_idx+1}: no rows match {_ROW_SEL!r}")
                break
            # Hover first to make sure row is in view + attach handlers
            try:
                row.hover(timeout=2000)
                _wait(page, 0.3)
            except Exception:
                pass
            # Right-click to get TV's context menu (Edit | Pause | Remove ...)
            row.click(button="right", timeout=2500)
            _wait(page, 0.6)
            # Pick the Remove option
            for menu_sel in (
                "div[role='menuitem']:has-text('Remove')",
                "div[role='menuitem']:has-text('Delete')",
                "[data-role='menuitem']:has-text('Remove')",
                "span:has-text('Remove')",
            ):
                try:
                    mi = page.locator(menu_sel).first
                    if mi.count() and mi.is_visible(timeout=500):
                        mi.click(timeout=1800)
                        clicked_delete = True
                        _wait(page, ROW_DELETE_DELAY_S)
                        break
                except Exception:
                    continue
            if not clicked_delete:
                # Esc to dismiss any open menu, then try keyboard Delete
                page.keyboard.press("Escape")
                _wait(page, 0.3)
                row.click(timeout=2000)
                _wait(page, 0.3)
                page.keyboard.press("Delete")
                _wait(page, 0.6)
            # Confirm dialog if it appears
            for c_sel in (
                "button:has-text('Yes, remove')",
                "button:has-text('Yes')",
                "button:has-text('Remove')",
                "button:has-text('Delete')",
            ):
                try:
                    cb = page.locator(c_sel).first
                    if cb.count() and cb.is_visible(timeout=400):
                        cb.click(timeout=1500)
                        _wait(page, 0.6)
                        break
                except Exception:
                    continue
        except Exception as e:
            print(f"  [warn] round {round_idx+1}: row click error: {e}")

        rows_after = _count_alert_rows(page)
        if rows_after >= rows_before:
            print(f"  [warn] round {round_idx+1}: rows didn't shrink "
                  f"({rows_before} -> {rows_after}); aborting row-loop")
            break
        deleted += (rows_before - rows_after)
        print(f"  [info] round {round_idx+1}: {rows_before} -> {rows_after} "
              f"(cumulative deleted={deleted})")

    return deleted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Just count alerts, don't delete")
    args = ap.parse_args()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1600, "height": 1000},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # Land on chart first (helps with login detection); then alerts page
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        if not _wait_for_login(ctx, page):
            print(">>> proceeding anyway")

        page.goto("https://www.tradingview.com/chart/?aside=alerts",
                  wait_until="domcontentloaded", timeout=30_000)
        _wait(page, PANEL_WAIT_S)

        # Open the alert manager side panel via Alt+A keyboard shortcut as a backup
        page.keyboard.press("Alt+a")
        _wait(page, 2.0)

        rows = _count_alert_rows(page)
        print(f"\n=== Found {rows} alert rows on the page ===")

        if args.dry_run:
            print("(dry-run) not deleting")
            ctx.close()
            return 0

        if rows == 0:
            print("Nothing to delete. Exiting.")
            ctx.close()
            return 0

        # Try the bulk Remove-all path first
        print("\n--- attempting bulk 'Remove all' ---")
        if _try_remove_all(page):
            _wait(page, 3.0)

        # Whatever remains -- pick off row by row
        remaining = _count_alert_rows(page)
        print(f"\nAfter bulk attempt: {remaining} rows remain")
        if remaining > 0:
            print("--- iterating row-by-row deletion ---")
            removed = _delete_row_by_row(page)
            print(f"  deleted {removed} via row-iteration")

        final = _count_alert_rows(page)
        print(f"\n=== Final: {final} alerts remain ===")
        if final > 0:
            print(">>> WARNING: could not delete all alerts via automation.")
            print(">>> Hit Enter after you delete the rest manually in the visible browser.")
            try:
                input("  > ")
            except EOFError:
                pass

        ctx.close()
        return 0 if final == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
