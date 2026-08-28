"""Probe TV's modify_alert endpoint with frequency="all" on one M1 alert.

create_alert rejects frequency="all". modify_alert is a different endpoint
that may have looser validation. If it accepts, we can convert all 20 alerts
to instant tick fire.

Strategy:
  1. Pick XAUUSD M1 alert
  2. Try modify with various endpoint paths and payload shapes
  3. Print what TV says
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
ROCKET_PRIME = "PUB;56f0fb74de7f4eed9325b987428b727e"


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # Capture all network requests
        network_log = []
        def on_req(req):
            if "pricealerts.tradingview.com" in req.url:
                network_log.append(("REQ", req.method, req.url, req.headers, req.post_data))
        def on_resp(resp):
            if "pricealerts.tradingview.com" in resp.url:
                try:
                    body = resp.text()[:300]
                except Exception:
                    body = ""
                network_log.append(("RESP", resp.status, resp.url, dict(resp.headers), body))
        page.on("request", on_req)
        page.on("response", on_resp)

        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(3)
        api = ctx.request

        json_hdrs = {"Origin": "https://www.tradingview.com",
                     "Referer": "https://www.tradingview.com/chart/",
                     "Content-Type": "application/json"}

        captures = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
        cap = captures[0]
        captured_url = cap["url"]
        captured_headers = cap.get("headers") or {}

        create_hdrs = {k: v for k, v in captured_headers.items()
                       if k.lower() not in ("host", "content-length", "cookie", "connection",
                                             "accept-encoding")}
        create_hdrs["Origin"] = "https://www.tradingview.com"
        create_hdrs["Referer"] = "https://www.tradingview.com/"
        create_hdrs["Content-Type"] = "text/plain;charset=UTF-8"

        # Find a M1 XAUUSD alert
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r") or []
        target = None
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            if "XAUUSD" in a.get("symbol", "") and str(a.get("resolution", "")) == "1":
                target = a
                break
        if not target:
            print("No XAUUSD M1 alert", flush=True)
            ctx.close()
            return 1
        aid = target["alert_id"]
        print(f"Target alert_id={aid}", flush=True)
        print(f"Current condition.frequency = {target.get('condition', {}).get('frequency')!r}", flush=True)

        # Try several modify endpoints + payload shapes
        # Build modified payload — set frequency=all in condition
        modified_condition = copy.deepcopy(target.get("condition") or {})
        modified_condition["frequency"] = "all"

        attempts = [
            # (label, url, content_type, body)
            ("modify_alert JSON full",
             "https://pricealerts.tradingview.com/modify_alert",
             "application/json",
             json.dumps({"payload": {"alert_id": aid, "alert": {"condition": modified_condition,
                                                                  "conditions": [modified_condition]}}})),
            ("modify_alert JSON partial",
             "https://pricealerts.tradingview.com/modify_alert",
             "application/json",
             json.dumps({"payload": {"alert_id": aid, "frequency": "all"}})),
            ("update_alert JSON",
             "https://pricealerts.tradingview.com/update_alert",
             "application/json",
             json.dumps({"payload": {"alert_id": aid, "condition": modified_condition}})),
            ("modify text/plain full payload",
             "https://pricealerts.tradingview.com/modify_alert",
             "text/plain;charset=UTF-8",
             json.dumps({"payload": {**target, "condition": modified_condition,
                                     "conditions": [modified_condition]}})),
            ("set_alert_frequency",
             "https://pricealerts.tradingview.com/set_frequency",
             "application/json",
             json.dumps({"payload": {"alert_id": aid, "frequency": "all"}})),
        ]

        for label, url, ct, body in attempts:
            hdrs = dict(create_hdrs)
            hdrs["Content-Type"] = ct
            try:
                rr = api.post(url, data=body, headers=hdrs, timeout=10_000)
                txt = rr.text()[:300]
                print(f"\n[{label}]", flush=True)
                print(f"  status={rr.status}", flush=True)
                print(f"  body={txt}", flush=True)
            except Exception as e:
                print(f"\n[{label}] EXCEPTION: {e}", flush=True)
            time.sleep(0.4)

        # Final check what frequency is now on the alert
        time.sleep(1)
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"alert_ids": [aid]}}),
                     headers=json_hdrs, timeout=10_000)
        try:
            data = r.json().get("r") or []
            for a in data:
                if a.get("alert_id") == aid:
                    print(f"\n[POST-PROBE] alert_id={aid} freq={a.get('condition', {}).get('frequency')!r}", flush=True)
                    break
        except Exception as e:
            print(f"final check err: {e}", flush=True)

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
