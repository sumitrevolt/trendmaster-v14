"""Delete all existing Rocket Prime alerts and recreate them for the
24 volatile pairs × 2 timeframes (M5, M15) = 48 alerts.

Pair list lives in reports/volatile_pairs.json so operator can adjust
without touching code.

Webhook URL still includes plot placeholders even though Method 99
(2026-05-10) empirically failed — Pine alert() blocks substitution
in URL too. The placeholders are harmless (arrive literal) and keep
the URL future-proof if RP indicator ever switches to alertcondition().

REALISTIC EXPECTATION (be honest with the operator):
  - These alerts WILL fire when RP draws Buy/Sell observation
  - Webhook WILL receive them
  - Bot WILL still REJECT (no direction extractable)
  - UNTIL we implement Telegram BUY/SELL button helper (or OCR, or
    switch to an indicator that exposes direction via alertcondition).

So this script doubles RP coverage on the chart side but doesn't
fix the direction problem.
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
CAPTURE_PATH = HERE / "capture_create_post.json"
PINE_TEMPLATE_PATH = HERE / "pine_alert_template.json"
ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"

VOLATILE_PAIRS_PATH = ROOT / "reports" / "volatile_pairs.json"

INSTANT_FREQ = None
# 2026-05-13: operator requested M5 + M15 only (was M5/M15/M30/H1).
# Fewer TFs → less noise, more signals per TF observed.
TARGET_TFS = ["5", "15"]
TF_LABEL = {"5": "M5", "15": "M15"}
LOGIN_TIMEOUT_S = 480

SECRET = None
TUNNEL_BASE = "https://shadow-cosmos-unending.ngrok-free.dev"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("TV_WEBHOOK_SECRET"):
            SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("TV_PUBLIC_URL"):
            TUNNEL_BASE = line.split("=", 1)[1].strip().strip('"').strip("'")

# Plot placeholders kept in URL despite Method 99 failure — they're
# harmless literals when alert() suppresses substitution, and become
# useful if RP source ever switches to alertcondition.
URL_PLOTS = (
    "&p0={{plot_0}}&p1={{plot_1}}&p2={{plot_2}}&p3={{plot_3}}&p4={{plot_4}}"
    "&p5={{plot_5}}&p6={{plot_6}}&p7={{plot_7}}&p8={{plot_8}}&p9={{plot_9}}"
)


def _ex(s):
    """Exchange mapping per pair for TV symbol field."""
    if s == "BTCUSD": return "VANTAGE"     # operator's chart confirmed
    if s == "ETHUSD": return "BINANCE"
    if s == "XTIUSD": return "FX"          # WTI oil
    if s == "XBRUSD": return "FX"          # Brent oil
    if s == "XNGUSD": return "NYMEX_DL"    # Nat gas
    # Everything else lands on OANDA (forex + metals)
    return "OANDA"


def _bs(s):
    """Broker symbol mapping where TV uses non-standard tickers."""
    if s == "XTIUSD": return "USOIL"
    if s == "XBRUSD": return "UKOIL"
    if s == "XNGUSD": return "NG1!"
    return s


def _cur(s):
    """Currency-id for TV symbol field (always quote currency)."""
    if s.startswith(("XAU", "XAG")) or s in ("BTCUSD", "ETHUSD", "XTIUSD", "XBRUSD", "XNGUSD"):
        return "USD"
    return s[-3:]


def _build_symbol_field(ex, bs, cur):
    obj = {"currency-id": cur, "session": "regular", "symbol": f"{ex}:{bs}"}
    return "=" + json.dumps(obj, separators=(",", ":"))


def wait_for_tv_login(api, json_hdrs, timeout_s=LOGIN_TIMEOUT_S):
    print(f">> Polling /list_alerts every 3s for up to {timeout_s}s...", flush=True)
    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        try:
            r = api.post("https://pricealerts.tradingview.com/list_alerts",
                         data=json.dumps({"payload": {"limit": 5}}),
                         headers=json_hdrs, timeout=8000)
            if r.status != last_status:
                print(f"  [{int(time.time())}] /list_alerts -> HTTP {r.status}", flush=True)
                last_status = r.status
            if r.status == 200 and '"s":"ok"' in r.text():
                return True
        except Exception as e:
            print(f"  poll error: {e}", flush=True)
        time.sleep(3)
    return False


def main() -> int:
    if not SECRET:
        print("[X] TV_WEBHOOK_SECRET not in config/.env"); return 2
    if not VOLATILE_PAIRS_PATH.exists():
        print(f"[X] {VOLATILE_PAIRS_PATH} missing"); return 2
    pairs_cfg = json.loads(VOLATILE_PAIRS_PATH.read_text(encoding="utf-8"))
    pairs = pairs_cfg["pairs"]

    if not CAPTURE_PATH.exists() or not PINE_TEMPLATE_PATH.exists():
        print(f"[X] capture or pine template missing"); return 2
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

    n_targets = len(pairs) * len(TARGET_TFS)
    print("=" * 70)
    print(f"recreate_rp_volatile_m5m15  -  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  pairs:  {len(pairs)}  ({', '.join(pairs[:6])}...)")
    print(f"  tfs:    {TARGET_TFS}")
    print(f"  target: {n_targets} alerts total")
    print(f"  tunnel: {TUNNEL_BASE}")
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

        if not wait_for_tv_login(api, json_hdrs):
            print("[X] login not detected"); ctx.close(); return 3

        r0 = api.post("https://pricealerts.tradingview.com/list_alerts",
                      data=json.dumps({"payload": {"limit": 5000}}),
                      headers=json_hdrs, timeout=8000)
        if r0.status != 200:
            print(f"[X] list_alerts HTTP {r0.status}"); ctx.close(); return 3

        alerts = r0.json().get("r", [])
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
        print(f"\n>> CREATING {n_targets} alerts (M5+M15 × {len(pairs)} pairs)...", flush=True)
        for sym in pairs:
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
                payload["message"] = ""
                payload["conditions"] = [new_condition]
                payload["name"] = None
                payload["web_hook"] = (
                    f"{TUNNEL_BASE}/tv-signal?secret={SECRET}"
                    f"&symbol={sym}&tf={res_str}"
                    f"{URL_PLOTS}"
                )
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
                        print(f"  [OK]   {sym:<8} {TF_LABEL[res_str]:<5} aid={aid}", flush=True)
                    else:
                        failed += 1
                        print(f"  [FAIL] {sym:<8} {TF_LABEL[res_str]:<5}: {txt[:140]}", flush=True)
                except Exception as e:
                    failed += 1
                    print(f"  [ERR] {sym:<8} {TF_LABEL[res_str]:<5}: {e}", flush=True)
                time.sleep(0.5)

        print(f"\n=== CREATED: {success}, failed: {failed} ===", flush=True)
        if failed > 0:
            print("\nFailures usually mean a pair/exchange combo doesn't exist in TV.")
            print("Update reports/volatile_pairs.json to remove unsupported pairs, then re-run.")

        ctx.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
