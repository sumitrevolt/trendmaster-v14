"""Pipeline routing test - DEFAULTS TO DRYRUN.

Hard-guard against the 2026-05-06 incident where this script (without dryrun)
opened 6 unintended trades. By default uses ?dryrun=1; live writes require
the explicit --i-mean-it flag AND interactive confirmation phrase.
"""
import sys
import urllib.request as u
import json

PAIRS = ["XAUUSD", "EURUSD", "USDJPY", "GBPUSD", "BTCUSD"]
TFS = [("5", "M5"), ("60", "H1")]
SECRET = "5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14"
BASE = "https://shadow-cosmos-unending.ngrok-free.dev/tv-signal"

LIVE = "--i-mean-it" in sys.argv
if LIVE:
    print("\n!!  LIVE MODE - these signals WILL trigger real MT5 trades.")
    print("    2026-05-06 incident: this script opened 6 unintended trades.")
    confirm = input("    Type EXACTLY  YES place real trades  to proceed: ")
    if confirm != "YES place real trades":
        print("    Aborted - did not type the exact phrase.")
        sys.exit(2)
    print("    [OK] Live confirmed. Proceeding...\n")
else:
    print("=== DRYRUN MODE (default) - no MT5 writes will happen ===")
    print("    Pass --i-mean-it AND type the exact confirm phrase to go live.\n")

ok, fail = 0, 0
for sym in PAIRS:
    for tf, label in TFS:
        dryrun_param = "" if LIVE else "&dryrun=1"
        url = f"{BASE}?secret={SECRET}&symbol={sym}&tf={tf}{dryrun_param}"
        body = b"Buy Observation @ 1.0"
        req = u.Request(url, data=body,
                        headers={"Content-Type": "text/plain"}, method="POST")
        try:
            r = u.urlopen(req, timeout=8)
            data = json.loads(r.read().decode())
            tag = "LIVE" if LIVE else "DRY"
            print(f"  [{tag}] {sym:7} {label:>3}: HTTP {r.status}  status={data.get('status')}  dir={data.get('direction','-')}")
            ok += 1
        except Exception as e:
            print(f"  [FAIL] {sym:7} {label:>3}: {e}")
            fail += 1

print(f"\n{'LIVE' if LIVE else 'DRYRUN'} done: {ok} ok, {fail} fail")
