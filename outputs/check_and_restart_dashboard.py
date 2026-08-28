"""Check dashboard process + restart if dead. Write result to file."""
import psutil, subprocess, time, urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOG = ROOT / "outputs" / "dash_check.log"
LOG.write_text(f"=== Dashboard check — {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")

def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

# 1. Check for dashboard processes
dash_pids = []
for p in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        if "dashboard_server" in cmd:
            age = int(time.time() - (p.info.get('create_time') or 0))
            dash_pids.append((p.info['pid'], age, cmd[:100]))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
log(f"Found {len(dash_pids)} dashboard processes:")
for pid, age, cmd in dash_pids:
    log(f"  PID {pid} age={age}s | {cmd}")

# 2. Check port 8765
try:
    r = urllib.request.urlopen("http://127.0.0.1:8765/", timeout=3)
    log(f"Port 8765 alive — HTTP {r.status}")
    port_alive = True
except Exception as e:
    log(f"Port 8765 DEAD: {e}")
    port_alive = False

# 3. If dead OR no process, kill all + respawn
if not port_alive or not dash_pids:
    log("\n--- Restarting dashboard ---")
    for pid, _, _ in dash_pids:
        try:
            psutil.Process(pid).kill()
            log(f"  killed PID {pid}")
        except Exception as ex:
            log(f"  kill {pid} failed: {ex}")
    time.sleep(2)

    # Clean lock if any
    lock = ROOT / "logs" / "dashboard_server.lock"
    try:
        if lock.exists():
            lock.unlink()
            log("  cleaned dashboard_server.lock")
    except Exception:
        pass

    pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    script = ROOT / "tools" / "dashboard_server.py"
    proc = subprocess.Popen(
        [str(pythonw), str(script)],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=0x00000008 | 0x08000000,
        close_fds=True,
    )
    log(f"  spawned dashboard PID {proc.pid}")
    time.sleep(6)
    try:
        st = psutil.Process(proc.pid).status()
        log(f"  status: {st}")
    except psutil.NoSuchProcess:
        log("  WARNING: dashboard died immediately")
    # Re-check port
    try:
        r = urllib.request.urlopen("http://127.0.0.1:8765/", timeout=4)
        log(f"  Port 8765 NOW alive — HTTP {r.status}")
    except Exception as e:
        log(f"  Port 8765 STILL dead: {e}")
        # Try to read dashboard.log for crash hints
        dash_log = ROOT / "logs" / "dashboard.log"
        if dash_log.exists():
            tail = dash_log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
            log("  Last 20 lines of dashboard.log:")
            for line in tail:
                log(f"    {line[:200]}")
log("Done.")
