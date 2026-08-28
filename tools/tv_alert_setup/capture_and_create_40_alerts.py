"""Capture + auto-create 40 plot-crossing Rocket Prime alerts.

[2026-05-09 final solution] The architectural blocker:
  - Rocket Prime is invite-only Pine indicator using alert() function calls
  - TradingView ignores alert dialog message field for alert()-driven alerts
  - Result: bodies arrive as `#### {{ticker}} ####` with no direction
  - Fix: switch alert CONDITION from "Any alert() function call" to plot-crossing
    on the named "Buy Observation #1" / "Sell Observation #1" plots that
    Rocket Prime exposes
  - But TV's plot-crossing alert payload structure is undocumented —
    we MUST capture one manual alert payload to know what to send

This script automates the capture + creation flow:

  PHASE 1 (manual, you do it once each for BUY and SELL):
    - Script opens Chrome, navigates to TradingView
    - Browser network is intercepted to watch /create_alert POST
    - YOU manually create:
        Alert 1: Rocket Prime Engine → "Buy Observation #1" → Crossing Up → 0
                 Webhook URL ends with &direction=buy
        Alert 2: Rocket Prime Engine → "Sell Observation #1" → Crossing Up → 0
                 Webhook URL ends with &direction=sell
    - Script captures both POST payloads to:
        tools/tv_alert_setup/captured_buy_alert.json
        tools/tv_alert_setup/captured_sell_alert.json

  PHASE 2 (automatic):
    - Script reads both captured templates
    - Loops over 5 pairs × 4 TFs × 2 dirs = 40 combinations
    - For each: substitutes symbol/TF/webhook URL into the right template
    - POSTs to TV's create_alert endpoint
    - Verifies via list_alerts that all 40 exist
    - Reports any failures

Usage:
    .venv\\Scripts\\python.exe tools\\tv_alert_setup\\capture_and_create_40_alerts.py

Browser stays open for up to 15 min while you do PHASE 1. Then auto-creates.
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

from playwright.sync_api import sync_playwright

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

PHASE1_TIMEOUT_S = 15 * 60  # 15 min for both manual captures

SECRET = None
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("TV_WEBHOOK_SECRET"):
            SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
WEBHOOK_BASE = f"https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret={SECRET}"


def _ex(s):
    if s in ("BTCUSD", "ETHUSD"): return "BINANCE"
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


def print_phase1_instructions():
    print("\n" + "=" * 70)
    print("PHASE 1 — Manual capture (5 minutes)")
    print("=" * 70)
    print("""
A Chrome browser will open. Please do the following:

  STEP A — Create the BUY alert template
  --------------------------------------
  1. Make sure Rocket Prime is on the chart (any pair). If not, add it.
  2. Click the bell icon (Alert) in the top toolbar, OR press Alt+A
  3. In the alert dialog:
     - Condition: click "Price" → change to "Rocket Prime Engine"
     - In the second dropdown that appears: pick the BUY-related plot.
       Likely named "Buy Observation #1", "Buy", or similar.
     - Trigger: "Crossing Up"
     - Value: 0
     - Webhook URL (paste exactly):
""")
    print(f"       {WEBHOOK_BASE}&symbol=" + "{{ticker}}&tf={{interval}}&direction=buy")
    print("""     - Message: leave empty
     - Click "Create"

  STEP B — Create the SELL alert template
  ---------------------------------------
  Same as STEP A but:
     - Condition's second dropdown: pick the SELL-related plot
       (Likely "Sell Observation #1", "Sell", or similar)
     - Webhook URL (paste exactly):
""")
    print(f"       {WEBHOOK_BASE}&symbol=" + "{{ticker}}&tf={{interval}}&direction=sell")
    print("""     - Click "Create"

The script will detect both POSTs and proceed to PHASE 2 automatically.

You have 15 minutes. Take your time. If you make a mistake, delete the
bad alert in TV's alert panel and create it again.
""")
    print("=" * 70 + "\n", flush=True)


def main() -> int:
    if not SECRET:
        print("[X] TV_WEBHOOK_SECRET not set in config/.env"); return 2
    if not TOP_5_PATH.exists():
        print(f"[X] {TOP_5_PATH} missing"); return 2
    top_5 = json.loads(TOP_5_PATH.read_text(encoding="utf-8"))["top_5"]

    print("=" * 70)
    print(f"capture_and_create_40_alerts  -  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  pairs: {top_5}")
    print(f"  tfs:   {TARGET_TFS}")
    print(f"  webhook base: {WEBHOOK_BASE}")
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

        # Watch for create_alert POSTs and decide buy vs sell from URL
        def on_request(request):
            try:
                if "pricealerts.tradingview.com/create_alert" not in request.url:
                    return
                if request.method != "POST":
                    return
                body = request.post_data
                if not body:
                    return
                # Parse the captured payload to find direction in webhook URL
                try:
                    data = json.loads(body)
                    payload = data.get("payload", {})
                    web_hook = payload.get("web_hook", "")
                except Exception:
                    return

                if "direction=buy" in web_hook and captured["buy"] is None:
                    captured["buy"] = {"url": request.url, "headers": dict(request.headers),
                                       "body": body, "ts": int(time.time())}
                    CAPTURED_BUY.write_text(json.dumps(captured["buy"], indent=2), encoding="utf-8")
                    print(f"\n  [OK] BUY template captured → {CAPTURED_BUY}", flush=True)
                elif "direction=sell" in web_hook and captured["sell"] is None:
                    captured["sell"] = {"url": request.url, "headers": dict(request.headers),
                                        "body": body, "ts": int(time.time())}
                    CAPTURED_SELL.write_text(json.dumps(captured["sell"], indent=2), encoding="utf-8")
                    print(f"\n  [OK] SELL template captured → {CAPTURED_SELL}", flush=True)
            except Exception as e:
                print(f"  [warn] request handler error: {e}", flush=True)

        page.on("request", on_request)

        try:
            page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            pass

        print_phase1_instructions()

        deadline = time.time() + PHASE1_TIMEOUT_S
        last_msg = 0
        while time.time() < deadline:
            if captured["buy"] and captured["sell"]:
                break
            if time.time() - last_msg > 60:
                got = []
                if captured["buy"]: got.append("BUY")
                if captured["sell"]: got.append("SELL")
                missing = [x for x in ("BUY", "SELL") if x not in got]
                print(f"  [..] waiting for {missing}; got {got}; remaining {int(deadline - time.time())}s",
                      flush=True)
                last_msg = time.time()
            time.sleep(2)

        if not (captured["buy"] and captured["sell"]):
            print(f"\n[X] PHASE 1 TIMEOUT. Got: buy={bool(captured['buy'])}  sell={bool(captured['sell'])}")
            print(f"   You can re-run this script — captures persist in {HERE}/")
            ctx.close(); return 3

        print("\n" + "=" * 70)
        print("PHASE 2 — auto-creating 38 remaining alerts")
        print("=" * 70)

        # Reuse api context for create POSTs
        api = ctx.request

        # Parse captured buy + sell template payloads
        buy_payload = json.loads(captured["buy"]["body"])["payload"]
        sell_payload = json.loads(captured["sell"]["body"])["payload"]
        # The captured payloads also include the headers needed
        buy_hdrs = {k: v for k, v in captured["buy"]["headers"].items()
                    if k.lower() not in ("host", "content-length", "cookie", "connection",
                                          "accept-encoding")}
        buy_hdrs["Origin"] = "https://www.tradingview.com"
        buy_hdrs["Referer"] = "https://www.tradingview.com/"
        buy_hdrs["Content-Type"] = "text/plain;charset=UTF-8"

        # Step 1: delete all existing Rocket Prime alerts
        list_r = api.post("https://pricealerts.tradingview.com/list_alerts",
                          data=json.dumps({"payload": {"limit": 5000}}),
                          headers={"Origin": "https://www.tradingview.com",
                                    "Referer": "https://www.tradingview.com/chart/",
                                    "Content-Type": "application/json"},
                          timeout=15_000)
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
                         headers={"Origin": "https://www.tradingview.com",
                                   "Referer": "https://www.tradingview.com/chart/",
                                   "Content-Type": "application/json"},
                         timeout=15_000)
            print(f"  [OK] deleted {len(existing_rp_ids)} existing Rocket Prime alerts")

        # Step 2: create 40 new alerts
        success = failed = 0
        captured_url = captured["buy"]["url"]  # same endpoint for both
        for sym in top_5:
            ex, bs, cur = _ex(sym), _bs(sym), _cur(sym)
            for tf in TARGET_TFS:
                for direction, base_payload in (("buy", buy_payload), ("sell", sell_payload)):
                    payload = copy.deepcopy(base_payload)
                    payload["symbol"] = _build_symbol_field(ex, bs, cur)
                    payload["resolution"] = tf
                    payload["expiration"] = (datetime.now(timezone.utc) + timedelta(days=30)).strftime(
                        "%Y-%m-%dT%H:%M:%S.000Z")
                    # Update conditions[0].resolution if present
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

        print(f"\n=== created {success}, failed {failed} ===")
        if success >= 38 and failed == 0:
            print("\n[OK] all 40 alerts active. The bot will now trade on actual Rocket Prime signals.")
            print("    Watch:  powershell -Command \"Get-Content logs\\tv_webhook.log -Tail 5 -Wait\"")
            print("    Expect: 'URL-DIRECTION BUY for <SYM> tf=<N>' lines on next signal.")
        ctx.close()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
