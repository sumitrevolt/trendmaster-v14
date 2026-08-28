"""
telegram_notifier.py — sync Telegram alerts for TrendMaster v14
================================================================

Why a sync notifier
-------------------
`trend_master_brain.py` runs a tight synchronous loop (`while True: tick_once()`).
The archived notifier was async (aiohttp) which doesn't play with that loop
without spinning up an event loop on every tick. This module uses plain
`requests` so the brain can call `notify_signal(...)` inline without any
async glue.

What it does
------------
* Reads TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / TELEGRAM_ENABLED from env
  (loads `.env` from project root, ./config/ or ./ai_trading_agents/).
* Throttles: only emits when the *direction changes* (NONE→BUY, BUY→SELL),
  with a hard floor of `min_interval_s` between any two messages per symbol.
  This stops the 250ms tick loop from blasting Sumit's phone.
* Never raises — wrapped in broad try/except so a flaky network or revoked
  bot token can't kill the trading brain.
* Singleton: `get_notifier()` returns one instance the brain reuses.

CLI smoke test
--------------
    python -m ai_trading_agents.telegram_notifier test

Sends one canned message to the configured chat. Confirms creds + network.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, Iterable, Optional

logger = logging.getLogger("telegram_notifier")


# ─── .env loading ──────────────────────────────────────────────────────────
# We search project root → config/.env → ai_trading_agents/.env. First hit
# wins, but we don't override anything already set in the real env.
def _load_env() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    here = Path(__file__).parent
    root = here.parent
    for cand in (root / ".env", root / "config" / ".env", here / ".env"):
        if cand.exists():
            load_dotenv(cand, override=False)


_load_env()

# ─── HTTP dep ─────────────────────────────────────────────────────────────
try:
    import requests  # type: ignore

    _HAS_REQ = True
except ImportError:
    _HAS_REQ = False
    logger.warning("`requests` not installed — Telegram notifications disabled. Install with: pip install requests")


_TG_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    """
    Send messages to a Telegram chat. Safe to call from the brain's hot loop
    — all failures are swallowed and logged.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: Optional[bool] = None,
        min_interval_s: float = 8.0,
        timeout_s: float = 5.0,
    ):
        self.token = (token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        raw_chat = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
        # Comma/semicolon-separated recipients are supported: "id1,id2,id3".
        # `chat_id` keeps the first value for backwards compatibility.
        self.chat_ids = [c.strip() for c in re.split(r"[,;]", raw_chat) if c.strip()]
        self.chat_id = self.chat_ids[0] if self.chat_ids else ""
        if enabled is None:
            enabled = os.getenv("TELEGRAM_ENABLED", "false").strip().lower() == "true"
        self.enabled = bool(enabled and self.token and self.chat_id and _HAS_REQ)
        self.timeout_s = float(timeout_s)
        self.min_interval_s = float(min_interval_s)

        # Per-symbol throttle state.
        self._lock = Lock()
        self._last_dir: Dict[str, str] = {}  # symbol -> last direction sent
        self._last_ts: Dict[str, float] = {}  # symbol -> last send wall-clock

        if self.enabled:
            logger.info(
                "Telegram notifier enabled (recipients=%d: %s, min_interval=%.1fs)",
                len(self.chat_ids),
                ",".join(self.chat_ids),
                self.min_interval_s,
            )
        else:
            why = []
            if not _HAS_REQ:
                why.append("no requests")
            if not self.token:
                why.append("no token")
            if not self.chat_id:
                why.append("no chat_id")
            if enabled is False:
                why.append("env disabled")
            logger.info("Telegram notifier disabled (%s).", ", ".join(why) or "unknown")

    # ─── low-level send ───────────────────────────────────────────────────
    def send(self, text: str, parse_mode: str = "HTML") -> bool:
        """Best-effort fan-out to every configured chat. Returns True if at
        least one recipient accepted the message."""
        if not self.enabled:
            return False
        url = _TG_API.format(token=self.token, method="sendMessage")
        ok_any = False
        for cid in self.chat_ids:
            payload = {
                "chat_id": cid,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            try:
                r = requests.post(url, json=payload, timeout=self.timeout_s)
                if r.status_code == 200 and r.json().get("ok"):
                    ok_any = True
                else:
                    logger.warning("Telegram send failed (chat %s): %s %s", cid, r.status_code, r.text[:200])
            except Exception as e:
                logger.warning("Telegram send error (chat %s): %s", cid, e)
        return ok_any

    # ─── high-level: signal alert with throttling ─────────────────────────
    def notify_signal(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        *,
        model: str = "rule",
        agent_dir: str = "NONE",
        reasons: Optional[Iterable[str]] = None,
        force: bool = False,
    ) -> bool:
        """
        Fire a Telegram alert for a signal. Throttled:
          * Skipped if direction == last sent direction for this symbol
            (so a sustained BUY across 100 ticks → exactly 1 message).
          * Skipped if last message for this symbol was within
            `min_interval_s` (catches direction-flip spam).
          * `force=True` bypasses throttling (used by smoke test).
        """
        if not self.enabled:
            return False
        direction = (direction or "NONE").upper()
        if direction not in ("BUY", "SELL", "NONE"):
            direction = "NONE"

        # Don't spam "NONE" updates — we only care about actual trade signals.
        if direction == "NONE" and not force:
            with self._lock:
                self._last_dir[symbol] = direction
            return False

        now = time.monotonic()
        with self._lock:
            last_dir = self._last_dir.get(symbol)
            last_ts = self._last_ts.get(symbol, 0.0)
            if not force:
                if last_dir == direction:
                    return False
                if (now - last_ts) < self.min_interval_s:
                    return False
            self._last_dir[symbol] = direction
            self._last_ts[symbol] = now

        emoji = "📈" if direction == "BUY" else "📉" if direction == "SELL" else "⏸️"
        ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            f"<b>{emoji} {symbol} {direction}</b>",
            f"Confidence: <b>{confidence * 100:.1f}%</b>",
            f"Model: <code>{model}</code>  |  Agents: <code>{agent_dir}</code>",
        ]
        if reasons:
            lines.append("")
            for r in list(reasons)[:5]:
                lines.append(f"• {r}")
        lines.append("")
        lines.append(f"<i>{ts_utc}</i>")
        return self.send("\n".join(lines))

    def notify_alert(self, title: str, message: str, emoji: str = "⚠️") -> bool:
        if not self.enabled:
            return False
        ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        text = f"<b>{emoji} {title}</b>\n\n{message}\n\n<i>{ts_utc}</i>"
        return self.send(text)


# ─── module-level singleton ───────────────────────────────────────────────
_notifier: Optional[TelegramNotifier] = None
_singleton_lock = Lock()


def get_notifier() -> TelegramNotifier:
    """Return the process-wide TelegramNotifier (built lazily)."""
    global _notifier
    with _singleton_lock:
        if _notifier is None:
            _notifier = TelegramNotifier()
        return _notifier


# Convenience top-level wrappers.
def notify_signal(symbol: str, direction: str, confidence: float, **kw) -> bool:
    return get_notifier().notify_signal(symbol, direction, confidence, **kw)


def notify_alert(title: str, message: str, emoji: str = "⚠️") -> bool:
    return get_notifier().notify_alert(title, message, emoji)


# ─── CLI smoke test ───────────────────────────────────────────────────────
def _cli() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = sys.argv[1:]
    n = get_notifier()
    if not n.enabled:
        print("[X] Telegram notifier is DISABLED.")
        print("    Check config/.env or ai_trading_agents/.env for:")
        print("      TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED=true")
        print("    And ensure `requests` is installed: pip install requests")
        return 2

    if not args or args[0] == "test":
        ok = n.notify_alert(
            "TrendMaster v14 connectivity test",
            "If you see this on your phone, the Telegram pipeline is wired up correctly.",
            emoji="✅",
        )
        print("[OK] Test message sent." if ok else "[X] Send failed — see log above.")
        return 0 if ok else 1

    if args[0] == "signal" and len(args) >= 3:
        sym, direction = args[1], args[2]
        conf = float(args[3]) if len(args) >= 4 else 0.62
        ok = n.notify_signal(
            sym, direction, conf, model="cli", agent_dir=direction.upper(), reasons=["CLI smoke test"], force=True
        )
        print("[OK] Signal sent." if ok else "[X] Send failed.")
        return 0 if ok else 1

    print("Usage:")
    print("  python -m ai_trading_agents.telegram_notifier test")
    print("  python -m ai_trading_agents.telegram_notifier signal XAUUSD BUY 0.71")
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
