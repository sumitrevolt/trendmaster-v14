"""Kill dashboard + respawn silently."""
import psutil, subprocess, time
from pathlib import Path
ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOG = ROOT / "outputs" / "restart_dash.log"
LOG.write_text(f"=== restart dash {time.strftime('%H:%M:%S')} ===\n", encoding="utf-8")

def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

killed = []
for p in psutil.process_iter(['pid','cmdline']):
    try:
        c = " ".join(p.info.get('cmdline') or [])
        if 'dashboard_server' in c:
            p.kill()
            killed.append(p.info['pid'])
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
log(f"killed {len(killed)} PIDs: {killed}")
time.sleep(2)

pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
script = ROOT / "tools" / "dashboard_server.py"
p = subprocess.Popen(
    [str(pythonw), str(script)],
    cwd=str(ROOT),
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    creationflags=0x00000008|0x08000000, close_fds=True,
)
log(f"spawned PID {p.pid}")
time.sleep(5)

try:
    import urllib.request
    r = urllib.request.urlopen("http://127.0.0.1:8765/", timeout=3)
    log(f"port 8765 HTTP {r.status}")
except Exception as e:
    log(f"port 8765 fail: {e}")
log("done.")
