"""Brain forensics monitor — captures memory/CPU snapshots + heartbeat
to disk every 30 seconds so silent brain crashes leave a forensic trail.

The 2026-05-09 incident: brain died at 20:49 IST without writing
trend_master_brain.err. No traceback. Possible causes (couldn't
distinguish without forensics):
  - Out-of-memory kill by Windows (silent SIGKILL)
  - Defender quarantine of a Python module mid-run
  - External taskkill from rogue script
  - Unhandled exception in a thread that bypassed sys.excepthook

This monitor runs as a sibling process (separate PID, separate lifetime
from brain) and writes:
  logs/brain_forensics.jsonl — one JSON-line per 30s sample with
    timestamp, brain_pid, alive, memory_rss_mb, memory_vms_mb,
    num_threads, cpu_percent, last_log_line_timestamp.

When brain dies, the LAST line in this jsonl tells you the state at
the moment of death (memory pressure, CPU spike, thread leak, etc.).

Run via: schtask "TrendMaster Brain Forensics" — every 30s.
Or detached: pythonw tools/brain_forensics_monitor.py --detached
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "logs" / "brain_forensics.jsonl"
BRAIN_PID_FILE = ROOT / "logs" / "brain.pid"
BRAIN_OUT = ROOT / "logs" / "trend_master_brain.out"
SAMPLE_INTERVAL_SEC = 30
MAX_LOG_BYTES = 50 * 1024 * 1024  # 50 MB cap


def read_brain_pid() -> int | None:
    if not BRAIN_PID_FILE.exists():
        return None
    try:
        return int(BRAIN_PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def find_brain_proc(brain_pid: int | None):
    """Returns psutil.Process for brain, walking parent->children if pid
    file points to a venv launcher shim that exec'd Python311 child."""
    import psutil
    candidates = []
    if brain_pid is not None and psutil.pid_exists(brain_pid):
        try:
            p = psutil.Process(brain_pid)
            candidates.append(p)
        except Exception:
            pass
    # Also scan for any python with trend_master_brain in cmdline
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            n = (proc.info.get("name") or "").lower()
            if "python" not in n:
                continue
            cmd = " ".join(proc.info.get("cmdline") or [])
            if "trend_master_brain" in cmd:
                candidates.append(psutil.Process(proc.info["pid"]))
        except Exception:
            continue
    if not candidates:
        return None
    # Prefer the one with most memory (real interpreter, not shim)
    candidates.sort(key=lambda p: -p.memory_info().rss if hasattr(p, "memory_info") else 0)
    return candidates[0]


def last_log_timestamp() -> str | None:
    """Tail of trend_master_brain.out — extract latest YYYY-MM-DD HH:MM:SS."""
    if not BRAIN_OUT.exists():
        return None
    try:
        sz = BRAIN_OUT.stat().st_size
        chunk_size = min(8192, sz)
        with open(BRAIN_OUT, "rb") as f:
            f.seek(max(0, sz - chunk_size))
            tail = f.read().decode("utf-8", errors="replace")
        m = re.findall(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", tail)
        return m[-1] if m else None
    except Exception:
        return None


def sample_once() -> dict:
    import psutil
    brain_pid = read_brain_pid()
    proc = find_brain_proc(brain_pid)
    sample = {
        "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "brain_pid_file": brain_pid,
        "alive": proc is not None,
        "last_log_ts": last_log_timestamp(),
    }
    if proc is not None:
        try:
            mem = proc.memory_info()
            sample.update({
                "actual_pid": proc.pid,
                "memory_rss_mb": round(mem.rss / 1024 / 1024, 1),
                "memory_vms_mb": round(mem.vms / 1024 / 1024, 1),
                "num_threads": proc.num_threads(),
                "cpu_percent": proc.cpu_percent(interval=0.1),
                "create_time": datetime.fromtimestamp(proc.create_time()).isoformat(timespec="seconds"),
                "uptime_min": round((time.time() - proc.create_time()) / 60, 1),
                "num_handles": getattr(proc, "num_handles", lambda: -1)(),
                "num_open_files": len(proc.open_files()) if hasattr(proc, "open_files") else -1,
            })
            # Detect children (venv shim → Python311 child)
            try:
                children = proc.children()
                sample["num_children"] = len(children)
            except Exception:
                pass
        except Exception as e:
            sample["sample_error"] = str(e)
    # Also sample system memory pressure
    try:
        vm = psutil.virtual_memory()
        sample["sys_mem_percent"] = vm.percent
        sample["sys_mem_avail_mb"] = round(vm.available / 1024 / 1024, 1)
    except Exception:
        pass
    return sample


def append_sample(sample: dict) -> None:
    LOG_PATH.parent.mkdir(exist_ok=True)
    # Rotate if too big (lossy: keep last 25MB)
    if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_LOG_BYTES:
        bak = LOG_PATH.with_suffix(".jsonl.old")
        try:
            if bak.exists():
                bak.unlink()
            LOG_PATH.rename(bak)
        except Exception:
            pass
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(sample, separators=(",", ":")) + "\n")


def run_once() -> int:
    sample = sample_once()
    append_sample(sample)
    if not sample.get("alive"):
        # Brain dead — print warning so any wrapper sees it
        print(f"[ALERT] brain DEAD at {sample['ts_utc']} (pid_file={sample.get('brain_pid_file')})")
        return 2
    return 0


def run_forever() -> int:
    print(f"brain_forensics_monitor: sampling every {SAMPLE_INTERVAL_SEC}s -> {LOG_PATH}")
    while True:
        try:
            sample = sample_once()
            append_sample(sample)
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            try:
                with open(LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts_utc": datetime.now(timezone.utc).isoformat(),
                                        "monitor_error": str(e)}) + "\n")
            except Exception:
                pass
        time.sleep(SAMPLE_INTERVAL_SEC)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Single sample then exit")
    parser.add_argument("--detached", action="store_true", help="Run forever loop")
    args = parser.parse_args()
    if args.detached:
        return run_forever()
    return run_once()


if __name__ == "__main__":
    raise SystemExit(main())
