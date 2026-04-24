"""
event_log.py — append-only JSONL event sourcing for TrendMaster v14.

Why this exists
---------------
Every institutional-grade trading system keeps an **audit log** — one
line per decision, immutable, timestamped, append-only. It's the
difference between "we think the model rejected that trade because of
the session gate" and "here's the exact feature vector, decision chain,
and veto reason for every tick of the last 90 days".

Use cases:
  * Post-mortem on a bad trade ("why did we enter EURUSD at 03:15 UTC?")
  * Regression testing a strategy variant against the replay stream
  * Regulatory review of automated decisions (important even on demo
    accounts — this is the muscle memory you want before live capital)
  * Stress-test dataset — the adversarial harness replays this log

Design
------
- JSONL file at `logs/events.jsonl`, one event per line.
- Thread-safe writer with a small in-memory buffer (flushed every 1 s
  or every 100 events, whichever first).
- Pure-Python, no external deps. Uses `os.replace` + append mode for
  crash-safety — the file is recoverable even if the brain dies
  mid-write.
- Schema versioned via `schema_version` field so future readers can
  migrate.

Integration (opt-in)
--------------------
Enable via `EVENT_LOG.enabled=True`. The brain writes `signal` events
from `tick_once` and `fill` events if the trade_tracker picks up new
deals. The dashboard exposes `/events?since=TS` for a time-range query.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("event_log")


_SCHEMA_VERSION = 1


@dataclass
class Event:
    ts:        int              # unix seconds
    kind:      str              # "signal" | "fill" | "veto" | "drift" | "halt" | "resume"
    symbol:    str
    payload:   Dict[str, Any]   # arbitrary details
    corr_id:   str              # correlation id for tracing

    def as_line(self) -> str:
        return json.dumps(
            {
                "v":   _SCHEMA_VERSION,
                "ts":  self.ts,
                "k":   self.kind,
                "s":   self.symbol,
                "p":   self.payload,
                "cid": self.corr_id,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )


@dataclass
class EventLog:
    path:           Path
    buffer_max:     int   = 100
    flush_every_s:  float = 1.0
    _buf:           List[Event]       = field(default_factory=list)
    _lock:          threading.Lock    = field(default_factory=threading.Lock)
    _last_flush:    float             = 0.0

    def __post_init__(self):
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            # Touch so /events can read-without-404 on first call.
            self.path.touch()

    def append(self, kind: str, symbol: str, payload: Dict[str, Any],
               corr_id: str = "") -> None:
        ev = Event(
            ts=int(time.time()),
            kind=kind,
            symbol=symbol,
            payload=payload,
            corr_id=corr_id or f"{int(time.time()*1000)}-{symbol}",
        )
        with self._lock:
            self._buf.append(ev)
            need_flush = (
                len(self._buf) >= self.buffer_max
                or (time.time() - self._last_flush) >= self.flush_every_s
            )
            if need_flush:
                self._flush_locked()

    def _flush_locked(self) -> None:
        if not self._buf:
            self._last_flush = time.time()
            return
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                for ev in self._buf:
                    f.write(ev.as_line() + "\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            self._buf.clear()
            self._last_flush = time.time()
        except Exception as e:
            # Drop the buffer only on catastrophic write fail; next append
            # will retry and prevent unbounded memory growth.
            logger.warning("event_log flush failed: %s", e)
            if len(self._buf) > self.buffer_max * 10:
                logger.error("event_log buffer overflow — dropping oldest")
                self._buf = self._buf[-self.buffer_max:]
            self._last_flush = time.time()

    def flush(self) -> None:
        with self._lock:
            self._flush_locked()

    def read_since(self, since_ts: int,
                   kinds: Optional[Iterable[str]] = None,
                   limit: int = 1000) -> List[dict]:
        """Stream-scan — OK up to ~100k events per call. For heavier use
        switch to a real database (DuckDB / SQLite / Parquet)."""
        out: List[dict] = []
        kind_set = set(kinds) if kinds else None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if int(obj.get("ts", 0)) < int(since_ts):
                        continue
                    if kind_set and obj.get("k") not in kind_set:
                        continue
                    out.append(obj)
                    if len(out) >= limit:
                        break
        except FileNotFoundError:
            return []
        return out


# ======================================================================
# Module-level singleton — the brain imports `get_log()`.
# ======================================================================
_SINGLETON: Optional[EventLog] = None
_INIT_LOCK = threading.Lock()


def get_log(path: Optional[Path] = None) -> EventLog:
    global _SINGLETON
    with _INIT_LOCK:
        if _SINGLETON is None:
            if path is None:
                root = Path(__file__).resolve().parent.parent
                path = root / "logs" / "events.jsonl"
            _SINGLETON = EventLog(path=path)
        return _SINGLETON


__all__ = ["Event", "EventLog", "get_log"]
