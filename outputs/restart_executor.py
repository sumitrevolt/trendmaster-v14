"""
2026-05-14 — Restart python_signal_executor to load the auto-archive patch.
Mirrors the health_watchdog kill+respawn pattern (kill-wait-unlink-spawn).
"""
import subprocess
import time
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
EXECUTOR = ROOT / "tools" / "python_signal_executor.py"
LOCK = ROOT / "logs" / "python_signal_executor.lock"
STATUS = Path(__file__).parent / "restart_executor_status.json"

CREATE_NO_WINDOW = 0x08000000
DETACHED = 0x00000008

report = {"ts": datetime.now().isoformat(timespec="seconds"), "phases": []}

# --- Phase 1: scan ---
try:
    import psutil
    pids_before = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cl = " ".join(p.info["cmdline"] or [])
            if "python_signal_executor.py" in cl:
                pids_before.append(p.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    report["pids_before"] = pids_before
    report["phases"].append(f"scan: {len(pids_before)} PIDs")
except ImportError:
    report["phases"].append("psutil missing — abort")
    STATUS.write_text(json.dumps(report, indent=2))
    raise SystemExit(1)

# --- Phase 2: terminate ---
for pid in pids_before:
    try:
        psutil.Process(pid).terminate()
    except psutil.NoSuchProcess:
        pass
report["phases"].append("terminate sent to all")

# --- Phase 3: wait up to 8s for everyone to die ---
deadline = time.time() + 8.0
while time.time() < deadline:
    still = []
    for pid in pids_before:
        try:
            p = psutil.Process(pid)
            if p.is_running():
                still.append(pid)
        except psutil.NoSuchProcess:
            pass
    if not still:
        break
    time.sleep(0.5)

# Force-kill stragglers
for pid in pids_before:
    try:
        p = psutil.Process(pid)
        if p.is_running():
            p.kill()
            report["phases"].append(f"force-killed PID {pid}")
    except psutil.NoSuchProcess:
        pass
time.sleep(1)
report["phases"].append("kill-wait done")

# --- Phase 4: unlink lock ---
try:
    if LOCK.exists():
        LOCK.unlink()
        report["phases"].append("lock unlinked")
    else:
        report["phases"].append("no lock to unlink")
except Exception as e:
    report["phases"].append(f"lock unlink failed: {e}")

# --- Phase 5: spawn fresh, detached, no window ---
try:
    proc = subprocess.Popen(
        [str(PYTHONW), str(EXECUTOR)],
        cwd=str(ROOT),
        creationflags=CREATE_NO_WINDOW | DETACHED,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    report["new_pid"] = proc.pid
    report["phases"].append(f"spawned PID {proc.pid}")
except Exception as e:
    report["phases"].append(f"spawn failed: {e}")
    STATUS.write_text(json.dumps(report, indent=2))
    raise SystemExit(1)

# --- Phase 6: verify new process up (5s grace, then check sentinel/log) ---
time.sleep(5)
pids_after = []
for p in psutil.process_iter(["pid", "name", "cmdline"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "python_signal_executor.py" in cl:
            pids_after.append(p.info["pid"])
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        continue
report["pids_after"] = pids_after
report["alive_after_5s"] = len(pids_after) > 0

# Check log file for restart marker
log_file = ROOT / "logs" / "python_executor.log"
if log_file.exists():
    # Read last 30 lines
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]
        recent_log = "\n".join(lines)
        report["recent_log_tail"] = lines[-10:] if len(lines) >= 10 else lines
    except Exception as e:
        report["log_read_error"] = str(e)

STATUS.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"BEFORE={report['pids_before']} AFTER={report['pids_after']} ALIVE={report['alive_after_5s']}")
