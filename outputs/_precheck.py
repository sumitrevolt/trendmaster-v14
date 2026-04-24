"""Pre-start check: what's already running, what's free."""
import os, sys, json, subprocess
os.chdir(r"C:\Users\Ratanshila\Documents\autmated trading")

print("=" * 70)
print("  PRE-START HEALTH CHECK")
print("=" * 70)

# 1. brain.pid file — is a brain already alive?
pid_file = "logs/brain.pid"
if os.path.exists(pid_file):
    with open(pid_file) as f:
        pid = f.read().strip()
    print(f"\n[brain.pid] {pid_file} exists -> PID={pid}")
    # Check if that PID is running via tasklist
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
                       capture_output=True, text=True, timeout=10)
    if pid in r.stdout:
        print(f"  STATUS: brain PID {pid} is ALIVE")
        for line in r.stdout.splitlines():
            if pid in line:
                print(f"  {line}")
    else:
        print(f"  STATUS: brain PID {pid} is DEAD (stale .pid file)")
else:
    print(f"\n[brain.pid] no {pid_file} — no prior brain detected")

# 2. Lock file state
lock = os.path.expandvars(r"%LOCALAPPDATA%\TrendMaster\brain.lock")
if os.path.exists(lock):
    with open(lock) as f:
        content = f.read().strip()
    print(f"\n[lock] {lock}")
    print(f"  {content}")
else:
    print(f"\n[lock] no active brain lock file")

# 3. Port 8000 (dashboard)
print("\n[port 8000] checking if dashboard port is in use...")
r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10)
hits = [l for l in r.stdout.splitlines()
        if ":8000 " in l and "LISTENING" in l]
if hits:
    print(f"  BUSY: {len(hits)} listener(s)")
    for h in hits[:3]:
        print(f"  {h.strip()}")
else:
    print("  FREE: no listener on :8000")

# 4. MT5 terminal
print("\n[MT5 terminal] checking if terminal64.exe is running...")
r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq terminal64.exe", "/FO", "CSV"],
                   capture_output=True, text=True, timeout=10)
if "terminal64.exe" in r.stdout:
    hits = [l for l in r.stdout.splitlines() if "terminal64.exe" in l]
    print(f"  MT5 RUNNING ({len(hits)} instance)")
    for h in hits:
        print(f"  {h}")
else:
    print("  MT5 NOT FOUND — brain cannot trade live. Offline mode OK for tests.")

# 5. Recent brain log tail
print("\n[brain log] last 5 lines of logs/trend_master_brain.err:")
try:
    with open("logs/trend_master_brain.err", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    for l in lines[-5:]:
        print(f"  {l.rstrip()}")
except FileNotFoundError:
    print("  (no log file yet)")

# 6. signal file freshness
sig_file = "trendmaster_signals.json"
if os.path.exists(sig_file):
    import time
    age = int(time.time() - os.path.getmtime(sig_file))
    with open(sig_file) as f:
        sig = json.load(f)
    print(f"\n[signal file] age={age}s  direction={sig.get('direction')}  conf={sig.get('confidence')}")
else:
    print(f"\n[signal file] {sig_file} does not exist yet")

print("\n" + "=" * 70)
print("  PRE-CHECK COMPLETE")
print("=" * 70)
