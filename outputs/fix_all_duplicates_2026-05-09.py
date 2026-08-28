"""Unified duplicate killer — handles every TrendMaster singleton that
got duplicated by the orphan-lock + dual-watchdog bug.

Kills duplicates of:
  - python_signal_executor.py   (MT5 OctaFX executor)
  - trailing_stop_manager.py    (trailing-stop service)

Leaves untouched:
  - trend_master_brain.py       (has its own lock — verify, don't touch)
  - tv_webhook_receiver.py      (single instance verified separately)
  - health_watchdog.py          (scheduled task, transient)

For each component:
  1. List all instances.
  2. Kill them all (parallel taskkill /F /PID).
  3. Wait up to 8s for PIDs to disappear.
  4. Delete orphan lock files (only after PIDs gone).
  5. Spawn ONE clean detached pythonw instance.
  6. Verify single instance + heartbeat in log.

Output: full log to stdout (captured by the wrapping .cmd to logs/).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"


# --- per-component config --------------------------------------------------
COMPONENTS = [
    {
        "name": "python_signal_executor",
        "match": "python_signal_executor",
        "script": ROOT / "tools" / "python_signal_executor.py",
        "log_path": ROOT / "logs" / "python_executor.log",
        "lock_path": ROOT / "logs" / "python_signal_executor.lock",
        "heartbeat_pattern": "heartbeat: iter=",
    },
    {
        "name": "trailing_stop_manager",
        "match": "trailing_stop_manager",
        "script": ROOT / "tools" / "trailing_stop_manager.py",
        "log_path": ROOT / "logs" / "trailing_stop.log",
        "lock_path": ROOT / "logs" / "trailing_stop_manager.lock",
        "heartbeat_pattern": "heartbeat iter=",
    },
]

# Verify-only — should be ONE instance, do NOT kill if duplicated; just
# warn loudly so the operator knows there's a deeper issue.
VERIFY_ONLY = [
    {"name": "trend_master_brain", "match": "trend_master_brain"},
    {"name": "tv_webhook_receiver", "match": "tv_webhook_receiver"},
]


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def find_procs(match: str) -> list[dict]:
    import psutil
    rows: list[dict] = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            name = (p.info.get("name") or "").lower()
            if "python" not in name:
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            if match not in cmd:
                continue
            rows.append(
                {
                    "pid": p.info["pid"],
                    "create_ts": p.info["create_time"],
                    "started": datetime.fromtimestamp(p.info["create_time"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "exe": (p.info.get("cmdline") or ["?"])[0],
                }
            )
        except Exception:
            continue
    return sorted(rows, key=lambda x: x["create_ts"])


def kill_pid(pid: int) -> bool:
    try:
        r = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True, text=True, timeout=10
        )
        return r.returncode == 0
    except Exception as e:
        print(f"  taskkill PID={pid} failed: {e}")
        return False


def wait_pids_gone(match: str, timeout: float = 8.0) -> list[int]:
    """Wait up to `timeout` for all matching PIDs to vanish. Returns
    list of survivors (empty = success)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        alive = [p["pid"] for p in find_procs(match)]
        if not alive:
            return []
        time.sleep(0.5)
    return [p["pid"] for p in find_procs(match)]


def spawn_detached(script_path: Path) -> int | None:
    if not PYTHONW.exists() or not script_path.exists():
        return None
    DETACHED = 0x00000008
    NOWIN = 0x08000000
    try:
        proc = subprocess.Popen(
            [str(PYTHONW), str(script_path)],
            cwd=str(ROOT),
            creationflags=DETACHED | NOWIN,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return proc.pid
    except Exception as e:
        print(f"  spawn failed: {e}")
        return None


def wait_log_pattern(log_path: Path, pattern: str, since_size: int, timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        if not log_path.exists():
            continue
        try:
            with open(log_path, "rb") as f:
                f.seek(since_size)
                tail = f.read().decode("utf-8", errors="replace")
            if pattern in tail:
                return True
        except Exception:
            continue
    return False


def fix_component(comp: dict) -> bool:
    name = comp["name"]
    print()
    print("=" * 72)
    print(f"  Component: {name}")
    print("=" * 72)

    procs = find_procs(comp["match"])
    print(f"[{now()}] found {len(procs)} instances")
    for p in procs:
        print(f"          PID={p['pid']}  started={p['started']}  exe={Path(p['exe']).name}")

    if len(procs) == 0:
        print(f"[{now()}] no instances at all — spawning a clean singleton")
    elif len(procs) == 1:
        print(f"[{now()}] OK - already singleton; skipping")
        return True

    # Snapshot log size before kill (for heartbeat detection later)
    log_size_before = comp["log_path"].stat().st_size if comp["log_path"].exists() else 0

    # 1. Kill all
    if procs:
        print(f"[{now()}] killing {len(procs)} processes...")
        for p in procs:
            ok = kill_pid(p["pid"])
            print(f"          {'OK ' if ok else 'FAIL'}  PID={p['pid']}")

    # 2. Wait for them to actually exit
    survivors = wait_pids_gone(comp["match"], timeout=10)
    if survivors:
        print(f"[{now()}] ERROR: PIDs still alive after 10s: {survivors}")
        return False
    print(f"[{now()}] all old PIDs gone")

    # 3. Delete lock file (now safe — no orphan handles)
    lock = comp["lock_path"]
    if lock.exists():
        try:
            lock.unlink()
            print(f"[{now()}] deleted lock: {lock.name}")
        except Exception as e:
            print(f"[{now()}] could not delete {lock.name}: {e}")

    # 4. Spawn ONE clean instance
    new_pid = spawn_detached(comp["script"])
    if not new_pid:
        print(f"[{now()}] spawn failed — watchdog will respawn within 60s")
        return False
    print(f"[{now()}] spawned PID={new_pid}")

    # 5. Wait for heartbeat
    print(f"[{now()}] waiting up to 60s for heartbeat...")
    if wait_log_pattern(comp["log_path"], comp["heartbeat_pattern"], log_size_before, 60):
        print(f"[{now()}] OK - heartbeat detected")
    else:
        print(f"[{now()}] WARNING: no heartbeat in 60s. Check {comp['log_path'].name}.")
        return False

    # 6. Final count
    final = find_procs(comp["match"])
    print(f"[{now()}] final state: {len(final)} instance(s)")
    for p in final:
        print(f"          PID={p['pid']}  started={p['started']}")
    return len(final) == 1


def main() -> int:
    print(f"=== fix_all_duplicates ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")
    print(f"ROOT: {ROOT}")

    overall_ok = True

    # Verify-only checks first
    print()
    print("--- verify-only (warn if duplicated, don't touch) ---")
    for comp in VERIFY_ONLY:
        procs = find_procs(comp["match"])
        if len(procs) <= 1:
            print(f"  OK   {comp['name']}: {len(procs)} instance(s)")
        else:
            print(f"  WARN {comp['name']}: {len(procs)} instances — singleton lock failing")
            for p in procs:
                print(f"       PID={p['pid']} started={p['started']} exe={Path(p['exe']).name}")

    # Fix duplicated singletons
    for comp in COMPONENTS:
        ok = fix_component(comp)
        overall_ok = overall_ok and ok

    print()
    print("=" * 72)
    print(f"  Final result: {'SUCCESS' if overall_ok else 'PARTIAL FAILURE — review log'}")
    print("=" * 72)
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
