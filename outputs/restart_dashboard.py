"""Kill existing dashboard + respawn silently with new code."""
import psutil, subprocess, time
from pathlib import Path

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOG = ROOT / "outputs" / "restart_dashboard.log"
LOG.write_text(f"=== Restart dashboard — {time.strftime('%H:%M:%S')} ===\n", encoding="utf-8")

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line)

# Kill existing
killed = []
for p in psutil.process_iter(['pid','cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        if "dashboard_server" in cmd:
            p.kill()
            killed.append(p.info['pid'])
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
log(f"Killed {len(killed)} dashboard PIDs: {killed}")
time.sleep(2)

# Spawn fresh
DETACHED = 0x00000008
NO_WINDOW = 0x08000000
pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
script = ROOT / "tools" / "dashboard_server.py"
proc = subprocess.Popen(
    [str(pythonw), str(script)],
    cwd=str(ROOT),
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    creationflags=DETACHED | NO_WINDOW, close_fds=True,
)
log(f"Spawned dashboard PID {proc.pid}")
time.sleep(5)

# Verify alive + port reachable
import urllib.request
try:
    r = urllib.request.urlopen("http://127.0.0.1:8765/", timeout=3)
    log(f"Dashboard /  responds HTTP {r.status} — OK")
except Exception as e:
    log(f"Dashboard / failed: {e}")
log("Done.")
