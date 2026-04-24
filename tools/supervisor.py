"""
tools/supervisor.py — tiny process supervisor for the brain + dashboard.

Why
---
The current START_TRENDMASTER_v14.bat launches the brain detached with a
PID in logs/brain.pid but doesn't watch it. If the brain crashes at 3 am
it stays dead until someone notices. This module adds:

    * periodic PID liveness check
    * auto-restart with exponential backoff (2s, 4s, 8s, ..., cap 120s)
    * /healthz probe (HTTP GET on dashboard port)
    * structured heartbeat log at logs/supervisor.log

Usage
-----
    python main.py supervise

Or wrap the existing .bat scripts by pointing them at `python main.py
supervise` instead of launching the brain directly.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.error import URLError
from urllib.request import urlopen

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
LOGS = _ROOT / "logs"
LOGS.mkdir(parents=True, exist_ok=True)

# Make project root importable so the Telegram notifier resolves cleanly
# even when this file is launched directly (`python tools/supervisor.py`).
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Optional Telegram alerts. If creds are missing or `requests` isn't
# installed the import yields a notifier whose .enabled is False, and
# every send becomes a no-op — supervisor still works, just silently.
try:
    from ai_trading_agents.telegram_notifier import get_notifier as _get_tg  # noqa: E402
except Exception:
    _get_tg = None  # type: ignore

logger = logging.getLogger("supervisor")


def _tg_alert(title: str, message: str, emoji: str = "⚠️") -> None:
    """Best-effort Telegram alert from the supervisor. Never raises."""
    if _get_tg is None:
        return
    try:
        _get_tg().notify_alert(title, message, emoji=emoji)
    except Exception as e:
        logger.debug("supervisor TG alert skipped: %s", e)


@dataclass
class ManagedProcess:
    name: str
    cmd: List[str]
    pid_file: Path
    log_out:  Path
    log_err:  Path
    popen: Optional[subprocess.Popen] = None
    restarts: int = 0

    def is_alive(self) -> bool:
        if self.popen is None:
            return False
        return self.popen.poll() is None

    def start(self) -> None:
        self.log_out.parent.mkdir(parents=True, exist_ok=True)
        out = open(self.log_out, "ab")
        err = open(self.log_err, "ab")
        self.popen = subprocess.Popen(self.cmd,
                                      cwd=str(_ROOT),
                                      stdout=out,
                                      stderr=err)
        self.pid_file.write_text(str(self.popen.pid), encoding="ascii")
        logger.info("started %s pid=%d cmd=%s", self.name, self.popen.pid, self.cmd)

    def stop(self) -> None:
        if self.popen and self.is_alive():
            try:
                self.popen.terminate()
                try:
                    self.popen.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.popen.kill()
            except Exception as e:
                logger.warning("stop failed for %s: %s", self.name, e)
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except OSError:
            pass


@dataclass
class Supervisor:
    procs: List[ManagedProcess]
    health_url: Optional[str] = None
    tick_s: float = 5.0

    @classmethod
    def default(cls) -> "Supervisor":
        py = sys.executable
        brain = ManagedProcess(
            name="brain",
            cmd=[py, "-u", "ai_trading_agents/trend_master_brain.py"],
            pid_file=LOGS / "brain.pid",
            log_out=LOGS / "trend_master_brain.log",
            log_err=LOGS / "trend_master_brain.err",
        )
        dash = ManagedProcess(
            name="dashboard",
            cmd=[py, "-u", "tools/dashboard.py"],
            pid_file=LOGS / "dashboard.pid",
            log_out=LOGS / "dashboard.out",
            log_err=LOGS / "dashboard.err",
        )
        return cls(procs=[brain, dash],
                   health_url="http://localhost:8000/healthz")

    def _backoff(self, restarts: int) -> float:
        return float(min(120, 2 ** max(1, restarts)))

    def run_forever(self) -> None:
        for p in self.procs:
            p.start()
        # Boot ping so Sumit's phone confirms the supervisor itself came up.
        _tg_alert(
            "TrendMaster v14 supervisor ONLINE",
            "Watching: " + ", ".join(p.name for p in self.procs),
            emoji="🟢",
        )
        stop = {"flag": False}

        def _sig(_signum, _frame):
            stop["flag"] = True
        for s in (signal.SIGINT, signal.SIGTERM):
            try: signal.signal(s, _sig)
            except Exception: pass

        try:
            while not stop["flag"]:
                time.sleep(self.tick_s)
                for p in self.procs:
                    if p.is_alive():
                        continue
                    wait = self._backoff(p.restarts)
                    next_n = p.restarts + 1
                    logger.warning("process %s exited — restarting in %.1fs "
                                   "(restart #%d)", p.name, wait, next_n)
                    # Push an alert on EVERY restart for the brain (it's the
                    # critical one). Dashboard restarts are noisy so we only
                    # alert on the brain — keeps the phone signal:noise ratio
                    # tolerable while still surfacing real outages.
                    if p.name == "brain":
                        _tg_alert(
                            f"TrendMaster v14 {p.name} CRASHED",
                            (f"Process exited unexpectedly.\n"
                             f"Restart #<code>{next_n}</code> in "
                             f"<code>{wait:.0f}s</code>\n"
                             f"Logs: <code>{p.log_err.name}</code>"),
                            emoji="🔴",
                        )
                    time.sleep(wait)
                    p.restarts += 1
                    p.start()
                    if p.name == "brain":
                        _tg_alert(
                            f"TrendMaster v14 {p.name} RESTARTED",
                            (f"Restart #<code>{p.restarts}</code> back online "
                             f"(pid=<code>{p.popen.pid if p.popen else '?'}</code>)"),
                            emoji="🟡",
                        )
                self._heartbeat()
        finally:
            for p in self.procs:
                p.stop()
            _tg_alert(
                "TrendMaster v14 supervisor OFFLINE",
                "Supervisor shutting down — managed processes stopped.",
                emoji="🛑",
            )

    def _heartbeat(self) -> None:
        snap = {
            "ts": int(time.time()),
            "procs": [{"name": p.name,
                       "alive": p.is_alive(),
                       "restarts": p.restarts,
                       "pid": (p.popen.pid if p.popen else None)}
                      for p in self.procs],
            "health": probe_health(self.health_url),
        }
        (LOGS / "supervisor.log").open("a", encoding="utf-8").write(
            json.dumps(snap) + "\n"
        )


def probe_health(url: str = "http://localhost:8000/healthz",
                 timeout: float = 2.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as r:
            if r.status != 200:
                return False
            body = r.read(64)
            return b"ok" in body.lower() or body.strip() == b"{}"
    except (URLError, ValueError, TimeoutError, OSError):
        return False


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    Supervisor.default().run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
