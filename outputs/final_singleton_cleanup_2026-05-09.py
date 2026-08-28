"""Final cleanup — kill the older duplicate of each component (keep
newest), wait, verify ONE remains. Doesn't spawn anything new since
both current instances are alive and heartbeating."""
from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COMPONENTS = ["python_signal_executor", "trailing_stop_manager"]


def find_procs(match: str) -> list[dict]:
    import psutil
    rows: list[dict] = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            n = (p.info.get("name") or "").lower()
            if "python" not in n:
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            if match not in cmd:
                continue
            rows.append({
                "pid": p.info["pid"],
                "create_ts": p.info["create_time"],
                "started": datetime.fromtimestamp(p.info["create_time"]).strftime("%H:%M:%S"),
                "cmdline": cmd,
            })
        except Exception:
            pass
    return sorted(rows, key=lambda x: x["create_ts"])


def main() -> int:
    overall_ok = True
    for match in COMPONENTS:
        print()
        print(f"=== {match} ===")
        procs = find_procs(match)
        print(f"  found {len(procs)} instance(s)")
        for p in procs:
            print(f"    PID={p['pid']}  started={p['started']}")

        if len(procs) <= 1:
            print(f"  OK already singleton")
            continue

        # Keep the NEWEST (highest create_ts), kill the rest
        keep = procs[-1]
        kill = procs[:-1]
        print(f"  KEEP PID={keep['pid']}  (newest, started={keep['started']})")
        for k in kill:
            print(f"  KILL PID={k['pid']}  (older, started={k['started']})")
            r = subprocess.run(
                ["taskkill", "/F", "/PID", str(k["pid"])],
                capture_output=True, text=True, timeout=10
            )
            print(f"       rc={r.returncode}  out={r.stdout.strip()}")

        # Wait
        time.sleep(3)
        after = find_procs(match)
        print(f"  after kill: {len(after)} instance(s)")
        for p in after:
            print(f"    PID={p['pid']}  started={p['started']}")
        if len(after) != 1:
            overall_ok = False

    # 60 sec verification — make sure no respawn
    print()
    print("Waiting 65s to confirm no dupe respawn from any remaining schtask...")
    time.sleep(65)

    print()
    print("=== final state ===")
    for match in COMPONENTS:
        procs = find_procs(match)
        marker = "OK  " if len(procs) == 1 else "WARN"
        print(f"  {marker} {match}: {len(procs)} instance(s)")
        for p in procs:
            print(f"        PID={p['pid']}  started={p['started']}")
        if len(procs) != 1:
            overall_ok = False

    print()
    print(f"Final: {'SUCCESS' if overall_ok else 'FAIL — respawn still happening'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
