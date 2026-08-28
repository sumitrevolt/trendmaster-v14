"""Brain liveness watchpet -- ping Telegram if brain.pid stale or process dead.

Run via Windows Task Scheduler every 5 min (or via cron). Idempotent + light.

Logic:
  1. Read logs/brain.pid (set by start_brain_clean.cmd).
  2. Check if PID exists in process table AND its CommandLine contains
     trend_master_brain. If either fails -> brain is DEAD or stale.
  3. ALSO check brain log mtime; if log hasn't been written in > 10 min,
     brain is alive but stuck.
  4. On death/stuck, send Telegram alert (deduped via state file so we don't
     spam every 5 min).

Returns 0 if alive, 2 if dead/stale, 3 if Telegram fail.
"""
from __future__ import annotations
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PID_FILE = ROOT / "logs" / "brain.pid"
# 2026-08-27 FIX: the brain actually logs to trend_master_brain.log (the .out
# file is a stale stdout redirect from an old start_brain_clean.cmd launch and is
# never updated by the live brain). Watching .out caused perpetual false
# "brain log idle" alerts. Watch the real, live log.
LOG_FILE = ROOT / "logs" / "trend_master_brain.log"
STATE_FILE = ROOT / "logs" / "watchpet_brain.state.json"
LOG_MAX_AGE_S = 600   # 10 min -- if log idle this long, brain is stuck
ALERT_DEDUP_S = 1800  # don't re-alert for same incident within 30 min

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "config" / ".env")
except ImportError:
    pass

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHATS = [c.strip() for c in os.getenv("TELEGRAM_CHAT_ID", "").replace(";", ",").split(",") if c.strip()]


def _alive(pid: int) -> bool | None:
    """Check process is alive AND is the brain (cmd-line match).

    Returns True/False only for a *definitive* answer; returns None when the
    check itself failed (psutil error, WMI hiccup, timeout). Callers must
    treat None as 'unknown' -- paging on None caused false 'brain DEAD'
    alerts while the brain was perfectly healthy (2026-08-26 13:04 UTC).
    """
    try:
        import psutil
        if not psutil.pid_exists(pid):
            return False
        p = psutil.Process(pid)
        cmd = " ".join(p.cmdline() or [])
        name = (p.name() or "").lower()
        if "python" not in name:
            return False
        # Definitive match / mismatch on cmdline.
        return "trend_master_brain" in cmd
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        pass  # fall through to legacy check
    except Exception:
        pass  # fall through to legacy check
    # Legacy fallback: PowerShell CIM query (slow, can time out under load).
    import subprocess
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             f"Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\" | "
             f"Where-Object {{ $_.CommandLine -like '*trend_master_brain*' }} | "
             f"Select-Object -ExpandProperty ProcessId"],
            timeout=10, text=True, stderr=subprocess.DEVNULL,
        ).strip()
        return out == str(pid)
    except Exception:
        return None  # check failed -- NOT evidence of death


def _send_tg(msg: str) -> bool:
    if not TG_TOKEN or not TG_CHATS:
        print(f"[no telegram] {msg}")
        return False
    try:
        import urllib.request as u, urllib.parse as up
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        ok = False
        for TG_CHAT in TG_CHATS:
            body = up.urlencode({"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown"}).encode()
            r = u.urlopen(u.Request(url, data=body), timeout=8)
            ok = ok or r.status == 200
        return ok
    except Exception as e:
        print(f"[tg fail] {e}")
        return False


def _any_live_brain_pid() -> "int | None":
    """Return the PID of ANY currently-running trend_master_brain process, or None.

    Used as a fallback when logs/brain.pid is stale (the brain can be restarted by
    paths that don't rewrite brain.pid, e.g. the watchdog / duplicate launcher).
    Scanning live processes avoids false 'brain DEAD' pages just because the pid
    file wasn't refreshed.
    """
    try:
        import psutil
        for p in psutil.process_iter(["pid", "cmdline", "name"]):
            try:
                name = (p.info.get("name") or "").lower()
                if "python" not in name:
                    continue
                cmd = " ".join(p.info.get("cmdline") or [])
                if "trend_master_brain" in cmd:
                    return int(p.info["pid"])
            except Exception:
                continue
    except Exception:
        pass
    return None


def _last_alert_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_alert_ts": 0, "last_msg": ""}


def _save_alert_state(sig: str) -> None:
    STATE_FILE.write_text(json.dumps({"last_alert_ts": int(time.time()), "last_sig": sig}))


def main() -> int:
    issues = []

    # 1. PID file present?
    live_pid = None
    if not PID_FILE.exists():
        # Don't immediately cry wolf -- the launcher may not have written it.
        # Check for a live brain process directly.
        live_pid = _any_live_brain_pid()
        if live_pid is None:
            issues.append("brain.pid missing and no brain process found")
        # else: brain is alive, pid file just missing -- refresh below
    else:
        try:
            pid = int(PID_FILE.read_text().strip())
            alive = _alive(pid)
            if alive is False:
                # pid-file PID dead -- but is SOME brain still running?
                live_pid = _any_live_brain_pid()
                if live_pid is None:
                    issues.append(f"brain PID {pid} dead or wrong process")
                # else: brain alive under a different PID (stale pid file);
                # we treat it as alive and refresh the pid file below.
            elif alive is None:
                # Check failed (WMI/psutil hiccup) -- log it, do NOT page.
                print(f"[WARN] aliveness check for PID {pid} errored; assuming alive")
                live_pid = pid
            else:
                live_pid = pid  # pid-file PID is the live brain
        except Exception as e:
            issues.append(f"brain.pid unreadable: {e}")

    # Refresh brain.pid if we found a live brain under a different PID (stale file).
    if live_pid and PID_FILE.exists() and PID_FILE.read_text().strip() != str(live_pid):
        try:
            PID_FILE.write_text(str(live_pid))
            print(f"[info] refreshed stale brain.pid -> {live_pid}")
        except Exception:
            pass

    # 2. Brain log fresh?
    if LOG_FILE.exists():
        age = time.time() - LOG_FILE.stat().st_mtime
        if age > LOG_MAX_AGE_S:
            issues.append(f"brain log idle for {int(age/60)} min (stuck?)")
    else:
        issues.append("brain log missing")

    if not issues:
        print(f"[OK] brain alive  ({datetime.now(timezone.utc).isoformat(timespec='seconds')})")
        return 0

    msg = "🚨 *TrendMaster brain ALERT*\n" + "\n".join(f"- {i}" for i in issues)
    print(msg)

    # Dedup on issue KINDS on issue KINDS (dead / log-idle), not exact text: the 'idle for N
    # min' counter changes every run, which used to defeat exact-match dedup
    # and re-page Telegram every 5 min during one incident.
    kinds = sorted(i.split(" ")[0] for i in issues)  # crude kind tag
    sig = ",".join(kinds)
    last = _last_alert_state()
    if time.time() - last.get("last_alert_ts", 0) < ALERT_DEDUP_S and last.get("last_sig") == sig:
        print(f"[skip telegram - same alert kinds {sig} within {ALERT_DEDUP_S}s window]")
        return 2

    if _send_tg(msg):
        _save_alert_state(sig)
        print("[telegram sent]")
        return 2
    return 3


if __name__ == "__main__":
    sys.exit(main())
