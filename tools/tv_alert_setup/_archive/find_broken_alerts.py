"""Find alerts with bad webhook URLs or weird messages causing TV delivery failures."""
from __future__ import annotations
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
PROFILE_DIR = HERE / "_browser_profile"
GOOD_URL = "https://shadow-cosmos-unending.ngrok-free.dev/tv-signal"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(user_data_dir=str(PROFILE_DIR), headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.tradingview.com/chart/", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(3)
    api = ctx.request
    hdrs = {"Origin":"https://www.tradingview.com","Referer":"https://www.tradingview.com/chart/","Content-Type":"application/json"}
    r = api.post("https://pricealerts.tradingview.com/list_alerts",
                 data=json.dumps({"payload":{"limit":5000}}), headers=hdrs, timeout=15_000)
    alerts = r.json().get("r", [])
    ctx.close()

print(f"Total alerts: {len(alerts)}\n")

# Categorize
no_webhook = []
wrong_webhook = []
weird_message = []
fire_errors = []
ok_count = 0

for a in alerts:
    aid = a.get("alert_id")
    sym_raw = a.get("symbol","")
    try:
        sym_obj = json.loads(sym_raw[1:]) if sym_raw.startswith("=") else {}
        sym = sym_obj.get("symbol", sym_raw)
    except Exception:
        sym = sym_raw
    res = str(a.get("resolution",""))
    web_hook = a.get("web_hook") or ""
    message = a.get("message") or ""
    last_error = a.get("last_error")
    last_stop = a.get("last_stop_reason")

    issue = None
    if not web_hook:
        no_webhook.append((aid, sym, res))
        issue = "no_webhook"
    elif GOOD_URL not in web_hook:
        wrong_webhook.append((aid, sym, res, web_hook[:80]))
        issue = "wrong_webhook"
    elif message and ("{" in message[:5] or "secret" in message[:30].lower()):
        weird_message.append((aid, sym, res, message[:80]))
        issue = "weird_message_contains_json"
    if last_error:
        fire_errors.append((aid, sym, res, str(last_error)[:120]))
    if not issue:
        ok_count += 1

print(f"=== OK alerts: {ok_count} ===\n")

if wrong_webhook:
    print(f"=== WRONG WEBHOOK URL ({len(wrong_webhook)}) — these will fail TV delivery ===")
    for aid, sym, res, hook in wrong_webhook:
        print(f"  [{aid}] {sym:<25} res={res:<3}  hook: {hook!r}")
    print()

if no_webhook:
    print(f"=== NO WEBHOOK ({len(no_webhook)}) ===")
    for aid, sym, res in no_webhook:
        print(f"  [{aid}] {sym:<25} res={res}")
    print()

if weird_message:
    print(f"=== MESSAGE FIELD HAS JSON OR 'secret' ({len(weird_message)}) ===")
    for aid, sym, res, msg in weird_message:
        print(f"  [{aid}] {sym:<25} res={res:<3}  msg: {msg!r}")
    print()

if fire_errors:
    print(f"=== ALERTS WITH last_error ({len(fire_errors)}) — TV reports delivery failure ===")
    for aid, sym, res, err in fire_errors:
        print(f"  [{aid}] {sym:<25} res={res:<3}  err: {err}")
    print()
