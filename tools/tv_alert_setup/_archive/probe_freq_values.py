"""Probe TV API: try every plausible frequency value on ONE test alert.

Strategy: pick XAUUSD M5 alert (1 of the 20). For each candidate frequency:
 1. delete the existing alert
 2. recreate with the candidate frequency
 3. record server response
 4. on success, leave it; on failure, continue probing

If we find a working "instant" value, the operator can switch ALL alerts
to that frequency by re-running set_instant_frequency.py with the new
INSTANT_FREQ constant.
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

# Candidate frequency values, in order of preference (fastest first).
CANDIDATES = [
    "all",                  # docs say this = every tick
    "1",                    # numeric: 1 second?
    "once_per_minute",      # 60s
    "once_per_bar",         # first hit in each bar (mid-bar fire)
    "ON_BAR",               # alternative casing
    "tick",                 # alternative literal
    "EVERY_BAR",
    "5",                    # numeric: 5 seconds?
]

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

        # Find one XAUUSD M5 alert
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])
        target_id = None
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            sym_raw = a.get("symbol", "")
            if "XAUUSD" in sym_raw and str(a.get("resolution", "")) == "5":
                target_id = a["alert_id"]
                break
        if not target_id:
            print("No XAUUSD M5 Rocket Prime alert to probe with", flush=True)
            ctx.close()
            return 1
        print(f"Probing using XAUUSD M5 (alert_id={target_id})", flush=True)

        winner = None

        def build_payload(freq, omit=False):
            new_condition = copy.deepcopy(pine_condition)
            new_condition["resolution"] = "5"
            if omit:
                new_condition.pop("frequency", None)
            else:
                new_condition["frequency"] = freq
            payload = copy.deepcopy(base_payload)
            payload["symbol"] = "={\"currency-id\":\"USD\",\"session\":\"regular\",\"symbol\":\"OANDA:XAUUSD\"}"
            payload["resolution"] = "5"
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
            return payload

        # Try each candidate. For each, delete-then-create.
        candidates_to_try = [(c, False) for c in CANDIDATES] + [("(omit)", True)]
        for freq, omit in candidates_to_try:
            label = "OMIT" if omit else f'freq="{freq}"'
            # Delete current XAUUSD M5 alert
            del_r = api.post("https://pricealerts.tradingview.com/delete_alerts",
                             data=json.dumps({"payload": {"alert_ids": [target_id]}}),
                             headers=json_hdrs, timeout=15_000)
            ok_del = del_r.status == 200 and '"s":"ok"' in del_r.text()
            if not ok_del:
                print(f"  [DEL FAIL]: {del_r.text()[:120]}", flush=True)
            time.sleep(0.4)

            # Create with candidate
            payload = build_payload(freq, omit)
            try:
                rr = api.post(captured_url, data=json.dumps({"payload": payload}),
                              headers=create_hdrs, timeout=15_000)
                txt = rr.text()[:300]
                if rr.status == 200 and '"s":"ok"' in txt:
                    aid = None
                    try: aid = rr.json().get("r", {}).get("alert_id")
                    except Exception: pass
                    print(f"  [WIN!]  {label:30}  → alert_id={aid}", flush=True)
                    target_id = aid  # next iteration will use this for delete
                    if winner is None:
                        winner = (freq, omit, aid)
                        # Stop at first winner — we have what we need
                        break
                else:
                    print(f"  [REJECTED] {label:30}  → {txt[:200]}", flush=True)
                    # alert was deleted but creation failed — recreate with fallback
                    fallback_payload = build_payload("60", False)
                    rr2 = api.post(captured_url, data=json.dumps({"payload": fallback_payload}),
                                   headers=create_hdrs, timeout=15_000)
                    if rr2.status == 200 and '"s":"ok"' in rr2.text():
                        try: target_id = rr2.json().get("r", {}).get("alert_id")
                        except Exception: pass
                        print(f"    (recreated XAUUSD M5 with freq=60 fallback aid={target_id})", flush=True)
                    else:
                        print(f"    [FALLBACK FAIL] {rr2.text()[:120]}", flush=True)
                        break
            except Exception as e:
                print(f"  [ERR] {label}: {e}", flush=True)
            time.sleep(0.4)

        if winner:
            freq, omit, aid = winner
            tag = "OMIT" if omit else f'frequency="{freq}"'
            print(f"\n=== WINNER: {tag} → alert_id={aid} ===", flush=True)
            print(f"Now switch all 20 alerts to this frequency by editing", flush=True)
            print(f"  set_instant_frequency.py:", flush=True)
            print(f'    INSTANT_FREQ = "{freq}"' if not omit else "    (remove frequency field)", flush=True)
        else:
            print("\n=== No instant frequency value accepted by TV API ===", flush=True)
            print("Recommended next step: change ONE alert manually in TV UI,", flush=True)
            print("re-capture the create_alert POST, and replay.", flush=True)

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
