"""
ops_maintenance.py — housekeeping for TrendMaster v14.

Why this exists
---------------
A production trading system needs operational hygiene that a retail
scaffold usually skips:
  * Log files grow unbounded — eventually fill the disk and crash the
    brain mid-trade.
  * State (`brain_state.json`) is a single point of failure — one bad
    write and cooldowns / DD tracking are lost.
  * Model files (`ai_trading_agents/ml_models/*.pkl`) can get corrupted
    during a train-time crash.
  * Event log (`logs/events.jsonl`) eats disk faster than everything
    else combined.

This module provides:
  * `rotate_logs(max_mb)` — splits large logs into `.1`, `.2`, ...
    archives, keeping the latest N under `keep_count`.
  * `snapshot_state(source, dest_dir, keep_days)` — rotating daily
    backups of state + model registry.
  * `vacuum(max_events, log_age_days)` — prunes oldest events beyond
    threshold so /events stays bounded.
  * `run_all()` — convenience wrapper the supervisor calls at UTC
    midnight.

No external deps. Pure stdlib.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("ops_maintenance")


@dataclass
class MaintenanceReport:
    ts: int = 0
    rotated: List[str] = field(default_factory=list)
    snapshots: List[str] = field(default_factory=list)
    pruned_events: int = 0
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__


# ======================================================================
# Log rotation
# ======================================================================
def rotate_logs(
    log_dir: Path,
    max_mb: float = 10.0,
    keep_count: int = 7,
    compress: bool = True,
    patterns: Optional[List[str]] = None,
) -> List[str]:
    """Rotate any log file > `max_mb`. Keeps `.1`, `.2`, ... up to
    `keep_count`. Older archives deleted. `.gz` suffix when compress=True.

    Safe to call while the brain is running — we only move files that
    have grown past the limit. The brain's next log write re-creates
    the original path.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    patterns = patterns or [
        "trend_master_brain.log",
        "trend_master_brain.out",
        "trend_master_brain.err",
        "dashboard.out",
        "dashboard.err",
        "supervisor.log",
        "events.jsonl",
        "trading.log",
    ]
    rotated: List[str] = []
    max_bytes = int(max_mb * 1024 * 1024)
    for name in patterns:
        path = log_dir / name
        if not path.exists():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size < max_bytes:
            continue
        # Shift existing archives .1 → .2 ... up to keep_count.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        ext = ".gz" if compress else ""
        archive = log_dir / f"{name}.{stamp}{ext}"
        try:
            if compress:
                with open(path, "rb") as src, gzip.open(archive, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                # Truncate the original — safer than delete + recreate
                # because other processes may hold open file handles.
                open(path, "w").close()
            else:
                shutil.move(str(path), str(archive))
            rotated.append(str(archive))
        except Exception as e:
            logger.warning("rotate_logs failed for %s: %s", path, e)
            continue
        # Garbage-collect old archives matching this prefix.
        archives = sorted(log_dir.glob(f"{name}.*"))
        if len(archives) > keep_count:
            for old in archives[:-keep_count]:
                try:
                    old.unlink()
                except OSError:
                    pass
    return rotated


# ======================================================================
# State snapshots
# ======================================================================
def snapshot_state(source_path: Path, dest_dir: Path, keep_days: int = 14) -> Optional[str]:
    """Copy the brain state file to dest_dir/brain_state_YYYY-MM-DD.json.
    Prune entries older than `keep_days`.
    """
    source_path = Path(source_path)
    dest_dir = Path(dest_dir)
    if not source_path.exists():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest = dest_dir / f"brain_state_{today}.json"
    try:
        shutil.copy2(source_path, dest)
    except Exception as e:
        logger.warning("snapshot_state failed: %s", e)
        return None
    # Prune
    cutoff = time.time() - keep_days * 86400
    for f in dest_dir.glob("brain_state_*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass
    return str(dest)


def snapshot_models(models_dir: Path, dest_dir: Path, keep_versions: int = 5) -> List[str]:
    """Copy all ml_models/*.pkl + registry.json into a dated subfolder."""
    models_dir = Path(models_dir)
    dest_dir = Path(dest_dir)
    if not models_dir.exists():
        return []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest = dest_dir / today
    dest.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    for f in models_dir.iterdir():
        if f.is_file() and f.suffix in (".pkl", ".json"):
            try:
                shutil.copy2(f, dest / f.name)
                copied.append(str(dest / f.name))
            except Exception as e:
                logger.warning("snapshot_models copy failed %s: %s", f, e)
    # Keep only `keep_versions` dated directories.
    dated = sorted([d for d in dest_dir.iterdir() if d.is_dir()])
    if len(dated) > keep_versions:
        for old in dated[:-keep_versions]:
            try:
                shutil.rmtree(old, ignore_errors=True)
            except Exception:
                pass
    return copied


# ======================================================================
# Event log vacuum
# ======================================================================
def vacuum_events(events_path: Path, max_lines: int = 500_000, max_age_days: int = 60) -> int:
    """Prune the JSONL event log if too large or too old.

    Keeps the TAIL — most recent events — because those are the ones
    you actually use for replay and debugging.
    """
    events_path = Path(events_path)
    if not events_path.exists():
        return 0
    cutoff_ts = int(time.time() - max_age_days * 86400)
    try:
        with open(events_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.warning("vacuum_events read failed: %s", e)
        return 0
    # Keep only the tail + only entries newer than cutoff.
    kept: List[str] = []
    for line in lines[-max_lines:]:
        try:
            obj = json.loads(line)
            if int(obj.get("ts", 0)) >= cutoff_ts:
                kept.append(line)
        except Exception:
            continue
    dropped = len(lines) - len(kept)
    if dropped <= 0:
        return 0
    # Write back atomically.
    tmp = events_path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(kept)
        os.replace(tmp, events_path)
    except Exception as e:
        logger.warning("vacuum_events write failed: %s", e)
        return 0
    return dropped


# ======================================================================
# Master run
# ======================================================================
def run_all(project_root: Optional[Path] = None) -> MaintenanceReport:
    report = MaintenanceReport(ts=int(time.time()))
    # Junction-safe project root — see ai_trading_agents._paths and the
    # 2026-04-30 postmortem.
    from ai_trading_agents._paths import project_root as _project_root

    root = Path(project_root) if project_root else _project_root()
    try:
        rotated = rotate_logs(root / "logs")
        report.rotated = rotated
    except Exception as e:
        report.errors.append(f"rotate_logs: {e!r}")
    try:
        snap = snapshot_state(root / "logs" / "brain_state.json", root / "logs" / "state_backups")
        if snap:
            report.snapshots.append(snap)
    except Exception as e:
        report.errors.append(f"snapshot_state: {e!r}")
    try:
        snaps = snapshot_models(root / "ai_trading_agents" / "ml_models", root / "logs" / "model_backups")
        report.snapshots.extend(snaps)
    except Exception as e:
        report.errors.append(f"snapshot_models: {e!r}")
    try:
        pruned = vacuum_events(root / "logs" / "events.jsonl")
        report.pruned_events = pruned
    except Exception as e:
        report.errors.append(f"vacuum_events: {e!r}")
    return report


__all__ = [
    "MaintenanceReport",
    "rotate_logs",
    "snapshot_state",
    "snapshot_models",
    "vacuum_events",
    "run_all",
]
