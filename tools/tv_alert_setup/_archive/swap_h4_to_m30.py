"""Swap H4 -> M30 for top 5 pairs.

User wants: M5, M15, M30, H1 (replacing H4 with M30).
Delete the 5 H4 alerts on top 5 pairs, then create 5 M30 alerts.
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

SECRET = None
for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
    if line.startswith("TV_WEBHOOK_SECRET"):
        SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
WEBHOOK_URL = f"https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret={SECRET}"


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


def main():
    top_5 = json.loads(TOP_5_PATH.read_text(encoding="utf-8"))["top_5"]
    print(f"Top 5: {top_5}")

    target_full = {f"{_ex(s)}:{_bs(s)}" for s in top_5}

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

        # 1. List existing
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])

        # 2. Find H4 alerts on top 5 pairs
        h4_to_delete = []
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            if str(a.get("resolution", "")) != "240":
                continue
            sym_raw = a.get("symbol", "")
            try:
                full = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
            except Exception:
                continue
            if full in target_full:
                h4_to_delete.append((a["alert_id"], full))

        print(f"\n=== Deleting {len(h4_to_delete)} H4 alerts ===")
        for aid, fs in h4_to_delete:
            print(f"  {aid} {fs}")
        if h4_to_delete:
            ids = [a[0] for a in h4_to_delete]
            rr = api.post("https://pricealerts.tradingview.com/delete_alerts",
                          data=json.dumps({"payload": {"alert_ids": ids}}),
                          headers=json_hdrs, timeout=15_000)
            ok = rr.status == 200 and '"s":"ok"' in rr.text()
            print(f"  delete: {'OK' if ok else 'FAIL ' + rr.text()[:120]}")

        # 3. Create M30 alerts for top 5
        time.sleep(1)
        print(f"\n=== Creating 5 M30 alerts ===")
        for sym in top_5:
            ex, bs, cur = _ex(sym), _bs(sym), _cur(sym)
            symbol_field = _build_symbol_field(ex, bs, cur)
            exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            new_condition = copy.deepcopy(pine_condition)
            new_condition["resolution"] = "30"
            payload = copy.deepcopy(base_payload)
            payload["symbol"] = symbol_field
            payload["resolution"] = "30"
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
                    aid = None
                    try: aid = rr.json().get("r", {}).get("alert_id")
                    except Exception: pass
                    print(f"  [OK]   {sym} M30  alert_id={aid}")
                else:
                    print(f"  [FAIL] {sym} M30  {txt[:120]}")
            except Exception as e:
                print(f"  [ERR]  {sym} M30  {e}")
            time.sleep(0.4)

        # 4. Final state
        time.sleep(1)
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts2 = r.json().get("r", [])
        rp = []
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
            rp.append((full, str(a.get("resolution", ""))))
        rp.sort()
        TF_LABEL = {"5": "M5", "15": "M15", "30": "M30", "60": "H1", "240": "H4"}
        print(f"\n=== Final state: {len(rp)} alerts ===")
        for fs, res in rp:
            print(f"  {fs:<25} {TF_LABEL.get(res, res)}")
        ctx.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
