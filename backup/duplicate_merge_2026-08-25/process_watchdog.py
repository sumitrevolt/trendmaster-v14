"""Watchdog that ensures the Rocket Prime pipeline processes stay alive.

Runs every minute. For each expected process (executor, trailing manager,
webhook receiver), checks if it's running. If not, respawns it via
pythonw.exe so it stays hidden.

Designed to be safe to run via schtasks every 1-5 minutes.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "process_watchdog.log", encoding="utf-8")],
)
log = logging.getLogger("watchdog")

PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"

# Expected long-running processes (script_path, friendly_name)
EXPECTED = [
    ("tools/python_signal_executor.py", "executor"),
    ("tools/trailing_stop_manager.py", "trail_mgr"),
    ("ai_trading_agents.tv_webhook_receiver", "webhook"),  # module path, not file
    ("tools/dashboard_server.py", "dashboard"),
]


_CREATE_NO_WINDOW = 0x08000000


def is_running(needle: str) -> bool:
    """Return True if any process command-line contains `needle`.
    Uses psutil (pure Python — no subprocess, no console flash)."""
    try:
        import psutil
        needle_lower = needle.lower()
        for p in psutil.process_iter(["cmdline"]):
            try:
                cl = p.info.get("cmdline") or []
                if needle_lower in " ".join(cl).lower():
                    return True
            except Exception:
                continue
        return False
    except ImportError:
        # Fallback: wmic with CREATE_NO_WINDOW (no flash)
        try:
            out = subprocess.check_output(
                ["wmic", "process", "get", "CommandLine"],
                timeout=15,
                creationflags=_CREATE_NO_WINDOW,
            ).decode("utf-8", "replace", errors="replace").lower()
            return needle.lower() in out
        except Exception as e:
            log.warning("ps check failed for %s: %s", needle, e)
            return False


def respawn(script_or_module: str, name: str) -> None:
    """Spawn the process hidden via pythonw."""
    try:
        if script_or_module.endswith(".py"):
            args = ["-u", str(ROOT / script_or_module)]
        else:
            args = ["-u", "-m", script_or_module]
        # CREATE_NO_WINDOW = no console flash
        subprocess.Popen(
            [str(PYTHONW)] + args,
            cwd=str(ROOT),
            creationflags=_CREATE_NO_WINDOW,
        )
        log.warning("RESPAWNED %s (%s)", name, script_or_module)
        # Try to send Telegram alert
        try:
            sys.path.insert(0, str(ROOT))
            from ai_trading_agents.telegram_notifier import get_notifier
            tg = get_notifier()
            if tg and tg.enabled:
                tg.send(f"<b>⚠️ Watchdog: respawned {name}</b>\n<i>Process was dead, restarted now</i>")
        except Exception:
            pass
    except Exception as e:
        log.error("failed to respawn %s: %s", name, e)


_MT5_STATE_FILE = LOG_DIR / "mt5_health_state.json"


def _check_mt5_health():
    """Detect MT5 disconnects between watchdog ticks; alert on edge transitions only."""
    import json as _json
    try:
        sys.path.insert(0, str(ROOT))
        from tools.safeguards import mt5_health_check
        ok, msg = mt5_health_check()
        # Read previous state
        prev = {}
        if _MT5_STATE_FILE.exists():
            try:
                prev = _json.loads(_MT5_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        was_ok = prev.get("ok", True)
        # Edge transitions
        if was_ok and not ok:
            log.error("MT5 went DOWN: %s", msg)
            try:
                from ai_trading_agents.telegram_notifier import get_notifier
                tg = get_notifier()
                if tg and tg.enabled:
                    tg.send(f"<b>🛑 MT5 DISCONNECTED</b>\n{msg}\n<i>Trades won't execute until reconnected.</i>")
            except Exception:
                pass
        elif (not was_ok) and ok:
            log.info("MT5 RECOVERED: %s", msg)
            try:
                from ai_trading_agents.telegram_notifier import get_notifier
                tg = get_notifier()
                if tg and tg.enabled:
                    tg.send(f"<b>✅ MT5 RECONNECTED</b>\n{msg}")
            except Exception:
                pass
        else:
            log.info("MT5 health: %s — %s", "OK" if ok else "DOWN", msg)
        _MT5_STATE_FILE.write_text(_json.dumps({"ok": ok, "msg": msg, "ts": int(time.time())}),
                                    encoding="utf-8")
    except Exception as e:
        log.warning("mt5 health check failed: %s", e)


_NGROK_STATE_FILE = LOG_DIR / "ngrok_health_state.json"
_NGROK_PUBLIC_URL = "https://shadow-cosmos-unending.ngrok-free.dev/status"


def _check_ngrok_external():
    """Hit the public ngrok URL — detects tunnel-down even when receiver is running.
    Watchdog can't restart ngrok itself (operator-owned), but Telegram alert lets
    you know your TV signals are silently bouncing."""
    import json as _json
    import urllib.request
    try:
        prev = {}
        if _NGROK_STATE_FILE.exists():
            try:
                prev = _json.loads(_NGROK_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        was_ok = prev.get("ok", True)
        try:
            req = urllib.request.Request(_NGROK_PUBLIC_URL, method="GET",
                                          headers={"User-Agent": "TM-Watchdog/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                ok = (200 <= r.status < 400)
                msg = f"ngrok status={r.status}"
        except Exception as e:
            ok = False
            msg = f"ngrok unreachable: {e}"
        if was_ok and not ok:
            log.error("ngrok PUBLIC URL DOWN: %s", msg)
            try:
                from ai_trading_agents.telegram_notifier import get_notifier
                tg = get_notifier()
                if tg and tg.enabled:
                    tg.send(
                        f"<b>🛑 NGROK TUNNEL DOWN</b>\n"
                        f"{msg}\n\n"
                        f"<i>TV signals are bouncing — Rocket Prime alerts won't reach the executor.\n"
                        f"Open ngrok dashboard or restart tunnel.</i>"
                    )
            except Exception:
                pass
        elif (not was_ok) and ok:
            log.info("ngrok RECOVERED: %s", msg)
            try:
                from ai_trading_agents.telegram_notifier import get_notifier
                tg = get_notifier()
                if tg and tg.enabled:
                    tg.send(f"<b>✅ NGROK TUNNEL BACK</b>\n{msg}")
            except Exception:
                pass
        else:
            log.info("ngrok health: %s — %s", "OK" if ok else "DOWN", msg)
        _NGROK_STATE_FILE.write_text(_json.dumps({"ok": ok, "msg": msg, "ts": int(time.time())}),
                                      encoding="utf-8")
    except Exception as e:
        log.warning("ngrok health check failed: %s", e)


def main():
    log.info("=== watchdog tick ===")
    _check_mt5_health()
    _check_ngrok_external()
    for path, name in EXPECTED:
        running = is_running(path)
        if running:
            log.info("  [OK]   %s — alive", name)
        else:
            log.warning("  [DEAD] %s — respawning", name)
            respawn(path, name)
            time.sleep(2)
    log.info("=== done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
