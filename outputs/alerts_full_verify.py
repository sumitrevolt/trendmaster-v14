"""Comprehensive TV alert health check — verify all 20 are properly set."""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE = Path(r"C:\Users\Ratanshila\Documents\autmated trading\tools\tv_alert_setup\_browser_profile")
ROCKET = "PUB;56f0fb74de7f4eed9325b987428b727e"
EXPECTED_PAIRS = {"XAUUSD", "EURUSD", "USDJPY", "GBPUSD", "BTCUSD"}
EXPECTED_TFS = {"5", "15", "30", "60"}  # M5/M15/M30/H1

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
                          "Content-Type": "application/json"}, timeout=20_000)
    alerts = r.json().get("r", [])
    rp = []
    for a in alerts:
        cond = a.get("condition") or {}
        if cond.get("type") != "pine_alert":
            continue
        if ((cond.get("series") or [{}])[0].get("pine_id")) != ROCKET:
            continue
        sym_raw = a.get("symbol", "")
        try:
            sym_full = json.loads(sym_raw[1:]).get("symbol", sym_raw) if sym_raw.startswith("=") else sym_raw
        except Exception:
            sym_full = sym_raw
        sym_clean = sym_full.split(":")[-1] if ":" in sym_full else sym_full
        # Treat BTCUSDT as BTCUSD for matching
        sym_clean = sym_clean.replace("BTCUSDT", "BTCUSD")
        rp.append({
            "id": a["alert_id"], "sym_full": sym_full, "sym": sym_clean,
            "res": str(a["resolution"]), "active": a["active"],
            "stop": a.get("last_stop_reason"), "fires": a.get("fire_count", 0),
            "expiration": a.get("expiration", "")[:10] if a.get("expiration") else "",
            "web_hook": a.get("web_hook") or "",
            "freq": (cond.get("frequency", "default")),
            "msg_len": len(a.get("message") or ""),
        })

    # Build coverage matrix
    cov = {(p, t): None for p in EXPECTED_PAIRS for t in EXPECTED_TFS}
    extras = []
    for a in rp:
        key = (a["sym"], a["res"])
        if key in cov:
            cov[key] = a
        else:
            extras.append(a)

    print(f"=== {len(rp)} Rocket Prime alerts (expected: 20) ===\n")

    print("--- Coverage matrix (5 pairs x 4 TFs) ---")
    print(f"  {'Pair':<8} {'M5':<8} {'M15':<8} {'M30':<8} {'H1':<8}")
    for p in sorted(EXPECTED_PAIRS):
        row = [p]
        for t in ("5", "15", "30", "60"):
            a = cov.get((p, t))
            if a is None:
                row.append("MISSING")
            elif not a["active"]:
                row.append("INACTIVE")
            else:
                row.append("OK")
        print(f"  {row[0]:<8} {row[1]:<8} {row[2]:<8} {row[3]:<8} {row[4]:<8}")

    if extras:
        print(f"\n--- {len(extras)} extra (not in 5x4) ---")
        for e in extras:
            print(f"  {e['sym_full']} res={e['res']} active={e['active']}")

    # URL completeness
    print(f"\n--- URL completeness check ---")
    url_secret = sum(1 for a in rp if "secret=" in a["web_hook"])
    url_sym = sum(1 for a in rp if "symbol=" in a["web_hook"])
    url_tf = sum(1 for a in rp if "tf=" in a["web_hook"])
    print(f"  secret= present: {url_secret}/{len(rp)}")
    print(f"  symbol= present: {url_sym}/{len(rp)}")
    print(f"  tf=     present: {url_tf}/{len(rp)}")

    # Frequency check
    print(f"\n--- Frequency setting ---")
    freqs = {}
    for a in rp:
        f = a["freq"]
        freqs[f] = freqs.get(f, 0) + 1
    for f, c in freqs.items():
        print(f"  freq={f}: {c} alerts  (60=once-per-bar-close, 1=tick)")

    # Expiration health
    print(f"\n--- Expiration ---")
    from datetime import datetime
    today = datetime.now().date()
    near_expiry = [a for a in rp if a["expiration"] and (datetime.strptime(a["expiration"], "%Y-%m-%d").date() - today).days < 5]
    print(f"  Expiring in <5 days: {len(near_expiry)}")
    # Show earliest 3
    rp_with_exp = sorted([a for a in rp if a["expiration"]], key=lambda x: x["expiration"])
    print(f"  Earliest 3: {[(a['sym'], a['res'], a['expiration']) for a in rp_with_exp[:3]]}")
    print(f"  Latest 3:   {[(a['sym'], a['res'], a['expiration']) for a in rp_with_exp[-3:]]}")

    # Message override check (should be empty for Rocket Prime to pass through alert() text)
    print(f"\n--- Message field (empty = good for Rocket Prime) ---")
    msg_empty = sum(1 for a in rp if a["msg_len"] == 0)
    msg_nonempty = sum(1 for a in rp if a["msg_len"] > 0)
    print(f"  Empty message:    {msg_empty}/{len(rp)}  (good)")
    print(f"  Non-empty msg:    {msg_nonempty}/{len(rp)}  (would override indicator's text)")

    # Auto-paused?
    inactive = [a for a in rp if not a["active"]]
    print(f"\n--- Currently active ---")
    print(f"  Active:           {sum(1 for a in rp if a['active'])}/{len(rp)}")
    if inactive:
        for a in inactive:
            print(f"    INACTIVE: {a['sym']} M{a['res']}  stop={a['stop']}")

    ctx.close()
