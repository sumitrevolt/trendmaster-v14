"""Open dialog, click notifications via Playwright, screenshot — see real state."""
from __future__ import annotations
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

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        viewport={"width": 1600, "height": 1000},
        args=["--start-maximized"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD&interval=5",
              wait_until="domcontentloaded", timeout=30_000)
    time.sleep(8)
    page.bring_to_front()
    page.evaluate("() => document.querySelector('canvas')?.click()")
    time.sleep(0.5)
    page.keyboard.press("Alt+a")
    time.sleep(3)
    page.screenshot(path=str(HERE / "01_dialog_opened.png"))
    print("Saved 01_dialog_opened.png")

    # Click notifications via Playwright (force) to ensure click lands
    print("Clicking notifications button via Playwright...")
    try:
        # Match button containing both 'Webhook' and 'Toasts' text
        btn = page.get_by_role("button").filter(has_text="Webhook").filter(has_text="Toasts").first
        if btn.count() == 0:
            btn = page.locator("button:has-text('Webhook')").filter(has_text="Toasts").first
        btn.click(force=True, timeout=4000)
        time.sleep(2)
        page.screenshot(path=str(HERE / "02_after_notif_click.png"))
        print("Saved 02_after_notif_click.png")
    except Exception as e:
        print(f"Click failed: {e}")

    # Check URL field visibility
    url_state = page.evaluate(
        """() => {
            const el = document.querySelector('#webhook-url');
            if (!el) return {found: false};
            const r = el.getBoundingClientRect();
            const cs = getComputedStyle(el);
            return {
                found: true,
                visible: r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden',
                x: r.x, y: r.y, w: r.width, h: r.height,
                value: el.value || '',
            };
        }"""
    )
    print(f"webhook-url state: {url_state}")

    # Also dump any new dialogs/modals that appeared
    modals = page.evaluate(
        """() => {
            const out = [];
            document.querySelectorAll('[role="dialog"], [role="menu"], [class*="modal"], [class*="popup"]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width < 50) return;
                const attrs = {};
                for (const a of el.attributes) attrs[a.name] = a.value.slice(0,80);
                out.push({tag: el.tagName, x: r.x, y: r.y, w: r.width, h: r.height, attrs});
            });
            return out;
        }"""
    )
    print(f"\n{len(modals)} modal/dialog/menu elements:")
    for m in modals[:10]:
        print(f"  <{m['tag']}> [{int(m['x']):4},{int(m['y']):4} {int(m['w'])}x{int(m['h'])}] role={m['attrs'].get('role','')!r} class={m['attrs'].get('class','')[:60]!r}")

    ctx.close()
