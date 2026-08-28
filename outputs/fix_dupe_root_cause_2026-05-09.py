"""Permanent fix for dupe-spawner: disable redundant Process Watchdog
schtask, then clean all dupes, then spawn one of each.

After this runs:
  - 'TrendMaster Process Watchdog' schtask = DISABLED (was 2-min, redundant
     with health_watchdog which is 1-min)
  - 'TrendMaster Health Watchdog' = ACTIVE (sole singleton enforcer)
  - 1 python_signal_executor running
  - 1 trailing_stop_manager running
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"

# --- schtasks to disable as redundant -------------------------------------
REDUNDANT_SCHTASKS = [
    r"\TrendMaster Process Watchdog",  # overlaps 100% with Health Watchdog
]


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
                {"pid": p.info["pid"],
                 "create_ts": p.info["create_time"],
                 "started": datetime.fromtimestamp(p.info["create_time"]).strftime("%H:%M:%S"),
                 "exe": (p.info.get("cmdline") or ["?"])[0]}
            )
        except Exception:
            continue
    return sorted(rows, key=lambda x: x["create_ts"])


def disable_schtask(name: str) -> bool:
    print(f"[{now()}] disabling schtask: {name}")
    try:
        r = subprocess.run(
            ["schtasks", "/Change", "/TN", name, "/DISABLE"],
            capture_output=True, text=True, timeout=15
        )
        ok = r.returncode == 0
        print(f"          {'OK ' if ok else 'FAIL'}  rc={r.returncode}")
        if r.stdout:
            print(f"          stdout: {r.stdout.strip()}")
        if r.stderr and not ok:
            print(f"          stderr: {r.stderr.strip()}")
        return ok
    except Exception as e:
        print(f"          EXC: {e}")
        return False


def kill_pid(pid: int) -> bool:
    try:
        r = subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                          capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def wait_gone(match: str, timeout: float = 10.0) -> list[int]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        alive = [p["pid"] for p in find_procs(match)]
        if not alive:
            return []
        time.sleep(0.5)
    return [p["pid"] for p in find_procs(match)]


def spawn_one(script: Path) -> int | None:
    if not PYTHONW.exists() or not script.exists():
        return None
    DETACHED, NOWIN = 0x00000008, 0x08000000
    try:
        proc = subprocess.Popen(
            [str(PYTHONW), str(script)],
            cwd=str(ROOT),
            creationflags=DETACHED | NOWIN,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True,
        )
        return proc.pid
    except Exception as e:
        print(f"  spawn failed: {e}")
        return None


def wait_log(log_path: Path, pattern: str, since: int, timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        if not log_path.exists():
            continue
        try:
            with open(log_path, "rb") as f:
                f.seek(since)
                tail = f.read().decode("utf-8", errors="replace")
            if pattern in tail:
                return True
        except Exception:
            pass
    return False


def fix_component(comp: dict) -> bool:
    print()
    print("=" * 72)
    print(f"  Component: {comp['name']}")
    print("=" * 72)
    procs = find_procs(comp["match"])
    print(f"[{now()}] {len(procs)} instance(s) before fix")
    for p in procs:
        print(f"          PID={p['pid']}  started={p['started']}  exe={Path(p['exe']).name}")

    log_size_before = comp["log_path"].stat().st_size if comp["log_path"].exists() else 0

    if procs:
        for p in procs:
            ok = kill_pid(p["pid"])
            print(f"[{now()}] kill PID={p['pid']}: {'OK' if ok else 'FAIL'}")

    survivors = wait_gone(comp["match"], 12)
    if survivors:
        print(f"[{now()}] ERROR: PIDs alive after kill: {survivors}")
        return False

    if comp["lock_path"].exists():
        try:
            comp["lock_path"].unlink()
            print(f"[{now()}] unlinked lock: {comp['lock_path'].name}")
        except Exception as e:
            print(f"[{now()}] couldn't unlink lock: {e}")

    new_pid = spawn_one(comp["script"])
    if not new_pid:
        return False
    print(f"[{now()}] spawned PID={new_pid}")

    if wait_log(comp["log_path"], comp["heartbeat_pattern"], log_size_before, 60):
        print(f"[{now()}] OK heartbeat detected")
    else:
        print(f"[{now()}] no heartbeat in 60s")
        return False

    final = find_procs(comp["match"])
    print(f"[{now()}] after fix: {len(final)} instance(s)")
    for p in final:
        print(f"          PID={p['pid']}  started={p['started']}  exe={Path(p['exe']).name}")
    return len(final) == 1


def main() -> int:
    print(f"=== fix_dupe_root_cause ({datetime.now()}) ===")

    # 1. Disable redundant schtasks
    print()
    print("--- step 1: disable redundant scheduled tasks ---")
    schtask_ok = True
    for tname in REDUNDANT_SCHTASKS:
        if not disable_schtask(tname):
            schtask_ok = False

    # 2. Wait briefly so any in-flight watchdog runs finish
    print()
    print(f"[{now()}] sleeping 8s so any in-flight schtask runs complete...")
    time.sleep(8)

    # 3. Fix each component
    print()
    print("--- step 2: kill dupes + spawn singletons ---")
    overall_ok = schtask_ok
    for comp in COMPONENTS:
        ok = fix_component(comp)
        overall_ok = overall_ok and ok

    # 4. Wait additional 60s and verify still singleton (catch process_watchdog respawn)
    print()
    print(f"[{now()}] waiting 70s to verify NO dupe-respawn occurs...")
    time.sleep(70)

    print()
    print("--- step 3: 70-second-later verification ---")
    for comp in COMPONENTS:
        procs = find_procs(comp["match"])
        if len(procs) == 1:
            print(f"  OK   {comp['name']}: 1 instance (singleton stable)")
        else:
            print(f"  WARN {comp['name']}: {len(procs)} instances — dupe respawned!")
            for p in procs:
                print(f"        PID={p['pid']}  started={p['started']}  exe={Path(p['exe']).name}")
            overall_ok = False

    print()
    print("=" * 72)
    print(f"  Final: {'SUCCESS' if overall_ok else 'PARTIAL — dupe-respawn detected'}")
    print("=" * 72)
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
