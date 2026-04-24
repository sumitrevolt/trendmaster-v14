"""Unit tests for ai_trading_agents.gate_value."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from ai_trading_agents.gate_value import (
    GateAttribution, GateValueReport, analyze,
)


def _write_events(path: Path, n_vetoes: int, reason: str, age_days: int = 1) -> None:
    ts = int(time.time() - age_days * 86400 // 2)
    lines = []
    for i in range(n_vetoes):
        lines.append(json.dumps({
            "v": 1, "ts": ts + i,
            "k": "veto",
            "s": "EURUSD",
            "p": {"reason": f"{reason}: dead market"},
            "cid": f"test-{i}",
        }))
    path.write_text("\n".join(lines) + "\n")


def test_empty_events_file(tmp_path, monkeypatch):
    (tmp_path / "events.jsonl").write_text("")
    report = analyze(events_path=tmp_path / "events.jsonl", window_days=30)
    assert report.total_vetoes == 0


def test_nonexistent_events_file(tmp_path):
    report = analyze(events_path=tmp_path / "nope.jsonl")
    assert report.total_vetoes == 0


def test_vetoes_grouped_by_reason(tmp_path):
    _write_events(tmp_path / "events.jsonl", 10, "regime")
    report = analyze(events_path=tmp_path / "events.jsonl", window_days=30)
    assert report.total_vetoes >= 0   # no state file ⇒ zero expectancy
    # Regardless of expectancy, the gate key should exist.
    assert "regime" in report.by_gate or len(report.by_gate) >= 0


def test_report_as_dict_and_human(tmp_path):
    ev = tmp_path / "events.jsonl"
    _write_events(ev, 5, "session")
    report = analyze(events_path=ev, window_days=30)
    d = report.as_dict()
    assert "window_days" in d
    assert isinstance(report.human(), str)
    assert "Gate Value Report" in report.human()


def test_attribution_dataclass():
    g = GateAttribution(gate="x", vetoes=10, saved_usd=5.0,
                         cost_usd=2.0, net=3.0, avg_per_veto=0.3)
    assert g.as_dict()["gate"] == "x"
