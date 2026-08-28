"""Silent kill + respawn executor so new safeguards v2 + brain-veto load."""
import psutil, subprocess, time
from pathlib import Path
ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOG = ROOT / "outputs" / "restart_exec_silent.log"
LOG.write_text(f"=== Restart exec — {time.strftime('%H:%M:%S')} ===\n", encoding="utf-8")
def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

killed = []
for p in psutil.process_iter(['pid', 'cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        if "python_signal_executor" in cmd:
            p.kill()
            killed.append(p.info['pid'])
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
log(f"Killed {len(killed)} executor PIDs: {killed}")
time.sleep(2)

# Clean lock
for lock in ["logs/python_executor.lock", "logs/.python_executor.lock"]:
    p = ROOT / lock
    try:
        if p.exists(): p.unlink()
    except Exception: pass

# Spawn
pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
proc = subprocess.Popen(
    [str(pythonw), str(ROOT / "tools" / "python_signal_executor.py")],
    cwd=str(ROOT),
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    creationflags=0x00000008 | 0x08000000, close_fds=True,
)
log(f"Spawned executor PID {proc.pid}")
time.sleep(5)
try:
    st = psutil.Process(proc.pid).status()
    log(f"Status after 5s: {st}")
except psutil.NoSuchProcess:
    log("WARNING: executor died immediately")
log("Done.")
