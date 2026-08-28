"""
telegram_commands.py — Telegram /command listener for TrendMaster v14
=====================================================================

Why a separate module
---------------------
`telegram_notifier.py` is push-only: brain → user. This adds the inverse
direction: user → brain. Sumit can text `/status` from his phone and get
a live snapshot back without having to RDP into the box.

How it works
------------
* Spawned as a daemon thread by the brain at boot.
* Long-polls `getUpdates` (timeout=30s) so we don't hammer the API.
* Maintains last-seen `update_id` so we don't re-process commands.
* Recognises a small whitelist of slash commands and dispatches to
  callbacks the brain registers via `register_command()`.
* All failures are logged and swallowed — a flaky network or revoked
  bot token must NEVER kill the trading loop.
* Only honours messages from the configured `TELEGRAM_CHAT_ID` (so a
  random stranger who guesses the bot username can't poke the brain).

Built-in commands
-----------------
    /ping     → "pong + uptime"
    /help     → list available commands
    /status   → snapshot from registered status callback (set by brain)
    /pnl      → daily PnL snapshot (registered by brain)
    /symbols  → list of active trading symbols (registered by brain)
    /halt     → flip brain into "no new trades" mode (registered by brain)
    /resume   → undo /halt — re-enable signal writes  (registered by brain)

The brain registers these callbacks at startup. If a callback isn't
registered, the listener replies "command not wired".

Usage from the brain
--------------------
    from ai_trading_agents.telegram_commands import get_listener

    listener = get_listener()
    listener.register_command("status", lambda: "OK, brain alive")
    listener.start()                                 # daemon, fire & forget
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

logger = logging.getLogger("telegram_commands")

# Re-use the notifier's .env discovery so this module works the same
# whether it's imported first, last, or alone (e.g. in a CLI smoke test).
try:
    from ai_trading_agents.telegram_notifier import _load_env as _tg_load_env  # type: ignore

    _tg_load_env()
except Exception:
    pass

try:
    import requests  # type: ignore

    _HAS_REQ = True
except ImportError:
    _HAS_REQ = False


_TG_API = "https://api.telegram.org/bot{token}/{method}"

# Commands the listener will dispatch on. Adding a command here only enables
# it — the brain still has to register a callback via register_command().
KNOWN_COMMANDS = (
    "ping",
    "help",
    "status",
    "pnl",
    "symbols",
    "halt",
    "resume",
    "why",
    # [enhancement 2026-04-23] /drift snapshot command for ADWIN detector.
    "drift",
    # [enhancement 2026-04-23 R3] /var portfolio risk snapshot.
    "var",
    # [enhancement 2026-04-23 R4 — operator grade] perf + digest.
    "perf",
    "digest",
    "gates",
)


class TelegramCommandListener:
    """
    Long-polls Telegram for /commands and dispatches to registered callbacks.

    Each callback returns either:
      * a `str`         → sent as plain HTML message.
      * `None` / falsy  → "(no data)" reply.
      * raises          → caught, logged, "(internal error)" reply.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        poll_timeout_s: int = 30,
        http_timeout_s: float = 35.0,
    ):
        # Re-use the same env vars the notifier reads, so a single .env wires
        # both sides (push notifier + pull command listener).
        # Comma/semicolon-separated recipients are supported: "id1,id2,id3".
        self.token = (token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        raw_chat = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
        self.chat_ids = [c.strip() for c in re.split(r"[,;]", raw_chat) if c.strip()]
        self.chat_id = self.chat_ids[0] if self.chat_ids else ""
        self.poll_timeout_s = int(poll_timeout_s)
        self.http_timeout_s = float(http_timeout_s)
        self.enabled = bool(self.token and self.chat_id and _HAS_REQ)

        # Update-id bookmark so we don't re-process the same /status forever.
        self._offset = 0
        self._handlers: Dict[str, Callable[[], Optional[str]]] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._started_at = time.time()

        if not self.enabled:
            why = []
            if not _HAS_REQ:
                why.append("no requests")
            if not self.token:
                why.append("no token")
            if not self.chat_id:
                why.append("no chat_id")
            logger.info("Telegram command listener disabled (%s).", ", ".join(why) or "unknown")

    # ─── public API ─────────────────────────────────────────────────────
    def register_command(self, name: str, fn: Callable[..., Optional[str]]) -> None:
        # `fn` may be either zero-arg `() -> str` or one-arg `(args:str) -> str`.
        # The dispatcher inspects the signature at call time and adapts.
        name = name.lstrip("/").lower()
        if name not in KNOWN_COMMANDS:
            logger.warning(
                "register_command: '%s' not in KNOWN_COMMANDS — ignored. Add it to KNOWN_COMMANDS to enable.", name
            )
            return
        self._handlers[name] = fn

    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        # Built-ins that don't need brain state.
        self._handlers.setdefault("ping", self._builtin_ping)
        self._handlers.setdefault("help", self._builtin_help)
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="tg-cmd-listener", daemon=True)
        self._thread.start()
        logger.info("Telegram command listener started (commands: %s)", ", ".join(sorted(self._handlers)))

    def stop(self) -> None:
        self._stop.set()

    # ─── built-ins ──────────────────────────────────────────────────────
    def _builtin_ping(self) -> str:
        up = time.time() - self._started_at
        h, rem = divmod(int(up), 3600)
        m, s = divmod(rem, 60)
        return f"pong — uptime {h}h{m:02d}m{s:02d}s"

    def _builtin_help(self) -> str:
        rows = []
        for cmd in KNOWN_COMMANDS:
            wired = "✓" if cmd in self._handlers else "·"
            rows.append(f"{wired} /{cmd}")
        return "<b>TrendMaster v14 commands</b>\n" + "\n".join(rows)

    # ─── send helper ────────────────────────────────────────────────────
    def _send(self, text: str, chat_id: Optional[str] = None) -> None:
        """Send to `chat_id`, or fan-out to every configured chat when None."""
        if not self.enabled:
            return
        targets = [chat_id] if chat_id else self.chat_ids
        url = _TG_API.format(token=self.token, method="sendMessage")
        for cid in targets:
            payload = {
                "chat_id": cid,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            try:
                requests.post(url, json=payload, timeout=self.http_timeout_s)
            except Exception as e:
                logger.debug("command reply send failed (chat %s): %s", cid, e)

    # ─── poll loop ──────────────────────────────────────────────────────
    def _poll_loop(self) -> None:
        # On startup we discard any backlog: if Sumit sent /status three
        # hours ago and the brain just came up, replying now would be
        # confusing. Bookmark to the latest update and start fresh.
        try:
            self._offset = self._fetch_latest_offset()
        except Exception as e:
            logger.debug("initial offset fetch failed: %s", e)

        backoff = 1.0
        while not self._stop.is_set():
            try:
                updates = self._get_updates()
                backoff = 1.0
                for upd in updates:
                    self._handle_update(upd)
            except Exception as e:
                # Network blip, DNS hiccup, broker-time API outage — log
                # and back off. Never let this thread die.
                logger.debug("getUpdates failed: %s (backoff=%.1fs)", e, backoff)
                self._stop.wait(backoff)
                backoff = min(60.0, backoff * 2)

    def _fetch_latest_offset(self) -> int:
        """One quick getUpdates with timeout=0 to find the newest update_id."""
        if not self.enabled:
            return 0
        url = _TG_API.format(token=self.token, method="getUpdates")
        r = requests.get(url, params={"timeout": 0, "limit": 1, "offset": -1}, timeout=self.http_timeout_s)
        data = r.json()
        if not data.get("ok"):
            return 0
        result = data.get("result") or []
        if not result:
            return 0
        return int(result[-1]["update_id"]) + 1

    def _get_updates(self) -> list:
        url = _TG_API.format(token=self.token, method="getUpdates")
        r = requests.get(
            url,
            params={"timeout": self.poll_timeout_s, "offset": self._offset},
            timeout=self.http_timeout_s,
        )
        data = r.json()
        if not data.get("ok"):
            return []
        return data.get("result") or []

    def _handle_update(self, upd: dict) -> None:
        try:
            self._offset = max(self._offset, int(upd["update_id"]) + 1)
        except Exception:
            pass

        msg = upd.get("message") or upd.get("edited_message") or {}
        chat = msg.get("chat") or {}
        text = (msg.get("text") or "").strip()
        if not text or not text.startswith("/"):
            return

        # Authorisation: only honour messages from configured chats.
        # str() compare because Telegram returns int chat ids.
        if str(chat.get("id")) not in {str(c) for c in self.chat_ids}:
            logger.warning("Ignoring command from unauthorised chat id=%s", chat.get("id"))
            return

        # Strip leading '/' and any '@botname' suffix Telegram adds in groups.
        parts = text.split(maxsplit=1)
        cmd = parts[0][1:].split("@", 1)[0].lower()
        # Everything after the command name becomes the args string. e.g.
        # "/why XAUUSD" -> args="XAUUSD", "/status" -> args="".
        args = parts[1].strip() if len(parts) > 1 else ""
        if cmd not in KNOWN_COMMANDS:
            return

        fn = self._handlers.get(cmd)
        if fn is None:
            self._send(f"(<code>/{cmd}</code> not wired into this brain build)", chat_id=str(chat.get("id")))
            return
        try:
            # Backwards-compatible dispatch. Most handlers were written for
            # the no-arg signature `Callable[[], Optional[str]]`. The /why
            # style commands need the rest of the message — we detect that
            # via inspection. Falls back to no-arg call on TypeError so a
            # handler that simply doesn't accept args still runs.
            import inspect as _inspect

            try:
                _params = _inspect.signature(fn).parameters
                if len(_params) >= 1:
                    reply = fn(args)
                else:
                    reply = fn()
            except (ValueError, TypeError):
                # Some callables (e.g., builtins, C-functions) don't expose
                # a signature. Try arg-form first, then fall back.
                try:
                    reply = fn(args)
                except TypeError:
                    reply = fn()
        except Exception as e:
            logger.warning("command /%s handler raised: %s", cmd, e)
            self._send(f"(internal error running <code>/{cmd}</code>)", chat_id=str(chat.get("id")))
            return
        if not reply:
            self._send(f"(no data for <code>/{cmd}</code>)", chat_id=str(chat.get("id")))
            return
        ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self._send(f"{reply}\n\n<i>{ts_utc}</i>", chat_id=str(chat.get("id")))


# ─── module-level singleton ────────────────────────────────────────────────
_listener: Optional[TelegramCommandListener] = None
_singleton_lock = threading.Lock()


def get_listener() -> TelegramCommandListener:
    global _listener
    with _singleton_lock:
        if _listener is None:
            _listener = TelegramCommandListener()
        return _listener
