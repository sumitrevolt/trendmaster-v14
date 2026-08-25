"""telegram_direction_helper.py — inline-keyboard direction prompt for Rocket Prime signals.

When a TV webhook fires a no-direction signal, this module pushes a
Telegram message with [BUY] [SELL] [SKIP] inline buttons. The operator
taps a button; `telegram_direction_listener.py` resolves the tap and
writes the trade signal via `tv_executor.write_tv_signal()`.

See docs/skills/trading-telegram-direction-helper/SKILL.md for full docs.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("tg_direction_helper")

_ROOT = Path(__file__).parent.parent
PENDING_FILE = _ROOT / "logs" / "pending_signals.jsonl"

# Timeout for pending signals (default 20 min)
_TIMEOUT_S = int(os.getenv("RP_DIRECTION_TIMEOUT_S", "1200"))

# Telegram API
_TG_API = "https://api.telegram.org/bot{token}/{method}"


def _get_creds() -> tuple:
    """Return (token, chat_id) from env."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return token, chat_id


def _tg_send(method: str, payload: dict, token: Optional[str] = None) -> dict:
    """Best-effort Telegram API call. Returns response dict or empty."""
    try:
        import requests
    except ImportError:
        return {}
    tok = token or _get_creds()[0]
    if not tok:
        return {}
    try:
        r = requests.post(
            _TG_API.format(token=tok, method=method),
            json=payload,
            timeout=10,
        )
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        logger.warning("Telegram API %s failed: %s", method, e)
        return {}


def load_pending() -> List[Dict]:
    """Load all pending signals from the JSONL file."""
    if not PENDING_FILE.exists():
        return []
    try:
        lines = PENDING_FILE.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in lines if line.strip()]
    except Exception as e:
        logger.warning("Failed to load pending signals: %s", e)
        return []


def _save_pending(signals: List[Dict]) -> None:
    """Save pending signals list to JSONL."""
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(s, separators=(",", ":")) for s in signals]
    PENDING_FILE.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")


def mark_resolved(sig_id: str, resolution: str = "placed", direction: str = "") -> None:
    """Mark a pending signal as resolved (remove from pending)."""
    pending = load_pending()
    pending = [p for p in pending if p.get("sig_id") != sig_id]
    _save_pending(pending)
    logger.info("Signal %s resolved: %s %s", sig_id, resolution, direction)


def edit_message(message_id: int, text: str) -> bool:
    """Edit an existing Telegram message."""
    token, chat_id = _get_creds()
    if not token or not chat_id or not message_id:
        return False
    resp = _tg_send("editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }, token)
    return resp.get("ok", False)


def answer_callback(callback_query_id: str, text: str) -> bool:
    """Answer a callback query (acknowledges the button tap)."""
    token, _ = _get_creds()
    if not token or not callback_query_id:
        return False
    resp = _tg_send("answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": False,
    }, token)
    return resp.get("ok", False)


def send_direction_prompt(symbol: str, timeframe: Optional[str] = None) -> Optional[str]:
    """Send an inline-keyboard BUY/SELL/SKIP prompt to the operator.

    Returns the sig_id if sent, None on failure.
    """
    token, chat_id = _get_creds()
    if not token or not chat_id:
        logger.warning("No Telegram creds — cannot send direction prompt")
        return None

    sig_id = f"{symbol}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    tf_display = timeframe or "?"

    # Build inline keyboard
    keyboard = {
        "inline_keyboard": [[
            {"text": "📈 BUY", "callback_data": f"d:b:{sig_id}"},
            {"text": "📉 SELL", "callback_data": f"d:s:{sig_id}"},
            {"text": "⏭ SKIP", "callback_data": f"d:x:{sig_id}"},
        ]]
    }

    text = (
        f"<b>{symbol} {tf_display}</b> — direction?\n"
        f"<i>Tap within {_TIMEOUT_S // 60} min or signal expires.</i>"
    )

    resp = _tg_send("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(keyboard),
    }, token)

    if not resp.get("ok"):
        logger.warning("Failed to send direction prompt: %s", resp)
        return None

    # Record pending signal
    msg_id = resp.get("result", {}).get("message_id")
    pending_entry = {
        "sig_id": sig_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "source": "rocket_prime",
        "created_at": int(time.time()),
        "timeout_at": int(time.time()) + _TIMEOUT_S,
        "message_id": msg_id,
        "resolution": "pending",
    }

    # Append to JSONL
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(pending_entry, separators=(",", ":")) + "\n")

    logger.info("Direction prompt sent: %s %s (sig_id=%s)", symbol, timeframe, sig_id)
    return sig_id


def cleanup_expired() -> int:
    """Remove expired pending signals. Returns count removed."""
    pending = load_pending()
    now = int(time.time())
    before = len(pending)
    active = [p for p in pending if p.get("timeout_at", 0) > now]
    removed = before - len(active)
    if removed > 0:
        _save_pending(active)
        logger.info("Cleaned up %d expired pending signals", removed)
    return removed


__all__ = [
    "PENDING_FILE",
    "load_pending",
    "mark_resolved",
    "edit_message",
    "answer_callback",
    "send_direction_prompt",
    "cleanup_expired",
]
