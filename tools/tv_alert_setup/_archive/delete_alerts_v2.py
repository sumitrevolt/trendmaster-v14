"""Robust TradingView alerts purge -- v2.

Approach:
  1. Open Playwright with persistent profile (already logged in).
  2. Goto chart page.
  3. Explicitly click the right-toolbar 'Alerts' button to open the panel.
  4. Wait for rows.
  5. JS-injection: enumerate rows, for each row dispatch hover events
     and find the visible 'remove' button; click via Playwright by coordinates.
  6. Loop until 0.

Run:
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\delete_alerts_v2.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("FATAL: playwright not installed.")
    sys.exit(2)

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"


def _open_alerts_panel(page) -> bool:
    """Click the right-rail 'Alerts' icon to open the alerts widget."""
    sel_candidates = [
        'button[aria-label="Alerts"]',
        'button[data-name="alerts"]',
        'button[data-tooltip="Alerts"]',
    ]
    for sel in sel_candidates:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=1500):
                loc.click(timeout=2000)
                page.wait_for_timeout(2000)
                # Verify it's now pressed (panel open)
                state = loc.get_attribute("aria-pressed")
                print(f"  [info] clicked {sel!r} -- aria-pressed={state}")
                if state == "true":
                    return True
                # Try clicking again if first didn't toggle
                if state == "false":
                    loc.click(timeout=2000)
                    page.wait_for_timeout(1500)
                    return True
        except Exception as e:
            print(f"  [warn] {sel!r} failed: {e}")
            continue
    return False


PROBE_AND_CLICK_DELETE_JS = r"""
() => {
    // 1. Find the alerts widget content area (rows live here, not in the toolbar button)
    //    Try multiple selectors; the widget pane sits inside the right-rail container.
    const panel = document.querySelector('.widgetbar-widget-alerts')
                || document.querySelector('[class*="widgetbar-widget-alerts"]')
                || document.querySelector('[data-widget-name="alerts"]');

    // 2. Find rows. Scope first to panel; if panel returns 0, fall back to global.
    let rows = [];
    if (panel) {
        rows = Array.from(panel.querySelectorAll('div[class*="firstItem-"][class*="symbolName-"]'));
    }
    if (rows.length === 0) {
        rows = Array.from(document.querySelectorAll('div[class*="firstItem-"][class*="symbolName-"]'));
        // Filter: keep only rows that are inside an alert widget (exclude watchlist symbols).
        // Watchlist rows are in '.widgetbar-widget-watchlist'; alert rows are NOT.
        rows = rows.filter(r => !r.closest('.widgetbar-widget-watchlist, [class*="widgetbar-widget-watchlist"]'));
    }

    if (rows.length === 0) {
        return {phase: 'no-rows', count: 0};
    }

    // 3. Take the first row, walk UP to find a parent that owns the action buttons.
    const row = rows[0];
    let actionsHost = null;
    let walker = row;
    for (let d = 0; d < 6; d++) {
        walker = walker.parentElement;
        if (!walker) break;
        // Force-show any hover-revealed children
        walker.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true}));
        walker.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
        // Look for buttons whose label contains 'remove'/'delete' (i)
        const btns = walker.querySelectorAll('button, [role="button"]');
        for (const b of btns) {
            const label = ((b.getAttribute('aria-label') || '') + '|' +
                           (b.getAttribute('title') || '') + '|' +
                           (b.getAttribute('data-name') || '') + '|' +
                           (b.innerText || '')).toLowerCase();
            if (/remove|delete|trash|bin/.test(label)) {
                actionsHost = walker;
                break;
            }
        }
        if (actionsHost) break;
    }

    if (!actionsHost) {
        return {phase: 'no-actions-host', count: rows.length, firstRowHtml: row.outerHTML.slice(0, 800)};
    }

    // 4. Find the actual delete button(s)
    const deleteBtn = (() => {
        const btns = actionsHost.querySelectorAll('button, [role="button"]');
        for (const b of btns) {
            const label = ((b.getAttribute('aria-label') || '') + '|' +
                           (b.getAttribute('title') || '') + '|' +
                           (b.getAttribute('data-name') || '') + '|' +
                           (b.innerText || '')).toLowerCase();
            if (/^remove|^delete|trash|bin/.test(label.split('|').filter(Boolean)[0] || '')) return b;
            if (/remove|delete/.test(label)) return b;
        }
        return null;
    })();

    if (!deleteBtn) {
        return {phase: 'no-delete-btn', count: rows.length, hostHtml: actionsHost.outerHTML.slice(0, 800)};
    }

    // 5. Get bounding rect for Playwright click
    const r = deleteBtn.getBoundingClientRect();
    return {
        phase: 'click',
        count: rows.length,
        x: Math.round(r.x + r.width/2),
        y: Math.round(r.y + r.height/2),
        btnLabel: (deleteBtn.getAttribute('aria-label') || deleteBtn.getAttribute('title') || deleteBtn.getAttribute('data-name') || ''),
    };
}
"""


COUNT_ALERTS_JS = r"""
() => {
    let rows = Array.from(document.querySelectorAll('div[class*="firstItem-"][class*="symbolName-"]'));
    rows = rows.filter(r => !r.closest('.widgetbar-widget-watchlist, [class*="widgetbar-widget-watchlist"]'));
    return rows.length;
}
"""


def main() -> int:
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
        page.wait_for_timeout(5000)

        if not _open_alerts_panel(page):
            print("[X] could not open alerts panel via toolbar")
            ctx.close()
            return 2

        page.wait_for_timeout(3000)
        initial = page.evaluate(COUNT_ALERTS_JS)
        print(f"[info] initial alerts visible: {initial}")
        if initial == 0:
            print("[OK] no alerts to delete")
            ctx.close()
            return 0

        deleted = 0
        for round_idx in range(60):
            probe = page.evaluate(PROBE_AND_CLICK_DELETE_JS)
            phase = probe.get('phase')
            count = probe.get('count', 0)
            if count == 0:
                print(f"  [OK] all alerts deleted after {round_idx} rounds, total={deleted}")
                break
            if phase == 'click':
                x = probe['x']; y = probe['y']
                page.mouse.click(x, y)
                print(f"  [round {round_idx+1}] clicked {probe.get('btnLabel')!r} at ({x},{y}); count was {count}")
                page.wait_for_timeout(1200)
                # Confirm if dialog appears
                for c_sel in ("button:has-text('Yes, remove')", "button:has-text('Yes')",
                              "button:has-text('Remove')", "button:has-text('Delete')"):
                    try:
                        cb = page.locator(c_sel).first
                        if cb.count() and cb.is_visible(timeout=400):
                            cb.click(timeout=1500)
                            page.wait_for_timeout(700)
                            break
                    except Exception:
                        continue
                page.wait_for_timeout(800)
                new_count = page.evaluate(COUNT_ALERTS_JS)
                if new_count < count:
                    deleted += (count - new_count)
                else:
                    print(f"  [warn] count did not shrink ({count} -> {new_count}); aborting")
                    print(f"  [dbg] last probe: {json.dumps(probe)[:400]}")
                    break
            else:
                print(f"  [warn] probe phase={phase}, dump={json.dumps(probe)[:400]}")
                if phase == 'no-actions-host':
                    # Save firstRowHtml so we can hand-pick a selector
                    Path("logs/tv_first_alert_row.html").write_text(probe.get('firstRowHtml', ''), encoding="utf-8")
                break

        # Final verification
        final = page.evaluate(COUNT_ALERTS_JS)
        print(f"\n=== FINAL: {final} alerts remain (deleted {deleted}) ===")
        ctx.close()
        return 0 if final == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
