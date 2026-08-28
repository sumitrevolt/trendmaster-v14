"""Expanded inspection of Rocket Prime alert conditions.

[2026-05-09 v2] The v1 script captured the alert dialog but didn't click
the Condition dropdown to enumerate options. This v2 does that.

Steps:
  1. Launch headed Chrome with persistent profile.
  2. Navigate to TradingView chart with Rocket Prime visible.
  3. Open Add Alert dialog (right-click on Rocket Prime indicator title
     in left status bar → "Add alert on Rocket Prime Engine").
  4. Click the Condition dropdown.
  5. Wait for expanded options.
  6. Capture every visible option's text.
  7. Click on each "Rocket Prime" sub-item to see its expanded children.
  8. Take screenshots at each step.
  9. Save everything to docs/guides/rocket_prime_dropdown_v2.txt + .png

Output files (in docs/guides/):
  - rocket_prime_v2_dialog.png         (alert dialog freshly opened)
  - rocket_prime_v2_condition_open.png (condition dropdown expanded)
  - rocket_prime_v2_options.json       (parsed list of every option seen)
  - rocket_prime_v2_report.txt         (human-readable summary)
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
OUT_DIR = HERE.parent.parent / "docs" / "guides"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    report = ["=== Rocket Prime expanded dropdown inspection ===",
              f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
            viewport={"width": 1600, "height": 1000},
            args=["--no-default-browser-check", "--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        try:
            page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            report.append(f"goto warning: {e}")

        time.sleep(8)
        page.bring_to_front()

        # Helper: click in chart area to make sure focus is on chart
        try:
            page.locator(".chart-container").first.click(position={"x": 800, "y": 400})
            time.sleep(1)
        except Exception:
            pass

        # 1. Open the Add Alert dialog via Alt+A
        page.keyboard.press("Alt+A")
        time.sleep(3)

        screenshot1 = OUT_DIR / "rocket_prime_v2_dialog.png"
        page.screenshot(path=str(screenshot1), full_page=False)
        report.append(f"[1] Alert dialog screenshot: {screenshot1}")

        # 2. Find the Condition dropdown. In TV's Add Alert dialog the
        # Condition row has a button labeled with the current condition
        # (default "Price"). Click it to expand.
        # The dropdown is typically a div role="combobox" or button.
        # We use a JS find approach since TV's classes are obfuscated.
        condition_btn = page.evaluate("""
            () => {
                // Find the Add Alert dialog
                const dialogs = document.querySelectorAll('[data-name="alerts-create-edit-dialog"], [role="dialog"]');
                let dialog = null;
                for (const d of dialogs) {
                    if (d.innerText && /create alert/i.test(d.innerText)) { dialog = d; break; }
                }
                if (!dialog) return {error: "no alert dialog found", n_dialogs: dialogs.length};

                // Find the Condition row — it's a button or combobox inside the dialog
                // Look for a button that contains "Price" or any condition text
                const buttons = dialog.querySelectorAll('button, [role="combobox"], [role="button"]');
                let cond_btn = null;
                for (const b of buttons) {
                    const t = (b.innerText || '').trim();
                    if (t === 'Price' || t === 'Rocket Prime Engine' || /\\bcondition\\b/i.test(t)) {
                        cond_btn = b;
                        break;
                    }
                }
                if (!cond_btn) {
                    // Get all interactive elements with their text for debugging
                    const all = [];
                    for (const b of buttons) {
                        const t = (b.innerText || '').trim();
                        if (t && t.length < 80) all.push({tag: b.tagName, role: b.getAttribute('role'), text: t});
                    }
                    return {error: "no condition button found", interactive: all.slice(0, 30)};
                }

                // Get its bounding rect for clicking
                const r = cond_btn.getBoundingClientRect();
                return {
                    found: true,
                    text: (cond_btn.innerText || '').trim(),
                    x: r.left + r.width/2,
                    y: r.top + r.height/2,
                };
            }
        """)
        report.append(f"\n[2] condition button query: {json.dumps(condition_btn)[:500]}")

        if condition_btn.get("found"):
            # Click it via mouse
            page.mouse.click(condition_btn["x"], condition_btn["y"])
            time.sleep(2)
            screenshot2 = OUT_DIR / "rocket_prime_v2_condition_open.png"
            page.screenshot(path=str(screenshot2), full_page=False)
            report.append(f"[3] Condition dropdown opened screenshot: {screenshot2}")

            # Capture all visible text in any popup/menu/listbox
            options_html = page.evaluate("""
                () => {
                    // After clicking the Condition button, a popup appears.
                    // Find all popups/listboxes that just rendered.
                    const popups = document.querySelectorAll(
                        '[role="listbox"], [role="menu"], [data-name*="menu"], [class*="dropdown"], [class*="popup"]'
                    );
                    const out = [];
                    for (const p of popups) {
                        const visible = p.offsetParent !== null;
                        if (!visible) continue;
                        const r = p.getBoundingClientRect();
                        if (r.width < 50) continue;
                        out.push({
                            tag: p.tagName,
                            role: p.getAttribute('role') || '',
                            data_name: p.getAttribute('data-name') || '',
                            class_preview: (p.className || '').toString().slice(0, 100),
                            text: (p.innerText || '').slice(0, 4000),
                            n_children: p.children.length,
                            x: r.x, y: r.y, w: r.width, h: r.height,
                        });
                    }
                    return out;
                }
            """)
            report.append(f"\n[4] visible popups (n={len(options_html)}):")
            for popup in options_html:
                report.append(f"  --- popup tag={popup['tag']} role={popup['role']} data_name={popup['data_name']!r} ---")
                report.append(f"      class={popup['class_preview']}")
                report.append(f"      n_children={popup['n_children']}")
                report.append(f"      text:")
                for line in popup["text"].splitlines():
                    if line.strip():
                        report.append(f"        > {line.strip()[:120]}")

            # If we see a Rocket Prime entry, click it to expand its sub-options
            try:
                rp_click = page.evaluate("""
                    () => {
                        // Find clickable elements containing "Rocket Prime"
                        const all = document.querySelectorAll('[role="option"], li, button, div');
                        for (const el of all) {
                            const t = (el.innerText || '').trim();
                            if (/rocket\\s*prime/i.test(t) && t.length < 100) {
                                const r = el.getBoundingClientRect();
                                if (r.width > 20 && el.offsetParent !== null) {
                                    return {found: true, text: t, x: r.left + r.width/2, y: r.top + r.height/2};
                                }
                            }
                        }
                        return {found: false};
                    }
                """)
                if rp_click.get("found"):
                    report.append(f"\n[5] Found Rocket Prime entry: {rp_click['text']!r} — clicking...")
                    page.mouse.click(rp_click["x"], rp_click["y"])
                    time.sleep(2)
                    screenshot3 = OUT_DIR / "rocket_prime_v2_after_select.png"
                    page.screenshot(path=str(screenshot3), full_page=False)
                    report.append(f"[6] After Rocket Prime selected: {screenshot3}")

                    # Now look for a second dropdown that exposes plots/conditions
                    second_options = page.evaluate("""
                        () => {
                            const popups = document.querySelectorAll(
                                '[role="listbox"], [role="menu"], [data-name*="menu"]'
                            );
                            const out = [];
                            for (const p of popups) {
                                if (p.offsetParent === null) continue;
                                const r = p.getBoundingClientRect();
                                if (r.width < 50) continue;
                                const items = [];
                                p.querySelectorAll('[role="option"], li, button').forEach(it => {
                                    const t = (it.innerText || '').trim();
                                    if (t && t.length < 100) items.push(t);
                                });
                                out.push({
                                    role: p.getAttribute('role') || '',
                                    full_text: (p.innerText || '').slice(0, 3000),
                                    items: items,
                                });
                            }
                            return out;
                        }
                    """)
                    report.append(f"\n[7] Second-level options after Rocket Prime click:")
                    for s in second_options:
                        report.append(f"  --- popup role={s['role']} ---")
                        for it in s["items"]:
                            report.append(f"      • {it}")
                        if not s["items"] and s["full_text"]:
                            report.append("      (no role=option items, full text dump:)")
                            for line in s["full_text"].splitlines():
                                if line.strip():
                                    report.append(f"        > {line.strip()[:120]}")
                else:
                    report.append("\n[5] No 'Rocket Prime' clickable found in expanded dropdown")
            except Exception as e:
                report.append(f"\n[5] Rocket Prime sub-click failed: {e}")
        else:
            report.append("\n[!] Condition button not found — alert dialog may not have opened")
            # Dump everything we see in the page that's clickable
            report.append("\n[debug] Top-level interactive elements visible:")
            interactive = page.evaluate("""
                () => {
                    const out = [];
                    document.querySelectorAll('button, [role="button"], [role="combobox"]').forEach(b => {
                        if (b.offsetParent !== null) {
                            const t = (b.innerText || '').trim();
                            if (t && t.length < 80) out.push(t);
                        }
                    });
                    return out.slice(0, 50);
                }
            """)
            for t in interactive:
                report.append(f"  • {t}")

        # Final pause for user to look at the browser
        report.append("\n[final] Browser will close in 20s...")
        time.sleep(20)
        ctx.close()

    out_txt = OUT_DIR / "rocket_prime_v2_report.txt"
    out_txt.write_text("\n".join(str(x) for x in report), encoding="utf-8")
    print(f"\nReport saved: {out_txt}")
    print("\n--- Last 100 lines ---")
    for line in report[-100:]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
