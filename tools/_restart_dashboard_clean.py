"""Kill all dashboard processes, wait, ensure none, then relaunch ONE."""
import psutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
SCRIPT = ROOT / "tools" / "dashboard_server.py"


def list_dash():
    out = []
    for p in psutil.process_iter(["pid", "cmdline", "create_time"]):
        try:
            cl = " ".join(p.info.get("cmdline") or []).lower()
            if "dashboard_server" in cl:
                out.append(p)
        except Exception:
            pass
    return out


# 1. Kill all
existing = list_dash()
print(f"Found {len(existing)} dashboard process(es)")
for p in existing:
    try:
        p.kill()
        print(f"  killed PID {p.info['pid']}")
    except Exception as e:
        print(f"  could not kill {p.info['pid']}: {e}")

# Wait + verify
time.sleep(4)
remaining = list_dash()
if remaining:
    print(f"WARN: {len(remaining)} still running, force-killing")
    for p in remaining:
        try:
            psutil.Process(p.info["pid"]).kill()
        except Exception:
            pass
    time.sleep(3)

remaining = list_dash()
print(f"After cleanup: {len(remaining)} dashboard processes")

# 2. Launch ONE
print(f"Launching: {PYW} {SCRIPT}")
subprocess.Popen(
    [str(PYW), str(SCRIPT)],
    cwd=str(ROOT),
    creationflags=0x08000000,
)
time.sleep(8)

# 3. Verify
new_dash = list_dash()
print(f"After relaunch: {len(new_dash)} dashboard processes")
for p in new_dash:
    print(f"  PID {p.info['pid']}")

# 4. Test HTTP
try:
    import urllib.request
    req = urllib.request.Request("http://localhost:8765/api/status")
    with urllib.request.urlopen(req, timeout=20) as r:
        import json
        obj = json.loads(r.read().decode("utf-8"))
        print()
        print(f"HTTP {r.status}")
        print(f"  per_pair_pnl: {len(obj.get('per_pair_pnl', []))} pairs")
        print(f"  spread: {len(obj.get('spread', []))} pairs")
        print(f"  duration all.n: {obj.get('duration', {}).get('all', {}).get('n')}")
        print(f"  brain learning: {len(obj.get('brain_learning', {}).get('by_class', []))} classes")
        print(f"  account: bal={obj.get('account', {}).get('balance')} pos={obj.get('account', {}).get('n_positions')}")
except Exception as e:
    print(f"HTTP FAIL: {e}")
