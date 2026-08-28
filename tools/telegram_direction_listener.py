"""telegram_direction_listener.py — long-running process that polls
Telegram for callback_query taps on inline-keyboard direction prompts,
matches against pending_signals.jsonl, and writes the resolved signal
to MT5 file dir via tv_executor.

Run via:
  pythonw tools/telegram_direction_listener.py

Watchdog adds this to the schtask list (same pattern as
python_signal_executor + trailing_stop_manager).
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    # 2026-05-13 fix: use override=True so config/.env always wins over
    # OS env. Earlier override=False caused listener to use a stale
    # TELEGRAM_BOT_TOKEN cached in OS env from a prior process, even
    # though config/.env had the correct token. Result: 1000+ 404s.
    for _cand in (ROOT / "config" / ".env", ROOT / ".env",
                  ROOT / "ai_trading_agents" / ".env"):
        if _cand.exists():
            load_dotenv(_cand, override=True)
except ImportError:
    pass

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "telegram_direction_listener.log", encoding="utf-8")],
)
log = logging.getLogger("tg_listener")

# Lazy import — avoid blowing up at module load
from ai_trading_agents.telegram_direction_helper import (
    load_pending, mark_resolved, edit_message, answer_callback,
    PENDING_FILE,
)
from ai_trading_agents.tv_executor import write_tv_signal

try:
    import requests  # type: ignore
except ImportError:
    log.error("requests library missing — install with: pip install requests")
    sys.exit(2)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not TOKEN:
    log.error("TELEGRAM_BOT_TOKEN not set in config/.env")
    sys.exit(3)

LAST_UPDATE_FILE = LOG_DIR / "telegram_direction_listener.last_update_id"


def _read_last_update_id() -> int:
    try:
        return int(LAST_UPDATE_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _write_last_update_id(uid: int) -> None:
    try:
        LAST_UPDATE_FILE.write_text(str(uid), encoding="utf-8")
    except Exception as e:
        log.warning("write last_update_id failed: %s", e)


def poll_updates(offset: int, timeout: int = 25) -> list[dict]:
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {
        "offset": offset + 1,
        "timeout": timeout,
        "allowed_updates": json.dumps(["callback_query"]),
    }
    try:
        r = requests.get(url, params=params, timeout=timeout + 5)
        if r.status_code != 200:
            log.warning("getUpdates HTTP %s body=%s", r.status_code, r.text[:200])
            return []
        body = r.json()
        if not body.get("ok"):
            log.warning("getUpdates not ok: %s", body)
            return []
        return body.get("result", [])
    except Exception as e:
        log.warning("getUpdates error: %s", e)
        return []


def handle_callback(cb: dict) -> None:
    """Process one callback_query event."""
    cbq_id = cb.get("id", "")
    data = cb.get("data", "")
    msg = cb.get("message", {}) or {}
    msg_id = msg.get("message_id")
    chat = msg.get("chat", {}) or {}
    from_user = (cb.get("from") or {}).get("username", "?")

    log.info("callback: data=%s from=%s msg_id=%s", data, from_user, msg_id)

    # data format: "d:b:<sig_id>" / "d:s:<sig_id>" / "d:x:<sig_id>"
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "d":
        log.warning("ignore unrecognized callback_data: %r", data)
        answer_callback(cbq_id, "Unknown action")
        return

    code = parts[1]
    sig_id = parts[2]

    # Lookup pending signal
    pending = load_pending()
    found = next((p for p in pending if p.get("sig_id") == sig_id), None)
    if not found:
        log.warning("no pending signal for sig_id=%s (expired or already handled)", sig_id)
        answer_callback(cbq_id, "Already handled or expired")
        edit_message(msg_id, "⚠️ Signal already handled or expired.")
        return

    symbol = found["symbol"]
    timeframe = found.get("timeframe")
    source = found.get("source", "rocket_prime")

    if code == "x":
        # SKIP
        mark_resolved(sig_id, resolution="skip")
        answer_callback(cbq_id, "Skipped ⏭")
        edit_message(msg_id, f"⏭ <b>{symbol}</b> skipped (no trade placed).")
        log.info("SKIP for %s", symbol)
        return

    if code not in ("b", "s"):
        log.warning("unknown direction code: %r", code)
        answer_callback(cbq_id, "Unknown direction")
        return

    direction = "buy" if code == "b" else "sell"

    # Write to MT5 signal file via tv_executor
    try:
        res = write_tv_signal(
            symbol=symbol,
            direction=direction,
            confidence=0.95,
            source="telegram_manual_direction",
            tv_strategy="rocket_prime_telegram",
            tv_price=None,
            tv_alert_ts=int(time.time()),
            tv_timeframe=timeframe,
        )
    except Exception as e:
        log.exception("write_tv_signal raised")
        answer_callback(cbq_id, "Internal error")
        edit_message(msg_id, f"❌ <b>{symbol}</b>: bot error — see listener log.\n<code>{e}</code>")
        return

    if not res.get("ok"):
        err = res.get("error", "rejected")
        log.warning("write_tv_signal rejected: %s", err)
        mark_resolved(sig_id, resolution="rejected", direction=direction)
        answer_callback(cbq_id, f"Rejected: {err}"[:200])
        edit_message(msg_id, f"❌ <b>{symbol}</b> {direction.upper()} rejected:\n<code>{err}</code>")
        return

    mark_resolved(sig_id, resolution="placed", direction=direction)
    emoji = "📈" if direction == "buy" else "📉"
    payload = res.get("payload", {})
    tf_display = payload.get("tv_timeframe") or timeframe or "?"
    if isinstance(tf_display, str) and tf_display.isdigit():
        tf_display = f"M{tf_display}"
    answer_callback(cbq_id, f"{direction.upper()} placed")
    edit_message(
        msg_id,
        f"{emoji} <b>{symbol}</b> {tf_display} {direction.upper()}\n"
        f"<i>Signal written to MT5 file at {time.strftime('%H:%M:%S')}</i>"
    )
    log.info("PLACED %s %s tf=%s path=%s", symbol, direction, tf_display, res.get("path"))


def main() -> int:
    log.info("telegram_direction_listener starting (poll interval=long, timeout=25s)")
    last_uid = _read_last_update_id()
    log.info("resume from last_update_id=%s", last_uid)

    # Heartbeat counter — watchdog can detect staleness
    iter_count = 0
    last_heartbeat = 0
    HEARTBEAT_INTERVAL = 60

    # Graceful shutdown
    def _shutdown(sig, frame):
        log.info("shutdown signal received")
        sys.exit(0)
    try:
        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)
    except Exception:
        pass

    while True:
        updates = poll_updates(last_uid, timeout=25)
        for u in updates:
            uid = u.get("update_id", 0)
            if uid > last_uid:
                last_uid = uid
                _write_last_update_id(last_uid)
            cb = u.get("callback_query")
            if cb:
                try:
                    handle_callback(cb)
                except Exception as e:
                    log.exception("handle_callback raised: %s", e)

        iter_count += 1
        now = int(time.time())
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            pend = load_pending()
            log.info("heartbeat: iter=%d last_uid=%d pending=%d",
                     iter_count, last_uid, len(pend))
            last_heartbeat = now

        # Small sleep to avoid hot-loop when getUpdates returns immediately
        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
