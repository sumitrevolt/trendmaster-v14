"""Create EURAUD H1 alert + try multiple TV symbol prefixes for XNGUSD."""
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

# (symbol_for_log, exchange, broker_symbol, currency)
TARGETS = [
    ("EURAUD", "OANDA",  "EURAUD",     "AUD"),
    ("XNGUSD", "TVC",    "NATGAS",     "USD"),  # try TVC:NATGAS
    ("XNGUSD", "NYMEX",  "NG1!",       "USD"),  # NYMEX continuous
    ("XNGUSD", "ICEUS",  "NG1!",       "USD"),  # ICE alternative
    ("XNGUSD", "FX_IDC", "NATGAS",     "USD"),  # FX_IDC
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
                   if k.lower() not in ("host", "content-length", "cookie", "connection",
                                         "accept-encoding")}
    create_hdrs["Origin"] = "https://www.tradingview.com"
    create_hdrs["Referer"] = "https://www.tradingview.com/"
    create_hdrs["Content-Type"] = "text/plain;charset=UTF-8"

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(3)
        api = ctx.request

        xngusd_done = False
        for sym, ex, bsym, cur in TARGETS:
            if sym == "XNGUSD" and xngusd_done:
                continue  # already created with one prefix
            full = f"{ex}:{bsym}"
            symbol_field = _build_symbol_field(ex, bsym, cur)
            exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

            new_condition = copy.deepcopy(pine_condition)
            new_condition["resolution"] = "60"

            payload = copy.deepcopy(base_payload)
            payload["symbol"] = symbol_field
            payload["resolution"] = "60"
            payload["expiration"] = exp
            payload["message"] = ""
            payload["conditions"] = [new_condition]
            payload["name"] = None
            payload["web_hook"] = WEBHOOK_URL
            for k in ("condition", "complexity", "type", "kinds", "cross_interval",
                      "expiration_policy", "pro_symbol", "presentation_data",
                      "mutable_study_data"):
                payload.pop(k, None)

            body = {"payload": payload}
            try:
                r = api.post(captured_url, data=json.dumps(body), headers=create_hdrs, timeout=15_000)
                txt = r.text()[:200]
                if r.status == 200 and '"s":"ok"' in txt:
                    aid = None
                    try:
                        aid = r.json().get("r", {}).get("alert_id")
                    except Exception:
                        pass
                    print(f"  [OK]   {sym} ({full})  alert_id={aid}")
                    if sym == "XNGUSD":
                        xngusd_done = True
                else:
                    print(f"  [FAIL] {sym} ({full})  {txt[:120]}")
            except Exception as e:
                print(f"  [ERR]  {sym} ({full})  {e}")
            time.sleep(0.4)

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
