"""Restart dashboard quietly — kill existing PID, spawn hidden via VBS, verify HTTP."""
import os
import subprocess
import time
import urllib.request
import sys
import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
DASH = ROOT / "tools" / "dashboard_server.py"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
OUT = LOG_DIR / "dashboard.out"
ERR = LOG_DIR / "dashboard.err"
STATUS_FILE = ROOT / "outputs" / "restart_dash_status.log"

# Mirror prints to a status file so external probe can verify outcome
_log_fh = open(STATUS_FILE, "w", encoding="utf-8")
_orig_print = print
def print(*args, **kwargs):
    msg = " ".join(str(a) for a in args)
    _orig_print(msg, **kwargs)
    _log_fh.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}\n")
    _log_fh.flush()

# Step 1: kill any existing dashboard_server.py PIDs
print("[1] scanning for existing dashboard processes...")
try:
    import psutil
    killed = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cl = " ".join(p.info["cmdline"] or [])
            if "dashboard_server.py" in cl:
                pid = p.info["pid"]
                p.terminate()
                killed.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # wait + force kill stragglers
    time.sleep(2)
    for pid in killed:
        try:
            p = psutil.Process(pid)
            if p.is_running():
                p.kill()
        except psutil.NoSuchProcess:
            pass
    print(f"    killed: {killed}")
except ImportError:
    subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe", "/FI", "WINDOWTITLE eq dashboard*"],
                   capture_output=True)
    print("    (psutil missing, used taskkill fallback)")

# Step 2: spawn fresh dashboard hidden
print("[2] spawning fresh dashboard...")
CREATE_NO_WINDOW = 0x08000000
DETACHED = 0x00000008
with open(OUT, "ab") as fout, open(ERR, "ab") as ferr:
    proc = subprocess.Popen(
        [str(PYTHONW), str(DASH)],
        cwd=str(ROOT),
        stdout=fout,
        stderr=ferr,
        creationflags=CREATE_NO_WINDOW | DETACHED,
        close_fds=True,
    )
print(f"    PID {proc.pid}")

# Step 3: wait for HTTP up
print("[3] waiting for HTTP 200 on :8765...")
for i in range(15):
    time.sleep(1)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/", timeout=2) as r:
            if r.status == 200:
                print(f"    OK in {i+1}s — PID {proc.pid} serving on :8765")
                break
    except Exception:
        continue
else:
    print(f"    TIMEOUT after 15s — check {ERR}")
    sys.exit(1)

print("[4] dashboard up. Open http://127.0.0.1:8765/")
