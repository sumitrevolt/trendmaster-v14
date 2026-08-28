"""
Events.jsonl rotation daemon for TrendMaster v14.

Rotates events.jsonl when > threshold_mb. Compresses old rotations,
prunes very old archives. Wires the previously-dead vacuum_events
function into a scheduled task.

Pure-Python; uses only stdlib (os, gzip, shutil, pathlib, datetime).
"""

from __future__ import annotations
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import gzip
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOGS = REPO / "logs"
EVENTS = LOGS / "events.jsonl"


def maybe_rotate(threshold_mb: int, force: bool) -> tuple[bool, str]:
    if not EVENTS.exists():
        return False, "events.jsonl does not exist; nothing to rotate"
    size_mb = EVENTS.stat().st_size / (1024 * 1024)
    if not force and size_mb <= threshold_mb:
        return False, f"size={size_mb:.1f}MB ≤ {threshold_mb}MB threshold; no rotation"
    date_str = datetime.now().strftime("%Y-%m-%d")
    rotated = LOGS / f"events.jsonl.{date_str}"
    n = 1
    while rotated.exists():
        rotated = LOGS / f"events.jsonl.{date_str}.{n}"
        n += 1
    try:
        os.rename(EVENTS, rotated)
        EVENTS.touch()
        return True, f"rotated {size_mb:.1f}MB → {rotated.name}"
    except PermissionError as e:
        return False, f"PermissionError (file in use by brain?): {e}"
    except Exception as e:
        return False, f"rotation failed: {type(e).__name__}: {e}"


def compress_old(compress_days: int) -> list[str]:
    cutoff = datetime.now() - timedelta(days=compress_days)
    actions = []
    for f in LOGS.glob("events.jsonl.*"):
        if f.suffix == ".gz":
            continue
        # Skip today's rotation (no .gz on fresh files)
        try:
            file_age = datetime.fromtimestamp(f.stat().st_mtime)
            if file_age > cutoff:
                continue
            gz_path = f.with_suffix(f.suffix + ".gz")
            if gz_path.exists():
                continue
            with f.open("rb") as src, gzip.open(gz_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            saved_mb = (f.stat().st_size - gz_path.stat().st_size) / (1024 * 1024)
            f.unlink()
            actions.append(f"compressed {f.name} → {gz_path.name} (saved {saved_mb:.1f}MB)")
        except Exception as e:
            actions.append(f"compress failed for {f.name}: {e}")
    return actions


def prune_very_old(prune_days: int) -> list[str]:
    cutoff = datetime.now() - timedelta(days=prune_days)
    actions = []
    for f in LOGS.glob("events.jsonl.*"):
        try:
            file_age = datetime.fromtimestamp(f.stat().st_mtime)
            if file_age < cutoff:
                size_mb = f.stat().st_size / (1024 * 1024)
                f.unlink()
                actions.append(f"pruned {f.name} (was {size_mb:.1f}MB, age {(datetime.now() - file_age).days}d)")
        except Exception as e:
            actions.append(f"prune failed for {f.name}: {e}")
    return actions


def detect_brain_holds_handle() -> bool:
    """Best-effort: if brain.pid exists and PID is alive, brain probably has handle."""
    try:
        import psutil
    except ImportError:
        return False
    pid_file = LOGS / "brain.pid"
    if not pid_file.exists():
        return False
    text = pid_file.read_text(encoding="ascii", errors="ignore").strip()
    for line in text.splitlines():
        if line.strip().isdigit() and psutil.pid_exists(int(line.strip())):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold-mb", type=int, default=50)
    ap.add_argument("--compress-days", type=int, default=30)
    ap.add_argument("--prune-days", type=int, default=90)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    print("Events Rotator - " + datetime.now().strftime("%Y-%m-%d %H:%M local"))
    print("=" * 44)

    rotated, msg = maybe_rotate(args.threshold_mb, args.force)
    print(f"rotation: {msg}")

    print()
    compress_actions = compress_old(args.compress_days)
    if compress_actions:
        print("compression:")
        for a in compress_actions:
            print(f"  {a}")
    else:
        print("compression: nothing eligible")

    print()
    prune_actions = prune_very_old(args.prune_days)
    if prune_actions:
        print("pruning:")
        for a in prune_actions:
            print(f"  {a}")
    else:
        print("pruning: nothing eligible")

    if rotated and detect_brain_holds_handle():
        print()
        print("NOTE: Brain process is running and may have events.jsonl open.")
        print("On Windows, brain will keep writing to the renamed file until next restart.")
        print("New events.jsonl will be empty until then. Restart at next opportunity.")


if __name__ == "__main__":
    main()
