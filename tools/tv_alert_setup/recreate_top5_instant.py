"""RECOVERY: recreate all 20 Rocket Prime alerts (top5 × M5/M15/M30/H1) with frequency=all.

The previous set_instant_frequency.py run deleted all 20 alerts but failed to
recreate them. This rebuilds them from the captured POST template.
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

INSTANT_FREQ = None  # PROBE WINNER 2026-05-06: omit field entirely → instant fire
TARGET_TFS = ["5", "15", "30", "60"]  # M5, M15, M30, H1
TF_LABEL = {"5": "M5", "15": "M15", "30": "M30", "60": "H1"}

SECRET = None
for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
    if line.startswith("TV_WEBHOOK_SECRET"):
        SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
# Webhook URL base (per-alert URL adds &symbol=<SYM>&tf=<RES> below).
# Including symbol + tf in the URL means the receiver doesn't have to text-infer
# them — produces tv_strategy="rocket_prime_text" with confidence 0.95 instead
# of "rocket_prime_inferred" with confidence 0.55-0.85, AND populates the
# tv_timeframe field for per-TF dedup + audit.
WEBHOOK_BASE = f"https://shadow-cosmos-unending.ngrok-free.dev/tv-signal?secret={SECRET}"


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
    print(f"Recreating alerts for top 5: {top_5}", flush=True)

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

        # Inventory existing
        r = api.post("https://pricealerts.tradingview.com/list_alerts",
                     data=json.dumps({"payload": {"limit": 5000}}),
                     headers=json_hdrs, timeout=15_000)
        alerts = r.json().get("r") or []
        existing = set()
        for a in alerts:
            cond = a.get("condition") or {}
            if cond.get("type") != "pine_alert":
                continue
            series = cond.get("series") or [{}]
            if series[0].get("pine_id") != ROCKET_PRIME:
                continue
            sym_raw = a.get("symbol", "")
            try:
                full = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
            except Exception:
                full = sym_raw
            existing.add((full, str(a.get("resolution", ""))))
        print(f"Existing Rocket Prime alerts: {len(existing)}", flush=True)
        for e in sorted(existing):
            print(f"  HAVE: {e}", flush=True)

        success = 0
        failed = 0
        skipped = 0
        for sym in top_5:
            ex, bs, cur = _ex(sym), _bs(sym), _cur(sym)
            full = f"{ex}:{bs}"
            for res_str in TARGET_TFS:
                if (full, res_str) in existing:
                    print(f"  [SKIP] {sym} {TF_LABEL[res_str]} already exists", flush=True)
                    skipped += 1
                    continue
                symbol_field = _build_symbol_field(ex, bs, cur)
                exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                new_condition = copy.deepcopy(pine_condition)
                new_condition["resolution"] = res_str
                if INSTANT_FREQ is None:
                    new_condition.pop("frequency", None)
                else:
                    new_condition["frequency"] = INSTANT_FREQ
                payload = copy.deepcopy(base_payload)
                payload["symbol"] = symbol_field
                payload["resolution"] = res_str
                payload["expiration"] = exp
                # 2026-05-07: Direction extraction via plot placeholders.
                # Rocket Prime's alert() text is "#### {symbol} ####" with no
                # direction word. Pine indicator plots are exposed as {{plot_N}}
                # placeholders (N=0..19). We pipe-pack plots 0-9 into the
                # message body so the receiver can read numerical values per
                # signal. Direction is identified by which plot is non-zero.
                payload["message"] = (
                    "RP|{{ticker}}|tf={{interval}}"
                    "|p0={{plot_0}}|p1={{plot_1}}|p2={{plot_2}}|p3={{plot_3}}|p4={{plot_4}}"
                    "|p5={{plot_5}}|p6={{plot_6}}|p7={{plot_7}}|p8={{plot_8}}|p9={{plot_9}}"
                    "|c={{close}}|t={{timenow}}"
                )
                payload["conditions"] = [new_condition]
                payload["name"] = None
                # Per-alert URL with symbol + tf for receiver routing/dedup
                payload["web_hook"] = f"{WEBHOOK_BASE}&symbol={sym}&tf={res_str}"
                for k in ("condition", "complexity", "type", "kinds", "cross_interval",
                          "expiration_policy", "pro_symbol", "presentation_data",
                          "mutable_study_data"):
                    payload.pop(k, None)
                try:
                    rr = api.post(captured_url, data=json.dumps({"payload": payload}),
                                  headers=create_hdrs, timeout=15_000)
                    txt = rr.text()[:200]
                    if rr.status == 200 and '"s":"ok"' in txt:
                        success += 1
                        aid = None
                        try: aid = rr.json().get("r", {}).get("alert_id")
                        except Exception: pass
                        print(f"  [OK]   {sym} {TF_LABEL[res_str]} freq={INSTANT_FREQ} aid={aid}", flush=True)
                    else:
                        failed += 1
                        print(f"  [FAIL] {sym} {TF_LABEL[res_str]}: {txt[:140]}", flush=True)
                except Exception as e:
                    failed += 1
                    print(f"  [ERR] {sym} {TF_LABEL[res_str]}: {e}", flush=True)
                time.sleep(0.5)

        print(f"\n=== Created {success}, failed {failed}, skipped {skipped} ===", flush=True)

        # Verify
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
            rp.append((full, str(a.get("resolution", "")), cond.get("frequency", "?")))
        rp.sort()
        print(f"\n=== Final Rocket Prime alerts: {len(rp)} ===", flush=True)
        for fs, res, freq in rp:
            print(f"  {fs:<25} {TF_LABEL.get(res, res):<5} freq={freq}", flush=True)
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
