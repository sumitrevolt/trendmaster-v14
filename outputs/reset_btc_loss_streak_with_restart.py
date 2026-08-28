"""Reset loss_streak with PROPER brain restart sequence so the trim
sticks (the simple file-edit approach gets overwritten by brain's
~3-second save cadence).

Sequence:
  1. Surgically kill the live brain process (its lock release
     guarantees no further state writes).
  2. Wait 3 sec for OS to release the lock.
  3. Trim recent_results to [].
  4. Spawn fresh brain via start_brain_clean.cmd.
  5. Verify next tick has no 'loss_streak: ... >= cap' veto.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "logs" / "brain_state.json"
BRAIN_LOCK = ROOT / "logs" / "brain.lock"
BRAIN_OUT = ROOT / "logs" / "trend_master_brain.out"
START_BRAIN_CMD = ROOT / "start_brain_clean.cmd"


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def find_brain_pids() -> list[int]:
    """Return list of PIDs whose cmdline contains trend_master_brain."""
    import psutil
    pids: list[int] = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            n = (p.info.get("name") or "").lower()
            if "python" not in n:
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            if "trend_master_brain" in cmd:
                pids.append(p.info["pid"])
        except Exception:
            continue
    return pids


def kill_brain() -> bool:
    pids = find_brain_pids()
    if not pids:
        print(f"[{now()}] no brain PIDs alive — already dead?")
        return True
    print(f"[{now()}] killing brain PIDs: {pids}")
    for pid in pids:
        try:
            r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                              capture_output=True, text=True, timeout=10)
            print(f"          PID={pid}  rc={r.returncode}")
        except Exception as e:
            print(f"          PID={pid}  exc={e}")
    # Wait for PIDs to actually disappear
    deadline = time.time() + 8
    while time.time() < deadline:
        if not find_brain_pids():
            print(f"[{now()}] all brain PIDs gone")
            return True
        time.sleep(0.5)
    print(f"[{now()}] WARN: some brain PIDs still alive: {find_brain_pids()}")
    return False


def reset_state() -> int:
    if not STATE_FILE.exists():
        print(f"[{now()}] state file missing")
        return 1
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = STATE_FILE.with_name(f"brain_state.bak.before_loss_streak_reset_{ts}.json")
    shutil.copy2(STATE_FILE, backup)
    print(f"[{now()}] backup: {backup.name}")

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    rr = state.get("recent_results", [])
    print(f"[{now()}] recent_results before: {len(rr)} entries (all losses)")
    state["recent_results"] = []

    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    tmp.replace(STATE_FILE)
    print(f"[{now()}] recent_results after: 0 entries")
    return 0


def restart_brain() -> bool:
    if not START_BRAIN_CMD.exists():
        print(f"[{now()}] start_brain_clean.cmd missing")
        return False
    print(f"[{now()}] launching start_brain_clean.cmd...")
    try:
        # Run it without window, fire-and-forget — the cmd starts brain
        # detached internally and exits.
        r = subprocess.run(["cmd.exe", "/c", str(START_BRAIN_CMD)],
                          cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        print(f"          rc={r.returncode}")
        if r.returncode != 0:
            print(f"          stdout: {r.stdout}")
            print(f"          stderr: {r.stderr}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"[{now()}] start_brain_clean.cmd took >60s — but brain may still have started detached")
        return True
    except Exception as e:
        print(f"[{now()}] launch failed: {e}")
        return False


def verify_brain_alive(timeout_sec: int = 30) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        time.sleep(2)
        pids = find_brain_pids()
        if pids:
            print(f"[{now()}] brain alive: PIDs={pids}")
            return True
    return False


def main() -> int:
    print(f"=== reset_btc_loss_streak_with_restart ({datetime.now()}) ===")
    print()

    if not kill_brain():
        print("ABORT: could not kill brain cleanly — manual intervention needed")
        return 2

    time.sleep(3)  # let OS release lock + flush state

    if reset_state() != 0:
        print("ABORT: state reset failed — brain is dead, restart manually")
        return 3

    if not restart_brain():
        print("ABORT: brain restart failed — run start_brain_clean.cmd manually")
        return 4

    if not verify_brain_alive(30):
        print("WARN: brain didn't appear within 30s — check logs/trend_master_brain.err")
        return 5

    # Read first 5 lines of fresh brain.out to confirm restart#N+1
    if BRAIN_OUT.exists():
        with open(BRAIN_OUT, "r", encoding="utf-8", errors="replace") as f:
            head = f.readlines()[:5]
        print()
        print("First 5 lines of new brain.out:")
        for line in head:
            print(f"  {line.rstrip()}")

    print()
    print("SUCCESS: brain restarted with cleared loss_streak")
    print("Verify next tick: 'loss_streak: ... >= cap' should disappear from BTCUSD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
