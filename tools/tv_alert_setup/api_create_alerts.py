"""Create the missing pine_alert TV alerts via API — clones user's Rocket Prime
template and adapts symbol + resolution for each (symbol, TF) combo.

Pre-flight:
  - alerts_full_inventory.json exists (from inventory_and_categorize.py)
  - pine_alert_template.json exists (from analyze_pine_alert.py)
  - Operator must be logged in to TV via Playwright persistent profile

Logic per target (symbol, TF):
  1. Skip if already exists (same symbol + resolution + same pine_id)
  2. Else clone template, replace symbol + resolution + (optional) name
  3. POST to /create_alert
  4. Verify via re-listing
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
TEMPLATE_PATH = HERE / "pine_alert_template.json"
INVENTORY_PATH = HERE / "alerts_full_inventory.json"
CONFIG_PATH = HERE / "alerts_config.json"
LOG_PATH = HERE / "api_create.log"

CREATE_URL = "https://pricealerts.tradingview.com/create_alert"
LIST_URL = "https://pricealerts.tradingview.com/list_alerts"

# Target TFs (TV resolution strings)
TF_TO_RES = {"M5": "5", "M15": "15", "H1": "60", "H4": "240"}

# 19 symbols (canonical TrendMaster set)
SYMBOLS = [
    "XAUUSD", "XAGUSD",
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
    "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY", "AUDJPY",
    "CADJPY", "EURGBP",
    "BTCUSD", "ETHUSD",
    "XTIUSD", "XBRUSD", "XNGUSD",
]

# Exchange per symbol (matching what user's existing alerts use)
def _exchange_for(sym: str) -> str:
    if sym in ("BTCUSD", "ETHUSD"):
        return "BINANCE"
    if sym in ("XTIUSD", "XBRUSD", "XNGUSD"):
        return "TVC"
    return "OANDA"


def _broker_sym(sym: str) -> str:
    return {"XTIUSD": "USOIL", "XBRUSD": "UKOIL", "XNGUSD": "NATGASUSD"}.get(sym, sym)


def _build_symbol_field(exchange: str, symbol: str) -> str:
    """Build the TV symbol-encoded field: '={"symbol":"OANDA:EURUSD",...}'."""
    obj = {
        "symbol": f"{exchange}:{symbol}",
        "adjustment": "splits",
        "session": "regular",
        "currency-id": "USD",
    }
    return "=" + json.dumps(obj, separators=(",", ":"))


def _existing_keys(alerts: list[dict], pine_id_filter: str) -> set[tuple[str, str]]:
    """Return set of (clean_symbol, resolution) for alerts using the given pine_id."""
    out = set()
    for a in alerts:
        cond = a.get("condition") or {}
        if cond.get("type") != "pine_alert":
            continue
        # check pine_id matches
        series = cond.get("series") or [{}]
        if series[0].get("pine_id") != pine_id_filter:
            continue
        sym_raw = a.get("symbol", "")
        try:
            sym_obj = json.loads(sym_raw[1:]) if sym_raw.startswith("=") else {}
            sym = sym_obj.get("symbol", "")
        except Exception:
            sym = sym_raw
        out.add((sym, str(a.get("resolution", ""))))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--filter-symbol", default=None)
    ap.add_argument("--filter-tf", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=None)
    args = ap.parse_args()

    if not TEMPLATE_PATH.exists():
        print(f"FATAL: {TEMPLATE_PATH} missing"); return 1
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    pine_id = template["condition"]["series"][0]["pine_id"]
    print(f"Template pine_id: {pine_id}")
    print(f"Template name:    {template.get('name', '?')}")

    # Build target list
    targets = []
    for sym in SYMBOLS:
        if args.filter_symbol and sym != args.filter_symbol.upper():
            continue
        for tf, res in TF_TO_RES.items():
            if args.filter_tf and tf != args.filter_tf.upper():
                continue
            targets.append({"symbol": sym, "tf": tf, "resolution": res,
                            "exchange": _exchange_for(sym),
                            "broker_symbol": _broker_sym(sym)})
    if args.max:
        targets = targets[:args.max]
    print(f"Targets: {len(targets)}")

    log_f = LOG_PATH.open("a", encoding="utf-8")
    log_f.write(f"\n=== api_create run {datetime.now(timezone.utc).isoformat()} ===\n")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE_DIR), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(4)
        api = ctx.request
        hdrs = {"Origin": "https://www.tradingview.com",
                "Referer": "https://www.tradingview.com/chart/",
                "Content-Type": "application/json"}

        # 1) Refresh existing alerts list
        r = api.post(LIST_URL, data=json.dumps({"payload": {"limit": 5000}}), headers=hdrs, timeout=15000)
        if r.status != 200:
            print(f"FATAL: list_alerts returned {r.status}"); ctx.close(); return 2
        existing_alerts = r.json().get("r", [])
        existing_keys = _existing_keys(existing_alerts, pine_id)
        print(f"Existing pine_alerts with this pine_id: {len(existing_keys)}")

        # 2) For each target, create if not exists
        created = 0
        skipped = 0
        failed = 0
        for i, t in enumerate(targets):
            full_sym = f"{t['exchange']}:{t['broker_symbol']}"
            key = (full_sym, t["resolution"])
            if key in existing_keys:
                print(f"  [skip {i+1}/{len(targets)}] {full_sym} res={t['resolution']} (exists)")
                skipped += 1
                continue
            # Clone + minimal adaptation. Keep ALL template fields including
            # presentation_data + complexity since TV might validate them.
            new_alert = copy.deepcopy(template)
            new_alert["symbol"] = _build_symbol_field(t["exchange"], t["broker_symbol"])
            new_alert["pro_symbol"] = new_alert["symbol"]
            new_alert["resolution"] = t["resolution"]
            new_alert["condition"]["resolution"] = t["resolution"]
            for c in new_alert.get("conditions", []):
                c["resolution"] = t["resolution"]
            # Remove ONLY fields TV will assign at create time
            new_alert.pop("alert_id", None)
            new_alert.pop("create_time", None)
            new_alert.pop("last_fire_time", None)
            new_alert.pop("last_fire_bar_time", None)
            new_alert.pop("last_error", None)
            new_alert.pop("last_stop_reason", None)
            # Fresh expiration: 30 days from now
            exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            new_alert["expiration"] = exp
            new_alert["expiration_policy"] = {"time": exp, "policy": "fixed_date"}
            new_alert["name"] = f"Rocket Prime: {t['symbol']} {t['tf']}"
            # Webhook URL: add symbol query param for text-mode parser
            base_url = template.get("web_hook", "https://shadow-cosmos-unending.ngrok-free.dev/tv-signal")
            sep = "&" if "?" in base_url else "?"
            new_alert["web_hook"] = f"{base_url}{sep}symbol={t['symbol']}"

            if args.dry_run:
                print(f"  [DRY {i+1}/{len(targets)}] {full_sym} res={t['resolution']} - would CREATE")
                continue

            body = {"payload": new_alert}
            try:
                r = api.post(CREATE_URL, data=json.dumps(body), headers=hdrs, timeout=15000)
                txt = r.text()[:300]
                if r.status == 200 and '"s":"ok"' in txt:
                    created += 1
                    new_id = None
                    try:
                        new_id = r.json().get("r", {}).get("alert_id")
                    except Exception:
                        pass
                    print(f"  [create ok {i+1}/{len(targets)}] {full_sym} res={t['resolution']} - new id={new_id}")
                    log_f.write(f"OK   {full_sym} res={t['resolution']} alert_id={new_id}\n")
                else:
                    failed += 1
                    print(f"  [FAIL {i+1}/{len(targets)}] {full_sym} res={t['resolution']}: {txt[:200]}")
                    log_f.write(f"FAIL {full_sym} res={t['resolution']}: HTTP {r.status} {txt[:300]}\n")
            except Exception as e:
                failed += 1
                print(f"  [ERR  {i+1}/{len(targets)}] {full_sym} res={t['resolution']}: {e}")
                log_f.write(f"ERR  {full_sym} res={t['resolution']}: {e}\n")
            time.sleep(0.5)  # politeness

        ctx.close()

    log_f.close()
    print(f"\n=== Results: created={created}  skipped={skipped}  failed={failed}  total={len(targets)} ===")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
