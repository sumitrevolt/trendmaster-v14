"""Refresh all Rocket Prime alerts: delete expired ones, recreate with CURRENT webhook URL.

Uses fresh session cookies exported from TradingView Desktop via CDP
(agent-browser --cdp 9225 cookies get --json > <file>).

Usage:
  .venv\\Scripts\\python.exe tools\\tv_alert_setup\\_refresh_alerts_webhook.py <cookies_json_file>
"""
from __future__ import annotations

import copy
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
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

TARGET_TFS = ["5", "15", "30", "60"]  # M5, M15, M30, H1
TF_LABEL = {"5": "M5", "15": "M15", "30": "M30", "60": "H1"}

SECRET = None
for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
    if line.startswith("TV_WEBHOOK_SECRET"):
        SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
        break

# Current public tunnel URL (cloudflared quick tunnel started 2026-08-22).
WEBHOOK_BASE = f"https://poll-mit-lenses-terry.trycloudflare.com/tv-signal?secret={SECRET}"


def _ex(s):
    if s in ("BTCUSD", "ETHUSD"):
        return "BINANCE"
    if s == "XTIUSD":
        return "FX"
    if s == "XBRUSD":
        return "FX"
    if s == "XNGUSD":
        return "NYMEX_DL"
    return "OANDA"


def _bs(s):
    if s == "XTIUSD":
        return "USOIL"
    if s == "XBRUSD":
        return "UKOIL"
    if s == "XNGUSD":
        return "NG1!"
    return s


def _cur(s):
    if s.startswith(("XAU", "XAG")) or s in ("BTCUSD", "ETHUSD", "XTIUSD", "XBRUSD", "XNGUSD"):
        return "USD"
    return s[-3:]


def load_cookies(path: Path) -> list[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raw = json.loads(path.read_text(encoding="utf-16"))
    return raw["data"]["cookies"]


def main() -> int:
    cookies_file = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not cookies_file or not cookies_file.exists():
        print("[X] cookies json file required (export via agent-browser --cdp 9225 cookies get --json)")
        return 2
    cookies = load_cookies(cookies_file)

    top_5 = json.loads(TOP_5_PATH.read_text(encoding="utf-8"))["top_5"]
    captures = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    cap = captures[0]
    captured_url = cap["url"]
    captured_headers = cap.get("headers") or {}
    base_payload = json.loads(cap.get("post_data") or "{}").get("payload", {})
    pine_condition = json.loads(PINE_TEMPLATE_PATH.read_text(encoding="utf-8"))["condition"]

    # 2026-08-22: captured headers contained stale auth tokens -> server saw an
    # unauthenticated request and returned no_webhook_permissions. Use the same
    # minimal cookie-authenticated headers that list_alerts/delete_alerts use.
    create_hdrs = {"Origin": "https://www.tradingview.com",
                   "Referer": "https://www.tradingview.com/",
                   "Content-Type": "text/plain;charset=UTF-8"}

    json_hdrs = {"Origin": "https://www.tradingview.com",
                 "Referer": "https://www.tradingview.com/chart/",
                 "Content-Type": "application/json"}

    exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
        ctx.add_cookies(cookies)
        api = ctx.request

        # ---- inventory ----
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=30_000)
        obj = r.json()
        alerts = obj.get("r") or []
        rp_ids = []
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            rp_ids.append(a["alert_id"])
        print(f"Found {len(alerts)} total alerts, {len(rp_ids)} Rocket Prime alerts to delete", flush=True)

        # ---- delete old RP alerts ----
        if rp_ids:
            for i in range(0, len(rp_ids), 25):
                chunk = rp_ids[i:i + 25]
                rr = api.post("https://pricealerts.tradingview.com/delete_alerts",
                              data=json.dumps({"payload": {"alert_ids": chunk}}),
                              headers=json_hdrs, timeout=30_000)
                ok = rr.status == 200 and '"s":"ok"' in rr.text()
                print(f"  delete batch ({len(chunk)}): {'OK' if ok else 'FAIL ' + rr.text()[:120]}", flush=True)
            time.sleep(2)

        # ---- recreate with current webhook ----
        success = failed = 0
        for sym in top_5:
            ex, bs, cur = _ex(sym), _bs(sym), _cur(sym)
            symbol_field = "=" + json.dumps(
                {"currency-id": cur, "session": "regular", "symbol": f"{ex}:{bs}"},
                separators=(",", ":"))
            for res_str in TARGET_TFS:
                new_condition = copy.deepcopy(pine_condition)
                new_condition["resolution"] = res_str
                new_condition.pop("frequency", None)
                payload = copy.deepcopy(base_payload)
                payload["symbol"] = symbol_field
                payload["resolution"] = res_str
                payload["expiration"] = exp
                payload["message"] = ""
                payload["conditions"] = [new_condition]
                payload["name"] = None
                plots = "".join(f"&p{i}={{{{plot_{i}}}}}" for i in range(10))
                payload["web_hook"] = f"{WEBHOOK_BASE}&symbol={sym}&tf={res_str}{plots}"
                for k in ("condition", "complexity", "type", "kinds", "cross_interval",
                          "expiration_policy", "pro_symbol", "presentation_data",
                          "mutable_study_data"):
                    payload.pop(k, None)
                try:
                    rr = api.post(captured_url, data=json.dumps({"payload": payload}),
                                  headers=create_hdrs, timeout=30_000)
                    txt = rr.text()[:200]
                    if rr.status == 200 and '"s":"ok"' in txt:
                        success += 1
                        aid = None
                        try:
                            aid = rr.json().get("r", {}).get("alert_id")
                        except Exception:
                            pass
                        print(f"  [OK]   {sym} {TF_LABEL[res_str]} aid={aid}", flush=True)
                    else:
                        failed += 1
                        print(f"  [FAIL] {sym} {TF_LABEL[res_str]}: {txt[:140]}", flush=True)
                except Exception as e:
                    failed += 1
                    print(f"  [ERR]  {sym} {TF_LABEL[res_str]}: {e}", flush=True)
                time.sleep(0.6)

        # ---- verify ----
        time.sleep(2)
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=30_000)
        alerts = (r.json().get("r") or [])
        active = sum(1 for a in alerts if a.get("active"))
        ngrok_left = sum(1 for a in alerts if "ngrok-free.dev" in (a.get("web_hook") or ""))
        print(f"\n=== created={success} failed={failed} | total={len(alerts)} active={active} old-ngrok-urls={ngrok_left} ===", flush=True)
        ctx.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
