"""Phase 1: enumerate ALL TV alerts via the right-side Alerts panel.

NO destructive actions. Just read state and dump to alerts_inventory.json.
Operator reviews before any deletion.

Strategy:
  1. Open Playwright Chromium (persistent profile)
  2. Click the Alerts icon in the right sidebar (data-name='alerts')
  3. Wait for the alerts list to load
  4. Extract every alert row's text content
  5. Categorize: created today vs older, with-webhook-url vs not
  6. Also try TV's pricealerts API with proper auth headers
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
INVENTORY_PATH = HERE / "alerts_inventory.json"
SCREENSHOT_PATH = HERE / "alerts_panel_screenshot.png"


def main() -> int:
    print("=== Phase 1: enumerate ALL TV alerts (read-only) ===\n")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1600, "height": 1000},
            args=["--start-maximized"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 1) Try the API approach first with full headers from page context.
        api = ctx.request
        try:
            page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
            time.sleep(5)
        except Exception as e:
            print(f"goto error: {e}")

        # 2) Click alerts icon in right sidebar (data-name='alerts')
        print("Opening Alerts panel...")
        try:
            page.locator("[data-name='alerts']").first.click(force=True, timeout=4000)
            time.sleep(2.5)
            print("[ok] alerts panel opened")
        except Exception as e:
            print(f"[warn] alerts panel click failed: {e}")

        # 3) Screenshot the panel
        page.screenshot(path=str(SCREENSHOT_PATH))
        print(f"Screenshot saved: {SCREENSHOT_PATH}")

        # 4) Extract every alert row from the DOM
        print("\nExtracting alert rows...")
        alerts = page.evaluate(
            """() => {
                // TV's alert list rows have role='listitem' OR specific class
                // We look in the right sidebar panel for items containing alert metadata
                const out = [];

                // Try multiple candidate selectors
                const selectors = [
                    '[data-name*="alert"][role="listitem"]',
                    '[data-test*="alert-item"]',
                    'div[class*="alertItem"]',
                    'div[class*="alert-item"]',
                    'div[class*="ListItem"][class*="alert"]',
                    // Fallback: any element with text matching alert pattern
                ];

                let elements = [];
                for (const sel of selectors) {
                    const found = document.querySelectorAll(sel);
                    if (found.length > 0) { elements = Array.from(found); break; }
                }

                // If still empty, try a broader scan: divs in the right panel that contain
                // both a symbol name AND a condition keyword
                if (elements.length === 0) {
                    const allDivs = document.querySelectorAll('div');
                    for (const d of allDivs) {
                        const r = d.getBoundingClientRect();
                        if (r.x < 1200) continue;  // right sidebar
                        if (r.width < 200 || r.width > 500) continue;
                        if (r.height < 30 || r.height > 200) continue;
                        const txt = (d.innerText || '').trim();
                        // alert rows typically contain symbol + "Crossing"/"Greater"/"Less"
                        if (/Crossing|Greater|Less|>=|<=|equals/i.test(txt) &&
                            /[A-Z]{6}|XAUUSD|EURUSD|BTCUSD/.test(txt)) {
                            elements.push(d);
                        }
                    }
                }

                elements.forEach((el, i) => {
                    const r = el.getBoundingClientRect();
                    out.push({
                        index: i,
                        text: (el.innerText || '').trim().slice(0, 300),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                });
                return out;
            }"""
        )

        print(f"\n=== Found {len(alerts)} alert rows ===")
        for a in alerts:
            print(f"  [{a['index']:2}] y={a['y']:4}  text: {a['text'][:120]!r}")

        # 5) Try TV's API with cookies from this session for richer data
        print("\n=== Trying TV pricealerts API with session cookies ===")
        api_results = {}
        candidates = [
            ("https://pricealerts.tradingview.com/list_alerts", "POST",
             '{"payload":{"limit":2000}}', "application/json"),
            ("https://www.tradingview.com/api/v1/alerts/", "GET", None, None),
        ]
        for url, method, body, ct in candidates:
            try:
                hdrs = {"Origin": "https://www.tradingview.com",
                        "Referer": "https://www.tradingview.com/chart/"}
                if ct:
                    hdrs["Content-Type"] = ct
                if method == "POST":
                    r = api.post(url, data=body, headers=hdrs, timeout=8000)
                else:
                    r = api.get(url, headers=hdrs, timeout=8000)
                txt = r.text()
                api_results[url] = {"status": r.status, "body": txt[:1500]}
                print(f"\n  {method} {url} -> {r.status}")
                print(f"    body[:300]: {txt[:300]!r}")
            except Exception as e:
                api_results[url] = {"error": str(e)}
                print(f"  {url} -> ERR {e}")

        # 6) Save inventory
        inventory = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "ui_alerts_count": len(alerts),
            "ui_alerts": alerts,
            "api_results": api_results,
        }
        INVENTORY_PATH.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
        print(f"\n=== Inventory saved: {INVENTORY_PATH} ===")

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
