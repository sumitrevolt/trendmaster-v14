"""Smoke tests for the code-review-graph tooling scripts.

These are import-level / basic-execution checks. They verify the scripts
don't crash on a valid graph DB and produce their expected outputs. Full
behavioral tests for trading logic live elsewhere — this file exists to
cover the audit/status utilities themselves so they don't rot silently.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _graph_db_present() -> bool:
    return (ROOT / ".code-review-graph" / "graph.db").exists()


@pytest.mark.skipif(not _graph_db_present(), reason="graph.db not built yet")
def test_graph_status_imports_cleanly() -> None:
    """tools/graph_status.py must import without side effects."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        mod = importlib.import_module("graph_status")
        assert callable(mod.main)
    finally:
        sys.path.pop(0)


@pytest.mark.skipif(not _graph_db_present(), reason="graph.db not built yet")
def test_graph_status_runs_end_to_end() -> None:
    """Running graph_status.py as a script against the real DB prints counts."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "graph_status.py")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # Must print the archive-share audit line somewhere.
    assert "archive share" in result.stdout


@pytest.mark.skipif(not _graph_db_present(), reason="graph.db not built yet")
def test_code_health_audit_produces_report(tmp_path, monkeypatch) -> None:
    """tools/code_health_audit.py writes docs/CODE_HEALTH_AUDIT.md."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        mod = importlib.import_module("code_health_audit")
        # Redirect report to a temp path to avoid overwriting the real one.
        monkeypatch.setattr(mod, "REPORT", tmp_path / "audit.md")
        rc = mod.main()
        assert rc == 0
        assert (tmp_path / "audit.md").exists()
        body = (tmp_path / "audit.md").read_text(encoding="utf-8")
        # Core sections must be present in the generated markdown.
        assert "# TrendMaster v14 Code Health Audit" in body
        assert "Untested live functions" in body
        assert "Dead-code candidates" in body
        assert "Complexity hotspots" in body
        assert "Change-risk nodes" in body
    finally:
        sys.path.pop(0)


def test_crg_hook_script_present() -> None:
    """tools/crg_hook.cmd must exist and reference the guard path."""
    hook = ROOT / "tools" / "crg_hook.cmd"
    assert hook.exists(), "tools/crg_hook.cmd missing"
    text = hook.read_text(encoding="utf-8", errors="ignore")
    # Safety: hook must never propagate a non-zero exit
    assert "exit /b 0" in text.lower()
    # Safety: hook must guard on .git presence
    assert ".git" in text
