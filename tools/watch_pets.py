"""
watch_pets.py - unified watchdog orchestrator for TrendMaster v14.

Runs every 5 min via Scheduled Task "TrendMaster Watch-Pets". Reads
all existing watch-skill outputs (brain liveness, junction guard,
alert bridge, drift alerts, zero-trades watchdog) and adds quick
fresh checks (disk free, logs size, gateway health). Aggregates into
one state file + JSONL log. Critical alerts also written to a
Telegram-independent channel (file + optional Windows Toast).

Why: existing watchers each post to Telegram via alert-bridge, which
is currently disabled. Without this aggregator, alerts fire silently.

Side effects: read-only by default. Self-heal disabled by default;
enable via --autoheal flag.

Exit codes (used by Scheduled Task to surface critical):
  0 - all OK or only WARN
  1 - one or more ERROR/CRITICAL detected
  2 - watchpets itself errored (unhandled exception)

Usage:
  .venv\\Scripts\\python.exe tools\\watch_pets.py
  .venv\\Scripts\\python.exe tools\\watch_pets.py --json
  .venv\\Scripts\\python.exe tools\\watch_pets.py --autoheal
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS = PROJECT_ROOT / "logs"
LOGS.mkdir(exist_ok=True)

STATE_FILE = LOGS / "watchpets_state.json"
LOG_JSONL = LOGS / "watchpets.jsonl"
ALERTS_JSONL = LOGS / "watchpets_alerts.jsonl"
LAST_AUTOHEAL = LOGS / "watchpets_last_autoheal.txt"
LAST_POSTMORTEM = LOGS / "watchpets_last_postmortem.txt"
LAST_TOAST = LOGS / "watchpets_last_toast.txt"
POSTMORTEM_DIR = PROJECT_ROOT / "docs" / "POSTMORTEMS"
POSTMORTEM_COOLDOWN_S = 3600  # don't draft another within 1h
TOAST_COOLDOWN_S = 600        # don't toast/speak more than once per 10 min

# -- thresholds (tunable) ----------------------------------------------------
DISK_FREE_GB_WARN = 10
DISK_FREE_GB_CRIT = 3
LOGS_SIZE_GB_WARN = 5
LOGS_SIZE_GB_CRIT = 20
EVENTS_JSONL_MB_WARN = 200
BRAIN_LIVENESS_AGE_S_WARN = 360   # >6 min without update
BRAIN_LIVENESS_AGE_S_CRIT = 900   # >15 min without update
GATEWAY_HEALTHZ_TIMEOUT_S = 5
SIGNAL_FRESH_S_WARN = 120         # last_signal older than 2min during market hours
SIGNAL_FRESH_S_CRIT = 600
TRADE_AGE_DAYS_WARN = 7
TRADE_AGE_DAYS_CRIT = 21
AUTOHEAL_COOLDOWN_S = 600         # don't try again within 10 min

# -- severity ----------------------------------------------------------------
OK, INFO, WARN, ERROR, CRITICAL = "OK", "INFO", "WARN", "ERROR", "CRITICAL"
SEVERITY_RANK = {OK: 0, INFO: 1, WARN: 2, ERROR: 3, CRITICAL: 4}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _safe_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _file_age_s(p: Path) -> float | None:
    try:
        return time.time() - p.stat().st_mtime
    except Exception:
        return None


def _tail(p: Path, n: int) -> list[str]:
    try:
        with p.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = min(size, 8192 * n)
            f.seek(size - block)
            data = f.read().decode("utf-8", errors="replace")
        return [ln for ln in data.splitlines() if ln.strip()][-n:]
    except Exception:
        return []


# ---------- individual checks ----------------------------------------------

def check_brain() -> dict:
    """Read brain.pid + brain_liveness.log; return verdict."""
    pid_file = LOGS / "brain.pid"
    pid = None
    alive = None
    if pid_file.exists():
        txt = pid_file.read_text(errors="ignore").strip()
        for line in txt.splitlines():
            if line.strip().isdigit():
                pid = int(line.strip())
                break
        if pid is not None:
            try:
                import psutil  # type: ignore
                alive = psutil.pid_exists(pid)
            except Exception:
                alive = None

    liveness_log = LOGS / "brain_liveness.log"
    liveness_age = _file_age_s(liveness_log)
    last_verdict = None
    if liveness_log.exists():
        for line in reversed(_tail(liveness_log, 30)):
            if line.startswith("VERDICT:"):
                last_verdict = line.split(":", 1)[1].strip()
                break

    severity = OK
    msg = "brain alive"
    if alive is False:
        severity = CRITICAL
        msg = f"brain pid {pid} NOT alive"
    elif last_verdict == "DEAD":
        severity = CRITICAL
        msg = "liveness verdict: DEAD"
    elif liveness_age is not None and liveness_age > BRAIN_LIVENESS_AGE_S_CRIT:
        severity = ERROR
        msg = f"liveness check stale: {int(liveness_age)}s"
    elif liveness_age is not None and liveness_age > BRAIN_LIVENESS_AGE_S_WARN:
        severity = WARN
        msg = f"liveness check stale: {int(liveness_age)}s"
    elif alive is None and pid is None:
        severity = WARN
        msg = "brain.pid missing or unreadable"

    return {
        "name": "brain",
        "severity": severity,
        "message": msg,
        "details": {"pid": pid, "alive": alive, "last_verdict": last_verdict, "liveness_log_age_s": int(liveness_age) if liveness_age else None},
    }


def check_drawdown() -> dict:
    """Compare session DD to daily limit from settings."""
    state = _safe_json(LOGS / "brain_state.json") or {}
    paused = state.get("trading_paused")
    sod_eq = state.get("start_of_day_equity")
    peak_eq = state.get("daily_drawdown_peak_eq")
    sess_low = state.get("session_low_equity")
    halt_until = state.get("drawdown_lockout_until")

    daily_limit_pct = 3.0  # default; matches config/settings.py daily_max_loss_pct
    try:
        env_override = os.environ.get("MAX_DAILY_DRAWDOWN")
        if env_override:
            daily_limit_pct = float(env_override)
    except Exception:
        pass

    dd_pct = None
    if (
        isinstance(peak_eq, (int, float))
        and isinstance(sess_low, (int, float))
        and peak_eq > 0
        and sess_low > 0
    ):
        dd_pct = (peak_eq - sess_low) / peak_eq * 100

    severity = OK
    msg = "DD within limit"
    if dd_pct is None:
        severity = INFO
        msg = "DD not measurable (session uninitialized)"
    elif dd_pct >= daily_limit_pct and not paused and not halt_until:
        # the textbook account-blowup case: limit hit, lockout NOT set
        severity = CRITICAL
        msg = f"DD {dd_pct:.2f}% >= limit {daily_limit_pct}% but lockout NOT set"
    elif dd_pct >= daily_limit_pct:
        severity = WARN
        msg = f"DD {dd_pct:.2f}% >= limit {daily_limit_pct}% (lockout set, expected)"
    elif dd_pct >= daily_limit_pct * 0.8:
        severity = WARN
        msg = f"DD {dd_pct:.2f}% nearing limit {daily_limit_pct}%"

    return {
        "name": "drawdown",
        "severity": severity,
        "message": msg,
        "details": {"sod_equity": sod_eq, "peak_eq": peak_eq, "session_low": sess_low, "dd_pct": round(dd_pct, 2) if dd_pct else None, "limit_pct": daily_limit_pct, "paused": paused, "halt_until": halt_until},
    }


def check_junction() -> dict:
    """Verify ai_trading_agents/ junction resolves to canonical."""
    junction = PROJECT_ROOT / "ai_trading_agents"
    canonical = Path(r"C:\TrendMaster_aita_canonical")
    canonical_brain = canonical / "trend_master_brain.py"

    severity = OK
    msg = "junction OK"
    details: dict = {}
    try:
        if not junction.exists():
            severity = CRITICAL
            msg = "ai_trading_agents/ missing entirely"
        elif not canonical.exists():
            severity = CRITICAL
            msg = "C:\\TrendMaster_aita_canonical\\ missing (junction target lost)"
        elif not canonical_brain.exists():
            severity = ERROR
            msg = "canonical trend_master_brain.py missing"
        else:
            # try resolve check (may follow junction)
            try:
                resolved = os.path.realpath(str(junction))
                details["resolved"] = resolved
                if "TrendMaster_aita_canonical" not in resolved:
                    severity = ERROR
                    msg = f"junction resolves to unexpected path: {resolved}"
            except Exception as e:
                details["resolve_error"] = str(e)
    except Exception as e:
        severity = ERROR
        msg = f"junction check exception: {e}"

    return {"name": "junction", "severity": severity, "message": msg, "details": details}


def check_disk() -> dict:
    """Free disk space + logs/ size."""
    try:
        total, used, free = shutil.disk_usage(str(PROJECT_ROOT))
        free_gb = free / (1024 ** 3)
    except Exception as e:
        return {"name": "disk", "severity": WARN, "message": f"disk_usage failed: {e}", "details": {}}

    logs_bytes = 0
    try:
        for p in LOGS.rglob("*"):
            if p.is_file():
                try:
                    logs_bytes += p.stat().st_size
                except Exception:
                    pass
    except Exception:
        pass
    logs_gb = logs_bytes / (1024 ** 3)

    events_jsonl = LOGS / "events.jsonl"
    events_mb = 0
    if events_jsonl.exists():
        events_mb = events_jsonl.stat().st_size / (1024 ** 2)

    severity = OK
    msg = f"disk free {free_gb:.1f} GB, logs {logs_gb:.2f} GB"
    if free_gb < DISK_FREE_GB_CRIT:
        severity = CRITICAL
        msg = f"disk free CRITICALLY LOW: {free_gb:.1f} GB"
    elif free_gb < DISK_FREE_GB_WARN:
        severity = WARN
        msg = f"disk free low: {free_gb:.1f} GB"
    elif logs_gb >= LOGS_SIZE_GB_CRIT:
        severity = ERROR
        msg = f"logs/ very large: {logs_gb:.1f} GB - rotate"
    elif logs_gb >= LOGS_SIZE_GB_WARN:
        severity = WARN
        msg = f"logs/ growing: {logs_gb:.1f} GB"
    elif events_mb >= EVENTS_JSONL_MB_WARN:
        severity = WARN
        msg = f"events.jsonl {events_mb:.0f} MB - rotator should run"

    return {
        "name": "disk",
        "severity": severity,
        "message": msg,
        "details": {"free_gb": round(free_gb, 2), "logs_gb": round(logs_gb, 2), "events_jsonl_mb": round(events_mb, 1)},
    }


def check_gateway() -> dict:
    """Probe OpenClaw gateway healthz."""
    import urllib.request

    severity = OK
    msg = "gateway healthy"
    details: dict = {}
    try:
        with urllib.request.urlopen("http://127.0.0.1:18789/healthz", timeout=GATEWAY_HEALTHZ_TIMEOUT_S) as r:
            body = r.read().decode("utf-8", errors="replace")
            details["status"] = r.status
            details["body"] = body[:200]
            if r.status != 200 or '"ok"' not in body or 'true' not in body:
                severity = WARN
                msg = f"gateway responded but body unexpected: {body[:100]}"
    except (TimeoutError, socket.timeout):
        severity = WARN
        msg = "gateway healthz timeout (gateway alive but slow)"
    except Exception as e:
        # gateway down is WARN not CRITICAL — gateway is for AI agent, not trading exec
        severity = WARN
        msg = f"gateway unreachable: {e.__class__.__name__}"

    return {"name": "gateway", "severity": severity, "message": msg, "details": details}


def check_signals_age() -> dict:
    """Latest signal timestamp across symbols; flag if stale during market hours."""
    state = _safe_json(LOGS / "brain_state.json") or {}
    lsps = state.get("last_signal_per_symbol") or {}
    if not isinstance(lsps, dict) or not lsps:
        return {"name": "signals", "severity": INFO, "message": "no signal state", "details": {}}

    latest_ts = 0
    for sym, payload in lsps.items():
        if isinstance(payload, dict):
            ts = payload.get("ts") or payload.get("timestamp") or 0
            try:
                ts = int(ts)
            except Exception:
                continue
            if ts > latest_ts:
                latest_ts = ts

    if latest_ts == 0:
        return {"name": "signals", "severity": INFO, "message": "no parseable signal timestamps", "details": {}}

    age_s = time.time() - latest_ts
    severity = OK
    msg = f"latest signal {int(age_s)}s old"
    if age_s > SIGNAL_FRESH_S_CRIT:
        severity = ERROR
        msg = f"latest signal {int(age_s/60)}min old (brain may be stuck)"
    elif age_s > SIGNAL_FRESH_S_WARN:
        severity = WARN
        msg = f"latest signal {int(age_s/60)}min old"

    return {"name": "signals", "severity": severity, "message": msg, "details": {"latest_ts": latest_ts, "age_s": int(age_s)}}


def check_recent_trades() -> dict:
    """Days since last trade (zero-trades watchdog complement)."""
    state = _safe_json(LOGS / "brain_state.json") or {}
    rr = state.get("recent_results") or []
    if not isinstance(rr, list) or not rr:
        return {"name": "trades", "severity": INFO, "message": "no recent_results entries", "details": {}}

    last_ts = 0
    for entry in rr:
        if isinstance(entry, dict):
            ts = entry.get("ts") or 0
            try:
                ts = int(ts)
            except Exception:
                continue
            if ts > last_ts:
                last_ts = ts

    if last_ts == 0:
        return {"name": "trades", "severity": INFO, "message": "no parseable trade timestamps", "details": {}}

    age_days = (time.time() - last_ts) / 86400
    severity = OK
    msg = f"last trade {age_days:.1f} days ago"
    if age_days > TRADE_AGE_DAYS_CRIT:
        severity = ERROR
        msg = f"no trades in {int(age_days)} days (zero-trades regression?)"
    elif age_days > TRADE_AGE_DAYS_WARN:
        severity = WARN
        msg = f"last trade {age_days:.1f} days ago"

    return {"name": "trades", "severity": severity, "message": msg, "details": {"last_ts": last_ts, "age_days": round(age_days, 1)}}


def check_alert_files() -> dict:
    """Surface any *.alert files or recent drift entries."""
    alert_files = [
        "pytest_health.alert",
        "zero_trades.alert",
        "brain.crash",
        "schtasks_audit.alert",
    ]
    active_alerts: list[str] = []
    for name in alert_files:
        f = LOGS / name
        if f.exists() and f.stat().st_size > 0:
            active_alerts.append(name)

    drift_log = LOGS / "drift_alerts.jsonl"
    drift_recent = 0
    if drift_log.exists():
        try:
            for line in _tail(drift_log, 50):
                try:
                    obj = json.loads(line)
                    ts = obj.get("ts") or obj.get("timestamp") or 0
                    if isinstance(ts, str):
                        try:
                            ts = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
                        except Exception:
                            continue
                    if ts and time.time() - int(ts) < 86400:
                        drift_recent += 1
                except Exception:
                    pass
        except Exception:
            pass

    severity = OK
    msg = "no active alerts"
    if active_alerts:
        severity = ERROR
        msg = f"active alert files: {', '.join(active_alerts)}"
    elif drift_recent > 0:
        severity = WARN
        msg = f"{drift_recent} drift alerts in last 24h"

    return {"name": "alerts", "severity": severity, "message": msg, "details": {"active_files": active_alerts, "drift_24h": drift_recent}}


# ---------- aggregator ------------------------------------------------------

def aggregate(checks: list[dict]) -> dict:
    overall = OK
    for c in checks:
        if SEVERITY_RANK[c["severity"]] > SEVERITY_RANK[overall]:
            overall = c["severity"]
    return {
        "ts": _now_iso(),
        "overall": overall,
        "checks": checks,
    }


def maybe_autoheal(checks: list[dict]) -> list[str]:
    """Take low-risk auto-heal actions. Cooldown via timestamp file."""
    actions: list[str] = []
    last = 0.0
    if LAST_AUTOHEAL.exists():
        try:
            last = float(LAST_AUTOHEAL.read_text().strip())
        except Exception:
            pass
    if time.time() - last < AUTOHEAL_COOLDOWN_S:
        return ["cooldown active, no autoheal"]

    by_name = {c["name"]: c for c in checks}

    # Heal 1: brain DEAD + market hours -> launch start_brain_clean.cmd
    brain = by_name.get("brain", {})
    if brain.get("severity") == CRITICAL and "DEAD" in brain.get("message", "").upper():
        # Conservative: only heal if local time is 06:00-23:59 (covers London/NY/Asia FX hours)
        hour = datetime.now().hour
        if 6 <= hour <= 23:
            start_script = PROJECT_ROOT / "start_brain_clean.cmd"
            if start_script.exists():
                # fire-and-forget so this script returns fast
                import subprocess
                try:
                    subprocess.Popen(
                        ["cmd", "/c", str(start_script)],
                        cwd=str(PROJECT_ROOT),
                        creationflags=0x00000008 if os.name == "nt" else 0,  # DETACHED_PROCESS
                    )
                    actions.append("autoheal: launched start_brain_clean.cmd")
                    LAST_AUTOHEAL.write_text(str(time.time()))
                except Exception as e:
                    actions.append(f"autoheal failed (start_brain_clean): {e}")
            else:
                actions.append("autoheal skipped: start_brain_clean.cmd not found")
        else:
            actions.append("autoheal skipped: outside market-hours window")

    # Heal 2: junction missing but canonical exists -> defer to operator (junction
    # rebuild needs mklink /J which is also non-admin but must be deliberate)
    j = by_name.get("junction", {})
    if j.get("severity") == CRITICAL and "ai_trading_agents/ missing" in j.get("message", ""):
        canonical = Path(r"C:\TrendMaster_aita_canonical")
        if canonical.exists():
            actions.append("autoheal recommendation: run tools\\restore_junction.cmd manually")
        else:
            actions.append("autoheal blocked: canonical source missing too, operator required")

    return actions


# ---------- postmortem auto-draft ------------------------------------------

def maybe_draft_postmortem(state: dict, autoheal_actions: list[str]) -> str | None:
    """Write a draft postmortem stub on CRITICAL, with cooldown.

    Returns the draft path if written, else None. Operator opens the
    draft, fills root-cause + remediation, renames to canonical
    YYYY-MM-DD_<slug>.md, and adds line to INDEX.md.
    """
    if state.get("overall") != CRITICAL:
        return None
    last = 0.0
    if LAST_POSTMORTEM.exists():
        try:
            last = float(LAST_POSTMORTEM.read_text().strip())
        except Exception:
            pass
    if time.time() - last < POSTMORTEM_COOLDOWN_S:
        return None  # still in cooldown
    try:
        POSTMORTEM_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None

    now = datetime.now(tz=timezone.utc).astimezone()
    stamp = now.strftime("%Y-%m-%d_%H%M")
    out_path = POSTMORTEM_DIR / f"_draft_{stamp}.md"

    # collect supporting evidence
    brain_err_tail = _tail(LOGS / "trend_master_brain.err", 30)
    brain_out_tail = _tail(LOGS / "trend_master_brain.log", 20) if (LOGS / "trend_master_brain.log").exists() else []
    state_json = json.dumps(state, indent=2, default=str)

    criticals = [c for c in state.get("checks", []) if c.get("severity") in (ERROR, CRITICAL)]

    lines: list[str] = []
    lines.append(f"# DRAFT postmortem - {now.strftime('%Y-%m-%d %H:%M %Z')}")
    lines.append("")
    lines.append("> **Auto-generated by `tools/watch_pets.py` on CRITICAL severity.**")
    lines.append(">")
    lines.append("> Operator: review, fill in **Root cause** and **Remediation**,")
    lines.append("> rename to `YYYY-MM-DD_<slug>.md`, add a row to `INDEX.md`.")
    lines.append("")
    lines.append("## Trigger")
    lines.append("")
    for c in criticals:
        lines.append(f"- **{c['name']}** ({c['severity']}): {c['message']}")
    lines.append("")
    lines.append("## Watchpet state at time of trigger")
    lines.append("```json")
    lines.append(state_json)
    lines.append("```")
    lines.append("")
    lines.append("## brain.err (last 30 lines)")
    lines.append("```")
    if brain_err_tail:
        lines.extend(brain_err_tail)
    else:
        lines.append("(no error output)")
    lines.append("```")
    lines.append("")
    if brain_out_tail:
        lines.append("## brain.log (last 20 lines)")
        lines.append("```")
        lines.extend(brain_out_tail)
        lines.append("```")
        lines.append("")
    lines.append("## Autoheal actions taken")
    lines.append("")
    if autoheal_actions:
        for a in autoheal_actions:
            lines.append(f"- {a}")
    else:
        lines.append("- none (autoheal disabled or none applicable)")
    lines.append("")
    lines.append("## Recommended next-step commands")
    lines.append("")
    lines.append("```cmd")
    lines.append("REM Quick state check:")
    lines.append("type logs\\watchpets_state.json")
    lines.append("")
    lines.append("REM Deep diagnostic:")
    lines.append(".venv\\Scripts\\python.exe tools\\diagnose_zero_trades.py")
    lines.append("")
    lines.append("REM If brain dead and you are sure you want it back:")
    lines.append("start_brain_clean.cmd")
    lines.append("")
    lines.append("REM Tail errors:")
    lines.append("powershell -Command \"Get-Content logs\\trend_master_brain.err -Tail 50\"")
    lines.append("```")
    lines.append("")
    lines.append("## Root cause")
    lines.append("")
    lines.append("_TODO operator: fill in._")
    lines.append("")
    lines.append("## Timeline")
    lines.append("")
    lines.append("_TODO operator: fill in._")
    lines.append("")
    lines.append("## Remediation")
    lines.append("")
    lines.append("_TODO operator: fill in._")
    lines.append("")
    lines.append("## Prevention")
    lines.append("")
    lines.append("_TODO operator: list invariants/checks added to prevent recurrence._")
    lines.append("")

    try:
        out_path.write_text("\n".join(lines), encoding="utf-8")
        LAST_POSTMORTEM.write_text(str(time.time()))
        return str(out_path)
    except Exception:
        return None


# ---------- attention-grabbing alert sinks --------------------------------

def maybe_windows_toast(state: dict) -> str | None:
    """Show Windows toast notification + speak via SAPI on CRITICAL.

    Cooldown: TOAST_COOLDOWN_S (10 min). Telegram-independent.
    Returns the action label if fired, else None.
    """
    if state.get("overall") not in (ERROR, CRITICAL):
        return None
    last = 0.0
    if LAST_TOAST.exists():
        try:
            last = float(LAST_TOAST.read_text().strip())
        except Exception:
            pass
    if time.time() - last < TOAST_COOLDOWN_S:
        return None

    criticals = [
        c for c in state.get("checks", [])
        if c.get("severity") in (ERROR, CRITICAL)
    ]
    if not criticals:
        return None
    headline = criticals[0]["message"][:120]
    summary = f"TrendMaster: {headline}"

    # Build a tiny PowerShell one-liner that:
    #  1. Sends Windows Toast notification (BurntToast OR fallback)
    #  2. Speaks via System.Speech (SAPI), low volume not to annoy
    ps_cmd = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Volume = 70; $s.Rate = 0; "
        f"$s.Speak('{headline.replace(chr(39), chr(39)+chr(39))}'); "
        # Toast via Windows Runtime API — works on Win10+ without BurntToast
        "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null; "
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; "
        f"$xml.LoadXml('<toast><visual><binding template=\"ToastText02\"><text id=\"1\">TrendMaster CRITICAL</text><text id=\"2\">{html_escape_for_xml(headline)}</text></binding></visual></toast>'); "
        "$toast = New-Object Windows.UI.Notifications.ToastNotification $xml; "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('TrendMaster').Show($toast)"
    )
    try:
        import subprocess
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            creationflags=0x00000008 if os.name == "nt" else 0,  # DETACHED_PROCESS
        )
        LAST_TOAST.write_text(str(time.time()))
        return f"toast+TTS: {summary}"
    except Exception as e:
        return f"toast/TTS failed: {e}"


def html_escape_for_xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("'", "&apos;")
        .replace('"', "&quot;")
    )


# ---------- alert sinks ----------------------------------------------------

def emit_alerts(state: dict, autoheal_actions: list[str]) -> None:
    line = json.dumps(state, default=str)
    try:
        with LOG_JSONL.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

    if SEVERITY_RANK[state["overall"]] >= SEVERITY_RANK[ERROR]:
        try:
            payload = {
                "ts": state["ts"],
                "overall": state["overall"],
                "criticals": [c for c in state["checks"] if c["severity"] in (ERROR, CRITICAL)],
                "autoheal": autoheal_actions,
            }
            with ALERTS_JSONL.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, default=str) + "\n")
        except Exception:
            pass

    try:
        STATE_FILE.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


# ---------- main -----------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit JSON state to stdout")
    parser.add_argument("--quiet", action="store_true", help="silent unless ERROR/CRITICAL")
    parser.add_argument("--autoheal", action="store_true", help="enable safe auto-heal actions")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        checks = [
            check_brain(),
            check_drawdown(),
            check_junction(),
            check_disk(),
            check_gateway(),
            check_signals_age(),
            check_recent_trades(),
            check_alert_files(),
        ]
    except Exception as e:
        print(f"watch_pets fatal: {e}\n{traceback.format_exc()}", file=sys.stderr)
        return 2

    state = aggregate(checks)
    autoheal_actions: list[str] = []
    if args.autoheal:
        try:
            autoheal_actions = maybe_autoheal(checks)
        except Exception as e:
            autoheal_actions = [f"autoheal exception: {e}"]
    state["autoheal"] = autoheal_actions

    # Auto-draft postmortem on CRITICAL (cooldown internal)
    draft_path = None
    try:
        draft_path = maybe_draft_postmortem(state, autoheal_actions)
        if draft_path:
            state["postmortem_draft"] = draft_path
    except Exception as e:
        state["postmortem_draft_error"] = str(e)

    # Windows Toast + TTS voice alert on CRITICAL/ERROR (cooldown 10 min)
    toast_action = None
    try:
        toast_action = maybe_windows_toast(state)
        if toast_action:
            state["toast"] = toast_action
    except Exception as e:
        state["toast_error"] = str(e)

    emit_alerts(state, autoheal_actions)

    if args.json:
        print(json.dumps(state, indent=2, default=str))
    elif not args.quiet or SEVERITY_RANK[state["overall"]] >= SEVERITY_RANK[ERROR]:
        print(f"[{state['ts']}] overall={state['overall']}")
        for c in checks:
            mark = {OK: "  ", INFO: "  ", WARN: "! ", ERROR: "X ", CRITICAL: "XX"}[c["severity"]]
            print(f"  {mark}{c['name']:<10} {c['severity']:<8} {c['message']}")
        if autoheal_actions:
            print("autoheal:")
            for a in autoheal_actions:
                print(f"  {a}")
        if draft_path:
            print(f"postmortem draft: {draft_path}")
        if toast_action:
            print(f"alert: {toast_action}")

    return 1 if SEVERITY_RANK[state["overall"]] >= SEVERITY_RANK[ERROR] else 0


if __name__ == "__main__":
    raise SystemExit(main())
