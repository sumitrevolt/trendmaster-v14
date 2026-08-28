"""Find ALL inactive Rocket Prime alerts + reactivate via /restart_alerts API."""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE = Path(r"C:\Users\Ratanshila\Documents\autmated trading\tools\tv_alert_setup\_browser_profile")
ROCKET = "PUB;56f0fb74de7f4eed9325b987428b727e"
HDRS = {"Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/chart/",
        "Content-Type": "application/json"}

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request

    r = api.post("https://pricealerts.tradingview.com/list_alerts",
                 data=json.dumps({"payload": {"limit": 5000}}), headers=HDRS, timeout=15_000)
    alerts = r.json().get("r", [])
    rp = []
    for a in alerts:
        cond = a.get("condition") or {}
        if cond.get("type") != "pine_alert":
            continue
        if ((cond.get("series") or [{}])[0].get("pine_id")) != ROCKET:
            continue
        sym = a.get("symbol", "")
        try:
            sym = json.loads(sym[1:]).get("symbol", sym) if sym.startswith("=") else sym
        except Exception:
            pass
        rp.append({"id": a["alert_id"], "sym": sym, "res": a["resolution"],
                   "active": a["active"], "stop": a.get("last_stop_reason"),
                   "err": a.get("last_error"), "fires": a.get("fire_count", 0)})

    inactive = [a for a in rp if not a["active"]]
    print(f"=== Rocket Prime: {len(rp)} total, {len(inactive)} INACTIVE ===")
    for a in inactive:
        print(f"  INACTIVE: id={a['id']}  {a['sym']:<25} res={a['res']:<5} stop={a['stop']} fires={a['fires']} err={a['err']}")

    if inactive:
        ids = [a["id"] for a in inactive]
        rr = api.post("https://pricealerts.tradingview.com/restart_alerts",
                      data=json.dumps({"payload": {"alert_ids": ids}}),
                      headers=HDRS, timeout=15_000)
        print(f"\n  restart_alerts({len(ids)}): status={rr.status} body={rr.text()[:200]}")

    time.sleep(2)
    r2 = api.post("https://pricealerts.tradingview.com/list_alerts",
                  data=json.dumps({"payload": {"limit": 5000}}), headers=HDRS, timeout=15_000)
    rp2 = [a for a in r2.json().get("r", [])
           if (a.get("condition") or {}).get("type") == "pine_alert"
           and ((a.get("condition") or {}).get("series") or [{}])[0].get("pine_id") == ROCKET]
    act = sum(1 for a in rp2 if a["active"])
    print(f"\n=== AFTER: {act}/{len(rp2)} active ===")
    ctx.close()
