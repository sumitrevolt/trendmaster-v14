"""Inspect what alert CONDITIONS Rocket Prime exposes in TradingView's UI.

[2026-05-09] Rocket Prime is invite-only and uses Pine `alert()` calls. The
"Any alert() function call" condition causes TV to ignore our alert message
template — placeholders never substitute. To deliver direction info, we need
plot-crossing conditions (e.g., "plot 0 crossing up 0.5") on which TV WILL
substitute placeholders.

This script automates the discovery step from
docs/guides/ROCKET_PRIME_40_ALERT_SETUP.md:

  1. Launches headed Chrome with persistent _browser_profile cookies.
  2. Navigates to a TV chart.
  3. Adds Rocket Prime indicator (if not present).
  4. Clicks "Add alert" on the indicator.
  5. Reads the Condition dropdown options.
  6. Saves the list as docs/guides/rocket_prime_alert_conditions.txt.

Usage:
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\inspect_rocket_prime_conditions.py

Headed mode so the user can intervene if cookies are expired.
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
PROFILE = HERE / "_browser_profile"
OUT_TXT = HERE.parent.parent / "docs" / "guides" / "rocket_prime_alert_conditions.txt"
OUT_TXT.parent.mkdir(parents=True, exist_ok=True)

ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"
LOGIN_TIMEOUT_S = 480


def main():
    out_lines = []
    out_lines.append(f"=== Rocket Prime alert conditions inspection ===")
    out_lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    out_lines.append("")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--no-default-browser-check", "--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        try:
            page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            out_lines.append(f"goto warning: {e}")

        # Wait for chart layout to load
        time.sleep(8)

        # Check if logged in by looking for the user avatar / login button
        is_logged_in = False
        try:
            # The "Sign in" button only appears when logged out
            page.wait_for_selector("text=/Sign in/i", timeout=2000)
            is_logged_in = False
        except Exception:
            is_logged_in = True

        if not is_logged_in:
            out_lines.append("[!] Not logged in to TV. Please sign in within 8 min...")
            print(out_lines[-1], flush=True)
            deadline = time.time() + LOGIN_TIMEOUT_S
            while time.time() < deadline:
                try:
                    if page.locator("text=/Sign in/i").count() == 0:
                        is_logged_in = True
                        break
                except Exception:
                    pass
                time.sleep(3)

        out_lines.append(f"Logged in: {is_logged_in}")

        # Try to query the indicator's metadata via the tv-scripting endpoint
        # — this gives us the indicator's metainfo including plot definitions
        # which is what TV's alert UI uses to populate the condition dropdown.
        api = ctx.request
        try:
            # The metainfo endpoint
            url = f"https://pine-facade.tradingview.com/pine-facade/translate/Script@tv-scripting-101/1.0?pine_id={ROCKET_PRIME}&pine_version=1.0"
            r = api.get(url, timeout=10_000)
            if r.status == 200:
                txt = r.text()
                out_lines.append(f"\n=== /pine-facade/translate response (status={r.status}) ===")
                out_lines.append(txt[:8000])
            else:
                out_lines.append(f"\n[!] /pine-facade/translate returned {r.status}")
        except Exception as e:
            out_lines.append(f"\n[!] pine-facade query failed: {e}")

        # Also try the alert builder's discovery endpoint for available conditions
        try:
            # This is the endpoint TV's alert dialog uses to populate
            # available alert series / conditions for an indicator.
            # We try a few known endpoints.
            endpoints = [
                ("get_alert_series",
                 "https://pricealerts.tradingview.com/get_alert_series?pine_id=" + ROCKET_PRIME),
                ("metainfo",
                 f"https://pine-facade.tradingview.com/pine-facade/translate/{ROCKET_PRIME}/1.0"),
            ]
            for label, url in endpoints:
                try:
                    rr = api.get(url, timeout=8_000)
                    out_lines.append(f"\n=== {label} (status={rr.status}) ===")
                    out_lines.append(rr.text()[:4000])
                except Exception as e:
                    out_lines.append(f"\n[!] {label} failed: {e}")
        except Exception:
            pass

        # Try the inspection_target — open a chart with Rocket Prime, then
        # click "Add Alert" and read the DOM of the condition dropdown.
        try:
            # 1. Make sure Rocket Prime is on the chart by adding the indicator.
            # The shortcut to open Indicators panel is "/" or click the
            # "Indicators" toolbar button. Easiest: trigger the keyboard shortcut.
            page.keyboard.press("Slash")  # opens search overlay
            time.sleep(1)
            # If a search overlay opened, type indicator name to add
            page.keyboard.type("Rocket Prime")
            time.sleep(2)
            # Click first result if visible
            try:
                first_result = page.locator("[data-name='itemFromList']").first
                if first_result.count() > 0:
                    first_result.click()
                    time.sleep(2)
                    out_lines.append("\n[OK] Added Rocket Prime to chart (or it's already added)")
            except Exception as e:
                out_lines.append(f"\n[!] could not click first search result: {e}")
            # Close any overlay
            page.keyboard.press("Escape")
            time.sleep(1)

            # 2. Open Add Alert dialog (Alt+A keyboard shortcut)
            page.keyboard.press("Alt+A")
            time.sleep(3)

            # 3. Try to find the Condition dropdown and dump its options.
            # The dropdown is a button that opens a list. We can read the
            # accessibility tree via JS.
            condition_options = page.evaluate("""
                () => {
                    // Search for any element that looks like the alert
                    // condition dropdown options.
                    const out = {};
                    const all = document.querySelectorAll('*');
                    let found = [];
                    for (const el of all) {
                        const txt = (el.innerText || '').trim();
                        // Look for "Rocket Prime" mentions that are NOT the
                        // chart pane label
                        if (/rocket\\s*prime/i.test(txt) && txt.length < 200) {
                            const role = el.getAttribute('role') || '';
                            const name = el.getAttribute('data-name') || '';
                            found.push({
                                tag: el.tagName,
                                role: role,
                                name: name,
                                text: txt.slice(0, 200),
                            });
                        }
                    }
                    out.found = found.slice(0, 50);
                    // Also look for any open dropdown/menu
                    const menus = document.querySelectorAll('[role="menu"], [role="listbox"], [data-name*="menu"]');
                    out.menus = [];
                    for (const m of menus) {
                        out.menus.push({
                            role: m.getAttribute('role') || '',
                            data_name: m.getAttribute('data-name') || '',
                            text_preview: (m.innerText || '').slice(0, 1500),
                        });
                    }
                    return out;
                }
            """)
            out_lines.append("\n=== DOM inspection of alert dialog ===")
            out_lines.append(json.dumps(condition_options, indent=2)[:6000])

            # Take a screenshot
            shot_path = HERE.parent.parent / "docs" / "guides" / "rocket_prime_alert_dialog.png"
            page.screenshot(path=str(shot_path), full_page=True)
            out_lines.append(f"\nScreenshot saved: {shot_path}")
        except Exception as e:
            out_lines.append(f"\n[!] DOM inspection failed: {e}")

        # Keep browser open for 30s in case user wants to look
        time.sleep(30)
        ctx.close()

    OUT_TXT.write_text("\n".join(str(x) for x in out_lines), encoding="utf-8")
    print(f"\nReport written to {OUT_TXT}")
    print("\n--- Last 80 lines ---")
    for line in out_lines[-80:]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
