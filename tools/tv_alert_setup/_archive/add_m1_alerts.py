"""Add M1 Rocket Prime alerts on top 5 pairs for fastest signal arrival.

TV API blocks instant-tick frequency for Pine alerts. M1 (1-minute bar close)
is the fastest legal config — alert fires within ~60s of indicator condition
true. Currently we have M5+M15+M30+H1 = 20 alerts. Adding M1 brings total
to 25 (at TV free plan quota wall).
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

        success = 0
        failed = 0
        quota_hit = False
        for sym in top_5:
            ex, bs, cur = _ex(sym), _bs(sym), _cur(sym)
            symbol_field = _build_symbol_field(ex, bs, cur)
            exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            new_condition = copy.deepcopy(pine_condition)
            new_condition["resolution"] = "1"
            payload = copy.deepcopy(base_payload)
            payload["symbol"] = symbol_field
            payload["resolution"] = "1"
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
                txt = rr.text()[:300]
                if rr.status == 200 and '"s":"ok"' in txt:
                    success += 1
                    aid = None
                    try: aid = rr.json().get("r", {}).get("alert_id")
                    except Exception: pass
                    print(f"  [OK]   {sym} M1 aid={aid}", flush=True)
                elif "max_complex_alerts_count_exceeded" in txt:
                    print(f"  [QUOTA] {sym} M1 — TV plan limit reached. Stopping.", flush=True)
                    quota_hit = True
                    break
                else:
                    failed += 1
                    print(f"  [FAIL] {sym} M1: {txt[:140]}", flush=True)
            except Exception as e:
                failed += 1
                print(f"  [ERR] {sym} M1: {e}", flush=True)
            time.sleep(0.5)

        print(f"\n=== Created {success}, failed {failed}, quota_hit={quota_hit} ===", flush=True)

        # Final state
        time.sleep(1)
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r") or []
        rp = []
        for a in alerts:
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
        TF_LABEL = {"1": "M1", "5": "M5", "15": "M15", "30": "M30", "60": "H1", "240": "H4"}
        print(f"\n=== Final Rocket Prime alerts: {len(rp)} ===", flush=True)
        for fs, res in rp:
            print(f"  {fs:<25} {TF_LABEL.get(res, res)}", flush=True)
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
