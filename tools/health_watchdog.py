"""TrendMaster Health Watchdog — runs every 60s via Windows scheduled task.

Mission: detect any failure in the trading pipeline and auto-recover within
one watchdog interval. Designed to run as user (NOT admin) so it can spawn
pythonw.exe processes detached.

Checked components (all critical for live trading):
  1. TV webhook receiver listening on 127.0.0.1:5005    -> /health 200
  2. ngrok tunnel reachable on shadow-cosmos-unending    -> /health 200
  3. python_signal_executor (MT5 OctaFX) heartbeating   -> log line within 90s
  4. ctrader_executor (IC Markets) heartbeating          -> log line within 90s
                                                            (skipped if tokens absent)
  5. trailing_stop_manager alive                         -> process exists

Auto-recovery actions:
  * If webhook /health fails 2 cycles in a row -> kill any orphan python on
    port 5005, relaunch via start_tv_webhook.cmd (incl. ngrok).
  * If executor heartbeat stale -> kill all instances, respawn singleton.
  * If ngrok process gone but webhook OK -> respawn ngrok only.
  * If ctrader_executor crashed but tokens present -> respawn singleton.
  * If MT5 process not running -> log + alert (operator must launch — we
    don't own the credentials).

Anti-thrash:
  * Each component has a separate cooldown (default 5 min between
    auto-restart attempts) so we don't loop-restart a broken module.
  * State persisted to logs/watchdog_state.json so cooldowns survive
    watchdog restarts.

Telegram on first failure (if creds present in config/.env).

Run interactively to test:
  .venv\\Scripts\\python.exe tools\\health_watchdog.py --once
  .venv\\Scripts\\python.exe tools\\health_watchdog.py --status

Install as scheduled task (1 min interval):
  schtasks /Create /TN "TrendMaster Health Watchdog" /TR "..." /SC MINUTE /MO 1 /RL LIMITED /F
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)
STATE = LOGS / "watchdog_state.json"
LOG = LOGS / "watchdog.log"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHONW = ROOT / ".venv" / "Scripts" / "pythonw.exe"

WEBHOOK_LOCAL = "http://127.0.0.1:5005/health"
WEBHOOK_PUBLIC_BASE_DEFAULT = "https://shadow-cosmos-unending.ngrok-free.dev"
# 2026-05-08: ngrok lives in winget's per-user package dir, NOT tools/.
# start_tv_webhook.cmd points to tools\ngrok.exe (which doesn't exist) so its
# auto-restart silently fails. We spawn ngrok directly here with the right
# path. Override via env NGROK_EXE if installed elsewhere.
NGROK_EXE_DEFAULT = (
    Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Ratanshila\AppData\Local"))
    / "Microsoft" / "WinGet" / "Packages"
    / "Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe" / "ngrok.exe"
)
NGROK_DOMAIN_DEFAULT = "shadow-cosmos-unending.ngrok-free.dev"
HEARTBEAT_FRESH_SEC = 120  # log line newer than this counts as alive
COOLDOWN_DEFAULT = 300     # 5 min between auto-restart attempts per component


# ─────────────────────────────────────────────────────────────────────
# Logging — append to watchdog.log (rotate at 5 MB)
# ─────────────────────────────────────────────────────────────────────
def _rotate_if_needed():
    try:
        if LOG.exists() and LOG.stat().st_size > 5 * 1024 * 1024:
            old = LOG.with_suffix(".log.1")
            if old.exists():
                old.unlink()
            LOG.rename(old)
    except Exception:
        pass


def _log(level: str, msg: str) -> None:
    _rotate_if_needed()
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{level}] {msg}\n"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    # Also stdout — useful when run interactively or piped to a console
    try:
        print(line.rstrip(), flush=True)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────
# State (cooldowns, last-known-good timestamps)
# ─────────────────────────────────────────────────────────────────────
def _load_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(s: dict) -> None:
    try:
        STATE.write_text(json.dumps(s, indent=2), encoding="utf-8")
    except Exception:
        pass


def _can_act(state: dict, key: str, cooldown: int = COOLDOWN_DEFAULT) -> bool:
    last = state.get(f"last_action_{key}", 0)
    return (time.time() - last) >= cooldown


def _stamp(state: dict, key: str) -> None:
    state[f"last_action_{key}"] = int(time.time())


# ─────────────────────────────────────────────────────────────────────
# Telegram alerts (best-effort; fail silent)
# ─────────────────────────────────────────────────────────────────────
def _notify(msg: str, dedup_key: str = "") -> None:
    """Send Telegram alert if creds present. Never raises.

    Dedup: same dedup_key won't notify again within 30 minutes. Prevents
    spam during retry loops (e.g. ngrok restart attempts each cycle).
    State stored in logs/watchdog_telegram_seen.json.
    """
    seen_path = LOGS / "watchdog_telegram_seen.json"
    if dedup_key:
        try:
            seen = json.loads(seen_path.read_text(encoding="utf-8")) if seen_path.exists() else {}
        except Exception:
            seen = {}
        last = seen.get(dedup_key, 0)
        if time.time() - last < 1800:  # 30 min
            return
        seen[dedup_key] = int(time.time())
        # Prune entries older than 24h to keep file small
        seen = {k: v for k, v in seen.items() if time.time() - v < 86400}
        try:
            seen_path.write_text(json.dumps(seen), encoding="utf-8")
        except Exception:
            pass
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / "config" / ".env")
    except Exception:
        return
    bot = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chats = [c.strip() for c in os.getenv("TELEGRAM_CHAT_ID", "").replace(";", ",").split(",") if c.strip()]
    if not bot or not chats:
        return
    try:
        url = f"https://api.telegram.org/bot{bot}/sendMessage"
        for chat in chats:
            data = json.dumps({"chat_id": chat, "text": f"🛡 watchdog: {msg}"}).encode()
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}, method="POST"
            )
            urllib.request.urlopen(req, timeout=4)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────
# Process helpers
# ─────────────────────────────────────────────────────────────────────
def _ps_match(needle: str) -> list:
    """Return list of (pid, cmdline) for python processes matching needle.

    2026-05-13: rewrote from powershell + Get-CimInstance to pure psutil.
    The powershell subprocess was spawning a transient conhost.exe window
    every minute (visible flash even with CREATE_NO_WINDOW) — root cause of
    operator's "terminal pop ho raha hai" complaint. Pure psutil = no
    subprocess, no conhost, fully silent.
    """
    out = []
    try:
        import psutil
        import re
        pat = re.compile(needle)
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = (p.info.get('name') or '').lower()
                if name not in ('python.exe', 'pythonw.exe'):
                    continue
                cmdline = " ".join(p.info.get('cmdline') or [])
                if pat.search(cmdline):
                    out.append((p.info['pid'], cmdline))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        _log("WARN", f"ps_match failed needle={needle}: {e}")
    return out


def _kill(pid: int) -> bool:
    """Kill a PID via psutil (no taskkill subprocess → no conhost flash)."""
    try:
        import psutil
        try:
            psutil.Process(pid).kill()
            return True
        except psutil.NoSuchProcess:
            return True  # already gone, considered success
    except Exception:
        return False


def _spawn_detached(args: list, cwd: Path = ROOT) -> int:
    """Spawn a process detached (no console, survives parent exit)."""
    DETACHED = 0x00000008
    NEWGROUP = 0x00000200
    NOWINDOW = 0x08000000
    try:
        p = subprocess.Popen(
            args, cwd=str(cwd), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, creationflags=DETACHED | NEWGROUP | NOWINDOW,
            close_fds=True,
        )
        return p.pid
    except Exception as e:
        _log("ERROR", f"spawn_detached failed args={args}: {e}")
        return 0


def _http_ok(url: str, timeout: int = 4) -> bool:
    try:
        req = urllib.request.Request(url, headers={"ngrok-skip-browser-warning": "true"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def _log_recent(path: Path, pattern: str, max_age_sec: int) -> bool:
    """True if the log file has a line matching pattern with a recent timestamp."""
    if not path.exists():
        return False
    try:
        # Read last 4 KB only — heartbeat lines arrive frequently
        size = path.stat().st_size
        with path.open("rb") as f:
            f.seek(max(0, size - 4096))
            tail = f.read().decode("utf-8", errors="replace")
        # Lines look like: "2026-05-07 20:38:45,040 [INFO] heartbeat: ..."
        ts_re = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
        for line in reversed(tail.splitlines()):
            if not re.search(pattern, line):
                continue
            m = ts_re.search(line)
            if not m:
                continue
            try:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                age = (datetime.now() - ts).total_seconds()
                return age <= max_age_sec
            except ValueError:
                continue
    except Exception:
        return False
    return False


# ─────────────────────────────────────────────────────────────────────
# Component checks + recovery
# ─────────────────────────────────────────────────────────────────────
def check_webhook_local(state: dict) -> bool:
    if _http_ok(WEBHOOK_LOCAL):
        return True
    _log("WARN", "webhook /health (local) not responding")
    if not _can_act(state, "webhook"):
        _log("INFO", "webhook restart in cooldown — skipping")
        return False
    # Kill any python on 5005 + relaunch via start_tv_webhook.cmd
    for pid, _cl in _ps_match("tv_webhook_receiver"):
        _kill(pid)
    time.sleep(2)
    bat = ROOT / "start_tv_webhook.cmd"
    if bat.exists():
        _spawn_detached(["cmd.exe", "/c", str(bat)])
        _stamp(state, "webhook")
        _notify("webhook restarted", dedup_key="webhook_restart")
        _log("INFO", "webhook restart attempted")
    else:
        _log("ERROR", f"{bat} missing — manual fix required")
    return False


def check_webhook_public(state: dict) -> bool:
    base = os.getenv("TV_PUBLIC_URL", WEBHOOK_PUBLIC_BASE_DEFAULT).rstrip("/")
    url = f"{base}/health"
    if _http_ok(url, timeout=6):
        return True
    _log("WARN", f"public webhook /health not reachable: {url}")
    # Public depends on tunnel. If local is OK, restart tunnel.
    if not _http_ok(WEBHOOK_LOCAL):
        return False  # local broken too — let check_webhook_local handle it
    if not _can_act(state, "ngrok"):
        return False

    # 2026-05-10: TUNNEL_MODE selects ngrok-free vs cloudflared.
    tunnel_mode = (os.getenv("TUNNEL_MODE", "ngrok") or "ngrok").lower()

    if tunnel_mode == "cloudflare":
        # Cloudflare Tunnel runs via cloudflared.exe. Kill any stale + respawn
        # via tools/cloudflare_tunnel_runner.py (handles config + named/quick
        # tunnel selection from .env).
        try:
            # psutil kill — no taskkill subprocess (no conhost flash)
            try:
                import psutil
                for proc in psutil.process_iter(['name']):
                    try:
                        if (proc.info.get('name') or '').lower() == 'cloudflared.exe':
                            proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except Exception:
                pass
        except Exception:
            pass
        time.sleep(3)
        try:
            DETACHED = 0x00000008
            NEWGROUP = 0x00000200
            NOWINDOW = 0x08000000
            log_out = LOGS / "cloudflare_tunnel.out"
            log_err = LOGS / "cloudflare_tunnel.err"
            with log_out.open("ab") as fout, log_err.open("ab") as ferr:
                p = subprocess.Popen(
                    [str(PYTHONW), str(ROOT / "tools" / "cloudflare_tunnel_runner.py")],
                    cwd=str(ROOT),
                    stdout=fout, stderr=ferr, stdin=subprocess.DEVNULL,
                    creationflags=DETACHED | NEWGROUP | NOWINDOW,
                    close_fds=True,
                )
            _stamp(state, "ngrok")  # reuse same cooldown bucket
            _notify("Cloudflare Tunnel restarted", dedup_key="cf_tunnel_restart")
            _log("INFO", f"cloudflare tunnel respawn attempted pid={p.pid}")
        except Exception as e:
            _log("ERROR", f"cloudflare tunnel spawn failed: {e}")
        return False

    # Default: ngrok mode.
    # Kill any stale ngrok. Wait LONGER (15s) so ngrok-cloud releases the
    # reserved-domain session — otherwise cloud rejects the new session as
    # "session conflict" (presents as ERR_NGROK_4018 misleadingly).
    try:
        # psutil kill — no taskkill subprocess
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                try:
                    if (proc.info.get('name') or '').lower() == 'ngrok.exe':
                        proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
    except Exception:
        pass
    time.sleep(15)
    # Spawn ngrok with the correct full path (winget install location)
    ngrok_exe = Path(os.getenv("NGROK_EXE", str(NGROK_EXE_DEFAULT)))
    domain = os.getenv("NGROK_DOMAIN", NGROK_DOMAIN_DEFAULT)
    if not ngrok_exe.exists():
        _log("ERROR", f"ngrok.exe not found at {ngrok_exe} — cannot auto-restart")
        return False
    # 2026-05-08: when launched via Windows scheduled task, env vars may not
    # propagate, so ngrok's default config-path resolution fails. Pass the
    # config file explicitly to guarantee authtoken is loaded.
    ngrok_cfg = Path(
        os.environ.get("LOCALAPPDATA", r"C:\Users\Ratanshila\AppData\Local")
    ) / "ngrok" / "ngrok.yml"
    log_out = LOGS / "ngrok.out"
    log_err = LOGS / "ngrok.err"
    try:
        DETACHED = 0x00000008
        NEWGROUP = 0x00000200
        NOWINDOW = 0x08000000
        # Build env that explicitly carries LOCALAPPDATA + USERPROFILE so ngrok
        # can find its config dir even when watchdog fires under schtasks.
        env = os.environ.copy()
        env.setdefault("LOCALAPPDATA", r"C:\Users\Ratanshila\AppData\Local")
        env.setdefault("USERPROFILE", r"C:\Users\Ratanshila")
        args = [str(ngrok_exe), "http", "5005",
                f"--domain={domain}", "--log=stdout"]
        if ngrok_cfg.exists():
            args.insert(1, "--config")
            args.insert(2, str(ngrok_cfg))
        with log_out.open("ab") as fout, log_err.open("ab") as ferr:
            p = subprocess.Popen(
                args,
                cwd=str(ROOT),
                stdout=fout, stderr=ferr, stdin=subprocess.DEVNULL,
                creationflags=DETACHED | NEWGROUP | NOWINDOW,
                close_fds=True, env=env,
            )
        _stamp(state, "ngrok")
        _notify("ngrok tunnel restarted (direct spawn)", dedup_key="ngrok_restart")
        _log("INFO", f"ngrok restart attempted pid={p.pid} args={args}")
    except Exception as e:
        _log("ERROR", f"ngrok spawn failed: {e}")
    return False


def check_executor(state: dict) -> bool:
    """python_signal_executor for MT5 OctaFX."""
    log_path = LOGS / "python_executor.log"
    fresh = _log_recent(log_path, r"heartbeat: iter=", HEARTBEAT_FRESH_SEC)
    if fresh:
        return True
    procs = _ps_match("python_signal_executor")
    _log("WARN", f"executor heartbeat stale (procs={len(procs)})")
    if not _can_act(state, "executor"):
        return False
    # Kill all + respawn singleton.
    # FIX 2026-05-09: previously we deleted the lock file BEFORE the
    # killed process had actually exited (taskkill returns async). The
    # old process kept its open handle to the now-deleted lock file
    # (Windows holds the inode open until last handle closes), and the
    # new process then created a fresh lock file with a different inode
    # and successfully locked byte 0. Result: TWO healthy executors
    # heartbeating in parallel until next watchdog cycle. Now we wait
    # for PIDs to actually disappear before unlinking + spawning.
    killed_pids = [pid for pid, _cl in procs]
    for pid in killed_pids:
        _kill(pid)
    # Wait up to 8s for all killed PIDs to vanish from the process list.
    deadline = time.time() + 8.0
    while time.time() < deadline:
        still_alive = _ps_match("python_signal_executor")
        if not still_alive:
            break
        time.sleep(0.5)
    else:
        survivors = [pid for pid, _cl in _ps_match("python_signal_executor")]
        _log("ERROR", f"executor PIDs still alive after 8s kill-wait: {survivors}")
        return False
    try:
        (LOGS / "python_signal_executor.lock").unlink(missing_ok=True)
    except Exception:
        pass
    _spawn_detached([str(PYTHONW), str(ROOT / "tools" / "python_signal_executor.py")])
    _stamp(state, "executor")
    _notify("python_signal_executor (MT5) restarted", dedup_key="executor_restart")
    _log("INFO", "executor restart attempted")
    return False


def check_ctrader(state: dict) -> bool:
    """ctrader_executor for IC Markets — only checked if tokens present."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / "config" / ".env")
    except Exception:
        return True  # silently skip
    if not os.getenv("CTRADER_ACCESS_TOKEN", "").strip():
        return True  # not configured yet
    if not os.getenv("CTRADER_ACCOUNT_ID", "").strip():
        _log("INFO", "ctrader: token present but account_id missing — skip")
        return True
    log_path = LOGS / "ctrader_executor.log"
    fresh = _log_recent(log_path, r"heartbeat|connected", HEARTBEAT_FRESH_SEC)
    if fresh:
        return True
    procs = _ps_match("ctrader_executor")
    if procs and log_path.exists():
        # Process up but log stale — give it 1 cycle grace before killing
        if not _log_recent(log_path, r".+", HEARTBEAT_FRESH_SEC * 2):
            _log("WARN", "ctrader log frozen >4min")
        else:
            return True
    _log("WARN", f"ctrader_executor stale (procs={len(procs)})")
    if not _can_act(state, "ctrader"):
        return False
    for pid, _cl in procs:
        _kill(pid)
    time.sleep(2)
    _spawn_detached([str(PYTHONW), str(ROOT / "tools" / "ctrader_executor.py")])
    _stamp(state, "ctrader")
    _notify("ctrader_executor (IC Markets) restarted", dedup_key="ctrader_restart")
    _log("INFO", "ctrader restart attempted")
    return False


def check_trailing(state: dict) -> bool:
    """trailing_stop_manager — non-critical but should be alive."""
    procs = _ps_match("trailing_stop_manager")
    if procs:
        return True
    _log("WARN", "trailing_stop_manager not running")
    if not _can_act(state, "trailing"):
        return False
    _spawn_detached([str(PYTHONW), str(ROOT / "tools" / "trailing_stop_manager.py")])
    _stamp(state, "trailing")
    _log("INFO", "trailing_stop_manager respawn attempted")
    return False


def check_telegram_listener(state: dict) -> bool:
    """telegram_direction_listener — operator-tap fallback for OCR.

    Critical for the BUY/SELL prompt path when OCR returns NONE.
    Singleton: kill ALL existing before respawning (HTTP 409 Conflict
    happens if 2+ instances poll Telegram getUpdates concurrently).
    """
    procs = _ps_match("telegram_direction_listener")
    if procs:
        # If somehow more than one logical instance is alive, kill extras
        # (2 PIDs = parent venv shim + Python311 child is fine; >2 means dupes)
        if len(procs) > 2:
            _log("WARN", f"telegram_listener has {len(procs)} PIDs — killing dupes")
            # Kill all then respawn
            for pid, _ in procs:
                _kill(pid)
            time.sleep(2)
            procs = []
        else:
            return True
    _log("WARN", "telegram_direction_listener not running")
    if not _can_act(state, "telegram_listener"):
        return False
    _spawn_detached([str(PYTHONW), str(ROOT / "tools" / "telegram_direction_listener.py")])
    _stamp(state, "telegram_listener")
    _log("INFO", "telegram_direction_listener respawn attempted")
    return False


def check_brain(state: dict) -> bool:
    """trend_master_brain — shadow learner. Should stay alive to update
    brain_state.json which feeds the brain-veto safeguard.
    """
    # Filter out brain_forensics_monitor.py — that's a separate diagnostic
    procs = [(pid, cmd) for pid, cmd in _ps_match("trend_master_brain")
             if "brain_forensics" not in cmd]
    if procs:
        return True
    _log("WARN", "trend_master_brain not running")
    if not _can_act(state, "brain"):
        return False
    _spawn_detached([str(PYTHONW), "-m", "ai_trading_agents.trend_master_brain"])
    _stamp(state, "brain")
    _log("INFO", "trend_master_brain respawn attempted")
    return False


def check_mt5(state: dict) -> bool:
    """MT5 terminal alive — we cannot relaunch with credentials, just alert."""
    try:
        # 2026-05-13: replaced powershell+Get-Process with pure psutil.
        # Each powershell subprocess.run was spawning conhost.exe (visible
        # flash even with CREATE_NO_WINDOW) every watchdog cycle = popup spam.
        import psutil
        n = sum(1 for p in psutil.process_iter(['name'])
                if (p.info.get('name') or '').lower() == 'terminal64.exe')
        if n > 0:
            return True
    except Exception:
        pass
    _log("ERROR", "MT5 terminal64 process NOT running")
    if _can_act(state, "mt5", cooldown=900):  # 15 min cooldown for alerts
        _notify("CRITICAL: MT5 terminal64 not running — operator must launch", dedup_key="mt5_missing")
        _stamp(state, "mt5")
    return False


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────
def run_once() -> dict:
    state = _load_state()
    results = {
        "ts": int(time.time()),
        "webhook_local": check_webhook_local(state),
        "webhook_public": check_webhook_public(state),
        "executor": check_executor(state),
        "trailing": check_trailing(state),
        # 2026-05-14 added: keep operator-tap + shadow-learner alive auto.
        "telegram_listener": check_telegram_listener(state),
        "brain": check_brain(state),
        "ctrader": check_ctrader(state),
        "mt5": check_mt5(state),
    }
    state["last_run_ts"] = results["ts"]
    state["last_results"] = results
    _save_state(state)
    healthy = all(v for k, v in results.items() if k != "ts")
    _log("INFO", f"cycle done healthy={healthy} results={results}")
    return results


def status() -> int:
    state = _load_state()
    last = state.get("last_results", {})
    ts = state.get("last_run_ts", 0)
    age = int(time.time() - ts) if ts else -1
    print(f"Watchdog last run: {age}s ago")
    for k, v in last.items():
        if k == "ts":
            continue
        mark = "OK  " if v else "FAIL"
        print(f"  [{mark}] {k}")
    return 0 if all(v for k, v in last.items() if k != "ts") else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="Run one check cycle and exit")
    p.add_argument("--status", action="store_true", help="Print last-run status")
    args = p.parse_args()
    if args.status:
        return status()
    if args.once or True:  # default: run once (scheduled task drives interval)
        results = run_once()
        return 0 if all(v for k, v in results.items() if k != "ts") else 1


if __name__ == "__main__":
    sys.exit(main())
