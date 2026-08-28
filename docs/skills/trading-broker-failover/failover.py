"""
Broker failover triage for TrendMaster v14.

Detects MT5 disconnect signals, classifies the right failover mode (A/B/C),
and prints the manual playbook. Never executes any P&L-affecting action.

Pure-Python; uses MetaTrader5 if available, degrades gracefully if not.
"""

from __future__ import annotations

import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(r"C:\Users\Ratanshila\Documents\autmated trading")
STATE_PATH = REPO_ROOT / "logs" / "brain_state.json"
MEMORY_PATH = REPO_ROOT / "brain_memory.json"


def check_mt5() -> dict:
    """Return {connected, last_tick_age_s, recent_retcodes}."""
    out = {"connected": None, "last_tick_age_s": None, "recent_retcodes": []}
    try:
        import MetaTrader5 as mt5  # type: ignore
        ok = mt5.initialize()
        if not ok:
            out["connected"] = False
            return out
        info = mt5.terminal_info()
        out["connected"] = bool(info.connected) if info else False
        try:
            mt5.shutdown()
        except Exception:
            pass
    except ImportError:
        out["connected"] = None
    # Fall back to brain_state for last_tick_ts
    if STATE_PATH.exists():
        try:
            st = json.loads(STATE_PATH.read_text())
            ts = st.get("last_tick_ts")
            if ts:
                last = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - last).total_seconds()
                out["last_tick_age_s"] = age
        except Exception:
            pass
    return out


def open_positions() -> list[dict]:
    if not MEMORY_PATH.exists():
        return []
    try:
        return json.loads(MEMORY_PATH.read_text()).get("open_positions", []) or []
    except Exception:
        return []


def classify_mode(mt5_status: dict, positions: list[dict], force: str | None) -> str:
    if force:
        return force
    age = mt5_status.get("last_tick_age_s") or 0
    connected = mt5_status.get("connected", True)
    if connected and age < 120:
        return "A"
    if not connected and age > 900:
        return "C"
    if not connected or age > 120:
        return "B" if positions else "A"
    return "A"


PLAYBOOK = {
    "A": [
        "1. Pause new entries via Telegram: /halt-team all",
        "2. Verify with: tools\\diagnose_zero_trades.py",
        "3. Wait for MT5 reconnect; resume via /resume-team all when stable.",
        "4. No position action needed.",
    ],
    "B": [
        "1. Pause new entries via Telegram: /halt-team all",
        "2. Verify pause: tools\\diagnose_zero_trades.py",
        "3. Open OctaFX-Demo web/mobile UI (NOT MT5 desktop) -> Trading -> Positions.",
        "4. Close every open position at market via the web UI.",
        "5. Persist new state:",
        "   .venv\\Scripts\\python.exe -c \"from ai_trading_agents.state_store import StateStore; s=StateStore(); st=s.load(); st['open_positions']=[]; st['trading_paused']=True; s.save(st)\"",
        "6. Wait for MT5 desktop reconnect (green status indicator).",
        "7. Run trading-position-reconciliation to confirm broker is flat.",
        "8. If still disconnected after 15 min, escalate to MODE C.",
    ],
    "C": [
        "1. Pause everything via Telegram: /halt-team all",
        "2. Open OctaFX-Demo web/mobile UI; close every open position at market.",
        "3. Stop the brain via start_brain_clean.cmd --stop  (NOT taskkill /F).",
        "4. File postmortem via trading-postmortem-new with slug like octafx_hard_halt_<date>.",
        "5. Do NOT restart brain until root cause is known and documented.",
    ],
}


def render(mt5_status: dict, positions: list[dict], mode: str) -> str:
    out = ["Broker Failover Triage - " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")]
    out.append("=" * 50)
    out.append("Connection status:")
    out.append(f"  MT5 connected: {mt5_status.get('connected')}")
    age = mt5_status.get("last_tick_age_s")
    out.append(f"  Last tick age: {age:.0f}s" if age else "  Last tick age: unknown")
    out.append("")
    out.append(f"Open positions ({len(positions)} per brain_memory.json - may be stale):")
    for p in positions[:10]:
        sl = f"SL {p.get('sl_px')}" if p.get("sl_px") else "no SL"
        out.append(f"  {p.get('symbol')} {p.get('side')} {p.get('lots')} lots  {sl}")
    out.append("")
    out.append(f"==> RECOMMENDED MODE: {mode}")
    out.append("")
    out.append("PLAYBOOK (execute manually in this order):")
    for line in PLAYBOOK[mode]:
        out.append("  " + line)
    out.append("")
    out.append("DO NOT:")
    out.append("  - Auto-close positions from the brain (the OrderSend path is what's failing).")
    out.append("  - Use taskkill /F on MT5 or python.exe (cascade-kill on Win11 24H2).")
    out.append("  - Restart the brain blindly while broker is partially responsive.")
    out.append("  - Lower MIN_CONF or re-enable spread_guard. Operator policy.")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["A", "B", "C"], default=None, help="Force a specific mode (drill)")
    ap.add_argument("--dry-run", action="store_true", help="Skip live MT5 check")
    args = ap.parse_args()

    if args.dry_run:
        mt5_status = {"connected": False, "last_tick_age_s": 7 * 60, "recent_retcodes": [10006, 10006, 10006]}
    else:
        mt5_status = check_mt5()

    positions = open_positions()
    mode = classify_mode(mt5_status, positions, args.mode)
    print(render(mt5_status, positions, mode))


if __name__ == "__main__":
    main()
