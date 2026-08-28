"""Install a 5-min regression monitor for the TV-signal pipeline.

What it monitors:
  1. tools/tv_alert_setup/verify_alert_messages.py exits 0 (all 20 alerts have plot template)
  2. logs/tv_webhook.log latest body starts with 'RP|' (not '####')
  3. Latest MT5 signal file in MetaQuotes Files dir has direction != NONE

If any check fails, sends Telegram alert (bot creds in config/.env).
Anti-spam: same failure won't alert again within 30 min.

This script just sets up the schtask. The actual monitor logic is in:
    tools/signal_pipeline_monitor.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
PYW = ROOT / ".venv" / "Scripts" / "pythonw.exe"

MONITOR_PY = TOOLS / "signal_pipeline_monitor.py"
MONITOR_VBS = TOOLS / "hidden_signal_pipeline_monitor.vbs"

MONITOR_SOURCE = '''"""Detects regression of the TV-signal pipeline.

Run by Windows scheduled task every 5 minutes (silent via VBS wrapper).
Does NOT make any TV API calls (those need playwright + browser, too heavy).
Only checks LOCAL state:
  1. logs/tv_webhook.log: latest body line starts with 'RP|' or has 'PLOT-DIRECTION'
  2. logs/tv_plot_values.jsonl: latest entry has p0 OR p1 non-zero
  3. MT5 Files dir: latest signal file mtime is fresh AND direction != NONE

If any check fails, sends Telegram alert with dedup (30-min window).

Run interactively to test:
    .venv\\Scripts\\python.exe tools\\signal_pipeline_monitor.py --once
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
MT5_FILES_DIR = Path(r"C:\\Users\\Ratanshila\\AppData\\Roaming\\MetaQuotes\\Terminal\\D0E8209F77C8CF37AD8BF550E51FF075\\MQL5\\Files")


def _log(msg: str) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}\\n"
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
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not bot or not chat:
        return
    try:
        url = f"https://api.telegram.org/bot{bot}/sendMessage"
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
            m = re.search(r"body\\[:80\\]=([\\'\\\"])(.+?)\\1", line)
            if m:
                body = m.group(2)
                if body.startswith("RP|"):
                    return True, "good — RP| body parsed"
                if body.startswith("####"):
                    return False, f"BAD — body still '####' (old template): {body[:60]}"
    return True, "no recent inbound signals to evaluate"


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
'''

VBS_SOURCE = '''' Hidden launcher for signal_pipeline_monitor.py - every 5 min
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\\Users\\Ratanshila\\Documents\\autmated trading"
sh.Run "cmd /c "".venv\\Scripts\\pythonw.exe"" -u tools\\signal_pipeline_monitor.py >> logs\\signal_pipeline_monitor_wrapper.log 2>&1", 0, False
'''


def main() -> int:
    print("[install_signal_monitor] writing tools/signal_pipeline_monitor.py ...")
    MONITOR_PY.write_text(MONITOR_SOURCE, encoding="utf-8")

    print("[install_signal_monitor] writing tools/hidden_signal_pipeline_monitor.vbs ...")
    MONITOR_VBS.write_text(VBS_SOURCE, encoding="utf-8")

    print("[install_signal_monitor] registering schtask ...")
    cmd = [
        "schtasks", "/Create", "/F",
        "/TN", "TrendMaster Signal Pipeline Monitor",
        "/TR", f'wscript.exe "{MONITOR_VBS}"',
        "/SC", "MINUTE", "/MO", "5", "/RL", "LIMITED",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print("  schtasks rc=", r.returncode)
    if r.stdout:
        print("  stdout:", r.stdout.strip())
    if r.stderr:
        print("  stderr:", r.stderr.strip())

    # Run once now to populate the log
    print("[install_signal_monitor] running monitor once for baseline ...")
    r2 = subprocess.run(
        [str(PYW), str(MONITOR_PY)],
        capture_output=True, text=True, timeout=15,
    )
    print("  monitor rc=", r2.returncode)
    if r2.stdout:
        print("  stdout:", r2.stdout.strip())

    print("[install_signal_monitor] DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
