"""
structured_log.py — optional JSON-lines logging for v14.

Why this exists
---------------
The brain uses free-form stdlib `logging` strings. Great for eyeballing
a terminal, bad for anything else — you can't grep reliably, can't feed
Loki / Elasticsearch / Datadog, and every operator has to learn the
exact phrasing of each log site.

This module adds an optional JSON-line formatter. When the env var
`LOG_FORMAT=json` is set at brain startup, every `logger.info(...)`
call emits a single JSON object per line with consistent fields
(`ts`, `level`, `msg`, `logger`, `module`, plus any `extra=` dict passed
in). Grep-friendly, parse-friendly, aggregator-friendly.

When `LOG_FORMAT` is unset (the default), behavior is unchanged —
existing logs stay free-form, the module is a no-op.

Context propagation
-------------------
We carry a per-symbol `corr_id` through contextvars so a single
`tick_once(sym)` call's log lines can be correlated without threading
them through every log call. The brain calls:

    with bind_context(symbol="XAUUSD", corr_id="abc123"):
        do_tick_stuff()   # every logger.info inside this block gets
                          # symbol+corr_id fields in the JSON output

Minimal dep
-----------
No `structlog` dependency — pure stdlib. Adds ~90 LoC. If structlog is
installed we do NOT override it (`get_logger()` still returns a stdlib
logger either way) — the two co-exist.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Optional

_CONTEXT: ContextVar[Dict[str, Any]] = ContextVar("_tm_context", default={})


@contextmanager
def bind_context(**kwargs):
    """Attach the given k/v pairs to every log record emitted inside
    the `with` block. Nested blocks stack cleanly; the parent's context
    is restored on exit."""
    token = _CONTEXT.set({**_CONTEXT.get(), **kwargs})
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def current_context() -> Dict[str, Any]:
    """Read-only view of the active context."""
    return dict(_CONTEXT.get())


class JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON.

    Schema:
        ts        — ISO-8601 UTC with ms precision
        level     — INFO / WARNING / ERROR / ...
        logger    — `logger.name`
        module    — file:lineno
        msg       — rendered message string (after % args)
        extra     — any kwargs passed as `extra={...}`
        ctx       — active `bind_context` fields at emit time

    If the record has an exception, `exc` is appended as the traceback
    string. Safe under concurrent emission — no state is held on the
    formatter itself.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": _iso_utc(record.created),
            "level": record.levelname,
            "logger": record.name,
            "module": f"{record.module}:{record.lineno}",
            "msg": record.getMessage(),
        }
        # Pull any `extra=` fields the caller attached. stdlib logging
        # stores them as attributes on the record, flattened — we copy
        # non-reserved ones only.
        _reserved = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _reserved and not k.startswith("_")}
        if extras:
            payload["extra"] = extras
        ctx = current_context()
        if ctx:
            payload["ctx"] = ctx
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=_default_serializer, separators=(",", ":"), ensure_ascii=False)


def _iso_utc(created: float) -> str:
    t = time.gmtime(created)
    ms = int((created - int(created)) * 1000)
    return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}T{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}.{ms:03d}Z"


def _default_serializer(obj):
    """Best-effort non-native → repr fallback for JSON dump."""
    try:
        return repr(obj)
    except Exception:
        return "<unserializable>"


def configure(level: Optional[int] = None, stream=None) -> bool:
    """Install the JSON formatter when `LOG_FORMAT=json`. Returns True
    if we reconfigured; False if the env var wasn't set and we left
    existing handlers untouched.

    Call early in brain startup, once per process.
    """
    if os.getenv("LOG_FORMAT", "").lower() not in ("json", "jsonl", "json-lines"):
        return False

    root = logging.getLogger()
    root.setLevel(level or _level_from_env())

    # Replace existing stream handlers' formatters rather than adding a
    # new handler — avoids double-emission if something else already
    # configured logging.
    _stream = stream or sys.stderr
    fmt = JsonFormatter()
    replaced = False
    for h in list(root.handlers):
        if isinstance(h, logging.StreamHandler):
            h.setFormatter(fmt)
            replaced = True
    if not replaced:
        h = logging.StreamHandler(_stream)
        h.setFormatter(fmt)
        root.addHandler(h)
    return True


def _level_from_env() -> int:
    name = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


__all__ = [
    "JsonFormatter",
    "bind_context",
    "current_context",
    "configure",
]
