"""Change all Rocket Prime alerts to fire on EVERY tick (instant), not bar close.

TradingView pine_alert frequency options:
  "all"                  - every tick (FASTEST — what we want)
  "once_per_bar"         - once per bar (mid)
  "once_per_bar_close"   - on bar close only (slowest, original setting)

Strategy: list all 20 alerts, delete each, recreate with frequency="all".
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

# FASTEST possible — fires on every tick that indicator's alert() condition is true
INSTANT_FREQ = "all"

SECRET = None
for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
    if line.startswith("TV_WEBHOOK_SECRET"):
        SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
WEBHOOK_URL = f"https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret={SECRET}"


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
                   if k.lower() not in ("host", "content-length", "cookie", "connection",
                                         "accept-encoding")}
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

        # 1. List all Rocket Prime alerts (full payloads so we can recreate)
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])
        rp_alerts = []
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            rp_alerts.append(a)
        print(f"Found {len(rp_alerts)} Rocket Prime alerts to update\n")

        # 2. For each: delete + recreate with frequency="all"
        success = 0
        failed = 0
        for a in rp_alerts:
            sym_raw = a.get("symbol", "")
            try:
                full = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
            except Exception:
                full = sym_raw
            res_str = str(a.get("resolution", ""))
            tf_label = {"1": "M1", "5": "M5", "15": "M15", "30": "M30", "60": "H1", "240": "H4"}.get(res_str, res_str)

            # Delete
            del_r = api.post("https://pricealerts.tradingview.com/delete_alerts",
                             data=json.dumps({"payload": {"alert_ids": [a["alert_id"]]}}),
                             headers=json_hdrs, timeout=15_000)
            if not (del_r.status == 200 and '"s":"ok"' in del_r.text()):
                failed += 1
                print(f"  [DEL FAIL] {full} {tf_label}: {del_r.text()[:120]}")
                continue
            time.sleep(0.3)

            # Recreate with same symbol/TF/webhook BUT frequency="all"
            new_condition = copy.deepcopy(pine_condition)
            new_condition["resolution"] = res_str
            new_condition["frequency"] = INSTANT_FREQ  # ← INSTANT FIRE

            payload = copy.deepcopy(base_payload)
            payload["symbol"] = sym_raw
            payload["resolution"] = res_str
            exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            payload["expiration"] = exp
            payload["message"] = ""
            payload["conditions"] = [new_condition]
            payload["name"] = None
            payload["web_hook"] = WEBHOOK_URL
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
                    print(f"  [OK]   {full:<25} {tf_label}  freq=all  alert_id={aid}")
                else:
                    failed += 1
                    print(f"  [CREATE FAIL] {full} {tf_label}: {txt[:120]}")
            except Exception as e:
                failed += 1
                print(f"  [ERR] {full} {tf_label}: {e}")
            time.sleep(0.4)

        # 3. Verify
        time.sleep(1)
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts2 = r.json().get("r", [])
        print(f"\n=== Final: {success} updated, {failed} failed ===\n")
        print("Verification — frequency on each alert:")
        for a in alerts2:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            sym_raw = a.get("symbol", "")
            try: full = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
            except Exception: full = sym_raw
            res_str = str(a.get("resolution", ""))
            freq = cond.get("frequency", "?")
            print(f"  {full:<25} res={res_str:<3}  freq={freq}")
        ctx.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
