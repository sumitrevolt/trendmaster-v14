"""
panic.py — flatten-all helper for the /halt close kill-switch.

Why this exists
---------------
The current `/halt` command blocks new entries but leaves open
positions running under the EA's TP/SL/BE management. That's the
documented behavior — but during a catastrophic event (news spike,
exchange hiccup, bad data feed, operator panic) the right action is
sometimes "flatten everything right now".

This module adds `flatten_all_positions(...)` — iterate MT5's position
list, issue `TRADE_ACTION_DEAL` close orders one at a time, aggregate
fills, return a structured summary. Wrapped in belts-and-braces:

  * Never raises. All exceptions are caught and reported in the
    summary. Caller is expected to log but not to re-throw.
  * Dry-run mode (`dry_run=True`) — returns the positions it *would*
    close without issuing any orders. For testing and confidence.
  * Magic-number filter — only close positions tagged by our EA
    (default `InpMagic=20260420`), leaving any manual trades alone.
  * Per-close timeout — bounded retry (5× 0.5s backoff) so a single
    frozen symbol can't wedge the whole flatten.

Integration
-----------
Not wired into the Telegram listener yet. To enable:

    # In trend_master_brain.py::_register_commands (or equivalent):
    cmds.register_command(
        "halt",
        handler=lambda args: _handle_halt_ex(args),
    )

    def _handle_halt_ex(self, args: str = "") -> str:
        parts = (args or "").strip().split()
        if parts and parts[0].lower() == "close":
            # Safety: require explicit confirmation.
            if len(parts) < 2 or parts[1].upper() != "YES":
                return ("Type <code>/halt close YES</code> to also close "
                        "open positions. Without <code>YES</code>, this "
                        "would only block new entries (plain /halt).")
            from ai_trading_agents.panic import flatten_all_positions
            summary = flatten_all_positions(
                comment="tm_halt_close",
                magic_filter=20260420,
            )
            return self._handle_halt() + "\n\n" + summary["human"]
        return self._handle_halt()

The above snippet lives in the report, NOT pre-wired in the brain —
operators must opt in explicitly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("panic")

try:
    import MetaTrader5 as mt5  # type: ignore

    _HAS_MT5 = True
except Exception:
    _HAS_MT5 = False


@dataclass
class FlattenResult:
    attempted: int = 0
    closed: int = 0
    failed: int = 0
    dry_run: bool = False
    per_symbol: Dict[str, Dict] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.closed == self.attempted

    def as_dict(self) -> dict:
        return {
            "attempted": self.attempted,
            "closed": self.closed,
            "failed": self.failed,
            "dry_run": self.dry_run,
            "per_symbol": self.per_symbol,
            "notes": self.notes,
            "success": self.success,
        }

    @property
    def human(self) -> str:
        """Human-readable summary suitable for a Telegram reply."""
        if self.dry_run:
            lines = [f"(dry-run) would close {self.attempted} position(s):"]
        else:
            lines = [f"Flatten summary: closed {self.closed}/{self.attempted}, {self.failed} failed."]
        for sym, info in self.per_symbol.items():
            lines.append(
                f"  • {sym}: {info.get('action', '?')} "
                f"lots={info.get('lots', 0.0):.2f} "
                f"{'OK' if info.get('ok') else 'FAIL'} "
                f"{info.get('note', '')}"
            )
        if self.notes:
            lines.append("Notes: " + "; ".join(self.notes))
        return "\n".join(lines)


def flatten_all_positions(
    comment: str = "tm_flatten",
    magic_filter: Optional[int] = 20260420,
    dry_run: bool = False,
    deviation: int = 50,
    max_retries: int = 5,
    retry_backoff_s: float = 0.5,
) -> FlattenResult:
    """Close every open MT5 position matching `magic_filter` (None =
    close all). Returns a structured summary — never raises.

    The caller (brain `_handle_halt_ex`) is expected to combine this
    with a persistent `/halt` flag so new entries stay blocked even
    after flatten completes.
    """
    result = FlattenResult(dry_run=dry_run)

    if not _HAS_MT5:
        result.notes.append("MT5 Python bridge not importable — nothing to do")
        return result

    try:
        positions = mt5.positions_get()
    except Exception as e:
        result.notes.append(f"mt5.positions_get() failed: {e!r}")
        return result
    if not positions:
        result.notes.append("no open positions")
        return result

    # Filter by magic.
    candidates = [p for p in positions if magic_filter is None or int(getattr(p, "magic", 0) or 0) == int(magic_filter)]
    result.attempted = len(candidates)

    for p in candidates:
        sym = str(getattr(p, "symbol", "") or "")
        vol = float(getattr(p, "volume", 0.0) or 0.0)
        ptype = int(getattr(p, "type", 0))  # 0 BUY, 1 SELL
        ticket = int(getattr(p, "ticket", 0))
        side = "sell" if ptype == 0 else "buy"

        # Record intent regardless of dry-run / error.
        info: Dict = {
            "ticket": ticket,
            "action": f"close-{side}",
            "lots": vol,
            "ok": None,
            "note": "",
        }

        if dry_run:
            info["ok"] = True
            info["note"] = "dry-run"
            result.per_symbol[sym] = info
            result.closed += 1
            continue

        # Build the close-order request. We re-read tick each try so a
        # stale quote doesn't get us rejected as REQUOTE.
        ok = False
        last_err = ""
        for attempt in range(max_retries):
            try:
                tick = mt5.symbol_info_tick(sym)
                if tick is None:
                    last_err = "no tick"
                    time.sleep(retry_backoff_s * (attempt + 1))
                    continue
                price = float(tick.bid if ptype == 0 else tick.ask)
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": ticket,
                    "symbol": sym,
                    "volume": vol,
                    "type": mt5.ORDER_TYPE_SELL if ptype == 0 else mt5.ORDER_TYPE_BUY,
                    "price": price,
                    "deviation": int(deviation),
                    "magic": int(magic_filter) if magic_filter else 0,
                    "comment": str(comment)[:31],
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                res = mt5.order_send(request)
                if res is None:
                    last_err = f"order_send returned None (err={mt5.last_error()})"
                    time.sleep(retry_backoff_s * (attempt + 1))
                    continue
                retcode = int(getattr(res, "retcode", 0))
                if retcode == mt5.TRADE_RETCODE_DONE or retcode == 10009:
                    ok = True
                    info["note"] = f"retcode={retcode}"
                    break
                last_err = f"retcode={retcode} comment={getattr(res, 'comment', '')}"
                time.sleep(retry_backoff_s * (attempt + 1))
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                time.sleep(retry_backoff_s * (attempt + 1))

        info["ok"] = bool(ok)
        if not ok:
            info["note"] = last_err or info["note"]
            result.failed += 1
        else:
            result.closed += 1
        result.per_symbol[sym] = info

    return result


__all__ = ["FlattenResult", "flatten_all_positions"]
