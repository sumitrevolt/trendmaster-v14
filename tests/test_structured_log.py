"""Unit tests for ai_trading_agents.structured_log (JSON formatter + ctx)."""
from __future__ import annotations

import json
import logging

import pytest

from ai_trading_agents import structured_log as sl


def _make_record(msg="hello", **extras):
    rec = logging.LogRecord(
        name="test_logger", level=logging.INFO, pathname=__file__, lineno=7,
        msg=msg, args=(), exc_info=None, func="t",
    )
    for k, v in extras.items():
        setattr(rec, k, v)
    rec.module = "test_structured_log"
    return rec


def test_formatter_emits_valid_json():
    fmt = sl.JsonFormatter()
    rec = _make_record("brain boot")
    out = fmt.format(rec)
    data = json.loads(out)
    assert data["level"] == "INFO"
    assert data["msg"] == "brain boot"
    assert data["logger"] == "test_logger"
    assert "ts" in data


def test_extras_round_trip():
    fmt = sl.JsonFormatter()
    rec = _make_record("veto", symbol="XAUUSD", reason="spread")
    out = json.loads(fmt.format(rec))
    assert out["extra"]["symbol"] == "XAUUSD"
    assert out["extra"]["reason"] == "spread"


def test_bind_context_propagates():
    fmt = sl.JsonFormatter()
    with sl.bind_context(symbol="EURUSD", corr_id="abc"):
        rec = _make_record("tick")
        out = json.loads(fmt.format(rec))
    assert out["ctx"]["symbol"] == "EURUSD"
    assert out["ctx"]["corr_id"] == "abc"


def test_bind_context_nested_restores_parent():
    with sl.bind_context(outer=1):
        assert sl.current_context() == {"outer": 1}
        with sl.bind_context(inner=2):
            assert sl.current_context() == {"outer": 1, "inner": 2}
        assert sl.current_context() == {"outer": 1}
    assert sl.current_context() == {}


def test_configure_no_env_returns_false(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    assert sl.configure() is False


def test_configure_with_json_env_installs(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    # Use a scratch root so we don't pollute other tests.
    import io
    buf = io.StringIO()
    assert sl.configure(stream=buf) is True
    root = logging.getLogger()
    # At least one handler should now carry a JsonFormatter.
    have_json = any(isinstance(h.formatter, sl.JsonFormatter)
                    for h in root.handlers)
    assert have_json


def test_exception_field_populated_on_exc_info():
    fmt = sl.JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        exc_info = sys.exc_info()
    rec = logging.LogRecord(
        name="t", level=logging.ERROR, pathname=__file__, lineno=1,
        msg="caught", args=(), exc_info=exc_info, func="t",
    )
    rec.module = "test_structured_log"
    out = json.loads(fmt.format(rec))
    assert "exc" in out
    assert "ValueError" in out["exc"]
