"""Diagnostic: open TV alerts page, dump DOM + heuristic counts to console + file.

Run:
  .venv\\Scripts\\python.exe tools\\tv_alert_setup\\inspect_alerts_dom.py

Output:
  logs/tv_alerts_dom_dump.txt -- structured snapshot for selector tuning.
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("FATAL: playwright not installed.")
    sys.exit(2)

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
PROJECT_ROOT = HERE.parent.parent
DUMP_PATH = PROJECT_ROOT / "logs" / "tv_alerts_dom_dump.txt"

# JavaScript run inside the page to enumerate "alert-like" rows
PROBE_JS = r"""
() => {
    const out = {url: location.href, title: document.title, candidates: []};
    // 1. Try data-name=alert* attributes
    const byDataName = document.querySelectorAll('[data-name*="alert" i]');
    out.byDataName = byDataName.length;

    // 2. Class names containing 'alert' (case-insensitive)
    const allEls = document.querySelectorAll('div, li, article');
    const classMatches = {};
    for (const el of allEls) {
        const cls = (el.className || '').toString().toLowerCase();
        if (cls.includes('alert')) {
            for (const c of cls.split(/\s+/)) {
                if (c.includes('alert')) {
                    classMatches[c] = (classMatches[c] || 0) + 1;
                }
            }
        }
    }
    out.classCounts = Object.fromEntries(
        Object.entries(classMatches).sort((a,b) => b[1]-a[1]).slice(0, 30)
    );

    // 3. Find rows that *look* like alert items - heuristic by text content
    // Alert rows typically contain symbol name + a state icon
    const possibleRows = [];
    const candidates = document.querySelectorAll('div[role="row"], div[role="listitem"], li, [class*="row" i], [class*="item" i]');
    for (const el of candidates) {
        const txt = (el.innerText || '').trim();
        if (txt.length < 5 || txt.length > 200) continue;
        // Look for typical alert text patterns: SYMBOL + price + condition word
        if (/\b(crossing|greater|less|equal|once per bar|exiting channel|entering channel|All instances)/i.test(txt) ||
            /\b(BTCUSD|EURUSD|XAUUSD|USDJPY|GBPUSD|XAGUSD)\b/.test(txt)) {
            possibleRows.push({
                tag: el.tagName,
                cls: (el.className || '').toString().slice(0, 100),
                text: txt.slice(0, 120),
                outerSnippet: el.outerHTML.slice(0, 300),
            });
            if (possibleRows.length >= 25) break;
        }
    }
    out.possibleRows = possibleRows;
    out.possibleRowCount = possibleRows.length;

    // 4. Snapshot the side panel container
    const sidePanel = document.querySelector('[data-name*="alerts"], [class*="alertsList"], aside, [class*="rightPane"]');
    out.sidePanelHtml = sidePanel ? sidePanel.outerHTML.slice(0, 2000) : null;

    return out;
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

        urls_to_probe = [
            "https://www.tradingview.com/chart/?aside=alerts",
            "https://www.tradingview.com/alerts/",
        ]

        results = []
        for url in urls_to_probe:
            print(f"\n=== probing {url} ===")
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(6000)
            # Trigger Alt+A to open the alerts panel if needed
            try:
                page.keyboard.press("Alt+a")
                page.wait_for_timeout(2000)
            except Exception:
                pass

            data = page.evaluate(PROBE_JS)
            print(json.dumps({k: v for k, v in data.items() if k != 'sidePanelHtml'},
                             indent=2, default=str)[:2500])
            results.append({"url": url, "data": data})

        DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
        DUMP_PATH.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        print(f"\n[OK] dumped {DUMP_PATH}")
        print(">>> Browser left open for manual inspection. Press Enter to close.")
        try:
            input("  > ")
        except Exception:
            pass
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
