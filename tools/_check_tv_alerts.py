"""Check status of TradingView alerts via TV's authenticated API."""
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PROFILE_DIR = HERE / "tv_alert_setup" / "_browser_profile"
GOOD_URL = "https://shadow-cosmos-unending.ngrok-free.dev/tv-signal"

print(f"Profile dir: {PROFILE_DIR}")
print(f"Profile exists: {PROFILE_DIR.exists()}")
print()

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE_DIR), headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request
    hdrs = {
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/chart/",
        "Content-Type": "application/json",
    }
    r = api.post(
        "https://pricealerts.tradingview.com/list_alerts",
        data=json.dumps({"payload": {"limit": 5000}}),
        headers=hdrs,
        timeout=15_000,
    )
    try:
        alerts = r.json().get("r", [])
    except Exception as e:
        print(f"Could not parse list_alerts response: {e}")
        print(f"Status: {r.status}")
        print(f"Body (first 500): {r.text()[:500]}")
        ctx.close()
        sys.exit(1)

    print(f"Total alerts: {len(alerts)}")
    print()

    if not alerts:
        print("=== NO ALERTS EXIST IN TV ACCOUNT ===")
        print("This is why no TV signals are arriving.")
        print("Need to recreate alerts via tools/tv_alert_setup/replay_pine_alerts.py")
        ctx.close()
        sys.exit(0)

    # Categorise by status
    active = []
    inactive = []
    no_webhook = []
    wrong_webhook = []
    has_errors = []
    by_symbol = {}

    for a in alerts:
        aid = a.get("alert_id")
        sym_raw = a.get("symbol", "")
        try:
            sym_obj = json.loads(sym_raw[1:]) if sym_raw.startswith("=") else {}
            sym = sym_obj.get("symbol", sym_raw)
        except Exception:
            sym = sym_raw
        web_hook = a.get("web_hook") or ""
        active_flag = a.get("active")
        last_error = a.get("last_error")
        last_fire = a.get("last_fire_time")
        res = str(a.get("resolution", ""))

        by_symbol.setdefault(sym, []).append((res, active_flag, last_fire, last_error))
        if not web_hook:
            no_webhook.append((aid, sym, res))
        elif GOOD_URL not in web_hook:
            wrong_webhook.append((aid, sym, res, web_hook[:60]))
        else:
            if active_flag:
                active.append((aid, sym, res, last_fire))
            else:
                inactive.append((aid, sym, res))
        if last_error:
            has_errors.append((aid, sym, res, str(last_error)[:100]))

    print(f"=== Active alerts (with correct webhook): {len(active)} ===")
    for aid, sym, res, lf in active[:20]:
        last = ""
        if lf:
            try:
                last = f" last_fire={int(time.time()) - int(lf)}s ago"
            except Exception:
                pass
        print(f"  [{aid}] {sym:<12} res={res}{last}")
    print()
    print(f"=== Inactive alerts: {len(inactive)} ===")
    for aid, sym, res in inactive[:10]:
        print(f"  [{aid}] {sym:<12} res={res}")
    print()
    if no_webhook:
        print(f"=== NO WEBHOOK: {len(no_webhook)} (these will never fire) ===")
        for aid, sym, res in no_webhook[:10]:
            print(f"  [{aid}] {sym:<12} res={res}")
        print()
    if wrong_webhook:
        print(f"=== WRONG WEBHOOK URL: {len(wrong_webhook)} ===")
        for aid, sym, res, hook in wrong_webhook[:10]:
            print(f"  [{aid}] {sym:<12} res={res}  -> {hook!r}")
        print()
    if has_errors:
        print(f"=== ALERTS WITH last_error: {len(has_errors)} ===")
        for aid, sym, res, err in has_errors[:10]:
            print(f"  [{aid}] {sym:<12} res={res}  err={err}")
    print()
    print(f"=== Symbol coverage ({len(by_symbol)} symbols) ===")
    for sym, info_list in sorted(by_symbol.items()):
        tfs = sorted({i[0] for i in info_list})
        print(f"  {sym:<12} TFs: {tfs}")

    ctx.close()
