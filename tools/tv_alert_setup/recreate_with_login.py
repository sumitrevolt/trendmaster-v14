"""All-in-one: open browser headed, wait for TV login, then delete+recreate
all Rocket Prime alerts with proper plot-direction template.

Why this script: cookies in _browser_profile/ expired (TV API returns 403).
Run this once when TV session needs a refresh; it'll pop up a real browser
window, sit on the chart page, poll the API every 2s to detect successful
login (when /list_alerts returns 200 instead of 403). Once detected, runs
the standard recreate flow non-interactively. Cookies persist for next run.

Usage:
  .venv\\Scripts\\python.exe tools\\tv_alert_setup\\recreate_with_login.py
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
CAPTURE_PATH = HERE / "capture_create_post.json"
PINE_TEMPLATE_PATH = HERE / "pine_alert_template.json"
ROOT = HERE.parent.parent
ENV_PATH = ROOT / "config" / ".env"
TOP_5_PATH = ROOT / "reports" / "top_5_pairs.json"
ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"

INSTANT_FREQ = None
TARGET_TFS = ["5", "15", "30", "60"]
TF_LABEL = {"5": "M5", "15": "M15", "30": "M30", "60": "H1"}
LOGIN_TIMEOUT_S = 480  # 8 minutes for user to login

SECRET = None
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


def wait_for_tv_login(api, json_hdrs, timeout_s=LOGIN_TIMEOUT_S):
    """Poll list_alerts API; return True when it stops returning 403."""
    print(f"\n>> Waiting up to {timeout_s}s for TV login to be detected...", flush=True)
    print(">> If browser shows login page, sign in (Google/Apple/email).", flush=True)
    print(">> Once logged in to TV, the script auto-proceeds.", flush=True)
    print(">> Detecting via API status (every 3s)\n", flush=True)
    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        try:
            r = api.post("https://pricealerts.tradingview.com/list_alerts",
                         data=json.dumps({"payload": {"limit": 5000}}),
                         headers=json_hdrs, timeout=8000)
            if r.status != last_status:
                print(f"  [{int(time.time())}] /list_alerts → HTTP {r.status}", flush=True)
                last_status = r.status
            if r.status == 200:
                txt = r.text()
                if '"r":[' in txt or '"r":{' in txt or '"s":"ok"' in txt:
                    n = txt.count('"alert_id"')
                    print(f"  [OK] LOGGED IN — list_alerts has {n} alerts", flush=True)
                    return True
        except Exception as e:
            print(f"  poll error: {e}", flush=True)
        time.sleep(3)
    print(">> Timeout waiting for login.", flush=True)
    return False


def main():
    if not TOP_5_PATH.exists():
        print(f"FATAL: {TOP_5_PATH} missing", flush=True)
        return 1
    top_5 = json.loads(TOP_5_PATH.read_text(encoding="utf-8"))["top_5"]
    print(f"Target pairs: {top_5}", flush=True)

    if not CAPTURE_PATH.exists() or not PINE_TEMPLATE_PATH.exists():
        print(f"FATAL: capture or pine template missing", flush=True)
        return 1
    captures = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    cap = captures[0]
    captured_url = cap["url"]
    captured_headers = cap.get("headers") or {}
    captured_body = json.loads(cap.get("post_data") or "{}")
    base_payload = captured_body.get("payload", {})
    pine_template = json.loads(PINE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    pine_condition = pine_template["condition"]

    create_hdrs = {k: v for k, v in captured_headers.items()
                   if k.lower() not in ("host", "content-length", "cookie", "connection",
                                         "accept-encoding")}
    create_hdrs["Origin"] = "https://www.tradingview.com"
    create_hdrs["Referer"] = "https://www.tradingview.com/"
    create_hdrs["Content-Type"] = "text/plain;charset=UTF-8"

    json_hdrs = {"Origin": "https://www.tradingview.com",
                 "Referer": "https://www.tradingview.com/chart/",
                 "Content-Type": "application/json"}

    with sync_playwright() as p:
        # HEADED mode so user can login if needed
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
            print(f"goto warning (continuing): {e}", flush=True)

        api = ctx.request

        # Try once without waiting — maybe cookies are still good
        r0 = api.post("https://pricealerts.tradingview.com/list_alerts",
                      data=json.dumps({"payload": {"limit": 5000}}),
                      headers=json_hdrs, timeout=8000)
        if r0.status != 200:
            ok = wait_for_tv_login(api, json_hdrs)
            if not ok:
                print("\n[X] Could not detect TV login. Aborting safely.", flush=True)
                ctx.close()
                return 2
        else:
            print(f"  [OK] Already logged in (cookies valid)", flush=True)

        # Now do the work
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])
        rp_existing = [a for a in alerts if (a.get("condition") or {}).get("type") == "pine_alert"
                       and ((a.get("condition") or {}).get("series") or [{}])[0].get("pine_id") == ROCKET_PRIME]
        print(f"\nFound {len(rp_existing)} existing Rocket Prime alerts", flush=True)
        if rp_existing:
            ids = [a["alert_id"] for a in rp_existing]
            print(f">> DELETING all {len(ids)}...", flush=True)
            BATCH = 25
            for i in range(0, len(ids), BATCH):
                chunk = ids[i:i + BATCH]
                rr = api.post("https://pricealerts.tradingview.com/delete_alerts",
                              data=json.dumps({"payload": {"alert_ids": chunk}}),
                              headers=json_hdrs, timeout=15_000)
                ok = rr.status == 200 and '"s":"ok"' in rr.text()
                print(f"  delete batch ({len(chunk)}): {'OK' if ok else 'FAIL ' + rr.text()[:120]}", flush=True)
            time.sleep(2)

        success = failed = 0
        print(f"\n>> CREATING {len(top_5) * len(TARGET_TFS)} alerts...", flush=True)
        for sym in top_5:
            ex, bs, cur = _ex(sym), _bs(sym), _cur(sym)
            for res_str in TARGET_TFS:
                symbol_field = _build_symbol_field(ex, bs, cur)
                exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                new_condition = copy.deepcopy(pine_condition)
                new_condition["resolution"] = res_str
                if INSTANT_FREQ is None:
                    new_condition.pop("frequency", None)
                else:
                    new_condition["frequency"] = INSTANT_FREQ
                payload = copy.deepcopy(base_payload)
                payload["symbol"] = symbol_field
                payload["resolution"] = res_str
                payload["expiration"] = exp
                # Direction extraction via plot placeholders.
                # Plus URL has &symbol=&tf= for fallback path, AND
                # we add explicit buy/sell wording in body via {{strategy.order.action}}
                # if available (pine indicators with strategy outputs).
                payload["message"] = (
                    "RP|{{ticker}}|tf={{interval}}"
                    "|p0={{plot_0}}|p1={{plot_1}}|p2={{plot_2}}|p3={{plot_3}}|p4={{plot_4}}"
                    "|p5={{plot_5}}|p6={{plot_6}}|p7={{plot_7}}|p8={{plot_8}}|p9={{plot_9}}"
                    "|c={{close}}|t={{timenow}}"
                )
                payload["conditions"] = [new_condition]
                payload["name"] = None
                payload["web_hook"] = f"{WEBHOOK_BASE}&symbol={sym}&tf={res_str}"
                for k in ("condition", "complexity", "type", "kinds", "cross_interval",
                          "expiration_policy", "pro_symbol", "presentation_data",
                          "mutable_study_data"):
                    payload.pop(k, None)
                try:
                    rr = api.post(captured_url, data=json.dumps({"payload": payload}),
                                  headers=create_hdrs, timeout=15_000)
                    txt = rr.text()[:200]
                    if rr.status == 200 and '"s":"ok"' in txt:
                        success += 1
                        aid = None
                        try: aid = rr.json().get("r", {}).get("alert_id")
                        except Exception: pass
                        print(f"  [OK]   {sym} {TF_LABEL[res_str]:<5} aid={aid}", flush=True)
                    else:
                        failed += 1
                        print(f"  [FAIL] {sym} {TF_LABEL[res_str]:<5}: {txt[:140]}", flush=True)
                except Exception as e:
                    failed += 1
                    print(f"  [ERR] {sym} {TF_LABEL[res_str]:<5}: {e}", flush=True)
                time.sleep(0.5)

        print(f"\n=== DONE: created {success}, failed {failed} ===", flush=True)

        # Verify
        time.sleep(1)
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts2 = r.json().get("r", [])
        rp = []
        for a in alerts2:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert": continue
            if ((cond.get("series") or [{}])[0]).get("pine_id") != ROCKET_PRIME: continue
            sym_raw = a.get("symbol", "")
            try: full = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
            except Exception: full = sym_raw
            rp.append((full, str(a.get("resolution", ""))))
        print(f"\n=== Final Rocket Prime alerts: {len(rp)} ===", flush=True)
        for fs, res in sorted(rp):
            print(f"  {fs:<25} {TF_LABEL.get(res, res)}", flush=True)

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
