"""Open TV chart, open alert dialog via Alt+A, dump dialog DOM to file.

Lets us update setup_tv_alerts.py selectors based on TV's actual current UI.
Uses the same persistent profile as setup_tv_alerts.py so login persists.

Output: tools/tv_alert_setup/dom_dump.html  +  dom_dump.json (aria tree)
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
OUT_HTML = HERE / "dom_dump.html"
OUT_TXT = HERE / "dom_dump_buttons_inputs.txt"

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
        # Wait for TradingView SPA to settle
        page.wait_for_timeout(8000)

        print("Pressing Alt+A to open alert dialog...")
        page.keyboard.press("Alt+a")
        page.wait_for_timeout(4000)

        # Capture full page HTML
        html = page.content()
        OUT_HTML.write_text(html, encoding="utf-8")
        print(f"Wrote full HTML: {OUT_HTML} ({len(html):,} bytes)")

        # Extract just the dialog-relevant elements (input/textarea/button) with their attrs
        elements = page.evaluate(
            """() => {
                const out = [];
                const tags = ['input', 'textarea', 'button', 'select', 'a'];
                tags.forEach(tag => {
                    document.querySelectorAll(tag).forEach(el => {
                        const r = el.getBoundingClientRect();
                        if (r.width === 0 && r.height === 0) return;  // skip hidden
                        const attrs = {};
                        for (const a of el.attributes) attrs[a.name] = a.value.slice(0, 80);
                        out.push({
                            tag: tag,
                            text: (el.innerText || el.value || '').slice(0, 60),
                            attrs: attrs,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        });
                    });
                });
                return out;
            }"""
        )

        lines = []
        for e in elements:
            attrs_str = " ".join(f"{k}={v!r}" for k, v in e["attrs"].items() if k in (
                "name", "id", "class", "type", "placeholder", "aria-label", "data-name", "data-test")) or "(no attrs)"
            txt = e["text"].replace("\n", " ").strip()
            lines.append(f"<{e['tag']:8}> [{e['x']:4},{e['y']:4} {e['w']:4}x{e['h']:3}] {txt[:50]:<50} | {attrs_str}")

        OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
        print(f"Wrote {len(elements)} elements: {OUT_TXT}")

        # Look for likely alert-dialog clues in the visible elements
        print("\n=== filtering for 'alert' / 'webhook' / 'notification' related ===")
        keywords = ("alert", "webhook", "notification", "message", "condition", "create")
        relevant = [
            e for e in elements
            if any(kw.lower() in (
                (e["text"] or "").lower() +
                " ".join(v.lower() for v in e["attrs"].values())
            ) for kw in keywords)
        ]
        for e in relevant[:40]:
            attrs_str = " ".join(f"{k}={v!r}" for k, v in e["attrs"].items() if k in (
                "name", "id", "class", "type", "placeholder", "aria-label", "data-name", "data-test"))
            txt = e["text"].replace("\n", " ").strip()
            print(f"  <{e['tag']}> {txt[:50]!r:<55} | {attrs_str[:160]}")

        print(f"\nTotal relevant: {len(relevant)}")
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
