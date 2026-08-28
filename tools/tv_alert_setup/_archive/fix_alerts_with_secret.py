"""Recreate the 13 deleted alerts using the WORKING template,
this time with the secret in the webhook URL."""
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

# Read secret
SECRET = None
for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
    if line.startswith("TV_WEBHOOK_SECRET"):
        SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
if not SECRET:
    sys.exit("FATAL: no secret")

WEBHOOK_URL = f"https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret={SECRET}"
print(f"Webhook URL: {WEBHOOK_URL[:80]}...{WEBHOOK_URL[-12:]}\n")

# All 19 target pairs (we'll skip ones already covered)
SYMBOLS = [
    "XAUUSD", "XAGUSD",
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
    "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY",
    "CADJPY", "EURGBP",
    "BTCUSD", "ETHUSD",
    "XTIUSD", "XBRUSD",
]


def _exchange(s):
    if s in ("BTCUSD", "ETHUSD"): return "BINANCE"
    if s in ("XTIUSD", "XBRUSD"): return "FX"
    return "OANDA"


def _broker_sym(s):
    return {"XTIUSD": "USOIL", "XBRUSD": "UKOIL"}.get(s, s)


def _currency_for(s):
    if s.startswith(("XAU", "XAG")) or s in ("BTCUSD", "ETHUSD", "XTIUSD", "XBRUSD"):
        return "USD"
    return s[-3:]


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

    json_hdrs = {"Origin": "https://www.tradingview.com",
                 "Referer": "https://www.tradingview.com/chart/",
                 "Content-Type": "application/json"}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(3)
        api = ctx.request

        # 1. List existing → find which pairs are already covered
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])
        covered = set()
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
                covered.add(sym_obj.get("symbol", ""))
            except Exception:
                pass
        print(f"=== Already-covered pairs: {len(covered)} ===")
        for c in sorted(covered):
            print(f"  + {c}")

        # 2. Create H1 alerts for all NOT covered
        missing = []
        for sym in SYMBOLS:
            full = f"{_exchange(sym)}:{_broker_sym(sym)}"
            if full not in covered:
                missing.append(sym)
        print(f"\n=== Missing pairs to create: {len(missing)} ===")
        print(f"  {missing}")

        if not missing:
            print("Nothing to do.")
            ctx.close()
            return 0

        # 3. Also need to update the 5 existing alerts to use new webhook URL with secret
        # Check which existing ones already have secret in URL
        need_url_update = []
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            wh = a.get("web_hook") or ""
            if "secret=" not in wh:
                need_url_update.append(a["alert_id"])
        if need_url_update:
            print(f"\nNote: {len(need_url_update)} existing alerts also need URL updated, but skipping for now to avoid loss")

        # 4. Create missing
        print(f"\n=== Creating {len(missing)} alerts with secret URL ===")
        success = 0
        failed = 0

        for i, sym in enumerate(missing):
            ex = _exchange(sym)
            bs = _broker_sym(sym)
            full = f"{ex}:{bs}"
            symbol_field = _build_symbol_field(ex, bs, _currency_for(sym))
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
            payload["web_hook"] = WEBHOOK_URL  # WITH SECRET
            for k in ("condition", "complexity", "type", "kinds", "cross_interval",
                      "expiration_policy", "pro_symbol", "presentation_data",
                      "mutable_study_data"):
                payload.pop(k, None)

            body = {"payload": payload}
            try:
                r = api.post(captured_url, data=json.dumps(body), headers=create_hdrs, timeout=15_000)
                txt = r.text()[:200]
                if r.status == 200 and '"s":"ok"' in txt:
                    success += 1
                    aid = None
                    try:
                        aid = r.json().get("r", {}).get("alert_id")
                    except Exception:
                        pass
                    print(f"  [OK   {i+1}/{len(missing)}] {sym:<8} ({full})  alert_id={aid}")
                else:
                    failed += 1
                    print(f"  [FAIL {i+1}/{len(missing)}] {sym:<8} ({full})  {txt[:100]}")
            except Exception as e:
                failed += 1
                print(f"  [ERR  {i+1}/{len(missing)}] {sym:<8}  {e}")
            time.sleep(0.4)

        print(f"\n=== Done. created={success}  failed={failed} ===")

        # Final verification
        print(f"\n=== Final state ===")
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])
        by_status = {"with_secret": [], "without": []}
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
                sym = sym_obj.get("symbol", "")
            except Exception:
                sym = sym_raw
            wh = a.get("web_hook") or ""
            if "secret=" in wh:
                by_status["with_secret"].append(sym)
            else:
                by_status["without"].append(sym)
        print(f"  with_secret: {len(by_status['with_secret'])}")
        for s in sorted(by_status["with_secret"]):
            print(f"    ✓ {s}")
        print(f"  without_secret: {len(by_status['without'])}")
        for s in sorted(by_status["without"]):
            print(f"    ✗ {s}")

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
