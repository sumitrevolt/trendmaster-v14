"""Add multi-timeframe Rocket Prime alerts within TV plan quota.

Strategy: TV Pro plan caps complex alerts at ~25. Currently we have 21
H1 alerts (1 per pair). This adds M15 for high-priority pairs to give
multi-TF coverage on the most-traded majors. After this, total = 25.

Priority order for additional TFs (most-active pairs first):
  1. XAUUSD M15  (gold — biggest mover)
  2. EURUSD M15  (most liquid)
  3. GBPUSD M15  (volatile)
  4. USDJPY M15  (yen carry)

If quota allows more (the user upgraded), the script extends to add
M5 + H4 too for these top pairs.
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
ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"

SECRET = None
for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
    if line.startswith("TV_WEBHOOK_SECRET"):
        SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
WEBHOOK_URL = f"https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret={SECRET}"

# Priority list — try in order, stop on quota error
ADD_LIST = [
    # (priority_rank, symbol, exchange, broker_sym, currency, tf_minutes_str)
    ("XAUUSD", "OANDA",   "XAUUSD", "USD", "15"),  # M15
    ("EURUSD", "OANDA",   "EURUSD", "USD", "15"),
    ("GBPUSD", "OANDA",   "GBPUSD", "USD", "15"),
    ("USDJPY", "OANDA",   "USDJPY", "USD", "15"),
    # If quota allows (user has Premium+):
    ("XAUUSD", "OANDA",   "XAUUSD", "USD", "5"),   # M5
    ("XAUUSD", "OANDA",   "XAUUSD", "USD", "240"), # H4
    ("EURUSD", "OANDA",   "EURUSD", "USD", "5"),
    ("EURUSD", "OANDA",   "EURUSD", "USD", "240"),
    ("GBPUSD", "OANDA",   "GBPUSD", "USD", "5"),
    ("GBPUSD", "OANDA",   "GBPUSD", "USD", "240"),
    ("USDJPY", "OANDA",   "USDJPY", "USD", "5"),
    ("USDJPY", "OANDA",   "USDJPY", "USD", "240"),
]


def _build_symbol_field(exchange, broker_sym, currency):
    obj = {"currency-id": currency, "session": "regular",
           "symbol": f"{exchange}:{broker_sym}"}
    return "=" + json.dumps(obj, separators=(",", ":"))


def main():
    captures = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    cap = captures[0]
    captured_url = cap["url"]
    captured_headers = cap.get("headers") or {}
    captured_body = json.loads(cap.get("post_data") or "{}")
    base_payload = captured_body.get("payload", {})
    pine_template = json.loads(PINE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    pine_condition = pine_template["condition"]

    create_hdrs = {k: v for k, v in captured_headers.items()
                   if k.lower() not in ("host", "content-length", "cookie",
                                         "connection", "accept-encoding")}
    create_hdrs["Origin"] = "https://www.tradingview.com"
    create_hdrs["Referer"] = "https://www.tradingview.com/"
    create_hdrs["Content-Type"] = "text/plain;charset=UTF-8"

    json_hdrs = {"Origin": "https://www.tradingview.com",
                 "Referer": "https://www.tradingview.com/chart/",
                 "Content-Type": "application/json"}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(3)
        api = ctx.request

        # Check existing alerts to avoid duplicates
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])
        existing = set()
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            sym_raw = a.get("symbol", "")
            try:
                sym_obj = json.loads(sym_raw[1:]) if sym_raw.startswith("=") else {}
                full_sym = sym_obj.get("symbol", "")
            except Exception:
                full_sym = sym_raw
            existing.add((full_sym, str(a.get("resolution", ""))))
        print(f"Existing Rocket Prime alerts: {len(existing)}")
        for fs, r_ in sorted(existing):
            print(f"  {fs} res={r_}")

        success = 0
        quota_hit = False
        for sym, ex, bs, cur, res_str in ADD_LIST:
            full = f"{ex}:{bs}"
            if (full, res_str) in existing:
                print(f"\n[SKIP] {sym} {full} res={res_str} already exists")
                continue

            symbol_field = _build_symbol_field(ex, bs, cur)
            exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            new_condition = copy.deepcopy(pine_condition)
            new_condition["resolution"] = res_str

            payload = copy.deepcopy(base_payload)
            payload["symbol"] = symbol_field
            payload["resolution"] = res_str
            payload["expiration"] = exp
            payload["message"] = ""
            payload["conditions"] = [new_condition]
            payload["name"] = None
            payload["web_hook"] = WEBHOOK_URL
            for k in ("condition", "complexity", "type", "kinds", "cross_interval",
                      "expiration_policy", "pro_symbol", "presentation_data",
                      "mutable_study_data"):
                payload.pop(k, None)

            tf_label = {"5": "M5", "15": "M15", "60": "H1", "240": "H4"}.get(res_str, res_str)
            try:
                rr = api.post(captured_url, data=json.dumps({"payload": payload}),
                              headers=create_hdrs, timeout=15_000)
                txt = rr.text()[:200]
                if rr.status == 200 and '"s":"ok"' in txt:
                    success += 1
                    aid = None
                    try:
                        aid = rr.json().get("r", {}).get("alert_id")
                    except Exception:
                        pass
                    print(f"  [OK]   {sym} {tf_label}  alert_id={aid}")
                elif "max_complex_alerts_count_exceeded" in txt:
                    print(f"  [QUOTA] {sym} {tf_label} — TV plan limit reached. Stopping.")
                    quota_hit = True
                    break
                else:
                    print(f"  [FAIL] {sym} {tf_label}  {txt[:150]}")
            except Exception as e:
                print(f"  [ERR]  {sym} {tf_label}  {e}")
            time.sleep(0.4)

        # Final inventory
        time.sleep(1)
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts2 = r.json().get("r", [])
        rp_total = sum(1 for a in alerts2
                       if (a.get("condition") or {}).get("type") == "pine_alert"
                       and ((a.get("condition") or {}).get("series") or [{}])[0].get("pine_id") == ROCKET_PRIME)
        print(f"\n=== Final Rocket Prime alerts: {rp_total} ===")
        print(f"Created this run: {success}")
        if quota_hit:
            print("Quota wall reached — to add more, upgrade TradingView plan to Premium+")

        ctx.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
