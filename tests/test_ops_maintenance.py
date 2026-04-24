"""Unit tests for ai_trading_agents.ops_maintenance."""

from __future__ import annotations

import gzip
import json
import os
import time
from pathlib import Path

import pytest

from ai_trading_agents.ops_maintenance import (
    rotate_logs,
    snapshot_state,
    snapshot_models,
    vacuum_events,
    run_all,
)


def test_rotate_small_file_does_nothing(tmp_path):
    log = tmp_path / "trend_master_brain.log"
    log.write_text("hello\n")
    rotated = rotate_logs(tmp_path, max_mb=10.0)
    assert rotated == []
    assert log.exists()
    assert log.read_text() == "hello\n"


def test_rotate_large_file_truncates(tmp_path):
    log = tmp_path / "trend_master_brain.log"
    log.write_text("A" * (2 * 1024 * 1024))  # 2 MB
    rotated = rotate_logs(tmp_path, max_mb=1.0, compress=True)
    assert len(rotated) == 1
    # Original file exists and is truncated.
    assert log.exists()
    assert log.stat().st_size == 0
    # Archive is gzipped.
    archive = Path(rotated[0])
    assert archive.exists()
    assert archive.suffix == ".gz"
    with gzip.open(archive, "rb") as f:
        assert len(f.read()) == 2 * 1024 * 1024


def test_rotate_uncompressed(tmp_path):
    log = tmp_path / "trend_master_brain.log"
    log.write_text("Z" * (2 * 1024 * 1024))
    rotated = rotate_logs(tmp_path, max_mb=1.0, compress=False)
    assert len(rotated) == 1


def test_snapshot_state_copies_file(tmp_path):
    src = tmp_path / "brain_state.json"
    src.write_text('{"halted": false}')
    dest_dir = tmp_path / "backups"
    path = snapshot_state(src, dest_dir, keep_days=7)
    assert path is not None
    assert Path(path).exists()
    assert json.loads(Path(path).read_text()) == {"halted": False}


def test_snapshot_state_missing_source(tmp_path):
    p = snapshot_state(tmp_path / "missing.json", tmp_path / "out")
    assert p is None


def test_snapshot_models_copies_pkls(tmp_path):
    src = tmp_path / "models"
    src.mkdir()
    (src / "lgbm_METALS.pkl").write_bytes(b"fake-pickle")
    (src / "registry.json").write_text("{}")
    dest = tmp_path / "mb"
    out = snapshot_models(src, dest, keep_versions=3)
    assert len(out) == 2


def test_vacuum_events_prunes_old(tmp_path):
    ev = tmp_path / "events.jsonl"
    now = int(time.time())
    old = now - 120 * 86400  # 120 days ago
    lines = [json.dumps({"ts": old, "k": "signal"}) + "\n" for _ in range(50)]
    lines += [json.dumps({"ts": now, "k": "signal"}) + "\n" for _ in range(50)]
    ev.write_text("".join(lines))
    pruned = vacuum_events(ev, max_lines=200, max_age_days=60)
    assert pruned >= 50
    kept = ev.read_text().splitlines()
    assert len(kept) <= 50


def test_vacuum_nonexistent_ok(tmp_path):
    assert vacuum_events(tmp_path / "none.jsonl") == 0


def test_run_all_returns_report(tmp_path):
    # Set up a minimal fake project structure.
    (tmp_path / "logs").mkdir()
    (tmp_path / "ai_trading_agents" / "ml_models").mkdir(parents=True)
    (tmp_path / "logs" / "brain_state.json").write_text('{"x": 1}')
    rep = run_all(project_root=tmp_path)
    assert rep.ts > 0
    assert isinstance(rep.rotated, list)
    assert isinstance(rep.snapshots, list)
    assert isinstance(rep.errors, list)
