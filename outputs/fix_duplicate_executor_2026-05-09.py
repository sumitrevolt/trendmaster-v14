"""Surgical fix for the duplicate-executor bug introduced by the watchdog
deleting the lock file while old process still holds the file handle
(orphan-lock-state — see CLAUDE.md 'Duplicate executor warning' notes).

What this does:
  1. Find all python_signal_executor.py processes via psutil.
  2. Kill them ALL by PID (taskkill /F /PID ...).
  3. Delete the orphaned lock file.
  4. Spawn ONE clean pythonw detached executor.
  5. Verify: only 1 process holds the lock + heartbeat appears within 30s.

Will NOT touch:
  - trend_master_brain.py
  - tv_webhook_receiver.py
  - trailing_stop_manager.py
  - ctrader_executor.py
  - health_watchdog.py
  - Any non-TrendMaster python.

Run via: outputs\\fix_duplicate_executor_2026-05-09.cmd
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "python_executor.log"
LOCK = ROOT / "logs" / "python_signal_executor.lock"
PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
EXECUTOR_SCRIPT = ROOT / "tools" / "python_signal_executor.py"


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def find_executors() -> list[dict]:
    import psutil
    rows: list[dict] = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            name = (p.info.get("name") or "").lower()
            if "python" not in name:
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            if "python_signal_executor" not in cmd:
                continue
            rows.append(
                {
                    "pid": p.info["pid"],
                    "started": datetime.fromtimestamp(p.info["create_time"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "create_ts": p.info["create_time"],
                    "cmd": cmd,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return rows


def kill_pid(pid: int) -> bool:
    """taskkill /F /PID <pid>. Returns True on success."""
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"  taskkill PID={pid} failed: {e}")
        return False


def spawn_clean_executor() -> int | None:
    """Spawn pythonw detached. Returns PID."""
    if not PYTHONW.exists():
        print(f"ERROR: {PYTHONW} not found")
        return None
    if not EXECUTOR_SCRIPT.exists():
        print(f"ERROR: {EXECUTOR_SCRIPT} not found")
        return None
    DETACHED_PROCESS = 0x00000008
    CREATE_NO_WINDOW = 0x08000000
    try:
        proc = subprocess.Popen(
            [str(PYTHONW), str(EXECUTOR_SCRIPT)],
            cwd=str(ROOT),
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return proc.pid
    except Exception as e:
        print(f"spawn failed: {e}")
        return None


def wait_for_heartbeat(timeout_sec: int = 60) -> bool:
    """Watch python_executor.log for a fresh 'heartbeat: iter=' line."""
    deadline = time.time() + timeout_sec
    start_size = LOG.stat().st_size if LOG.exists() else 0
    while time.time() < deadline:
        time.sleep(2)
        if not LOG.exists():
            continue
        try:
            with open(LOG, "rb") as f:
                f.seek(start_size)
                tail = f.read().decode("utf-8", errors="replace")
            if "heartbeat: iter=" in tail:
                return True
        except Exception:
            continue
    return False


def main() -> int:
    print(f"[{now()}] === fix_duplicate_executor ===")

    # 1. Find current executors
    executors = find_executors()
    print(f"[{now()}] found {len(executors)} python_signal_executor processes")
    for e in executors:
        print(f"          PID={e['pid']}  started={e['started']}")

    if len(executors) <= 1:
        print(f"[{now()}] no duplicates — nothing to fix.")
        return 0

    # 2. Kill all
    print(f"[{now()}] killing all {len(executors)} executor processes...")
    for e in executors:
        ok = kill_pid(e["pid"])
        print(f"          {'OK ' if ok else 'FAIL'}  PID={e['pid']}")

    # 3. Wait for OS to clean up
    time.sleep(3)

    # 4. Verify all gone
    remaining = find_executors()
    if remaining:
        print(f"[{now()}] WARNING: {len(remaining)} executors still alive after kill:")
        for e in remaining:
            print(f"          PID={e['pid']}")
        print(f"[{now()}] aborting — manual intervention needed (taskkill /F /PID <pid>)")
        return 1

    # 5. Delete orphan lock file
    if LOCK.exists():
        try:
            LOCK.unlink()
            print(f"[{now()}] deleted orphan lock file: {LOCK.name}")
        except Exception as e:
            print(f"[{now()}] could not unlink lock ({e}) — proceeding anyway")
    else:
        print(f"[{now()}] no lock file present (already clean)")

    # 6. Spawn one clean executor
    print(f"[{now()}] spawning fresh singleton executor...")
    new_pid = spawn_clean_executor()
    if not new_pid:
        print(f"[{now()}] spawn failed. Watchdog will respawn within 60s instead.")
        return 1
    print(f"[{now()}] spawned PID={new_pid}")

    # 7. Wait for heartbeat
    print(f"[{now()}] waiting up to 60s for first heartbeat...")
    if wait_for_heartbeat(60):
        print(f"[{now()}] OK - heartbeat seen")
    else:
        print(f"[{now()}] WARNING: no heartbeat in 60s. Check logs/python_executor.log.")
        return 1

    # 8. Final check
    final = find_executors()
    print(f"[{now()}] final state: {len(final)} executor process(es)")
    for e in final:
        print(f"          PID={e['pid']}  started={e['started']}")
    if len(final) == 1:
        print(f"[{now()}] SUCCESS — singleton restored")
        return 0
    else:
        print(f"[{now()}] FAIL — expected 1 process, got {len(final)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
