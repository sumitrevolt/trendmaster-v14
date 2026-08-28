"""Spawn dashboard server silently + clean up any webhook duplicates."""
import psutil
import subprocess
import time
from pathlib import Path

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOG = ROOT / "outputs" / "spawn_dashboard.log"

DETACHED = 0x00000008
NO_WINDOW = 0x08000000

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

LOG.write_text(f"=== Spawn dashboard + dedupe — {time.strftime('%H:%M:%S')} ===\n", encoding="utf-8")

# 1. Dedupe webhook — keep only the OLDEST single logical instance (parent shim + Python311 child)
webhook_pairs = {}  # ppid → (pid, name, create_time)
for p in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'ppid']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        if "tv_webhook_receiver" in cmd:
            webhook_pairs[p.info['pid']] = {
                'name': p.info.get('name'),
                'ppid': p.info.get('ppid'),
                'ctime': p.info.get('create_time') or 0,
                'cmd': cmd[:120],
            }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

log(f"Found {len(webhook_pairs)} webhook PIDs:")
for pid, info in webhook_pairs.items():
    age = (time.time() - info['ctime']) / 60
    log(f"  PID {pid} ppid={info['ppid']} age={age:.1f}min")

# Group by parent-chain: a logical instance is .venv pythonw + its Python311 child
# Keep the chain with the EARLIEST .venv pythonw (the "oldest" original spawn)
venv_parents = {pid: i for pid, i in webhook_pairs.items() if '.venv' in i['cmd']}
# Sort venv parents by ctime (earliest first)
sorted_parents = sorted(venv_parents.items(), key=lambda x: x[1]['ctime'])
if len(sorted_parents) > 1:
    log(f"\nKeep oldest venv parent: PID {sorted_parents[0][0]}")
    keep_pids = {sorted_parents[0][0]}
    # Also keep its child (Python311 with this PID as ppid)
    for pid, i in webhook_pairs.items():
        if i['ppid'] == sorted_parents[0][0]:
            keep_pids.add(pid)
    log(f"  + its child(ren): {keep_pids - {sorted_parents[0][0]}}")
    # Kill the rest
    for pid in webhook_pairs:
        if pid not in keep_pids:
            try:
                psutil.Process(pid).kill()
                log(f"  killed dupe PID {pid}")
            except Exception as e:
                log(f"  failed to kill PID {pid}: {e}")
    time.sleep(2)
else:
    log("Webhook: single instance, no dedupe needed")

# 2. Find dashboard process
dash_running = False
for p in psutil.process_iter(['cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        if "dashboard_server" in cmd:
            dash_running = True
            break
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

if dash_running:
    log("\nDashboard already running — no action needed")
else:
    log("\nDashboard NOT running — spawning silently")
    pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    dash_script = ROOT / "tools" / "dashboard_server.py"
    if not dash_script.exists():
        log(f"  [ERROR] script missing: {dash_script}")
    else:
        try:
            p = subprocess.Popen(
                [str(pythonw), str(dash_script)],
                cwd=str(ROOT),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=DETACHED | NO_WINDOW,
                close_fds=True,
            )
            log(f"  spawned dashboard PID {p.pid}")
            time.sleep(4)
            # Verify it's still alive
            try:
                proc = psutil.Process(p.pid)
                log(f"  alive: status={proc.status()}")
            except psutil.NoSuchProcess:
                log(f"  WARNING: dashboard PID died immediately — check tools\\dashboard_server.py")
        except Exception as e:
            log(f"  [ERROR] spawn failed: {e}")

# 3. Final state
log("\n=== Final webhook + dashboard processes ===")
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        if "tv_webhook_receiver" in cmd or "dashboard_server" in cmd:
            log(f"  PID {p.info['pid']} {p.info['name']}: {cmd[:120]}")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

log("\nDone.")
