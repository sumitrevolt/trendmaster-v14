"""
state_store.py — durable state for the brain across restarts.

Why
---
The brain holds in-memory state that matters across restarts:
  * recent_results (rolling P&L list — feeds loss_streak gate)
  * cooldown_until_ts (when can we trade again after a streak)
  * last_signal_per_symbol (avoid double-firing across restarts)
  * start_of_day_equity (for daily profit lock)
  * daily_pnl (Telegram daily summary)
  * restart_count / last_started_at (operations visibility)

If the brain crashes mid-session, all of that is lost — cooldowns reset,
profit lock resets to 0, streak counter resets. This module gives us a
small atomic JSON snapshot so a fresh process picks up where it left off.

Usage
-----
    from ai_trading_agents.state_store import StateStore
    store = StateStore()                       # logs/brain_state.json
    state = store.load()
    state["restart_count"] = state.get("restart_count", 0) + 1
    store.save(state)
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

logger = logging.getLogger("state_store")

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_DEFAULT_PATH = _ROOT / "logs" / "brain_state.json"


_DEFAULTS: Dict[str, Any] = {
    "schema_version":          2,
    "restart_count":           0,
    "last_started_at":         0,
    "last_saved_at":           0,
    "recent_results":          [],   # most recent last; ring-buffer-trimmed
    "cooldown_until_ts":       0,
    "last_signal_per_symbol":  {},   # {symbol: {direction, ts, confidence}}
    "start_of_day_equity":     0.0,
    "start_of_day_date":       "",   # "YYYY-MM-DD" UTC
    "daily_pnl_close":         0.0,  # realized P&L for the running UTC day
    "session_high_equity":     0.0,
    "session_low_equity":      0.0,
    # Phase G additions ────────────────────────────────────────────────
    "trading_paused":          False, # set True by /halt, False by /resume
    "trading_paused_at":       0,
    "trading_resumed_at":      0,
    "last_processed_deal_ts":  0,    # bookmark for trade_tracker.poll()
    "drawdown_lockout_until":  0,    # set by daily_loss_limit gate
    "daily_drawdown_peak_eq":  0.0,  # peak equity within current UTC day
}

# How many recent trade results we keep (loss_streak only needs the tail
# few, but keeping 50 lets us compute richer rolling stats for telegram).
_MAX_RESULTS = 50


class StateStore:
    """
    Atomic JSON state file. Single writer process expected (the brain),
    but reads from other tools (dashboard, CLI) are safe — atomic replace
    means readers always see a complete file.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else _DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return dict(_DEFAULTS)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("state file is not a dict")
            # Merge with defaults so older state files just gain new keys.
            out = dict(_DEFAULTS)
            out.update(data)
            # Trim recent_results in case it grew somehow.
            out["recent_results"] = list(out.get("recent_results", []))[-_MAX_RESULTS:]
            return out
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.warning("Could not load brain state (%s); starting fresh.", e)
            return dict(_DEFAULTS)

    def save(self, state: Dict[str, Any]) -> bool:
        """Atomic write with retry. Returns True if persisted.

        [R11 2026-04-23] Windows os.replace() intermittently hits
        WinError 5 (Access denied) when dashboard/OS has the target file
        open for read at the exact moment we're replacing. Retry up to
        5 times with exponential backoff before giving up — total max
        wait ~1.5s, so we don't stall the tick loop.
        """
        with self._lock:
            try:
                state["last_saved_at"] = int(time.time())
                # Trim before persist.
                if "recent_results" in state and isinstance(state["recent_results"], list):
                    state["recent_results"] = state["recent_results"][-_MAX_RESULTS:]
                tmp_fd, tmp_name = tempfile.mkstemp(
                    prefix=".brain_state_", suffix=".tmp",
                    dir=str(self.path.parent))
                try:
                    with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                        json.dump(state, f, separators=(",", ":"))
                        f.flush()
                        try:
                            os.fsync(f.fileno())
                        except OSError:
                            pass
                    # Retry os.replace() — Windows fileshare race.
                    last_err: Optional[BaseException] = None
                    for attempt in range(5):
                        try:
                            os.replace(tmp_name, self.path)
                            return True
                        except PermissionError as e:
                            last_err = e
                            # 50ms, 100ms, 200ms, 400ms, 800ms
                            time.sleep(0.05 * (2 ** attempt))
                            continue
                    if last_err is not None:
                        raise last_err
                    return False
                except Exception:
                    try:
                        if os.path.exists(tmp_name):
                            os.unlink(tmp_name)
                    except OSError:
                        pass
                    raise
            except Exception as e:
                logger.warning("Could not persist brain state: %s", e)
                return False

    # ─── helpers used by brain ────────────────────────────────────────────
    def append_result(self, state: Dict[str, Any], r_multiple: float) -> None:
        results = list(state.get("recent_results", []))
        results.append(float(r_multiple))
        state["recent_results"] = results[-_MAX_RESULTS:]

    def update_signal(self, state: Dict[str, Any], symbol: str,
                      direction: str, confidence: float) -> None:
        sym_map = dict(state.get("last_signal_per_symbol", {}))
        sym_map[symbol] = {
            "direction":  direction,
            "confidence": round(float(confidence), 4),
            "ts":         int(time.time()),
        }
        state["last_signal_per_symbol"] = sym_map


__all__ = ["StateStore"]
