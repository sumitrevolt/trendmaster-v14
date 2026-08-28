"""Trace where the USDJPY signal came from + list ALL TV alerts (not just Rocket Prime)."""
import json
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
PROFILE = ROOT / "tools" / "tv_alert_setup" / "_browser_profile"
ROCKET = "PUB;56f0fb74de7f4eed9325b987428b727e"

print("=== Last 8 webhook signals (with strategy + source) ===")
sig_path = ROOT / "logs" / "tv_signals.jsonl"
lines = sig_path.read_text().splitlines()
for line in lines[-8:]:
    try:
        d = json.loads(line)
        ts = d.get("ts", 0)
        ts_iso = datetime.fromtimestamp(ts).isoformat(timespec="seconds")
        age = (time.time() - ts) / 60
        print(f"  {ts_iso} ({age:5.1f}min ago)  {d.get('symbol'):8} {d.get('direction'):4} "
              f"tf={d.get('tv_timeframe') or '-'}  src={d.get('tv_strategy') or '?'}")
    except Exception:
        pass

print("\n=== ALL TV alerts (full inventory) ===")
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE), headless=True)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request

    r = api.post("https://pricealerts.tradingview.com/list_alerts",
                 data=json.dumps({"payload": {"limit": 5000}}),
                 headers={"Origin": "https://www.tradingview.com",
                          "Referer": "https://www.tradingview.com/chart/",
                          "Content-Type": "application/json"}, timeout=15_000)
    alerts = r.json().get("r", [])
    print(f"  Total alerts on account: {len(alerts)}")

    rp = []
    other = []
    for a in alerts:
        cond = a.get("condition") or {}
        ctype = cond.get("type")
        sym_raw = a.get("symbol", "")
        try:
            sym = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
        except Exception:
            sym = sym_raw
        info = {
            "id": a.get("alert_id"),
            "sym": sym,
            "res": a.get("resolution"),
            "active": a.get("active"),
            "ctype": ctype,
            "name": a.get("name"),
            "last_fire": a.get("last_fire_time"),
            "web_hook": (a.get("web_hook") or "")[:80],
        }
        if ctype == "pine_alert":
            pid = (cond.get("series") or [{}])[0].get("pine_id", "")
            info["pine_id"] = pid
            if pid == ROCKET:
                rp.append(info)
            else:
                other.append({**info, "category": "OTHER_PINE"})
        else:
            other.append({**info, "category": ctype or "unknown"})

    print(f"  Rocket Prime alerts: {len(rp)}")
    print(f"  OTHER alerts: {len(other)}")
    if other:
        print("\n  --- NON-ROCKET-PRIME ALERTS (these should be deleted if you want only RP) ---")
        for o in other:
            print(f"    id={o['id']}  category={o.get('category')}  {o['sym']:<25} "
                  f"res={o['res']:<5} active={o['active']} name={o['name']}")
            print(f"      webhook: {o['web_hook']}")

    ctx.close()
