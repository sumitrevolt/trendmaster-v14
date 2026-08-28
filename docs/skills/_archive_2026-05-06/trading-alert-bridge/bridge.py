"""
Alert bridge for TrendMaster v14.

Watches logs/*.alert + logs/drift_alerts.jsonl, forwards new entries to
Telegram. Idempotent via state file.

Pure-Python; stdlib + ai_trading_agents.telegram_notifier.
"""

from __future__ import annotations
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
LOGS = REPO / "logs"
STATE = LOGS / "alert_bridge_state.json"
FAILURES = LOGS / "alert_bridge_failures.log"

ALERT_FILES = ["pytest_health.alert", "zero_trades.alert", "brain.crash"]
DRIFT_LOG = LOGS / "drift_alerts.jsonl"
RATE_LIMIT_PER_MIN = 10


def load_state() -> dict:
    if not STATE.exists():
        return {"alert_files_seen_mtime": {}, "drift_jsonl_offset": 0, "telegram_send_log": []}
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"alert_files_seen_mtime": {}, "drift_jsonl_offset": 0, "telegram_send_log": []}


def save_state(s: dict) -> None:
    STATE.write_text(json.dumps(s, indent=2))


def send_telegram(msg: str) -> bool:
    try:
        sys.path.insert(0, str(REPO))
        from ai_trading_agents.telegram_notifier import get_notifier
        n = get_notifier()
        return bool(n.send(msg))
    except Exception as e:
        with FAILURES.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}\t{type(e).__name__}\t{e}\t{msg}\n")
        return False


def collect_alert_file_messages(state: dict) -> list[str]:
    messages = []
    for name in ALERT_FILES:
        p = LOGS / name
        if not p.exists():
            continue
        mtime = p.stat().st_mtime
        last_seen = state["alert_files_seen_mtime"].get(name, 0)
        if mtime > last_seen:
            try:
                content = p.read_text(encoding="utf-8", errors="replace").strip()[:500]
            except Exception as e:
                content = f"<read failed: {e}>"
            messages.append(f"[TrendMaster ALERT] {name}\n{content}")
            state["alert_files_seen_mtime"][name] = mtime
    return messages


def collect_drift_messages(state: dict) -> list[str]:
    if not DRIFT_LOG.exists():
        return []
    messages = []
    offset = state.get("drift_jsonl_offset", 0)
    try:
        with DRIFT_LOG.open(encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    team = ev.get("team", "?")
                    feature = ev.get("feature", "?")
                    detector = ev.get("detector", "?")
                    fired = ev.get("fired_at", "?")
                    messages.append(f"[TrendMaster ALERT] Drift {detector} on {team}/{feature} fired {fired}")
                except json.JSONDecodeError:
                    pass
            state["drift_jsonl_offset"] = f.tell()
    except Exception as e:
        with FAILURES.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}\tdrift read error\t{e}\n")
    return messages


def can_send_now(state: dict) -> bool:
    """Rate limit: max RATE_LIMIT_PER_MIN messages per rolling minute."""
    now = time.time()
    log = state.get("telegram_send_log", [])
    log = [t for t in log if now - t < 60]
    state["telegram_send_log"] = log
    return len(log) < RATE_LIMIT_PER_MIN


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--reset-state", action="store_true")
    args = ap.parse_args()

    state = load_state()

    if args.reset_state:
        # Mark all existing alerts as seen
        for name in ALERT_FILES:
            p = LOGS / name
            if p.exists():
                state["alert_files_seen_mtime"][name] = p.stat().st_mtime
        if DRIFT_LOG.exists():
            state["drift_jsonl_offset"] = DRIFT_LOG.stat().st_size
        save_state(state)
        print("State reset. All current alerts marked as seen.")
        return

    file_msgs = collect_alert_file_messages(state)
    drift_msgs = collect_drift_messages(state)
    all_msgs = file_msgs + drift_msgs

    if not all_msgs:
        if not args.quiet:
            print("Alert Bridge - " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
            print("No pending alerts.")
        save_state(state)
        return

    if not args.quiet:
        print("Alert Bridge - " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        print(f"{len(all_msgs)} alerts to dispatch")

    sent = 0
    for msg in all_msgs:
        if not can_send_now(state):
            print(f"Rate-limited; deferred: {msg[:80]}")
            continue
        if send_telegram(msg):
            state.setdefault("telegram_send_log", []).append(time.time())
            sent += 1
            if not args.quiet:
                print(f"  sent: {msg[:80]}")
        else:
            if not args.quiet:
                print(f"  send FAILED, queued in failures.log: {msg[:80]}")

    save_state(state)
    if not args.quiet:
        print(f"\n{sent}/{len(all_msgs)} dispatched to Telegram")


if __name__ == "__main__":
    main()
