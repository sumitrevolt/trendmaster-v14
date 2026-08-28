"""Open TV chart and inspect the right-side ALERTS MANAGE panel DOM.

We need the structure of:
  - each alert row (selector + name extraction)
  - the row's 3-dot menu / delete button
  - how clicking opens edit dialog

Output: tools/tv_alert_setup/alerts_panel_dump.txt + .png screenshot
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
OUT_TXT = HERE / "alerts_panel_dump.txt"
OUT_SCREEN = HERE / "alerts_panel_screen.png"
OUT_JSON = HERE / "alerts_panel_rows.json"

CHART_URL = "https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD&interval=5"


def main() -> int:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1600, "height": 1000},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print(f"Navigating to {CHART_URL} ...")
        page.goto(CHART_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(7000)

        # Open the alerts panel only if not already visible.
        # Check by looking for any element in right sidebar with text we expect
        # (e.g. "any alert()" or "Crossing").
        is_open = page.evaluate(
            r"""() => {
                const candidates = document.querySelectorAll('div, span, p');
                for (const el of candidates) {
                    const r = el.getBoundingClientRect();
                    if (r.x < 1100 || r.width < 50) continue;
                    const t = (el.innerText || '').toLowerCase();
                    if (t.includes('any alert(') || t.includes('crossing') ||
                        t.includes('trendmaster') || t.includes('rocket prime')) {
                        return true;
                    }
                }
                return false;
            }"""
        )
        print(f"alerts panel currently open: {is_open}")
        if not is_open:
            print("Opening alerts panel via toggle...")
            try:
                page.locator("button[data-name='alerts']").first.click(force=True, timeout=2000)
                page.wait_for_timeout(2500)
            except Exception as e:
                print(f"  toggle click failed: {e!s:.80}")
        else:
            page.wait_for_timeout(1000)

        # Switch to "Alerts" tab (not Log). Tab buttons live near top of panel.
        print("Switching to Alerts tab (not Log)...")
        switched = page.evaluate(
            r"""() => {
                // Find tab buttons in right panel area
                const candidates = document.querySelectorAll('button, [role="tab"], div[role="button"]');
                for (const el of candidates) {
                    const r = el.getBoundingClientRect();
                    if (r.x < 1100 || r.y > 200 || r.y < 80) continue;
                    const t = (el.innerText || '').trim();
                    if (t === 'Alerts' || /^Alerts$/i.test(t)) {
                        el.click();
                        return {clicked: t, x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
                return null;
            }"""
        )
        print(f"  tab click result: {switched}")
        page.wait_for_timeout(1500)

        page.screenshot(path=str(OUT_SCREEN))
        print(f"Screenshot: {OUT_SCREEN}")

        # Dump alerts panel rows. Strategy: find all elements containing
        # "alert() function call" text or "Crossing" or "TrendMaster",
        # walk up to the ROW container, capture its bounds + attrs.
        rows = page.evaluate(
            r"""() => {
                // Strategy: find ANY div in the right sidebar (x>1100) whose
                // innerText contains a known alert-name pattern, then walk UP
                // to find the row container (the parent that itself contains
                // the symbol+TF info but isn't too big).
                const seedKeywords = [
                    'any alert(', 'crossing', 'trendmaster', 'rocket prime',
                    'observation', 'observation:', '#### '
                ];
                const seedNodes = [];
                document.querySelectorAll('div, span, p').forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.x < 1100 || r.width < 50 || r.height < 8) return;
                    const t = (el.innerText || '').toLowerCase();
                    if (t.length < 5 || t.length > 500) return;
                    if (seedKeywords.some(k => t.includes(k))) {
                        seedNodes.push(el);
                    }
                });
                // For each seed, walk up <= 6 ancestors looking for the row container.
                // A row container has height in 50-200 px range.
                const seenRows = new Set();
                const rows = [];
                for (const seed of seedNodes) {
                    let node = seed;
                    for (let depth = 0; depth < 8; depth++) {
                        if (!node) break;
                        const r = node.getBoundingClientRect();
                        if (r.height >= 40 && r.height <= 220 && r.width > 200) {
                            if (!seenRows.has(node)) {
                                seenRows.add(node);
                                const txt = (node.innerText || '').slice(0, 250)
                                    .replace(/\s+/g, ' ').trim();
                                const buttons = [];
                                node.querySelectorAll('button, [role="button"]').forEach(b => {
                                    const br = b.getBoundingClientRect();
                                    buttons.push({
                                        al: b.getAttribute('aria-label') || '',
                                        dn: b.getAttribute('data-name') || '',
                                        cls: (b.getAttribute('class') || '').slice(0, 50),
                                        btxt: (b.innerText || '').slice(0, 30)
                                              .replace(/\s+/g, ' ').trim(),
                                        x: Math.round(br.x), y: Math.round(br.y),
                                        w: Math.round(br.width), h: Math.round(br.height),
                                    });
                                });
                                rows.push({
                                    tag: node.tagName,
                                    cls: (node.getAttribute('class') || '').slice(0, 100),
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height),
                                    text: txt,
                                    buttons: buttons,
                                    depth: depth,
                                });
                            }
                            break;  // found row, stop walking up
                        }
                        node = node.parentElement;
                    }
                }
                return rows;
            }"""
        )

        # Also dump panel header buttons (broom = clear, ✓✓ = mark read, etc.)
        header_btns = page.evaluate(
            r"""() => {
                const out = [];
                document.querySelectorAll('button, [role="button"]').forEach(b => {
                    const r = b.getBoundingClientRect();
                    if (r.x < 1100 || r.y > 250 || r.y < 80) return;
                    const al = b.getAttribute('aria-label') || '';
                    const dn = b.getAttribute('data-name') || '';
                    const txt = (b.innerText || '').slice(0, 30).replace(/\s+/g,' ').trim();
                    out.push({al, dn, txt, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)});
                });
                return out;
            }"""
        )

        lines = []
        lines.append(f"=== Alerts panel header buttons (right sidebar, top) — {len(header_btns)} ===")
        for b in header_btns:
            lines.append(f"  [{b['x']},{b['y']} {b['w']}x{b['h']}] aria={b['al']!r} data-name={b['dn']!r} text={b['txt']!r}")
        lines.append("")
        lines.append(f"=== Alert rows — {len(rows)} ===")
        for i, r in enumerate(rows):
            lines.append(f"\nROW [{i}] @ ({r['x']},{r['y']}) {r['w']}x{r['h']}  cls={r['cls']!r}")
            lines.append(f"  text: {r['text']!r}")
            lines.append(f"  {len(r['buttons'])} buttons:")
            for b in r['buttons'][:10]:
                lines.append(f"    [{b['x']},{b['y']} {b['w']}x{b['h']}] aria={b['al']!r} data-name={b['dn']!r} text={b['btxt']!r} cls={b['cls']!r}")
        OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
        OUT_JSON.write_text(json.dumps({"header": header_btns, "rows": rows}, indent=2), encoding="utf-8")
        print(f"Dump: {OUT_TXT}")
        print(f"JSON: {OUT_JSON}")
        print(f"Found {len(rows)} alert rows.")

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
