"""ASCII-only recovery: brain is currently dead from full_btc_unblock
crashing in step 3. Steps 1-2 already done. This finishes the job:
  - Edit state (recent_results=[], last_processed_deal_ts=now)
  - Restart brain
  - Verify
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
BRAIN_OUT = ROOT / "logs" / "trend_master_brain.out"
START_BRAIN = ROOT / "start_brain_clean.cmd"


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now()}] {msg}")


def find_brain_pids() -> list[int]:
    import psutil
    return [
        p.info["pid"]
        for p in psutil.process_iter(["pid", "name", "cmdline"])
        if "python" in (p.info.get("name") or "").lower()
        and "trend_master_brain" in " ".join(p.info.get("cmdline") or [])
    ]


def main() -> int:
    print(f"=== full_btc_unblock_recovery ({datetime.now()}) ===")
    print()

    # Edit state
    log("STEP A: clearing recent_results + bumping last_processed_deal_ts")
    if not STATE_FILE.exists():
        log("  state file missing")
        return 1
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = STATE_FILE.with_name(f"brain_state.bak.recovery_{ts_str}.json")
    shutil.copy2(STATE_FILE, backup)
    log(f"  backup: {backup.name}")
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    n_before = len(state.get("recent_results", []))
    state["recent_results"] = []
    new_ts = int(time.time())
    old_ts = state.get("last_processed_deal_ts", 0)
    state["last_processed_deal_ts"] = new_ts
    log(f"  recent_results: {n_before} -> 0")
    log(f"  last_processed_deal_ts: {old_ts} -> {new_ts}")
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    tmp.replace(STATE_FILE)
    log("  state written")
    print()

    # Make sure brain is dead before restart (defensive)
    log("STEP B: ensuring brain is dead before restart")
    pids = find_brain_pids()
    if pids:
        log(f"  killing leftover PIDs: {pids}")
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                          capture_output=True, text=True)
        time.sleep(3)
    else:
        log("  no brain alive (expected)")
    print()

    # Start brain
    log("STEP C: launching start_brain_clean.cmd")
    if not START_BRAIN.exists():
        log("  start_brain_clean.cmd missing")
        return 2
    try:
        r = subprocess.run(["cmd.exe", "/c", str(START_BRAIN)], cwd=str(ROOT),
                          capture_output=True, text=True, timeout=60)
        log(f"  rc={r.returncode}")
        if r.returncode != 0:
            print(f"  stdout (last 500 chars): {r.stdout[-500:]}")
            print(f"  stderr (last 500 chars): {r.stderr[-500:]}")
            return 3
    except subprocess.TimeoutExpired:
        log("  timeout but brain may have started detached")
    print()

    # Verify
    log("STEP D: verifying brain alive")
    deadline = time.time() + 30
    while time.time() < deadline:
        time.sleep(2)
        pids = find_brain_pids()
        if pids:
            log(f"  brain alive: PIDs={pids}")
            break
    else:
        log("  brain didn't appear within 30s")
        return 4

    # Wait for first tick + check
    time.sleep(8)
    if not BRAIN_OUT.exists():
        log("  brain.out missing")
        return 5

    head = BRAIN_OUT.read_text(encoding="utf-8", errors="replace")
    if "TrendMaster brain online" not in head:
        log("  brain log doesn't show 'online' marker")
        return 6

    if "loss_streak" in head and "veto" in head:
        log("  WARN: loss_streak veto STILL appearing")
        for line in head.split("\n"):
            if "loss_streak" in line and "veto" in line:
                log(f"     {line}")
                break
    else:
        log("  no loss_streak veto seen - BTC unblocked")

    print()
    log("RECOVERY COMPLETE")
    log("  - patch_trade_tracker: done in earlier run")
    log("  - state cleared: recent_results=[], bookmark=now")
    log("  - brain restarted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
