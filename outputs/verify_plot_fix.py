"""End-to-end verify the plot-direction fix using ?dryrun=1 (safe — no trade).

Test cases:
  1. BUY case  : p0=1.0, p1=0.0      -> expect direction=BUY,  src=rocket_prime_plot0
  2. SELL case : p0=0.0, p1=1.0      -> expect direction=SELL, src=rocket_prime_plot1
  3. EDGE case : both zero            -> expect fallback to inference (rocket_prime_inferred)
  4. Real fmt  : exact TV body shape  -> verify regex parses correctly
"""
import urllib.request as u
import json
import time
from pathlib import Path

SECRET = "5a36fc80ccbdb6ef7b813d7820170c581e5b13dd99649f14"
BASE = "https://shadow-cosmos-unending.ngrok-free.dev/tv-signal"

CASES = [
    {
        "name": "BUY scenario (p0 set, p1 zero)",
        "body": "RP|XAUUSD|tf=15|p0=1.0|p1=0.0|p2=0.0|p3=0.0|p4=0.0|p5=0.0|p6=0.0|p7=0.0|p8=0.0|p9=0.0|c=4685.50|t=1778132000",
        "url_extra": "&symbol=XAUUSD&tf=15&dryrun=1",
        "expect_dir": "BUY",
        "expect_src_contains": "plot0",
    },
    {
        "name": "SELL scenario (p0 zero, p1 set)",
        "body": "RP|XAUUSD|tf=15|p0=0.0|p1=1.0|p2=0.0|p3=0.0|p4=0.0|p5=0.0|p6=0.0|p7=0.0|p8=0.0|p9=0.0|c=4685.50|t=1778132000",
        "url_extra": "&symbol=XAUUSD&tf=15&dryrun=1",
        "expect_dir": "SELL",
        "expect_src_contains": "plot1",
    },
    {
        "name": "Both zero (edge — should fall to inference)",
        "body": "RP|XAUUSD|tf=15|p0=0.0|p1=0.0|p2=0.0|p3=0.0|p4=0.0|p5=0.0|p6=0.0|p7=0.0|p8=0.0|p9=0.0|c=4685.50|t=1778132000",
        "url_extra": "&symbol=XAUUSD&tf=15&dryrun=1",
        "expect_dir": "*",        # fallback inference will pick something
        "expect_src_contains": "inferred",
    },
    {
        "name": "Both non-zero (heuristic falls through)",
        "body": "RP|XAUUSD|tf=15|p0=1.0|p1=1.0|p2=0.0|p3=0.0|p4=0.0|p5=0.0|p6=0.0|p7=0.0|p8=0.0|p9=0.0|c=4685.50|t=1778132000",
        "url_extra": "&symbol=XAUUSD&tf=15&dryrun=1",
        "expect_dir": "*",
        "expect_src_contains": "inferred",
    },
    {
        "name": "EURUSD BUY (different symbol)",
        "body": "RP|EURUSD|tf=5|p0=1.0|p1=0.0|p2=0.0|p3=0.0|p4=0.0|p5=0.0|p6=0.0|p7=0.0|p8=0.0|p9=0.0|c=1.1745|t=1778132000",
        "url_extra": "&symbol=EURUSD&tf=5&dryrun=1",
        "expect_dir": "BUY",
        "expect_src_contains": "plot0",
    },
]

print("=== Sending 5 dryrun test bodies (no real trades) ===\n")
results = []
for i, c in enumerate(CASES, 1):
    url = f"{BASE}?secret={SECRET}{c['url_extra']}"
    body = c["body"].encode("ascii")
    req = u.Request(url, data=body, headers={"Content-Type": "text/plain"}, method="POST")
    try:
        r = u.urlopen(req, timeout=8)
        resp = json.loads(r.read().decode())
        print(f"[{i}] {c['name']}")
        print(f"    HTTP {r.status}  status={resp.get('status')}  symbol={resp.get('symbol')}  direction={resp.get('direction')}")
        results.append({"case": c["name"], "status": resp.get("status"), "direction": resp.get("direction")})
    except Exception as e:
        print(f"[{i}] {c['name']}  FAIL: {e}")
        results.append({"case": c["name"], "error": str(e)})
    time.sleep(0.5)

# Read the diagnostic log to confirm plot values were captured
print("\n=== logs/tv_plot_values.jsonl (last 5 entries) ===")
plot_log = Path(r"C:\Users\Ratanshila\Documents\autmated trading\logs\tv_plot_values.jsonl")
if plot_log.exists():
    lines = plot_log.read_text().splitlines()
    for line in lines[-5:]:
        try:
            d = json.loads(line)
            print(f"  ts={d.get('ts')}  sym={d.get('symbol')}  plots={d.get('plots')}")
        except Exception:
            pass
else:
    print(f"  (file not yet created — receiver may not have written yet)")

# Receiver stats
print("\n=== Webhook receiver stats ===")
try:
    r = u.urlopen("https://shadow-cosmos-unending.ngrok-free.dev/status", timeout=5)
    d = json.loads(r.read().decode())
    m = d.get("metrics", {})
    print(f"  requests={m.get('requests_total')}  writes_ok={m.get('writes_ok')}  rejected={m.get('rejected')}  dryruns={m.get('dryruns')}")
except Exception as e:
    print(f"  status fail: {e}")

# Last entries from tv_signals.jsonl
print("\n=== Last 6 tv_signals.jsonl entries ===")
tv_log = Path(r"C:\Users\Ratanshila\Documents\autmated trading\logs\tv_signals.jsonl")
lines = tv_log.read_text().splitlines() if tv_log.exists() else []
for line in lines[-6:]:
    try:
        d = json.loads(line)
        ts = d.get("ts")
        print(f"  ts={ts}  event={d.get('event')}  sym={d.get('symbol')}  dir={d.get('direction')}  src={d.get('tv_strategy')}")
    except Exception:
        pass

print("\n=== TEST SUMMARY ===")
for r in results:
    print(f"  {r}")
