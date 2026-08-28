"""Verify singleton at LOGICAL level (parent venv launcher counts as one
with its Python311 child). On Windows, .venv\\Scripts\\pythonw.exe is a
shim that spawns the actual Python311 interpreter — so 2 PIDs per logical
instance is normal. We group by parent-child."""
from __future__ import annotations

import time
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"


def find_procs_with_parent(match: str) -> list[dict]:
    import psutil
    rows = []
    for p in psutil.process_iter(["pid", "ppid", "name", "cmdline", "create_time"]):
        try:
            n = (p.info.get("name") or "").lower()
            if "python" not in n:
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            if match not in cmd:
                continue
            rows.append({
                "pid": p.info["pid"],
                "ppid": p.info.get("ppid"),
                "name": p.info["name"],
                "started": datetime.fromtimestamp(p.info["create_time"]).strftime("%H:%M:%S"),
                "create_ts": p.info["create_time"],
            })
        except Exception:
            pass
    return rows


def group_logical(procs: list[dict]) -> list[list[dict]]:
    """Group parent and child as ONE logical instance."""
    by_pid = {p["pid"]: p for p in procs}
    children_of: dict[int, list[dict]] = {}
    roots: list[dict] = []
    for p in procs:
        ppid = p["ppid"]
        if ppid in by_pid:
            children_of.setdefault(ppid, []).append(p)
        else:
            roots.append(p)
    groups = []
    for r in roots:
        chain = [r]
        # follow children chain
        stack = [r["pid"]]
        seen = {r["pid"]}
        while stack:
            cur = stack.pop()
            for c in children_of.get(cur, []):
                if c["pid"] not in seen:
                    chain.append(c)
                    stack.append(c["pid"])
                    seen.add(c["pid"])
        groups.append(chain)
    return groups


def spawn_one(script: Path) -> int | None:
    DETACHED, NOWIN = 0x00000008, 0x08000000
    try:
        return subprocess.Popen(
            [str(PYTHONW), str(script)],
            cwd=str(ROOT),
            creationflags=DETACHED | NOWIN,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True,
        ).pid
    except Exception:
        return None


COMPONENTS = {
    "python_signal_executor": ROOT / "tools" / "python_signal_executor.py",
    "trailing_stop_manager": ROOT / "tools" / "trailing_stop_manager.py",
}


def main() -> int:
    print(f"=== verify_singleton_logical ({datetime.now()}) ===")

    # Step 1: Check current state
    print()
    for match, script in COMPONENTS.items():
        procs = find_procs_with_parent(match)
        groups = group_logical(procs)
        print(f"--- {match} ---")
        print(f"  raw PIDs: {len(procs)}")
        for p in procs:
            print(f"    PID={p['pid']} ppid={p['ppid']} started={p['started']} name={p['name']}")
        print(f"  logical instances (parent-child grouped): {len(groups)}")
        for i, g in enumerate(groups):
            pids = [p["pid"] for p in g]
            print(f"    group {i}: {pids}")

        # If 0 logical instances, spawn one
        if len(groups) == 0:
            print(f"  RESPAWN: 0 instances — spawning fresh")
            new_pid = spawn_one(script)
            print(f"  spawned PID={new_pid}")
        elif len(groups) > 1:
            # Sort by group's earliest create_ts; kill all but newest
            groups.sort(key=lambda g: min(p["create_ts"] for p in g))
            keep = groups[-1]
            for g in groups[:-1]:
                root = g[0]
                print(f"  KILL group root PID={root['pid']} (older)")
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(root["pid"])],
                               capture_output=True, text=True, timeout=10)
        else:
            print(f"  OK: exactly 1 logical instance")

    # Step 2: Wait 30s and re-verify
    print()
    print("Waiting 30s to verify state stable...")
    time.sleep(30)

    print()
    print("=== final logical state ===")
    overall_ok = True
    for match in COMPONENTS:
        procs = find_procs_with_parent(match)
        groups = group_logical(procs)
        marker = "OK  " if len(groups) == 1 else "WARN"
        print(f"  {marker} {match}: {len(procs)} PIDs in {len(groups)} logical instance(s)")
        for i, g in enumerate(groups):
            pids = [p["pid"] for p in g]
            started = min(p["started"] for p in g)
            print(f"        group {i} pids={pids} started={started}")
        if len(groups) != 1:
            overall_ok = False

    print()
    print(f"Final: {'SUCCESS — singleton confirmed' if overall_ok else 'FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
