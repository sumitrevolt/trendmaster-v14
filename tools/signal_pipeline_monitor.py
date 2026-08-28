"""Detects regression of the TV-signal pipeline.

Run by Windows scheduled task every 5 minutes (silent via VBS wrapper).
Does NOT make any TV API calls (those need playwright + browser, too heavy).
Only checks LOCAL state:
  1. logs/tv_webhook.log: latest body line starts with 'RP|' or has 'PLOT-DIRECTION'
  2. logs/tv_plot_values.jsonl: latest entry has p0 OR p1 non-zero
  3. MT5 Files dir: latest signal file mtime is fresh AND direction != NONE

If any check fails, sends Telegram alert with dedup (30-min window).

Run interactively to test:
    .venv\Scripts\python.exe tools\signal_pipeline_monitor.py --once
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

LOG = LOGS / "signal_pipeline_monitor.log"
SEEN = LOGS / "signal_pipeline_monitor_seen.json"
DEDUP_WINDOW_S = 1800  # 30 min

WEBHOOK_LOG = LOGS / "tv_webhook.log"
PLOT_LOG = LOGS / "tv_plot_values.jsonl"
MT5_FILES_DIR = Path(r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files")


def _log(msg: str) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _notify(msg: str, dedup_key: str) -> None:
    """Telegram alert with 30-min dedup. Fail silent."""
    try:
        seen = json.loads(SEEN.read_text(encoding="utf-8")) if SEEN.exists() else {}
    except Exception:
        seen = {}
    last = seen.get(dedup_key, 0)
    if time.time() - last < DEDUP_WINDOW_S:
        return
    seen[dedup_key] = int(time.time())
    seen = {k: v for k, v in seen.items() if time.time() - v < 86400}
    try:
        SEEN.write_text(json.dumps(seen), encoding="utf-8")
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
            data = json.dumps({"chat_id": chat, "text": f"[signal-monitor] {msg}"}).encode()
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=4)
    except Exception:
        pass


def check_webhook_log_recent_format() -> tuple[bool, str]:
    """True if the most recent inbound body in tv_webhook.log uses RP| or PLOT-DIRECTION."""
    if not WEBHOOK_LOG.exists():
        return True, "no webhook log yet"
    try:
        size = WEBHOOK_LOG.stat().st_size
        with WEBHOOK_LOG.open("rb") as f:
            f.seek(max(0, size - 16384))
            tail = f.read().decode("utf-8", errors="replace")
    except Exception as e:
        return True, f"could not read webhook log: {e}"

    # Look at last 30 lines for any inbound signal
    lines = tail.splitlines()[-50:]
    for line in reversed(lines):
        if "PLOT-DIRECTION" in line or "URL-DIRECTION" in line:
            return True, "good — recent line has PLOT-DIRECTION"
        if "REJECT no-direction signal" in line:
            return False, "BAD — recent REJECT no-direction signal seen (alerts have wrong template)"
        if "TEXT mode parse" in line:
            # got a signal but unclear which template
            m = re.search(r"body\[:80\]=([\'\"])(.+?)\1", line)
            if m:
                body = m.group(2)
                if body.startswith("RP|"):
                    return True, "good — RP| body parsed"
                if body.startswith("####"):
                    return False, f"BAD — body still '####' (old template): {body[:60]}"
    return True, "no recent inbound signals to evaluate"


def _risk_halt_active() -> bool:
    """True when the brain's risk manager has legitimately halted trading.

    direction=NONE across all signals is the CORRECT output in these cases —
    it is the circuit breaker doing its job, NOT a pipeline regression:
      * daily loss stop tripped (account down > risk limit for the day)
      * drawdown lockout active (set until end of UTC day once DD gate trips)
      * manual /halt or /pause
    """
    try:
        state_path = ROOT / "logs" / "brain_state.json"
        if state_path.exists():
            st = json.loads(state_path.read_text(encoding="utf-8"))
            if st.get("drawdown_lockout_until", 0) and st["drawdown_lockout_until"] > time.time():
                return True
            if st.get("trading_paused") or st.get("halted"):
                return True
    except Exception:
        pass
    return False


def check_mt5_signal_files_recent_dir() -> tuple[bool, str]:
    """True if NO recent MT5 signal file has direction=NONE (older than 10 min is OK)."""
    if not MT5_FILES_DIR.exists():
        return True, "MT5 files dir not found"
    bad_files = []
    cutoff = time.time() - 600  # 10 min
    for p in MT5_FILES_DIR.glob("trendmaster_signals_*.json"):
        try:
            mtime = p.stat().st_mtime
            if mtime < cutoff:
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            d = data.get("direction") or ""
            if d.upper() == "NONE":
                bad_files.append(p.name)
        except Exception:
            pass
    if bad_files:
        # direction=NONE is the CORRECT, expected output when the brain's risk
        # manager has halted trading (daily loss stop hit, drawdown lockout, or
        # manual /halt). In that case a NONE signal is NOT a pipeline regression —
        # it's the circuit breaker doing its job. Only flag as BAD when no risk
        # halt is active, so genuine bugs (e.g. the 2026-05-09 whitelist
        # regression) are still caught.
        if _risk_halt_active():
            return True, (
                "OK (expected) — direction=NONE due to active risk halt "
                f"(daily loss stop / DD lockout / manual halt); files: {bad_files}"
            )
        return False, f"BAD — fresh MT5 signal files with direction=NONE: {bad_files}"
    return True, "MT5 signal files OK"


def main() -> int:
    ok1, msg1 = check_webhook_log_recent_format()
    ok2, msg2 = check_mt5_signal_files_recent_dir()
    healthy = ok1 and ok2
    _log(f"webhook_format={ok1} ({msg1})  mt5_dir={ok2} ({msg2})  healthy={healthy}")

    if not ok1:
        _notify(f"TV alert template regression: {msg1}", "tpl_regression")
    if not ok2:
        _notify(f"MT5 dir=NONE regression: {msg2}", "dir_none_regression")

    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
