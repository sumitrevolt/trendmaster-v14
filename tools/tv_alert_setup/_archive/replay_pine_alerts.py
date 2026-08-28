"""Replay missing Pine alerts via TV's create_alert API.

Strategy:
  - Use captured /create_alert POST (URL + headers) for the validation tokens
  - Replace the body's condition+symbol fields with Pine alert structure
    from one of user's existing Rocket Prime alerts
  - POST for each missing (symbol, TF) combo

Inputs:
  - capture_create_post.json  (URL + headers from real successful POST)
  - pine_alert_template.json  (existing Rocket Prime alert structure)
  - missing_alerts.json       (70 (symbol, TF) combos to create)

Outputs:
  - logs/replay_pine.log      (per-alert result)
  - alerts_done.json          (alert_ids of newly created)
"""
from __future__ import annotations
import argparse
import copy
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "_browser_profile"
CAPTURE_PATH = HERE / "capture_create_post.json"
PINE_TEMPLATE_PATH = HERE / "pine_alert_template.json"
MISSING_PATH = HERE / "missing_alerts.json"
DONE_PATH = HERE / "alerts_done.json"


def _load_done() -> set:
    if DONE_PATH.exists():
        try:
            return set(json.loads(DONE_PATH.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def _save_done(done: set) -> None:
    DONE_PATH.write_text(json.dumps(sorted(done), indent=2, default=str), encoding="utf-8")


def _build_symbol_field(exchange: str, broker_sym: str, currency: str) -> str:
    obj = {
        "currency-id": currency,
        "session": "regular",
        "symbol": f"{exchange}:{broker_sym}",
    }
    return "=" + json.dumps(obj, separators=(",", ":"))


def _currency_for(symbol: str) -> str:
    """Best guess at the symbol's quote currency for the symbol field."""
    # Last 3 chars are typically the quote currency
    if symbol.startswith("XAU") or symbol.startswith("XAG"):
        return "USD"
    if symbol in ("BTCUSD", "ETHUSD"):
        return "USD"
    if symbol in ("XTIUSD", "XBRUSD", "XNGUSD"):
        return "USD"
    return symbol[-3:] if len(symbol) >= 3 else "USD"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=None, help="cap number to process")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--filter-symbol", default=None)
    ap.add_argument("--filter-tf", default=None)
    args = ap.parse_args()

    if not CAPTURE_PATH.exists():
        print(f"FATAL: {CAPTURE_PATH} missing"); return 1
    if not PINE_TEMPLATE_PATH.exists():
        print(f"FATAL: {PINE_TEMPLATE_PATH} missing"); return 1
    if not MISSING_PATH.exists():
        print(f"FATAL: {MISSING_PATH} missing"); return 1

    captures = json.loads(CAPTURE_PATH.read_text(encoding="utf-8"))
    cap = captures[0]  # use first captured POST as template
    captured_url = cap["url"]
    captured_headers = cap.get("headers") or {}
    captured_body = json.loads(cap.get("post_data") or "{}")
    base_payload = captured_body.get("payload", {})

    pine_template = json.loads(PINE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    pine_condition = pine_template["condition"]
    pine_complexity = pine_template.get("complexity", "complex")
    pine_type = pine_template.get("type", "indicator")
    pine_kinds = pine_template.get("kinds", ["regular"])
    pine_presentation_template = pine_template.get("presentation_data", {})

    missing = json.loads(MISSING_PATH.read_text(encoding="utf-8"))
    if args.filter_symbol:
        missing = [m for m in missing if m["symbol"] == args.filter_symbol.upper()]
    if args.filter_tf:
        missing = [m for m in missing if m["tf"] == args.filter_tf.upper()]
    if args.max:
        missing = missing[:args.max]

    print(f"=== Replay Pine alerts ===")
    print(f"  Captured URL: {captured_url[:100]}...")
    print(f"  Pine pine_id: {pine_condition['series'][0].get('pine_id')}")
    print(f"  Missing to create: {len(missing)}")
    print()

    # Sanitize headers — keep TV's exact content-type (text/plain, NOT application/json!)
    hdrs = {k: v for k, v in captured_headers.items()
            if k.lower() not in ("host", "content-length", "cookie", "connection",
                                  "accept-encoding")}
    hdrs["Origin"] = "https://www.tradingview.com"
    hdrs["Referer"] = "https://www.tradingview.com/"
    # IMPORTANT: TV uses text/plain;charset=UTF-8 (we saw this in capture)
    hdrs["Content-Type"] = "text/plain;charset=UTF-8"

    log_path = HERE.parent.parent / "logs" / "replay_pine.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = log_path.open("a", encoding="utf-8")
    log_f.write(f"\n=== replay run {datetime.now(timezone.utc).isoformat()} ===\n")

    done = _load_done()
    success = 0
    failed = 0

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=True
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(3)
        api = ctx.request

        for i, m in enumerate(missing):
            tf_uid = f"{m['full_symbol']}|{m['resolution']}"
            if tf_uid in done:
                print(f"  [skip {i+1}/{len(missing)}] {m['full_symbol']} res={m['resolution']}")
                continue

            # Build the merged payload: captured base + Pine condition
            symbol_field = _build_symbol_field(
                m["exchange"], m["broker_symbol"], _currency_for(m["symbol"])
            )
            resolution = m["resolution"]
            exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

            # Build pine_alert conditions[] from template
            new_condition = copy.deepcopy(pine_condition)
            new_condition["resolution"] = resolution
            # Frequency from template ("60" = once per minute? actually it's freq id)

            # Start from CAPTURED payload (has the right shape: conditions plural,
            # active, ignore_warnings). REPLACE only what differs for pine_alert.
            payload = copy.deepcopy(base_payload)
            payload["symbol"] = symbol_field
            payload["resolution"] = resolution
            payload["expiration"] = exp
            payload["message"] = ""  # Pine controls the message
            payload["conditions"] = [new_condition]   # ← KEY swap: cross → pine_alert
            payload["name"] = None  # captured had null; let TV use indicator default
            # Webhook URL — keep pattern with secret + ticker query params
            secret_url = base_payload.get("web_hook", "")
            # If captured URL has secret + ticker, mirror it; else build fresh
            if "secret=" in secret_url and "ticker" in secret_url:
                payload["web_hook"] = secret_url  # already has the format
            else:
                payload["web_hook"] = f"https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?symbol={m['symbol']}"
            # Remove ANY top-level keys not in the captured payload structure
            for k in ("condition", "complexity", "type", "kinds", "cross_interval",
                      "expiration_policy", "pro_symbol", "presentation_data",
                      "mutable_study_data"):
                payload.pop(k, None)

            body = {"payload": payload}

            if args.dry_run:
                print(f"  [DRY {i+1}/{len(missing)}] {m['full_symbol']} res={resolution}")
                continue

            try:
                r = api.post(captured_url, data=json.dumps(body), headers=hdrs, timeout=15_000)
                txt = r.text()[:400]
                if r.status == 200 and '"s":"ok"' in txt:
                    success += 1
                    new_id = None
                    try:
                        new_id = r.json().get("r", {}).get("alert_id")
                    except Exception:
                        pass
                    done.add(tf_uid)
                    _save_done(done)
                    print(f"  [OK   {i+1}/{len(missing)}] {m['full_symbol']} res={resolution}  alert_id={new_id}")
                    log_f.write(f"OK   {m['full_symbol']} res={resolution} alert_id={new_id}\n")
                else:
                    failed += 1
                    print(f"  [FAIL {i+1}/{len(missing)}] {m['full_symbol']} res={resolution}  {txt[:200]}")
                    log_f.write(f"FAIL {m['full_symbol']} res={resolution}: {txt[:300]}\n")
            except Exception as e:
                failed += 1
                print(f"  [ERR  {i+1}/{len(missing)}] {m['full_symbol']} res={resolution}  {e}")
                log_f.write(f"ERR  {m['full_symbol']} res={resolution}: {e}\n")
            time.sleep(0.4)  # polite

        ctx.close()

    log_f.close()
    print(f"\n=== Done. created={success}  failed={failed}  total={len(missing)} ===")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
