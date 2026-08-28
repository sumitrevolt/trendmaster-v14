"""Step 2: After Alt+A, click 'App, Toasts, Email, Webhook' to expand notifications,
then dump the DOM again to find webhook-specific inputs."""
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
OUT_TXT = HERE / "dom_dump_step2.txt"

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

        print("Pressing Alt+A to open alert dialog...")
        page.keyboard.press("Alt+a")
        page.wait_for_timeout(4000)

        print("Clicking 'App, Toasts, Email, Webhook' button to expand notifications...")
        try:
            page.locator("button:has-text('Webhook')").first.click(timeout=5000)
            page.wait_for_timeout(2500)
        except Exception as e:
            print(f"Could not click notifications button: {e}")

        # Now extract all visible interactive elements + every input/textarea/checkbox
        elements = page.evaluate(
            """() => {
                const out = [];
                const sel = 'input, textarea, button, [role="checkbox"], [role="switch"], [role="tab"], select';
                document.querySelectorAll(sel).forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 && r.height === 0) return;
                    const attrs = {};
                    for (const a of el.attributes) attrs[a.name] = a.value.slice(0, 100);
                    out.push({
                        tag: el.tagName.toLowerCase(),
                        text: (el.innerText || el.value || el.placeholder || '').slice(0, 70),
                        attrs: attrs,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        checked: el.checked,
                    });
                });
                return out;
            }"""
        )

        lines = []
        for e in elements:
            attrs_kept = {k: v for k, v in e["attrs"].items() if k in (
                "name", "id", "class", "type", "placeholder", "aria-label", "data-name",
                "data-test", "role", "value")}
            attrs_str = " ".join(f"{k}={v!r}" for k, v in attrs_kept.items()) or "(no attrs)"
            txt = e["text"].replace("\n", " ").strip()
            chk = "  [CHECKED]" if e.get("checked") else ""
            lines.append(f"<{e['tag']:10}> [{e['x']:4},{e['y']:4} {e['w']:4}x{e['h']:3}]{chk} {txt[:60]:<60} | {attrs_str}")

        OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
        print(f"Wrote {len(elements)} elements: {OUT_TXT}")

        # Print the most likely webhook-related ones
        print("\n=== webhook / message / url candidates ===")
        for e in elements:
            blob = (
                (e["text"] or "").lower() + " " +
                " ".join(v.lower() for v in e["attrs"].values())
            )
            if "webhook" in blob or "message" in blob or "url" in blob:
                attrs_kept = {k: v for k, v in e["attrs"].items() if k in (
                    "name", "id", "class", "type", "placeholder", "aria-label", "data-name", "role")}
                attrs_str = " ".join(f"{k}={v!r}" for k, v in attrs_kept.items())
                txt = e["text"].replace("\n", " ").strip()
                print(f"  <{e['tag']}> {txt[:60]!r} | {attrs_str[:200]}")

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
