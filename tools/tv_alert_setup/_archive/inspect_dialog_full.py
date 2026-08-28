"""Comprehensive probe: open alert dialog, find ALL editable fields including
contenteditable divs, dump complete dialog tree."""
from __future__ import annotations
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
OUT_TXT = HERE / "dom_dump_full.txt"

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

        print("Navigating to chart ...")
        page.goto(CHART_URL, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(8000)

        print("Pressing Alt+A ...")
        page.keyboard.press("Alt+a")
        page.wait_for_timeout(3000)

        # Find the dialog container — TV uses div[data-name='create-alert-dialog'] or similar
        dialog_info = page.evaluate(
            """() => {
                const dlgs = document.querySelectorAll(
                    '[role="dialog"], [data-name*="dialog"], [data-name*="alert"], [class*="dialog"]'
                );
                const out = [];
                dlgs.forEach(d => {
                    const r = d.getBoundingClientRect();
                    if (r.width === 0 && r.height === 0) return;
                    if (r.width < 200) return; // too small to be the dialog
                    const attrs = {};
                    for (const a of d.attributes) attrs[a.name] = a.value.slice(0, 80);
                    out.push({tag: d.tagName, x: r.x, y: r.y, w: r.width, h: r.height, attrs});
                });
                return out;
            }"""
        )
        print(f"\n=== {len(dialog_info)} candidate dialog containers ===")
        for d in dialog_info[:8]:
            print(f"  <{d['tag']}> [{int(d['x']):4},{int(d['y']):4} {int(d['w'])}x{int(d['h']):3}] {d['attrs']}")

        # Find ALL editable elements including contenteditable
        elements = page.evaluate(
            """() => {
                const out = [];
                const sel = 'input, textarea, [contenteditable="true"], [contenteditable=""], [role="textbox"]';
                document.querySelectorAll(sel).forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 && r.height === 0) return;
                    const attrs = {};
                    for (const a of el.attributes) attrs[a.name] = a.value.slice(0, 100);
                    let text = '';
                    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                        text = el.value || '';
                    } else {
                        text = el.innerText || el.textContent || '';
                    }
                    out.push({
                        tag: el.tagName.toLowerCase(),
                        text: text.slice(0, 100),
                        attrs: attrs,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                });
                return out;
            }"""
        )

        lines = []
        print(f"\n=== {len(elements)} editable elements ===")
        for e in elements:
            attrs_kept = {k: v for k, v in e["attrs"].items() if k in (
                "name", "id", "class", "type", "placeholder", "aria-label", "data-name",
                "data-test", "role", "contenteditable")}
            attrs_str = " ".join(f"{k}={v!r}" for k, v in attrs_kept.items())
            txt = e["text"].replace("\n", " ").strip()
            line = f"<{e['tag']:<14}> [{e['x']:4},{e['y']:4} {e['w']:4}x{e['h']:3}] {txt[:60]:<60} | {attrs_str[:200]}"
            print(line)
            lines.append(line)

        OUT_TXT.write_text("\n".join(lines), encoding="utf-8")

        # Also find the submit button(s)
        print(f"\n=== submit buttons ===")
        submits = page.evaluate(
            """() => {
                const btns = [];
                document.querySelectorAll("button[type='submit'], button[name='submit']").forEach(b => {
                    const r = b.getBoundingClientRect();
                    if (r.width === 0 && r.height === 0) return;
                    btns.push({text: b.innerText, x: r.x, y: r.y, w: r.width, h: r.height});
                });
                return btns;
            }"""
        )
        for b in submits:
            print(f"  text={b['text']!r:<20} pos=({int(b['x'])},{int(b['y'])}) {int(b['w'])}x{int(b['h'])}")

        # Take a screenshot of the dialog
        screenshot_path = HERE / "alert_dialog_screenshot.png"
        page.screenshot(path=str(screenshot_path), full_page=False)
        print(f"\nScreenshot: {screenshot_path}")

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
