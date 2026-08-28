"""Reconfigure TV alerts to multi-TF on top 5 pairs.

1. Read top 5 from reports/top_5_pairs.json
2. List existing Rocket Prime alerts
3. Delete H1 alerts on the 14 pairs NOT in top 5 (free quota)
4. For top 5 pairs: ensure M5 + M15 + H1 + H4 alerts exist
5. Verify final state: 5 pairs × 4 TFs = 20 alerts
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

TARGET_TFS = ["5", "15", "60", "240"]  # M5, M15, H1, H4
TF_LABEL = {"5": "M5", "15": "M15", "60": "H1", "240": "H4"}


def _exchange(s):
    if s in ("BTCUSD", "ETHUSD"): return "BINANCE"
    if s == "XTIUSD": return "FX"
    if s == "XBRUSD": return "FX"
    if s == "XNGUSD": return "NYMEX_DL"
    return "OANDA"


def _broker_sym(s):
    if s == "XTIUSD": return "USOIL"
    if s == "XBRUSD": return "UKOIL"
    if s == "XNGUSD": return "NG1!"
    return s


def _currency(s):
    if s.startswith(("XAU", "XAG")) or s in ("BTCUSD", "ETHUSD", "XTIUSD", "XBRUSD", "XNGUSD"):
        return "USD"
    return s[-3:]


def _build_symbol_field(ex, bs, cur):
    obj = {"currency-id": cur, "session": "regular", "symbol": f"{ex}:{bs}"}
    return "=" + json.dumps(obj, separators=(",", ":"))


def main():
    if not TOP_5_PATH.exists():
        print(f"FATAL: run rank_top_pairs.py first. Missing {TOP_5_PATH}")
        return 1
    top_5 = json.loads(TOP_5_PATH.read_text(encoding="utf-8"))["top_5"]
    print(f"Top 5 pairs: {top_5}")

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

    # Build target full-symbol set for top 5
    target_full_syms = set()
    for sym in top_5:
        ex, bs = _exchange(sym), _broker_sym(sym)
        target_full_syms.add(f"{ex}:{bs}")

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
        rp_existing = []  # (alert_id, full_sym, resolution)
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
            rp_existing.append((a["alert_id"], full, str(a.get("resolution", ""))))
        print(f"\n=== Existing Rocket Prime alerts: {len(rp_existing)} ===")
        for aid, fs, res in rp_existing:
            print(f"  [{aid}] {fs} res={res}")

        # 2. Delete alerts NOT in top 5 + alerts on top 5 with non-target TFs
        delete_ids = []
        keep_set = set()  # (full_sym, res) we already have for top 5
        for aid, fs, res in rp_existing:
            if fs in target_full_syms and res in TARGET_TFS:
                keep_set.add((fs, res))
            else:
                delete_ids.append(aid)

        if delete_ids:
            print(f"\n=== Deleting {len(delete_ids)} alerts (non-top-5 or non-target-TF) ===")
            BATCH = 25
            for i in range(0, len(delete_ids), BATCH):
                chunk = delete_ids[i:i + BATCH]
                rr = api.post("https://pricealerts.tradingview.com/delete_alerts",
                              data=json.dumps({"payload": {"alert_ids": chunk}}),
                              headers=json_hdrs, timeout=15_000)
                ok = rr.status == 200 and '"s":"ok"' in rr.text()
                print(f"  delete batch ({len(chunk)}): {'OK' if ok else 'FAIL'}")
                time.sleep(0.4)

        # 3. Compute missing (top_5 × 4 TFs minus what we kept)
        missing = []
        for sym in top_5:
            ex, bs, cur = _exchange(sym), _broker_sym(sym), _currency(sym)
            full = f"{ex}:{bs}"
            for res_str in TARGET_TFS:
                if (full, res_str) not in keep_set:
                    missing.append({"symbol": sym, "ex": ex, "bs": bs, "cur": cur,
                                     "full": full, "res": res_str})

        print(f"\n=== Missing alerts to create: {len(missing)} ===")
        for m in missing:
            print(f"  {m['symbol']} {TF_LABEL.get(m['res'], m['res'])}")

        # 4. Create missing
        success = 0
        failed = 0
        time.sleep(1)
        for m in missing:
            symbol_field = _build_symbol_field(m["ex"], m["bs"], m["cur"])
            exp = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            new_condition = copy.deepcopy(pine_condition)
            new_condition["resolution"] = m["res"]
            payload = copy.deepcopy(base_payload)
            payload["symbol"] = symbol_field
            payload["resolution"] = m["res"]
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
                    success += 1
                    aid = None
                    try: aid = rr.json().get("r", {}).get("alert_id")
                    except Exception: pass
                    print(f"  [OK]   {m['symbol']} {TF_LABEL[m['res']]}  alert_id={aid}")
                else:
                    failed += 1
                    print(f"  [FAIL] {m['symbol']} {TF_LABEL[m['res']]}  {txt[:120]}")
            except Exception as e:
                failed += 1
                print(f"  [ERR]  {m['symbol']} {TF_LABEL[m['res']]}  {e}")
            time.sleep(0.4)

        # 5. Final verification
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
        print(f"\n=== Final state: {len(rp)} Rocket Prime alerts ===")
        for fs, res in rp:
            print(f"  {fs:<25} {TF_LABEL.get(res, res)}")

        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
