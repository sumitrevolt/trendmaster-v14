"""Nuclear cleanup: kill ALL duplicate python(w) + visible cmd windows
hosting TrendMaster components, then respawn ONE silent of each.

This is aggressive — only run when popup spam is bad. After this:
  - 1 webhook (pythonw, no cmd parent)
  - 1 executor (pythonw, no cmd parent)
  - 1 trailing-stop-manager (pythonw, no cmd parent)
  - 0 leftover visible cmd windows
"""
import psutil
import time
import subprocess
import os
from pathlib import Path

ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOG = ROOT / "outputs" / "nuclear_cleanup.log"

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

LOG.write_text(f"=== Nuclear cleanup — {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n", encoding="utf-8")

# 1. Kill ALL TrendMaster pythonw/python + visible cmd parents
TARGETS = [
    "tv_webhook_receiver",
    "python_signal_executor",
    "trailing_stop_manager",
    "telegram_direction_listener",
    "brain_forensics_monitor",
]
VISIBLE_CMD_PATTERNS = [
    "title TV Webhook",
    "title TV_Webhook",
    "title Python Signal Executor",
    "title Ngrok",
    "title Cloudflared",
    "tv_webhook_receiver",
    "python_signal_executor",
    "trailing_stop_manager",
    "ngrok http 5005",
    "cloudflared tunnel",
]

killed_py = []
killed_cmd = []
for p in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        cmd_lower = cmd.lower()
        name = (p.info.get('name') or '').lower()

        # Python/pythonw matching TrendMaster components
        if name in ('python.exe', 'pythonw.exe'):
            if any(t in cmd for t in TARGETS):
                log(f"  KILL python PID {p.info['pid']}: {cmd[:120]}")
                try:
                    p.terminate()
                    killed_py.append(p.info['pid'])
                except Exception as e:
                    log(f"    terminate failed: {e}")
                    try:
                        p.kill()
                    except Exception:
                        pass

        # cmd.exe windows hosting TrendMaster launches
        elif name == 'cmd.exe':
            if any(pat.lower() in cmd_lower for pat in VISIBLE_CMD_PATTERNS):
                log(f"  KILL cmd PID {p.info['pid']}: {cmd[:120]}")
                try:
                    p.terminate()
                    killed_cmd.append(p.info['pid'])
                except Exception as e:
                    log(f"    terminate failed: {e}")
                    try:
                        p.kill()
                    except Exception:
                        pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

log(f"\nKilled {len(killed_py)} python procs: {killed_py}")
log(f"Killed {len(killed_cmd)} cmd windows: {killed_cmd}\n")

# Wait for terminations to settle
time.sleep(4)

# 2. Force-kill any survivors
survivors_py = []
survivors_cmd = []
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        name = (p.info.get('name') or '').lower()
        if name in ('python.exe', 'pythonw.exe') and any(t in cmd for t in TARGETS):
            survivors_py.append(p.info['pid'])
            try:
                p.kill()
            except Exception:
                pass
        elif name == 'cmd.exe' and any(pat.lower() in cmd.lower() for pat in VISIBLE_CMD_PATTERNS):
            survivors_cmd.append(p.info['pid'])
            try:
                p.kill()
            except Exception:
                pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

if survivors_py:
    log(f"Force-killed survivor python: {survivors_py}")
if survivors_cmd:
    log(f"Force-killed survivor cmd: {survivors_cmd}")
time.sleep(2)

# 3. Clean stale locks
for lock in ["logs/python_executor.lock", "logs/.python_executor.lock"]:
    p = ROOT / lock
    try:
        if p.exists():
            p.unlink()
            log(f"  cleaned lock {p.name}")
    except Exception as e:
        log(f"  lock cleanup {p.name} failed: {e}")

# 4. Respawn webhook + executor + trailing-stop SILENTLY via CREATE_NO_WINDOW
DETACHED = 0x00000008
NO_WINDOW = 0x08000000

def silent_spawn(args, cwd):
    log(f"  silent spawn: {' '.join(str(a) for a in args)}")
    return subprocess.Popen(
        args, cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=DETACHED | NO_WINDOW,
        close_fds=True,
    )

pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
time.sleep(1)
p_web = silent_spawn([str(pythonw), "-m", "ai_trading_agents.tv_webhook_receiver"], cwd=ROOT)
log(f"  webhook spawned PID {p_web.pid}")
time.sleep(2)
p_exec = silent_spawn([str(pythonw), str(ROOT / "tools" / "python_signal_executor.py")], cwd=ROOT)
log(f"  executor spawned PID {p_exec.pid}")
time.sleep(1)
p_trail = silent_spawn([str(pythonw), str(ROOT / "tools" / "trailing_stop_manager.py")], cwd=ROOT)
log(f"  trailing-stop spawned PID {p_trail.pid}")

time.sleep(3)
log("\n=== Final state ===")
final = {"webhook": 0, "executor": 0, "trailing": 0}
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        if "tv_webhook_receiver" in cmd:
            final["webhook"] += 1
            log(f"  webhook PID {p.info['pid']}: {cmd[:100]}")
        elif "python_signal_executor" in cmd:
            final["executor"] += 1
            log(f"  executor PID {p.info['pid']}: {cmd[:100]}")
        elif "trailing_stop_manager" in cmd:
            final["trailing"] += 1
            log(f"  trailing PID {p.info['pid']}: {cmd[:100]}")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

log(f"\nCounts: webhook={final['webhook']}, executor={final['executor']}, trailing={final['trailing']}")
log("Expected: all = 2 (parent venv shim + child Python311)")
log("Done.")
