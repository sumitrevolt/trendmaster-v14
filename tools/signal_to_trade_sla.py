"""Signal-to-Trade SLA monitor.

[2026-05-09 GODMODE] The 5-day silent failure (local_generator dropped by
ALLOWED_STRATEGIES whitelist) cost the operator 5 days of zero trading because
nothing alerted on the gap. This module closes that gap.

Every 60s, this script reads the last 60s of `logs/python_executor.log` and
the last 60s of `logs/tv_webhook.log`, and answers ONE question:

    "Did any TV→EA OK arrive in the last 60s but no ORDER PLACED followed
     within 90s for that symbol/direction?"

If yes → fire a Telegram alert with structured details. Anti-spam: same
alert key won't fire again within 30 min.

Trip conditions ALSO covered:
  - executor not heartbeating (stale > 120s)         → Telegram
  - safeguards module reported as DISABLED in startup banner → Telegram
  - tv_webhook.log has 'REJECT no-direction' lines   → Telegram (TV chain
                                                       still architecturally
                                                       broken — ack first time
                                                       per 30 min)

Run interactively:
    .venv\\Scripts\\python.exe tools\\signal_to_trade_sla.py --once

Or as a Windows scheduled task (1-min interval, hidden VBS):
    See tools/hidden_signal_to_trade_sla.vbs (created by
    outputs/install_sla_monitor_2026-05-09.cmd).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

EXEC_LOG = LOGS / "python_executor.log"
WEBHOOK_LOG = LOGS / "tv_webhook.log"
SLA_LOG = LOGS / "signal_to_trade_sla.log"
SEEN = LOGS / "signal_to_trade_sla_seen.json"

DEDUP_WINDOW_S = 1800  # 30 min between same-key alerts
EXEC_HEARTBEAT_FRESH_S = 120  # heartbeat older than 120s is stale
SIGNAL_TO_TRADE_SLA_S = 90    # signal in webhook → trade in executor must be ≤90s

# Match webhook log: "TV→EA OK  symbol=XAUUSD dir=BUY tf=M5 conf=0.850 ..."
RE_WEBHOOK_OK = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,\.\d]*\s*\[INFO\]\s*"
    r"TV.{0,4}EA OK\s+symbol=(?P<sym>\w+)\s+dir=(?P<dir>\w+)"
)

# Match executor log: "ORDER PLACED XAUUSD BUY [QUICK] lots=0.01 ... deal=NNN"
RE_ORDER_PLACED = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,\.\d]*\s*\[INFO\]\s*"
    r"ORDER PLACED\s+(?P<sym>\w+)\s+(?P<dir>BUY|SELL)"
)

# Match executor log heartbeat
RE_HEARTBEAT = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,\.\d]*\s*\[INFO\]\s*"
    r"heartbeat:\s*iter=(?P<iter>\d+)"
)

# Match REJECT no-direction signal (TV chain still broken)
RE_REJECT_NO_DIR = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,\.\d]*\s*\[WARNING\]\s*"
    r"REJECT no-direction signal for (?P<sym>\w+)"
)

# Match startup banner safeguards-disabled error
RE_SAFEGUARDS_DISABLED = re.compile(r"\[X\] SAFEGUARDS DISABLED")


def _log(msg: str) -> None:
    """Append a line to logs/signal_to_trade_sla.log."""
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    try:
        with SLA_LOG.open("a", encoding="utf-8") as f:
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
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(ROOT / "config" / ".env")
    except Exception:
        return
    bot = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chats = [c.strip() for c in os.getenv("TELEGRAM_CHAT_ID", "").replace(";", ",").split(",") if c.strip()]
    if not bot or not chats:
        _log(f"WARN no telegram creds — would have alerted: {msg}")
        return
    try:
        url = f"https://api.telegram.org/bot{bot}/sendMessage"
        for chat in chats:
            data = json.dumps({"chat_id": chat, "text": f"[SLA] {msg}"}).encode()
            req = urllib.request.Request(url, data=data,
                                         headers={"Content-Type": "application/json"},
                                         method="POST")
            urllib.request.urlopen(req, timeout=4)
        _log(f"TELEGRAM SENT key={dedup_key}: {msg}")
    except Exception as e:
        _log(f"WARN telegram failed: {e}")


def _read_tail(path: Path, max_bytes: int = 65536) -> str:
    if not path.exists():
        return ""
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            f.seek(max(0, size - max_bytes))
            return f.read().decode("utf-8", errors="replace")
    except Exception as e:
        _log(f"WARN could not read {path.name}: {e}")
        return ""


def _parse_ts(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp()


def check_signal_to_trade_sla(now: float) -> list:
    """Returns list of (symbol, dir, lag_s) tuples for signals that arrived
    >SIGNAL_TO_TRADE_SLA_S ago without a matching ORDER PLACED."""
    cutoff = now - 600  # look back 10 minutes max
    sla_cutoff = now - SIGNAL_TO_TRADE_SLA_S

    webhook_tail = _read_tail(WEBHOOK_LOG)
    exec_tail = _read_tail(EXEC_LOG)

    # Collect (ts, sym, dir) for webhook OKs in window
    signals = []
    for m in RE_WEBHOOK_OK.finditer(webhook_tail):
        try:
            ts = _parse_ts(m.group("ts"))
            if cutoff <= ts <= sla_cutoff:
                sym = m.group("sym").upper()
                d = m.group("dir").upper()
                if d != "NONE":
                    signals.append((ts, sym, d))
        except Exception:
            continue

    # Collect (ts, sym, dir) for ORDER PLACED in window
    orders = []
    for m in RE_ORDER_PLACED.finditer(exec_tail):
        try:
            ts = _parse_ts(m.group("ts"))
            if cutoff <= ts <= now:
                orders.append((ts, m.group("sym").upper(), m.group("dir").upper()))
        except Exception:
            continue

    # For each signal, find a matching order within SIGNAL_TO_TRADE_SLA_S window
    breaches = []
    for sig_ts, sym, d in signals:
        matched = False
        for ord_ts, ord_sym, ord_dir in orders:
            if ord_sym == sym and ord_dir == d and 0 <= (ord_ts - sig_ts) <= SIGNAL_TO_TRADE_SLA_S:
                matched = True
                break
        if not matched:
            breaches.append((sym, d, int(now - sig_ts)))
    return breaches


def check_executor_heartbeat(now: float) -> bool:
    """True if executor has heartbeated within last 120s."""
    tail = _read_tail(EXEC_LOG, max_bytes=8192)
    last_ts = 0.0
    for m in RE_HEARTBEAT.finditer(tail):
        try:
            ts = _parse_ts(m.group("ts"))
            last_ts = max(last_ts, ts)
        except Exception:
            continue
    age = int(now - last_ts) if last_ts else 99999
    return age <= EXEC_HEARTBEAT_FRESH_S


def check_safeguards_active() -> bool:
    """True if executor's recent startup banner did NOT show safeguards disabled."""
    tail = _read_tail(EXEC_LOG, max_bytes=8192)
    return not RE_SAFEGUARDS_DISABLED.search(tail)


def check_tv_chain_health(now: float) -> int:
    """Returns count of REJECT no-direction signals in last 10 min.
    A non-zero count means the TV chain is delivering broken bodies."""
    cutoff = now - 600
    tail = _read_tail(WEBHOOK_LOG)
    n = 0
    for m in RE_REJECT_NO_DIR.finditer(tail):
        try:
            ts = _parse_ts(m.group("ts"))
            if ts >= cutoff:
                n += 1
        except Exception:
            continue
    return n


def main() -> int:
    now = time.time()

    # 1) signal-to-trade SLA breach
    breaches = check_signal_to_trade_sla(now)
    if breaches:
        # Group by symbol+dir so multiple TFs aren't multiple alerts
        keys = {f"{s}_{d}" for s, d, _ in breaches}
        for k in keys:
            sym, d = k.rsplit("_", 1)
            lag = max(b[2] for b in breaches if b[0] == sym and b[1] == d)
            _notify(
                f"SLA BREACH: {sym} {d} signal arrived {lag}s ago, no trade. "
                f"Check executor + safeguards.",
                dedup_key=f"sla_breach_{sym}_{d}",
            )
            _log(f"BREACH {sym} {d} lag={lag}s")

    # 2) executor heartbeat
    if not check_executor_heartbeat(now):
        _notify(
            "Executor heartbeat STALE >120s. Probably crashed. "
            "Run: outputs\\restart_executor_FIX_2026-05-09.cmd",
            dedup_key="exec_heartbeat_stale",
        )
        _log("WARN executor heartbeat stale")

    # 3) safeguards loaded
    if not check_safeguards_active():
        _notify(
            "CRITICAL: SAFEGUARDS DISABLED in executor (concentration caps + DD + news + spread). "
            "Trading without safety net. Check executor startup log immediately.",
            dedup_key="safeguards_disabled",
        )
        _log("CRITICAL safeguards disabled")

    # 4) TV chain — info-level, alerts only on first sighting per 30 min
    n_no_dir = check_tv_chain_health(now)
    if n_no_dir >= 5:
        _notify(
            f"TV chain still broken: {n_no_dir} 'REJECT no-direction' in last 10 min. "
            f"Rocket Prime alert() override. local_generator covers trading; "
            f"deferred fix per memory entry.",
            dedup_key="tv_chain_broken",
        )

    if not breaches and check_executor_heartbeat(now) and check_safeguards_active():
        _log(f"OK breaches=0 hb=fresh safeguards=on tv_no_dir={n_no_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
