"""1. Re-enable TrendMaster Reactivate Alerts schtask (auto-heal TV alerts)
2. Change schedule from hourly to every 5 min
3. Start trend_master_brain.py process silently (so it learns from trades)
"""
import subprocess
import time
import psutil
from pathlib import Path
from datetime import datetime

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOG = ROOT / "outputs" / "autoheal_brain.log"
LOG.write_text(f"=== Auto-heal + brain — {datetime.now()} ===\n", encoding="utf-8")

NO_WIN = 0x08000000
DETACHED = 0x00000008

def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

# ─── Step 1: re-enable Reactivate Alerts schtask + change to 5 min ──
log("--- Step 1: re-enable TrendMaster Reactivate Alerts schtask ---")
TASK_NAME = r"\TrendMaster Reactivate Alerts"
try:
    # Enable
    r1 = subprocess.run(
        ["schtasks", "/Change", "/TN", TASK_NAME, "/ENABLE"],
        capture_output=True, text=True, timeout=8,
        creationflags=NO_WIN,
    )
    log(f"  /ENABLE: rc={r1.returncode} {r1.stdout.strip()[:120]} {r1.stderr.strip()[:120]}")

    # Change trigger to every 5 min (MO: minutes)
    r2 = subprocess.run(
        ["schtasks", "/Change", "/TN", TASK_NAME, "/RI", "5", "/DU", "9999:00"],
        capture_output=True, text=True, timeout=8,
        creationflags=NO_WIN,
    )
    log(f"  /RI 5: rc={r2.returncode} {r2.stdout.strip()[:120]} {r2.stderr.strip()[:120]}")

    # Run it immediately
    r3 = subprocess.run(
        ["schtasks", "/Run", "/TN", TASK_NAME],
        capture_output=True, text=True, timeout=8,
        creationflags=NO_WIN,
    )
    log(f"  /Run (first fire): rc={r3.returncode} {r3.stdout.strip()[:120]}")
except Exception as e:
    log(f"  ERROR: {e}")

# ─── Step 2: kill any existing brain + spawn fresh ──
log("\n--- Step 2: start trend_master_brain.py silently ---")
killed = []
for p in psutil.process_iter(['pid', 'cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        if "trend_master_brain" in cmd and "brain_forensics" not in cmd:
            p.kill()
            killed.append(p.info['pid'])
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
log(f"  Killed {len(killed)} existing brain PIDs: {killed}")
time.sleep(2)

# Brain runs as a module via `python -m ai_trading_agents.trend_master_brain`
pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
try:
    proc = subprocess.Popen(
        [str(pythonw), "-m", "ai_trading_agents.trend_master_brain"],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=DETACHED | NO_WIN,
        close_fds=True,
    )
    log(f"  Spawned brain PID {proc.pid}")
    time.sleep(4)
    try:
        st = psutil.Process(proc.pid).status()
        log(f"  Status after 4s: {st}")
    except psutil.NoSuchProcess:
        log(f"  WARNING: brain died immediately — check logs/trend_master_brain.err")
except Exception as e:
    log(f"  Brain spawn FAILED: {e}")

# ─── Step 3: verify Reactivate Alerts schtask state ──
log("\n--- Step 3: final schtask check ---")
try:
    r = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"],
        capture_output=True, text=True, timeout=8,
        creationflags=NO_WIN,
    )
    for line in r.stdout.splitlines():
        line = line.strip()
        if any(k in line for k in ("TaskName", "Status", "Next Run", "Schedule")):
            log(f"  {line}")
except Exception as e:
    log(f"  ERROR: {e}")

log("\nDone.")
