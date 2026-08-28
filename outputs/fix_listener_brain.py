"""Kill all telegram listeners + brain instances, respawn ONE of each silently."""
import psutil, subprocess, time
from pathlib import Path

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOG = ROOT / "outputs" / "fix_listener_brain.log"
LOG.write_text(f"=== Fix listener + brain — {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")

def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {m}\n")

DETACHED = 0x00000008
NO_WIN = 0x08000000
TARGETS = {"telegram_direction_listener", "trend_master_brain"}

# Find and kill ALL instances
killed = {t: [] for t in TARGETS}
for p in psutil.process_iter(['pid', 'cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        for target in TARGETS:
            if target in cmd and "brain_forensics" not in cmd:
                try:
                    p.kill()
                    killed[target].append(p.info['pid'])
                except Exception as e:
                    log(f"  kill {p.info['pid']} ({target}) failed: {e}")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

for t, pids in killed.items():
    log(f"Killed {len(pids)} {t} PIDs: {pids}")

time.sleep(3)

# Verify all killed
survivors = []
for p in psutil.process_iter(['pid', 'cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        for target in TARGETS:
            if target in cmd and "brain_forensics" not in cmd:
                survivors.append((target, p.info['pid']))
    except Exception:
        pass
if survivors:
    log(f"WARNING: survivors {survivors} — force-killing")
    for _, pid in survivors:
        try: psutil.Process(pid).kill()
        except: pass
    time.sleep(1)

# Spawn ONE telegram listener
pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
listener = ROOT / "tools" / "telegram_direction_listener.py"
p1 = subprocess.Popen(
    [str(pythonw), str(listener)],
    cwd=str(ROOT),
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    creationflags=DETACHED | NO_WIN, close_fds=True,
)
log(f"Spawned telegram listener PID {p1.pid}")

time.sleep(2)

# Spawn ONE brain (via module)
p2 = subprocess.Popen(
    [str(pythonw), "-m", "ai_trading_agents.trend_master_brain"],
    cwd=str(ROOT),
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    creationflags=DETACHED | NO_WIN, close_fds=True,
)
log(f"Spawned brain PID {p2.pid}")

time.sleep(5)

# Verify alive
for label, pid in [("telegram listener", p1.pid), ("brain", p2.pid)]:
    try:
        st = psutil.Process(pid).status()
        log(f"  {label} PID {pid} status: {st}")
    except psutil.NoSuchProcess:
        log(f"  {label} PID {pid} DIED immediately — check logs")

# Final check via process list
final = {t: 0 for t in TARGETS}
for p in psutil.process_iter(['cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        for t in TARGETS:
            if t in cmd and "brain_forensics" not in cmd:
                final[t] += 1
    except Exception:
        pass
log(f"\nFinal counts: {final}")
log("Done.")
