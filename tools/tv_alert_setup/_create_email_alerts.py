"""Create ONE email-only Rocket Prime alert via pricealerts API (no web_hook).

Tests whether the account can still create technical+email alerts on the
current (free) plan. If OK, run with --all to create the full matrix.
"""
from __future__ import annotations

import copy
import json
import sys
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
TOP_5_PATH = ROOT / "reports" / "top_5_pairs.json"

TARGET_TFS = ["5", "15", "30", "60"]
TF_LABEL = {"5": "M5", "15": "M15", "30": "M30", "60": "H1"}


def load_cookies(path: Path) -> list[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raw = json.loads(path.read_text(encoding="utf-16"))
    return raw["data"]["cookies"]


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


def build_payload(base_payload, pine_condition, sym, res_str) -> dict:
    symbol_field = "=" + json.dumps(
        {"currency-id": _cur(sym), "session": "regular",
         "symbol": f"{_ex(sym)}:{_bs(sym)}"},
        separators=(",", ":"))
    # 2026-08-22: free-plan max alert lifetime ~30d; 365d caused invalid_request
    exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    new_condition = copy.deepcopy(pine_condition)
    new_condition["resolution"] = res_str
    payload = copy.deepcopy(base_payload)
    payload["symbol"] = symbol_field
    payload["resolution"] = res_str
    payload["expiration"] = exp
    payload["message"] = (
        f"RP|{{{{ticker}}}}|tf={res_str}"
        "|p0={{plot_0}}|p1={{plot_1}}|p2={{plot_2}}|p3={{plot_3}}|p4={{plot_4}}"
        "|p5={{plot_5}}|p6={{plot_6}}|p7={{plot_7}}|p8={{plot_8}}|p9={{plot_9}}"
        "|c={{close}}"
    )
    payload["conditions"] = [new_condition]
    payload["name"] = None
    payload.pop("web_hook", None)  # FREE PLAN: no webhook entitlement
    for k in ("condition", "complexity", "type", "kinds", "cross_interval",
              "expiration_policy", "pro_symbol", "presentation_data",
              "mutable_study_data"):
        payload.pop(k, None)
    return payload


def main() -> int:
    cookies_file = Path(sys.argv[1])
    run_all = "--all" in sys.argv
    cookies = load_cookies(cookies_file)

    captures = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    cap = captures[0]
    captured_url = cap["url"]
    base_payload = json.loads(cap.get("post_data") or "{}").get("payload", {})
    pine_condition = json.loads(PINE_TEMPLATE_PATH.read_text(encoding="utf-8"))["condition"]

    hdrs = {"Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/chart/",
            "Content-Type": "text/plain;charset=UTF-8"}
    json_hdrs = {"Origin": "https://www.tradingview.com",
                 "Referer": "https://www.tradingview.com/chart/",
                 "Content-Type": "application/json"}

    top_5 = json.loads(TOP_5_PATH.read_text(encoding="utf-8"))["top_5"]

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
        ctx.add_cookies(cookies)
        api = ctx.request

        # inventory to skip duplicates
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=30_000)
        existing = set()
        obj = r.json()
        for a in (obj.get("r") or []):
            cond = a.get("condition") or {}
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != "PUB;56f0fb74de7f4eed9325b987428b727e":
                continue
            existing.add(str(a.get("resolution")))

        jobs = []
        for sym in top_5:
            tfs = TARGET_TFS if run_all else ["5"]
            for res_str in tfs:
                jobs.append((sym, res_str))

        ok = fail = skip = 0
        for sym, res_str in jobs:
            if res_str in existing and not run_all:
                print(f"[SKIP] {sym} {TF_LABEL[res_str]} exists")
                skip += 1
                continue
            payload = build_payload(base_payload, pine_condition, sym, res_str)
            try:
                rr = api.post(captured_url, data=json.dumps({"payload": payload}),
                              headers=hdrs, timeout=30_000)
                txt = rr.text()[:220]
                if rr.status == 200 and '"s":"ok"' in txt:
                    aid = None
                    try:
                        aid = rr.json().get("r", {}).get("alert_id")
                    except Exception:
                        pass
                    print(f"[OK]   {sym} {TF_LABEL[res_str]} aid={aid}", flush=True)
                    ok += 1
                else:
                    print(f"[FAIL] {sym} {TF_LABEL[res_str]}: {txt}", flush=True)
                    fail += 1
                    if not run_all:
                        print("-> single test failed; aborting (fix before --all)")
                        ctx.close()
                        return 1
            except Exception as e:
                print(f"[ERR]  {sym} {TF_LABEL[res_str]}: {e}", flush=True)
                fail += 1
            import time
            time.sleep(0.6)

        # verify
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=30_000)
        alerts = r.json().get("r") or []
        active = sum(1 for a in alerts if a.get("active"))
        print(f"\n=== created={ok} failed={fail} skipped={skip} | total={len(alerts)} active={active} ===")
        ctx.close()
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
