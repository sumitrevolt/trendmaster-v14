"""Cleanup duplicate / low-priority Rocket Prime alerts and create H1 alerts
for all 19 target pairs.

Strategy: target = 19 H1 alerts, one per pair. Delete everything else
(duplicates, M1, M5/M15/H4 leftovers, EURAUD which isn't in our list).
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
PROFILE_DIR = HERE / "_browser_profile"
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
TARGET_RES = "60"  # H1 only — fits within quota
ROCKET_PRIME_PINE_ID = "PUB;56f0fb74de7f4eed9325b987428b727e"


def _exchange(s):
    if s in ("BTCUSD", "ETHUSD"): return "BINANCE"
    if s == "XTIUSD": return "FX"  # try FX prefix for oils
    if s == "XBRUSD": return "FX"
    if s == "XNGUSD": return "TVC"
    return "OANDA"


def _broker_sym(s):
    if s == "XTIUSD": return "USOIL"
    if s == "XBRUSD": return "UKOIL"
    if s == "XNGUSD": return "NATGASUSD"
    return s


def _currency_for(s):
    if s.startswith(("XAU", "XAG")) or s in ("BTCUSD", "ETHUSD", "XTIUSD", "XBRUSD", "XNGUSD"):
        return "USD"
    return s[-3:] if len(s) >= 3 else "USD"


def _build_symbol_field(exchange, broker_sym, currency):
    obj = {"currency-id": currency, "session": "regular",
           "symbol": f"{exchange}:{broker_sym}"}
    return "=" + json.dumps(obj, separators=(",", ":"))


def main():
    if not CAPTURE_PATH.exists() or not PINE_TEMPLATE_PATH.exists():
        print("FATAL: missing capture or template files")
        return 1

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
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(3)
        api = ctx.request

        # 1. List current alerts
        print("=== Step 1: List current alerts ===")
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])
        print(f"  Total alerts: {len(alerts)}")

        # 2. Identify which Rocket Prime alerts to KEEP vs DELETE
        # Keep: 1 alert per (symbol, H1) for our 19 target pairs
        # Delete: everything else that's a Rocket Prime complex alert
        target_pairs = set()
        for s in SYMBOLS:
            target_pairs.add(f"{_exchange(s)}:{_broker_sym(s)}")

        keep_ids = set()
        delete_ids = []
        kept_pairs = set()  # already-covered (full_symbol)

        # First pass: keep one H1 per target pair
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME_PINE_ID:
                continue  # not our indicator
            sym_raw = a.get("symbol", "")
            try:
                sym_obj = json.loads(sym_raw[1:]) if sym_raw.startswith("=") else {}
                full_sym = sym_obj.get("symbol", "")
            except Exception:
                full_sym = sym_raw
            res = str(a.get("resolution", ""))
            aid = a["alert_id"]

            if full_sym in target_pairs and res == TARGET_RES and full_sym not in kept_pairs:
                keep_ids.add(aid)
                kept_pairs.add(full_sym)
            else:
                delete_ids.append((aid, full_sym, res))

        # Pairs that don't have ANY alert yet
        missing_pairs = [s for s in SYMBOLS
                         if f"{_exchange(s)}:{_broker_sym(s)}" not in kept_pairs]

        print(f"  Keeping H1: {len(keep_ids)} alerts")
        for fp in sorted(kept_pairs):
            print(f"    + {fp}")
        print(f"  To delete: {len(delete_ids)} alerts")
        for aid, fp, res in delete_ids:
            print(f"    - {aid} {fp} res={res}")
        print(f"  Pairs missing any alert: {len(missing_pairs)} -> {missing_pairs}")

        # 3. Delete in batches
        if delete_ids:
            print(f"\n=== Step 2: Delete {len(delete_ids)} alerts ===")
            ids_only = [a[0] for a in delete_ids]
            BATCH = 25
            for i in range(0, len(ids_only), BATCH):
                chunk = ids_only[i:i+BATCH]
                r = api.post("https://pricealerts.tradingview.com/delete_alerts",
                             data=json.dumps({"payload": {"alert_ids": chunk}}),
                             headers=json_hdrs, timeout=15_000)
                txt = r.text()
                if r.status == 200 and '"s":"ok"' in txt:
                    print(f"  [batch ok] deleted {len(chunk)}")
                else:
                    print(f"  [batch FAIL] {txt[:200]}")
                time.sleep(0.4)

        # 4. Create H1 alerts for missing pairs
        if missing_pairs:
            print(f"\n=== Step 3: Create H1 alerts for {len(missing_pairs)} missing pairs ===")
            success = 0
            failed = 0
            fail_details = []
            for sym in missing_pairs:
                ex = _exchange(sym)
                bs = _broker_sym(sym)
                full_sym = f"{ex}:{bs}"
                symbol_field = _build_symbol_field(ex, bs, _currency_for(sym))
                exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

                new_condition = copy.deepcopy(pine_condition)
                new_condition["resolution"] = TARGET_RES

                payload = copy.deepcopy(base_payload)
                payload["symbol"] = symbol_field
                payload["resolution"] = TARGET_RES
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
                    r = api.post(captured_url, data=json.dumps(body), headers=create_hdrs, timeout=15_000)
                    txt = r.text()[:300]
                    if r.status == 200 and '"s":"ok"' in txt:
                        success += 1
                        aid = None
                        try:
                            aid = r.json().get("r", {}).get("alert_id")
                        except Exception:
                            pass
                        print(f"  [OK]   {sym:<8} ({full_sym})  alert_id={aid}")
                    else:
                        failed += 1
                        fail_details.append((sym, txt))
                        print(f"  [FAIL] {sym:<8} ({full_sym})  {txt[:150]}")
                except Exception as e:
                    failed += 1
                    print(f"  [ERR]  {sym:<8} ({full_sym})  {e}")
                time.sleep(0.4)

            print(f"\n  Created: {success}  Failed: {failed}")
            if fail_details:
                print("\n  Fail details:")
                for sym, txt in fail_details:
                    print(f"    {sym}: {txt[:120]}")

        # 5. Final verification — list active Rocket Prime alerts
        print(f"\n=== Step 4: Final verification ===")
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r", [])
        active_rp_h1 = []
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
                full_sym = sym_obj.get("symbol", "")
            except Exception:
                full_sym = sym_raw
            res = str(a.get("resolution", ""))
            active = a.get("active")
            wh = a.get("web_hook") or ""
            ok_wh = "shadow-cosmos-unending" in wh
            active_rp_h1.append((full_sym, res, active, ok_wh))
        active_rp_h1.sort()
        print(f"  Total Rocket Prime alerts now: {len(active_rp_h1)}")
        for fs, res, act, wh in active_rp_h1:
            mark = "✓" if (act and wh and res == TARGET_RES) else "x"
            print(f"  [{mark}] {fs:<25} res={res} active={act} webhook_ok={wh}")

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
