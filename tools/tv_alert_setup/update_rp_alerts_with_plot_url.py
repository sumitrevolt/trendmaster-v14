"""Update existing 20 Rocket Prime alerts via TV API to include plot
placeholders in the WEBHOOK URL field (not message body).

KEY INSIGHT (2026-05-10): TV substitutes {{plot_0}}..{{plot_19}} placeholders
in BOTH message body AND webhook URL. Pine alert() function override
hardcodes the BODY but does NOT touch the URL. Therefore putting plot
placeholders in URL bypasses the alert() override.

Once URL has &p0={{plot_0}}&p1={{plot_1}}..., bot's tv_webhook_receiver.py
extracts plot values from URL query → determines direction (p0 non-zero
= BUY, p1 non-zero = SELL).

This script does NOT delete+create alerts (which destroys creation timestamp
+ confuses TV's internal alert state). It uses the /modify_alert endpoint
to update only the web_hook field.

Run: .venv\\Scripts\\python.exe tools\\tv_alert_setup\\update_rp_alerts_with_plot_url.py
"""
from __future__ import annotations
import copy
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
ROOT = HERE.parent.parent
ENV_PATH = ROOT / "config" / ".env"
ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"
LOGIN_TIMEOUT_S = 480

SECRET = None
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("TV_WEBHOOK_SECRET"):
            SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

# Resolve current public tunnel URL — read from config/.env
PUBLIC_URL = "https://shadow-cosmos-unending.ngrok-free.dev"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("TV_PUBLIC_URL"):
            PUBLIC_URL = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

# Plot range — TV supports plot_0..plot_19. We use p0..p9 (sufficient for
# RP which has at most 10 plot outputs based on label structure).
PLOT_PLACEHOLDERS = "&p0={{plot_0}}&p1={{plot_1}}&p2={{plot_2}}&p3={{plot_3}}&p4={{plot_4}}&p5={{plot_5}}&p6={{plot_6}}&p7={{plot_7}}&p8={{plot_8}}&p9={{plot_9}}"


def build_webhook_url(symbol: str, tf: str) -> str:
    return (
        f"{PUBLIC_URL}/tv-signal?secret={SECRET}"
        f"&symbol={symbol}&tf={tf}"
        f"{PLOT_PLACEHOLDERS}"
    )


def wait_for_login(api, headers, timeout_s=LOGIN_TIMEOUT_S) -> bool:
    print(f">> Polling /list_alerts every 3s for up to {timeout_s}s...", flush=True)
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            r = api.post("https://pricealerts.tradingview.com/list_alerts",
                         data=json.dumps({"payload": {"limit": 5}}),
                         headers=headers, timeout=8000)
            if r.status != last:
                print(f"  [{int(time.time())}] /list_alerts -> HTTP {r.status}", flush=True)
                last = r.status
            if r.status == 200 and '"s":"ok"' in r.text():
                return True
        except Exception as e:
            print(f"  poll error: {e}", flush=True)
        time.sleep(3)
    return False


def main() -> int:
    if not SECRET:
        print("[X] TV_WEBHOOK_SECRET not in config/.env"); return 2

    print("=" * 70)
    print(f"update_rp_alerts_with_plot_url  -  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  public URL: {PUBLIC_URL}")
    print(f"  placeholders: p0..p9 (10 plot outputs)")
    print("=" * 70)

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
        except Exception:
            pass

        api = ctx.request

        json_hdrs = {"Origin": "https://www.tradingview.com",
                     "Referer": "https://www.tradingview.com/chart/",
                     "Content-Type": "application/json"}

        if not wait_for_login(api, json_hdrs):
            print("[X] login not detected"); ctx.close(); return 3

        # 1. List all RP alerts
        list_r = api.post("https://pricealerts.tradingview.com/list_alerts",
                          data=json.dumps({"payload": {"limit": 5000}}),
                          headers=json_hdrs, timeout=15_000)
        alerts = list_r.json().get("r", [])
        rp_alerts = [a for a in alerts
                     if (a.get("condition") or {}).get("type") == "pine_alert"
                     and ((a.get("condition") or {}).get("series") or [{}])[0].get("pine_id") == ROCKET_PRIME]
        print(f"\n>> Found {len(rp_alerts)} Rocket Prime alerts", flush=True)
        if not rp_alerts:
            print("[X] no RP alerts to update — run capture_and_create_40_alerts.py first")
            ctx.close(); return 4

        # 2. For each alert: extract symbol+tf, build new URL, update via API
        success = failed = 0
        for a in rp_alerts:
            sym_raw = a.get("symbol", "")
            try:
                sym_obj = json.loads(sym_raw[1:]) if sym_raw.startswith("=") else {}
                full_sym = sym_obj.get("symbol", "")
                # full_sym is like "BINANCE:BTCUSD" or "OANDA:USDJPY" — extract base
                base_sym = full_sym.split(":")[-1] if ":" in full_sym else full_sym
            except Exception:
                base_sym = sym_raw
            tf = str(a.get("resolution", ""))
            new_url = build_webhook_url(base_sym, tf)

            # Build modify_alert payload — copy alert + change web_hook only
            payload = copy.deepcopy(a)
            payload["web_hook"] = new_url
            payload["name"] = None
            for k in ("active", "complexity", "type", "kinds", "cross_interval",
                      "expiration_policy", "pro_symbol", "presentation_data",
                      "mutable_study_data", "create_time", "last_fire_time",
                      "last_fire_bar_time", "last_error", "last_stop_reason"):
                payload.pop(k, None)

            modify_hdrs = dict(json_hdrs)
            modify_hdrs["Content-Type"] = "text/plain;charset=UTF-8"

            try:
                rr = api.post("https://pricealerts.tradingview.com/modify_alert",
                              data=json.dumps({"payload": payload}),
                              headers=modify_hdrs, timeout=15_000)
                ok = rr.status == 200 and '"s":"ok"' in rr.text()
                if ok:
                    success += 1
                    print(f"  [OK]   {base_sym:<8} TF={tf:<3} aid={a['alert_id']}", flush=True)
                else:
                    failed += 1
                    print(f"  [FAIL] {base_sym:<8} TF={tf:<3} aid={a['alert_id']}: {rr.text()[:120]}", flush=True)
            except Exception as e:
                failed += 1
                print(f"  [ERR]  {base_sym:<8} TF={tf:<3}: {e}", flush=True)
            time.sleep(0.4)

        print(f"\n=== modified {success}, failed {failed} ===")

        # 3. Verify by re-listing and showing one webhook URL
        if success > 0:
            time.sleep(1)
            list_r = api.post("https://pricealerts.tradingview.com/list_alerts",
                              data=json.dumps({"payload": {"limit": 5000}}),
                              headers=json_hdrs, timeout=15_000)
            alerts2 = list_r.json().get("r", [])
            rp2 = [a for a in alerts2 if ((a.get("condition") or {}).get("series") or [{}])[0].get("pine_id") == ROCKET_PRIME]
            if rp2:
                wh = rp2[0].get("web_hook", "")
                print(f"\nSample updated webhook URL:")
                print(f"  {wh[:200]}...")
                if "plot_0" in wh or "p0=" in wh:
                    print("[OK] placeholder confirmed in URL")
                else:
                    print("[!] placeholder NOT in URL — modify may have silently failed")

        ctx.close()
        return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
