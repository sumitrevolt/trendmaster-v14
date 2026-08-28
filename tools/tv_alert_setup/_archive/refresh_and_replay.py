"""One-shot: refresh TV inventory, compute missing, replay all 76 alerts."""
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
PROFILE_DIR = HERE / "_browser_profile"
INVENTORY_PATH = HERE / "alerts_full_inventory.json"
CAPTURE_PATH = HERE / "capture_create_post.json"
PINE_TEMPLATE_PATH = HERE / "pine_alert_template.json"

SYMBOLS = [
    "XAUUSD", "XAGUSD",
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
    "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY",
    "CADJPY", "EURGBP",
    "BTCUSD", "ETHUSD",
    "XTIUSD", "XBRUSD", "XNGUSD",
]
TF_MAP = {"M5": "5", "M15": "15", "H1": "60", "H4": "240"}
ROCKET_PRIME_PINE_ID = "PUB;56f0fb74de7f4eed9325b987428b727e"


def _exchange(s):
    if s in ("BTCUSD", "ETHUSD"): return "BINANCE"
    if s in ("XTIUSD", "XBRUSD", "XNGUSD"): return "TVC"
    return "OANDA"


def _broker_sym(s):
    return {"XTIUSD": "USOIL", "XBRUSD": "UKOIL", "XNGUSD": "NATGASUSD"}.get(s, s)


def _currency_for(symbol):
    if symbol.startswith("XAU") or symbol.startswith("XAG"):
        return "USD"
    if symbol in ("BTCUSD", "ETHUSD", "XTIUSD", "XBRUSD", "XNGUSD"):
        return "USD"
    return symbol[-3:] if len(symbol) >= 3 else "USD"


def _build_symbol_field(exchange, broker_sym, currency):
    obj = {"currency-id": currency, "session": "regular",
           "symbol": f"{exchange}:{broker_sym}"}
    return "=" + json.dumps(obj, separators=(",", ":"))


def main():
    if not CAPTURE_PATH.exists() or not PINE_TEMPLATE_PATH.exists():
        print(f"FATAL: missing capture_create_post.json or pine_alert_template.json")
        return 1

    captures = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    cap = captures[0]
    captured_url = cap["url"]
    captured_headers = cap.get("headers") or {}
    captured_body = json.loads(cap.get("post_data") or "{}")
    base_payload = captured_body.get("payload", {})

    pine_template = json.loads(PINE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    pine_condition = pine_template["condition"]

    hdrs = {k: v for k, v in captured_headers.items()
            if k.lower() not in ("host", "content-length", "cookie", "connection",
                                  "accept-encoding")}
    hdrs["Origin"] = "https://www.tradingview.com"
    hdrs["Referer"] = "https://www.tradingview.com/"
    hdrs["Content-Type"] = "text/plain;charset=UTF-8"

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(3)
        api = ctx.request

        # Step 1: refresh inventory
        print("=== Refreshing TV alert inventory ===")
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers={"Origin": "https://www.tradingview.com",
                              "Referer": "https://www.tradingview.com/chart/",
                              "Content-Type": "application/json"},
                     timeout=15_000)
        data = r.json()
        INVENTORY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        alerts = data.get("r", [])
        print(f"  Inventory: {len(alerts)} alerts total")

        # Step 2: compute existing Rocket Prime coverage
        existing = set()
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME_PINE_ID:
                continue
            sym_raw = a.get("symbol", "")
            try:
                sym_obj = json.loads(sym_raw[1:]) if sym_raw.startswith("=") else {}
                sym = sym_obj.get("symbol", "")
            except Exception:
                sym = sym_raw
            existing.add((sym, str(a.get("resolution", ""))))
        print(f"  Existing Rocket Prime alerts: {len(existing)}")

        # Step 3: compute missing
        missing = []
        for sym in SYMBOLS:
            full_sym = f"{_exchange(sym)}:{_broker_sym(sym)}"
            for tf, res in TF_MAP.items():
                if (full_sym, res) not in existing:
                    missing.append({
                        "symbol": sym, "exchange": _exchange(sym),
                        "broker_symbol": _broker_sym(sym),
                        "full_symbol": full_sym,
                        "tf": tf, "resolution": res,
                    })
        print(f"  Missing: {len(missing)}/76")
        print()

        # Step 4: create each missing alert
        print(f"=== Creating {len(missing)} alerts ===")
        success = 0
        failed = 0
        fail_reasons = {}
        new_ids = []

        for i, m in enumerate(missing):
            symbol_field = _build_symbol_field(
                m["exchange"], m["broker_symbol"], _currency_for(m["symbol"])
            )
            resolution = m["resolution"]
            exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

            new_condition = copy.deepcopy(pine_condition)
            new_condition["resolution"] = resolution

            payload = copy.deepcopy(base_payload)
            payload["symbol"] = symbol_field
            payload["resolution"] = resolution
            payload["expiration"] = exp
            payload["message"] = ""
            payload["conditions"] = [new_condition]
            payload["name"] = None
            payload["web_hook"] = "https://shadow-cosmos-unending.ngrok-free.dev/tv-signal"
            for k in ("condition", "complexity", "type", "kinds", "cross_interval",
                      "expiration_policy", "pro_symbol", "presentation_data",
                      "mutable_study_data"):
                payload.pop(k, None)

            body = {"payload": payload}

            try:
                r = api.post(captured_url, data=json.dumps(body), headers=hdrs, timeout=15_000)
                txt = r.text()[:300]
                if r.status == 200 and '"s":"ok"' in txt:
                    success += 1
                    aid = None
                    try:
                        aid = r.json().get("r", {}).get("alert_id")
                    except Exception:
                        pass
                    new_ids.append(aid)
                    print(f"  [OK   {i+1}/{len(missing)}] {m['symbol']:<8} {m['tf']:<4}  alert_id={aid}")
                else:
                    failed += 1
                    # Extract short reason
                    short_reason = txt[:120]
                    fail_reasons[short_reason] = fail_reasons.get(short_reason, 0) + 1
                    print(f"  [FAIL {i+1}/{len(missing)}] {m['symbol']:<8} {m['tf']:<4}  {txt[:150]}")
            except Exception as e:
                failed += 1
                print(f"  [ERR  {i+1}/{len(missing)}] {m['symbol']:<8} {m['tf']:<4}  {e}")
            time.sleep(0.4)

        ctx.close()

    print()
    print(f"=== DONE: created={success}  failed={failed}  total={len(missing)} ===")
    if fail_reasons:
        print(f"\nUnique failure reasons:")
        for reason, count in sorted(fail_reasons.items(), key=lambda x: -x[1]):
            print(f"  [{count}x] {reason}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
