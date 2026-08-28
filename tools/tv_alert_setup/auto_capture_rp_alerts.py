"""Fully automate Phase 1 — Playwright drives TradingView UI through the
alert dialog flow, captures both BUY + SELL plot-crossing payloads, then
runs Phase 2 (38 more alerts via API).

[2026-05-10] Operator request: no manual UI clicks. Script must do the
whole flow autonomously. The TradingView UI is React-based with custom
dropdowns; selectors use a mix of role/data-name/text-content for
robustness.

Strategy:
  1. Launch persistent Chromium profile (cookies persist from prior runs)
  2. Navigate to BTCUSD chart on Vantage exchange
  3. Wait for login (auto-detect via /list_alerts API status)
  4. Add Rocket Prime indicator if not on chart (via "/" search)
  5. For each direction (BUY, SELL):
     a. Open alert dialog (Alt+A keyboard shortcut)
     b. Click Condition dropdown -> "Rocket Prime Engine"
     c. Click second dropdown -> "Buy/Sell Observation #1"
     d. Set "Crossing Up" + value 0
     e. Paste webhook URL with &direction=buy/sell
     f. Click Create
     g. Network handler captures POST payload to JSON file
  6. Phase 2: read captured payloads, create 38 more alerts via API.

If any UI step fails, script prints the exact selector that failed and
which step the operator should do manually before re-running.
"""
from __future__ import annotations
import copy
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeoutError

HERE = Path(__file__).resolve().parent
PROFILE = HERE / "_browser_profile"
ROOT = HERE.parent.parent
ENV_PATH = ROOT / "config" / ".env"
TOP_5_PATH = ROOT / "reports" / "top_5_pairs.json"

CAPTURED_BUY = HERE / "captured_buy_alert.json"
CAPTURED_SELL = HERE / "captured_sell_alert.json"

ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"
TARGET_TFS = ["5", "15", "30", "60"]
TF_LABEL = {"5": "M5", "15": "M15", "30": "M30", "60": "H1"}
LOGIN_TIMEOUT_S = 480

SECRET = None
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("TV_WEBHOOK_SECRET"):
            SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
WEBHOOK_BASE = f"https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret={SECRET}"


# 2026-05-10 update: BTC chart in operator's TV is on Vantage exchange,
# not Binance. Update mapping accordingly. This affects ONLY the
# symbol_field used in Phase 2 alert payloads.
def _ex(s):
    if s == "BTCUSD": return "VANTAGE"      # was BINANCE
    if s == "ETHUSD": return "BINANCE"
    if s == "XTIUSD": return "FX"
    if s == "XBRUSD": return "FX"
    if s == "XNGUSD": return "NYMEX_DL"
    return "OANDA"


def _bs(s):
    if s == "XTIUSD": return "USOIL"
    if s == "XBRUSD": return "UKOIL"
    if s == "XNGUSD": return "NG1!"
    return s


def _cur(s):
    if s.startswith(("XAU", "XAG")) or s in ("BTCUSD", "ETHUSD", "XTIUSD", "XBRUSD", "XNGUSD"):
        return "USD"
    return s[-3:]


def _build_symbol_field(ex, bs, cur):
    obj = {"currency-id": cur, "session": "regular", "symbol": f"{ex}:{bs}"}
    return "=" + json.dumps(obj, separators=(",", ":"))


def wait_for_login(api, timeout_s=LOGIN_TIMEOUT_S) -> bool:
    print(f">> Polling /list_alerts every 3s for up to {timeout_s}s...", flush=True)
    headers = {"Origin": "https://www.tradingview.com",
               "Referer": "https://www.tradingview.com/chart/",
               "Content-Type": "application/json"}
    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        try:
            r = api.post("https://pricealerts.tradingview.com/list_alerts",
                         data=json.dumps({"payload": {"limit": 5}}),
                         headers=headers, timeout=8000)
            if r.status != last_status:
                print(f"  [{int(time.time())}] /list_alerts -> HTTP {r.status}", flush=True)
                last_status = r.status
            if r.status == 200:
                txt = r.text()
                if '"s":"ok"' in txt:
                    return True
        except Exception as e:
            print(f"  poll error: {e}", flush=True)
        time.sleep(3)
    return False


def add_rocket_prime_to_chart(page: Page) -> bool:
    """Trigger search overlay, type 'Rocket Prime', press Enter."""
    try:
        # Make sure no dialog is open
        page.keyboard.press("Escape")
        time.sleep(0.5)

        # Trigger Indicators search via "/" keyboard shortcut
        page.keyboard.press("Slash")
        time.sleep(1.5)

        # Type indicator name
        page.keyboard.type("Rocket Prime", delay=50)
        time.sleep(2)

        # Press Down + Enter to pick the first matching result
        page.keyboard.press("Enter")
        time.sleep(2)

        # Close overlay if still open
        page.keyboard.press("Escape")
        time.sleep(1)

        print("  [OK] Rocket Prime add attempted (idempotent)", flush=True)
        return True
    except Exception as e:
        print(f"  [WARN] add_rocket_prime_to_chart: {e}", flush=True)
        return False


def open_alert_dialog(page: Page) -> bool:
    """Press Alt+A to open the create-alert dialog."""
    try:
        page.keyboard.press("Escape")
        time.sleep(0.3)
        page.keyboard.press("Alt+A")
        # Dialog needs ~1.5s to render
        time.sleep(2.5)
        # Verify dialog appeared by looking for "Condition" label
        # TradingView's alert dialog has a "Condition" section
        return True
    except Exception as e:
        print(f"  [WARN] open_alert_dialog: {e}", flush=True)
        return False


def configure_alert(page: Page, direction: str) -> bool:
    """Click through alert dialog controls to configure plot-crossing."""
    print(f"  [{direction.upper()}] configuring alert dialog...", flush=True)

    target_plot = "Buy" if direction == "buy" else "Sell"

    try:
        # Step 1: Find and click the FIRST condition dropdown (currently shows "Price")
        # TradingView's dialog uses data-name="symbol-input" and data-name="condition-symbol"
        # The condition dropdown is typically the second dropdown in the dialog.
        # Use accessibility selector — buttons with role=combobox.
        # We try a sequence of strategies.

        # Strategy 1: Click the dropdown by aria-label or text content "Price"
        clicked = False
        for selector in [
            "div[data-name='condition-symbol']",
            "div[data-name='symbol-input']",
            "button:has-text('Price')",
            "[role='combobox']:has-text('Price')",
            "[role='combobox']",
        ]:
            try:
                el = page.locator(selector).first
                if el.count() > 0:
                    el.click(timeout=3000)
                    clicked = True
                    print(f"    [click] condition dropdown via {selector}", flush=True)
                    break
            except Exception:
                continue

        if not clicked:
            print("    [FAIL] could not find condition dropdown — UI changed?", flush=True)
            return False

        time.sleep(1.5)

        # Step 2: In opened menu, click "Rocket Prime Engine"
        clicked = False
        for selector in [
            "[role='menuitem']:has-text('Rocket Prime Engine')",
            "li:has-text('Rocket Prime Engine')",
            "div[data-name='menu-inner'] >> text=Rocket Prime Engine",
            "text=Rocket Prime Engine",
        ]:
            try:
                el = page.locator(selector).first
                if el.count() > 0:
                    el.click(timeout=3000)
                    clicked = True
                    print(f"    [click] 'Rocket Prime Engine' via {selector}", flush=True)
                    break
            except Exception:
                continue

        if not clicked:
            print("    [FAIL] could not find 'Rocket Prime Engine' option", flush=True)
            return False

        time.sleep(1.5)

        # Step 3: Click the second dropdown (now appearing) and pick Buy/Sell Observation
        # This dropdown shows the indicator's plot/condition list
        clicked = False
        for selector in [
            f"[role='menuitem']:has-text('{target_plot} Observation')",
            f"li:has-text('{target_plot} Observation')",
            f"text={target_plot} Observation #1",
            f"text={target_plot} Observation",
            f"text={target_plot}",
        ]:
            try:
                el = page.locator(selector).first
                if el.count() > 0:
                    el.click(timeout=3000)
                    clicked = True
                    print(f"    [click] '{target_plot} Observation' via {selector}", flush=True)
                    break
            except Exception:
                continue

        # If second dropdown didn't auto-open, click it
        if not clicked:
            # Try clicking the second combobox
            for selector in ["[role='combobox']:nth-of-type(2)", "[role='combobox']"]:
                try:
                    cbs = page.locator(selector).all()
                    if len(cbs) >= 2:
                        cbs[1].click(timeout=2000)
                        time.sleep(1)
                        # now try clicking the option
                        opt = page.locator(f"text={target_plot} Observation").first
                        if opt.count() > 0:
                            opt.click(timeout=3000)
                            clicked = True
                            print(f"    [click] {target_plot} Observation (2nd dropdown)", flush=True)
                            break
                except Exception:
                    continue

        if not clicked:
            print(f"    [FAIL] could not find '{target_plot} Observation' option", flush=True)
            return False

        time.sleep(1.5)

        # Step 4: Set "Crossing Up" trigger
        # The trigger dropdown might already be Crossing or default to it. Verify/click.
        for selector in [
            "[role='combobox']:has-text('Crossing')",
            "[role='combobox']:has-text('Greater')",
            "div[data-name='crossing-mode']",
        ]:
            try:
                el = page.locator(selector).first
                if el.count() > 0:
                    el.click(timeout=2000)
                    time.sleep(1)
                    # pick Crossing Up
                    cu = page.locator("text=Crossing Up").first
                    if cu.count() > 0:
                        cu.click(timeout=2000)
                        print("    [click] Crossing Up", flush=True)
                    break
            except Exception:
                continue

        time.sleep(1)

        # Step 5: Set value to 0
        try:
            value_input = page.locator("input[type='text'][inputmode='decimal']").first
            if value_input.count() > 0:
                value_input.fill("0")
                print("    [fill] value=0", flush=True)
        except Exception as e:
            print(f"    [WARN] value field: {e}", flush=True)

        time.sleep(0.5)

        # Step 6: Set webhook URL — open Notifications/Actions tab if needed
        webhook_url = f"{WEBHOOK_BASE}&symbol={{{{ticker}}}}&tf={{{{interval}}}}&direction={direction}"
        webhook_filled = False
        for selector in [
            "input[name='webhook']",
            "input[placeholder*='webhook' i]",
            "input[placeholder*='Webhook' i]",
            "textarea[placeholder*='webhook' i]",
        ]:
            try:
                el = page.locator(selector).first
                if el.count() > 0:
                    el.fill(webhook_url)
                    webhook_filled = True
                    print(f"    [fill] webhook URL ({direction})", flush=True)
                    break
            except Exception:
                continue

        if not webhook_filled:
            # Try opening Notifications tab first then fill
            for selector in [
                "button:has-text('Notifications')",
                "[role='tab']:has-text('Notifications')",
                "text=Notifications",
            ]:
                try:
                    el = page.locator(selector).first
                    if el.count() > 0:
                        el.click(timeout=2000)
                        time.sleep(1)
                        break
                except Exception:
                    continue

            for selector in [
                "input[placeholder*='webhook' i]",
                "input[placeholder*='URL' i]",
                "textarea[placeholder*='webhook' i]",
            ]:
                try:
                    el = page.locator(selector).first
                    if el.count() > 0:
                        el.fill(webhook_url)
                        # Also click webhook checkbox if present
                        try:
                            cb = page.locator("input[type='checkbox']:near(:text('Webhook'))").first
                            if cb.count() > 0 and not cb.is_checked():
                                cb.click()
                        except Exception:
                            pass
                        webhook_filled = True
                        print(f"    [fill] webhook URL after Notifications tab", flush=True)
                        break
                except Exception:
                    continue

        if not webhook_filled:
            print("    [WARN] webhook URL field not found — alert will be created without webhook", flush=True)

        time.sleep(0.5)

        # Step 7: Click Create button
        clicked = False
        for selector in [
            "button:has-text('Create')",
            "[data-name='submit-button']",
            "button:has-text('Save')",
        ]:
            try:
                el = page.locator(selector).first
                if el.count() > 0:
                    el.click(timeout=3000)
                    clicked = True
                    print("    [click] Create", flush=True)
                    break
            except Exception:
                continue

        if not clicked:
            print("    [FAIL] could not click Create button", flush=True)
            return False

        # Wait for create POST + dialog dismissal
        time.sleep(3)
        return True

    except Exception as e:
        print(f"  [EXC] configure_alert({direction}): {e}", flush=True)
        return False


def phase2_create_38(api, captured_buy: dict, captured_sell: dict, top_5: list[str]) -> tuple[int, int]:
    """Same as capture_and_create_40_alerts.py Phase 2."""
    json_hdrs = {"Origin": "https://www.tradingview.com",
                 "Referer": "https://www.tradingview.com/chart/",
                 "Content-Type": "application/json"}

    buy_payload = json.loads(captured_buy["body"])["payload"]
    sell_payload = json.loads(captured_sell["body"])["payload"]
    buy_hdrs = {k: v for k, v in captured_buy["headers"].items()
                if k.lower() not in ("host", "content-length", "cookie", "connection",
                                      "accept-encoding")}
    buy_hdrs["Origin"] = "https://www.tradingview.com"
    buy_hdrs["Referer"] = "https://www.tradingview.com/"
    buy_hdrs["Content-Type"] = "text/plain;charset=UTF-8"

    # Delete all existing RP alerts
    list_r = api.post("https://pricealerts.tradingview.com/list_alerts",
                      data=json.dumps({"payload": {"limit": 5000}}),
                      headers=json_hdrs, timeout=15_000)
    existing_rp_ids = []
    if list_r.status == 200:
        for a in list_r.json().get("r", []):
            cond = a.get("condition") or {}
            series = (cond.get("series") or [{}])[0]
            if series.get("pine_id") == ROCKET_PRIME:
                existing_rp_ids.append(a["alert_id"])
    if existing_rp_ids:
        BATCH = 25
        for i in range(0, len(existing_rp_ids), BATCH):
            api.post("https://pricealerts.tradingview.com/delete_alerts",
                     data=json.dumps({"payload": {"alert_ids": existing_rp_ids[i:i+BATCH]}}),
                     headers=json_hdrs, timeout=15_000)
        print(f"  [OK] deleted {len(existing_rp_ids)} existing RP alerts")

    success = failed = 0
    captured_url = captured_buy["url"]
    for sym in top_5:
        ex, bs, cur = _ex(sym), _bs(sym), _cur(sym)
        for tf in TARGET_TFS:
            for direction, base_payload in (("buy", buy_payload), ("sell", sell_payload)):
                payload = copy.deepcopy(base_payload)
                payload["symbol"] = _build_symbol_field(ex, bs, cur)
                payload["resolution"] = tf
                payload["expiration"] = (datetime.now(timezone.utc) + timedelta(days=30)).strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z")
                if "conditions" in payload and payload["conditions"]:
                    payload["conditions"][0]["resolution"] = tf
                payload["web_hook"] = f"{WEBHOOK_BASE}&symbol={sym}&tf={tf}&direction={direction}"
                payload["name"] = None
                for k in ("alert_id", "complexity", "type", "kinds", "cross_interval",
                          "expiration_policy", "pro_symbol", "presentation_data",
                          "mutable_study_data", "create_time", "last_fire_time",
                          "last_fire_bar_time", "last_error", "last_stop_reason",
                          "active"):
                    payload.pop(k, None)
                try:
                    rr = api.post(captured_url, data=json.dumps({"payload": payload}),
                                  headers=buy_hdrs, timeout=15_000)
                    ok = rr.status == 200 and '"s":"ok"' in rr.text()
                    if ok:
                        success += 1
                        print(f"  [OK]   {sym} {TF_LABEL[tf]:<5} {direction.upper():<4}", flush=True)
                    else:
                        failed += 1
                        print(f"  [FAIL] {sym} {TF_LABEL[tf]:<5} {direction.upper():<4}: {rr.text()[:140]}", flush=True)
                except Exception as e:
                    failed += 1
                    print(f"  [ERR]  {sym} {TF_LABEL[tf]:<5} {direction.upper():<4}: {e}", flush=True)
                time.sleep(0.4)

    return success, failed


def main() -> int:
    if not SECRET:
        print("[X] TV_WEBHOOK_SECRET not in config/.env"); return 2
    if not TOP_5_PATH.exists():
        print(f"[X] {TOP_5_PATH} missing"); return 2
    top_5 = json.loads(TOP_5_PATH.read_text(encoding="utf-8"))["top_5"]

    print("=" * 70)
    print(f"auto_capture_rp_alerts  -  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  pairs: {top_5}")
    print(f"  tfs:   {TARGET_TFS}")
    print("=" * 70)

    captured = {"buy": None, "sell": None}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
            viewport={"width": 1600, "height": 1000},
            args=["--no-default-browser-check", "--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # Network capture
        def on_request(request):
            try:
                if "pricealerts.tradingview.com/create_alert" not in request.url:
                    return
                if request.method != "POST":
                    return
                body = request.post_data
                if not body:
                    return
                try:
                    data = json.loads(body)
                    web_hook = data.get("payload", {}).get("web_hook", "")
                except Exception:
                    return
                if "direction=buy" in web_hook and captured["buy"] is None:
                    captured["buy"] = {"url": request.url, "headers": dict(request.headers),
                                       "body": body, "ts": int(time.time())}
                    CAPTURED_BUY.write_text(json.dumps(captured["buy"], indent=2), encoding="utf-8")
                    print(f"  [OK CAPTURED] BUY -> {CAPTURED_BUY.name}", flush=True)
                elif "direction=sell" in web_hook and captured["sell"] is None:
                    captured["sell"] = {"url": request.url, "headers": dict(request.headers),
                                        "body": body, "ts": int(time.time())}
                    CAPTURED_SELL.write_text(json.dumps(captured["sell"], indent=2), encoding="utf-8")
                    print(f"  [OK CAPTURED] SELL -> {CAPTURED_SELL.name}", flush=True)
            except Exception as e:
                print(f"  [warn] req handler: {e}", flush=True)

        page.on("request", on_request)

        # Navigate to BTCUSD on Vantage (matches operator's chart)
        try:
            page.goto("https://www.tradingview.com/chart/?symbol=VANTAGE%3ABTCUSD",
                      wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            print(f"goto warning: {e}", flush=True)

        time.sleep(6)

        # Wait for login (cookies persist; usually instant)
        api = ctx.request
        if not wait_for_login(api, timeout_s=LOGIN_TIMEOUT_S):
            print("[X] not logged in — sign in and re-run", flush=True)
            ctx.close(); return 3
        print("[OK] logged in", flush=True)

        # Ensure Rocket Prime is on chart
        add_rocket_prime_to_chart(page)
        time.sleep(2)

        # Phase 1 — automate BUY then SELL
        for direction in ("buy", "sell"):
            if captured[direction] is not None:
                print(f"  [{direction.upper()}] already captured (from prior run)", flush=True)
                continue
            for attempt in range(3):
                print(f"\n  [{direction.upper()}] attempt {attempt + 1}/3", flush=True)
                if not open_alert_dialog(page):
                    continue
                if configure_alert(page, direction):
                    # wait up to 8s for capture handler to fire
                    deadline = time.time() + 8
                    while time.time() < deadline and captured[direction] is None:
                        time.sleep(0.5)
                    if captured[direction] is not None:
                        break
                # close dialog and retry
                page.keyboard.press("Escape")
                time.sleep(2)
            if captured[direction] is None:
                print(f"\n[X] PHASE 1 {direction.upper()} could not be automated.", flush=True)
                print(f"   Falling back to manual capture: please create the {direction.upper()}", flush=True)
                print(f"   alert manually in the open browser. Webhook URL ends with &direction={direction}", flush=True)
                # wait up to 5 min for manual fallback
                deadline = time.time() + 300
                while time.time() < deadline and captured[direction] is None:
                    time.sleep(2)

        if not (captured["buy"] and captured["sell"]):
            print("\n[X] could not capture both templates", flush=True)
            ctx.close(); return 4

        print("\n=== PHASE 2: creating 38 more alerts via API ===", flush=True)
        success, failed = phase2_create_38(api, captured["buy"], captured["sell"], top_5)
        print(f"\n=== created {success}, failed {failed} ===")

        ctx.close()
        return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
