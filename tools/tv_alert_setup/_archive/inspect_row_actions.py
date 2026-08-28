"""Deep DOM inspector: discover the actual delete-button structure of TV alert rows.

Output:
  logs/tv_alert_row_structure.json  -- detailed row anatomy for selector design.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("FATAL: playwright not installed.")
    sys.exit(2)

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
DUMP_PATH = HERE.parent.parent / "logs" / "tv_alert_row_structure.json"

PROBE_JS = r"""
() => {
    const result = {timestamp: Date.now(), url: location.href};

    // 1. Find the alerts widget container (scoped, no false positives from watchlist)
    const panel = document.querySelector('.widgetbar-widget-alerts')
                || document.querySelector('[class*="widgetbar-widget-alerts"]');
    if (!panel) {
        result.error = 'no widgetbar-widget-alerts panel';
        return result;
    }
    result.panelClass = panel.className.slice(0, 200);

    // 2. Capture panel header / toolbar buttons (for bulk Remove-all discovery)
    const headerBtns = [];
    const headerCandidates = panel.querySelectorAll('header button, [class*="header"] button, [class*="toolbar"] button');
    for (const b of headerCandidates) {
        headerBtns.push({
            cls: (b.className || '').toString().slice(0, 100),
            ariaLabel: b.getAttribute('aria-label') || '',
            title: b.getAttribute('title') || '',
            dataName: b.getAttribute('data-name') || '',
            text: (b.innerText || '').trim().slice(0, 40),
        });
    }
    result.headerBtns = headerBtns;

    // 3. Find every alert row inside the panel
    const rows = Array.from(panel.querySelectorAll('div[class*="firstItem-"][class*="symbolName-"]'));
    result.rowCount = rows.length;

    // 4. For each of the first 3 rows, walk up the DOM looking for siblings/ancestors
    //    that contain action buttons. Capture full ancestor chain.
    const samples = [];
    for (let i = 0; i < Math.min(3, rows.length); i++) {
        const row = rows[i];
        const ancestors = [];
        let walker = row;
        for (let d = 0; d < 8 && walker; d++) {
            const sib = [];
            // List all sibling nodes
            const siblings = walker.parentElement ? Array.from(walker.parentElement.children) : [];
            for (const s of siblings) {
                const buttons = s.querySelectorAll('button, [role="button"]');
                for (const b of buttons) {
                    sib.push({
                        cls: (b.className || '').toString().slice(0, 100),
                        ariaLabel: b.getAttribute('aria-label') || '',
                        title: b.getAttribute('title') || '',
                        dataName: b.getAttribute('data-name') || '',
                        text: (b.innerText || '').trim().slice(0, 40),
                    });
                }
            }
            ancestors.push({
                depth: d,
                tag: walker.tagName,
                cls: (walker.className || '').toString().slice(0, 120),
                btnCount: walker.parentElement
                    ? walker.parentElement.querySelectorAll('button, [role="button"]').length
                    : 0,
                sibButtons: sib.slice(0, 10),
            });
            walker = walker.parentElement;
        }
        samples.push({rowIdx: i, rowText: (row.innerText || '').slice(0, 80), ancestors});
    }
    result.samples = samples;

    // 5. Force-hover the first row to reveal hidden action buttons + re-snapshot
    if (rows.length > 0) {
        const first = rows[0];
        // Add a CSS rule that forces all descendants of alert rows to be visible
        const style = document.createElement('style');
        style.textContent = `
            div[class*="firstItem-"], div[class*="firstItem-"] * {
                visibility: visible !important;
                opacity: 1 !important;
                display: revert !important;
            }
            div[class*="row-"][class*="alert"] button,
            div[class*="row-"][class*="alert"] [role="button"] {
                visibility: visible !important;
                opacity: 1 !important;
                pointer-events: auto !important;
            }
        `;
        document.head.appendChild(style);

        // Dispatch mouseenter / mouseover on the row + ancestors
        let walker = first;
        for (let d = 0; d < 4 && walker; d++) {
            walker.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true, cancelable: true}));
            walker.dispatchEvent(new MouseEvent('mouseover', {bubbles: true, cancelable: true}));
            walker = walker.parentElement;
        }

        // Now re-scan parent for buttons
        const parent2 = first.parentElement && first.parentElement.parentElement;
        if (parent2) {
            const buttonsAfterHover = [];
            const allBtns = parent2.querySelectorAll('button, [role="button"]');
            for (const b of allBtns) {
                buttonsAfterHover.push({
                    cls: (b.className || '').toString().slice(0, 120),
                    ariaLabel: b.getAttribute('aria-label') || '',
                    title: b.getAttribute('title') || '',
                    dataName: b.getAttribute('data-name') || '',
                    text: (b.innerText || '').trim().slice(0, 40),
                    visible: !!(b.offsetWidth || b.offsetHeight),
                });
            }
            result.afterHoverButtons = buttonsAfterHover.slice(0, 30);
        }

        // Also dump first row's outerHTML (truncated) for selector visualisation
        result.firstRowHtml = first.outerHTML.slice(0, 1500);
        // And the row's ancestor at depth=2 (likely the actual row container)
        const grand = first.parentElement && first.parentElement.parentElement;
        result.rowContainerHtml = grand ? grand.outerHTML.slice(0, 2500) : null;
    }

    return result;
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

        page.goto("https://www.tradingview.com/chart/?aside=alerts",
                  wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(7000)
        # Make sure the alerts side panel is open
        try:
            page.keyboard.press("Alt+a")
        except Exception:
            pass
        page.wait_for_timeout(2500)

        data = page.evaluate(PROBE_JS)
        # Save to file
        DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
        DUMP_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"[OK] dump written -> {DUMP_PATH}")
        # Print summary to console
        print(json.dumps({
            'rowCount': data.get('rowCount'),
            'panelClass': data.get('panelClass', '')[:100],
            'headerBtnCount': len(data.get('headerBtns', [])),
            'sampleCount': len(data.get('samples', [])),
            'afterHoverBtnCount': len(data.get('afterHoverButtons', [])),
            'error': data.get('error'),
        }, indent=2))
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
