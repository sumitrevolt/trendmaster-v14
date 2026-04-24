"""Unit tests for ai_trading_agents/telegram_commands.py.

All tests run OFFLINE — `requests` is never actually called because we
construct listeners with empty token/chat_id (so `enabled=False`) or
monkeypatch the requests module out.
"""
from __future__ import annotations

import pytest

from ai_trading_agents.telegram_commands import (
    KNOWN_COMMANDS,
    TelegramCommandListener,
)


# ─── KNOWN_COMMANDS sanity ─────────────────────────────────────────────────
# Phase G3 added /halt and /resume; Phase G7 added /why <symbol>.
# [enhancement 2026-04-23] added /drift for the ADWIN detector snapshot.
# The set check is the canonical assertion; the length check below is just
# a guard so anyone adding a new command has to update the set above on
# purpose (not silently grow the surface).
EXPECTED_COMMANDS = {"ping", "help", "status", "pnl", "symbols", "halt", "resume", "why",
                     "drift", "var", "perf", "digest", "gates"}


def test_known_commands_contains_expected_set():
    assert set(KNOWN_COMMANDS) == EXPECTED_COMMANDS


def test_known_commands_length_matches_expected():
    assert len(KNOWN_COMMANDS) == len(EXPECTED_COMMANDS)


# ─── helper: make an offline listener ──────────────────────────────────────
@pytest.fixture(autouse=True)
def _no_env_creds(monkeypatch):
    """Strip Telegram env vars so the constructor's `or os.getenv(...)`
    fallback can't accidentally pick up real credentials from a loaded
    .env file. This must run BEFORE every test in this module."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


def _offline_listener() -> TelegramCommandListener:
    # Empty creds + env stripped above → enabled=False, no network.
    return TelegramCommandListener(token="", chat_id="")


# ─── register_command ──────────────────────────────────────────────────────
def test_register_command_accepts_known_name():
    lst = _offline_listener()
    lst.register_command("status", lambda: "ok")
    assert "status" in lst._handlers


def test_register_command_strips_leading_slash():
    lst = _offline_listener()
    lst.register_command("/pnl", lambda: "0.0")
    assert "pnl" in lst._handlers


def test_register_command_rejects_unknown_name():
    lst = _offline_listener()
    lst.register_command("nuke", lambda: "boom")
    assert "nuke" not in lst._handlers


def test_register_command_is_case_insensitive():
    lst = _offline_listener()
    lst.register_command("STATUS", lambda: "ok")
    assert "status" in lst._handlers


# ─── _builtin_ping ─────────────────────────────────────────────────────────
def test_builtin_ping_starts_with_pong():
    lst = _offline_listener()
    reply = lst._builtin_ping()
    assert reply.startswith("pong")


def test_builtin_ping_includes_uptime_format():
    lst = _offline_listener()
    reply = lst._builtin_ping()
    # "pong — uptime 0h00m00s" style
    assert "uptime" in reply
    assert "h" in reply and "m" in reply and "s" in reply


# ─── _builtin_help ─────────────────────────────────────────────────────────
def test_builtin_help_lists_all_known_commands():
    lst = _offline_listener()
    reply = lst._builtin_help()
    for cmd in KNOWN_COMMANDS:
        assert f"/{cmd}" in reply


def test_builtin_help_marks_wired_commands_with_check():
    lst = _offline_listener()
    lst._handlers["status"] = lambda: "ok"
    reply = lst._builtin_help()
    # Wired marker is the unicode check; unwired is the middle-dot.
    # We just assert the wired symbol appears next to /status's line.
    lines = reply.splitlines()
    status_line = next(line for line in lines if "/status" in line)
    unwired_line = next(line for line in lines if "/pnl" in line)
    assert status_line.strip().startswith("\u2713")  # ✓
    assert unwired_line.strip().startswith("\u00b7")  # ·


def test_builtin_help_has_header():
    lst = _offline_listener()
    reply = lst._builtin_help()
    assert "TrendMaster" in reply


# ─── enabled flag wiring ───────────────────────────────────────────────────
def test_listener_disabled_when_no_credentials():
    lst = _offline_listener()
    assert lst.enabled is False


def test_listener_start_is_noop_when_disabled():
    lst = _offline_listener()
    lst.start()  # must not raise, must not spawn a thread
    assert lst._thread is None


# ─── monkeypatch sanity: confirm we don't hit the network ─────────────────
def test_send_is_safe_when_disabled(monkeypatch):
    """_send() must early-return when enabled=False — even if `requests` is
    swapped for an exploding sentinel, no call should be made."""
    import ai_trading_agents.telegram_commands as tc

    class _Boom:
        def post(self, *a, **k):
            raise AssertionError("network must not be touched")

    monkeypatch.setattr(tc, "requests", _Boom(), raising=False)
    lst = _offline_listener()
    lst._send("hello")  # must not raise
