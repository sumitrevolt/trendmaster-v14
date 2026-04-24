"""Nightly "is the brain actually trading?" watchdog.

Reads `logs/brain_state.json` (no MT5 touch, no brain touch) and posts
a Telegram alert if the brain has been silent for too long without a
legitimate reason.

This was written after the 2026-04-24 zero-trades incident where the
brain ran healthy for 47 days without placing a single trade because
of a feature-alignment bug. A watchdog that fires once a day and
compares `max(recent_results.ts)` to wall-clock would have caught that
in 24 hours. See `docs/POSTMORTEMS/2026-04-24_zero_trades.md`.

Verdicts (exit codes in parens):
    OK           (0)  - recent trade activity within window
    HALTED       (0)  - brain is explicitly halted; alert but don't panic
    STALE        (1)  - no deal in STALE_HOURS hours AND not halted
    MODEL_STUCK  (1)  - confidences near-uniform across markets
    NO_STATE     (2)  - state file missing (brain may have crashed)

Usage
-----
    python tools/zero_trades_watchdog.py

Scheduled via `install_zero_trades_watchdog.bat` (schtasks daily 09:00 local).
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

STATE_PATH = REPO_ROOT / "logs" / "brain_state.json"

# Tunables
STALE_HOURS = 24
UNIFORM_STD = 0.05  # conf std below this across diverse markets => likely broken
UNIFORM_MEAN_1_3 = (0.28, 0.40)  # if conf mean lives in this band, model may be uniform-1/3
STALE_SIGNAL_HOURS = 6  # drop signal records older than this for the stats


def _fmt_ts(val: Any) -> str:
    try:
        t = int(float(val))
        if t == 0:
            return "never"
        return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
    except Exception:
        return str(val)


def last_deal_ts(state: Dict[str, Any]) -> Optional[int]:
    """Return unix ts of the most recent closed deal, or None."""
    rr = state.get("recent_results") or []
    if not isinstance(rr, list) or not rr:
        return None
    ts_list: List[int] = []
    for r in rr:
        try:
            ts_list.append(int(float(r.get("ts", 0))))
        except Exception:
            continue
    return max(ts_list) if ts_list else None


def confidence_stats(state: Dict[str, Any], now_ts: float) -> Tuple[Optional[float], Optional[float], int]:
    """Mean, std, and count of FRESH (< STALE_SIGNAL_HOURS old) confidences."""
    signals = state.get("last_signal_per_symbol") or {}
    cutoff = now_ts - STALE_SIGNAL_HOURS * 3600
    confs: List[float] = []
    for _sym, s in signals.items():
        try:
            ts = float(s.get("ts") or 0)
            if ts < cutoff:
                continue
            confs.append(float(s.get("confidence", 0.0)))
        except (TypeError, ValueError):
            continue
    if not confs:
        return None, None, 0
    if len(confs) == 1:
        return confs[0], 0.0, 1
    return statistics.mean(confs), statistics.pstdev(confs), len(confs)


def send_telegram(title: str, body: str) -> bool:
    try:
        from ai_trading_agents.telegram_notifier import get_notifier  # type: ignore
    except Exception as e:
        print(f"[telegram] import failed: {e}")
        return False
    try:
        get_notifier().notify_alert(title, body, emoji="🔕")
        return True
    except Exception as e:
        print(f"[telegram] notify_alert failed: {e}")
        return False


def main() -> int:
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()

    if not STATE_PATH.exists():
        send_telegram(
            "Zero-trades watchdog: NO_STATE",
            f"{STATE_PATH} is missing. Brain may have crashed or not run yet.",
        )
        print("[NO_STATE] state file missing")
        return 2

    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        send_telegram("Zero-trades watchdog: NO_STATE", f"Cannot parse state: {e}")
        print(f"[NO_STATE] {e}")
        return 2

    # HALTED path: alert as reminder, but not as emergency.
    if state.get("halted") or state.get("trading_paused"):
        reason = "halted" if state.get("halted") else "trading_paused"
        send_telegram(
            "Zero-trades watchdog: HALTED",
            f"Brain is {reason}. "
            f"Set at {_fmt_ts(state.get('trading_paused_at'))}. "
            f"If intentional, ignore. If not, `/resume` in Telegram.",
        )
        print(f"[HALTED] reason={reason}")
        return 0

    # STALE path
    last_ts = last_deal_ts(state)
    hours_since = None
    if last_ts is not None:
        hours_since = (now_ts - last_ts) / 3600

    # MODEL_STUCK path (check even if stale is flagged - helps diagnose)
    mean, std, n_fresh = confidence_stats(state, now_ts)
    model_stuck = (
        mean is not None
        and std is not None
        and n_fresh >= 5
        and std < UNIFORM_STD
        and UNIFORM_MEAN_1_3[0] <= mean <= UNIFORM_MEAN_1_3[1]
    )

    if model_stuck:
        send_telegram(
            "Zero-trades watchdog: MODEL_STUCK",
            f"Confidence distribution across {n_fresh} markets looks degenerate: "
            f"mean={mean:.3f} std={std:.3f}. "
            f"This matches the 2026-04-24 feature-alignment signature. "
            f"Run `python tools/diagnose_zero_trades.py` for details.",
        )
        print(f"[MODEL_STUCK] mean={mean:.3f} std={std:.3f} n={n_fresh}")
        return 1

    if hours_since is None or hours_since > STALE_HOURS:
        body = (
            f"No closed deal in {hours_since:.1f}h (threshold {STALE_HOURS}h). "
            if hours_since is not None
            else "No recorded deals at all. "
        )
        if mean is not None:
            body += f"Current conf mean={mean:.3f} std={std:.3f} over {n_fresh} fresh signals. "
        body += "If the market is genuinely quiet, ignore. Otherwise run `tools/diagnose_zero_trades.py`."
        send_telegram("Zero-trades watchdog: STALE", body)
        print(f"[STALE] hours_since={hours_since}  mean={mean}  std={std}  n_fresh={n_fresh}")
        return 1

    # OK path
    print(f"[OK] last deal {hours_since:.1f}h ago  mean={mean}  std={std}  n_fresh={n_fresh}")
    if os.getenv("ZERO_TRADES_WATCHDOG_QUIET_OK", "").lower() not in ("1", "true", "yes"):
        send_telegram(
            "Zero-trades watchdog: OK",
            f"Last deal {hours_since:.1f}h ago. Conf mean={mean:.3f} std={std:.3f} "
            f"over {n_fresh} markets. Scheduler is alive.",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
