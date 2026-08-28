"""
why_no_trades.py - end-to-end check on why trades aren't firing.

Walks the funnel: brain alive? signals fresh? signal JSON written? MT5 running?
EA process? what gates vetoed each BUY/SELL? markets open?

Run: .venv\\Scripts\\python.exe tools\\why_no_trades.py
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
SIG_PRIMARY = "trendmaster_signals.json"

MT5_DATA = Path(
    r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075"
)
MT5_FILES = MT5_DATA / "MQL5" / "Files"
MT5_EXPERTS = MT5_DATA / "MQL5" / "Experts"


def fmt(label: str, value: object, ok: bool | None = None) -> str:
    badge = "OK " if ok else ("FAIL" if ok is False else "    ")
    return f"  [{badge}] {label}: {value}"


def proc_running(name: str) -> tuple[bool, list[int]]:
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"imagename eq {name}", "/FO", "CSV", "/NH"],
            text=True,
            timeout=8,
        )
        pids = []
        for line in out.splitlines():
            parts = [p.strip('"') for p in line.split(",")]
            if len(parts) >= 2 and parts[0].lower() == name.lower():
                try:
                    pids.append(int(parts[1]))
                except ValueError:
                    pass
        return (len(pids) > 0, pids)
    except Exception as e:
        return (False, [])


def main() -> int:
    print("=" * 70)
    print(f"why_no_trades — {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    # ─── 1. brain alive? ─────────────────────────────────────────────────
    print("\n[1] BRAIN")
    brain_pid_file = LOGS / "brain.pid"
    brain_pid = None
    if brain_pid_file.exists():
        try:
            brain_pid = int(brain_pid_file.read_text(encoding="ascii").strip())
            print(fmt("brain.pid", brain_pid, ok=True))
        except (ValueError, OSError):
            print(fmt("brain.pid (unreadable)", "??", ok=False))
    else:
        print(fmt("brain.pid", "MISSING", ok=False))

    if brain_pid:
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, 0, brain_pid)
            alive = bool(h)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
            print(fmt(f"PID {brain_pid} alive", "yes" if alive else "NO", ok=alive))
        except Exception as e:
            print(fmt("alive check error", e))

    out_log = LOGS / "trend_master_brain.out"
    if out_log.exists():
        age = time.time() - out_log.stat().st_mtime
        print(fmt("brain.out fresh", f"{age:.0f}s ago", ok=age < 90))

    # ─── 2. signals state ────────────────────────────────────────────────
    print("\n[2] SIGNALS (in-memory state)")
    state_file = LOGS / "brain_state.json"
    if state_file.exists():
        s = json.loads(state_file.read_text(encoding="utf-8"))
        per_sym = s.get("last_signal_per_symbol", {})
        now = time.time()
        buys, sells, nones = [], [], []
        for sym, sig in per_sym.items():
            if not isinstance(sig, dict):
                continue
            d = sig.get("direction", "NONE")
            ts = sig.get("ts", 0)
            age = now - ts
            if age > 24 * 3600:
                continue
            if d == "BUY":
                buys.append((sym, sig))
            elif d == "SELL":
                sells.append((sym, sig))
            else:
                nones.append((sym, sig))
        print(fmt("BUY signals", f"{len(buys)} ({', '.join(s for s,_ in buys)})"))
        print(fmt("SELL signals", f"{len(sells)} ({', '.join(s for s,_ in sells)})"))
        print(fmt("NONE", len(nones)))

        # show why for actionable ones
        actionable = buys + sells
        for sym, sig in actionable[:6]:
            conf = sig.get("confidence")
            why = sig.get("why") or sig.get("vetoes") or sig.get("blocked_by")
            ts = sig.get("ts", 0)
            age = now - ts
            print(f"\n   ── {sym} {sig.get('direction')} conf={conf} age={age:.0f}s")
            for k in ("why", "vetoes", "blocked_by", "ea_quorum", "agents",
                     "profit_filter", "mtf", "reentry"):
                if k in sig:
                    val = sig[k]
                    if isinstance(val, (dict, list)):
                        val = json.dumps(val)[:200]
                    print(f"      {k}: {val}")

    # ─── 3. signal JSON files (what EA reads) ───────────────────────────
    print("\n[3] SIGNAL FILES (what EA reads)")
    candidate_dirs = [ROOT, MT5_FILES]
    found_any = False
    for d in candidate_dirs:
        if not d.exists():
            print(fmt(f"dir {d}", "DOES NOT EXIST"))
            continue
        files = sorted(d.glob("trendmaster_signals*.json"))
        if not files:
            print(fmt(f"signal files in {d}", "0", ok=False))
        else:
            found_any = True
            print(f"  signal files in {d}:")
            for f in files[:6]:
                age = time.time() - f.stat().st_mtime
                try:
                    j = json.loads(f.read_text(encoding="utf-8"))
                    sig_age = time.time() - j.get("ts", 0)
                    print(
                        f"    {f.name}: file_age={age:.0f}s "
                        f"sig_age={sig_age:.0f}s "
                        f"dir={j.get('direction')} "
                        f"conf={j.get('confidence')}"
                    )
                except Exception as e:
                    print(f"    {f.name}: PARSE_ERR {e}")
    if not found_any:
        print("  >>> NO signal files anywhere — brain may not be in MT5-aware mode <<<")

    # ─── 4. MT5 + EA running? ───────────────────────────────────────────
    print("\n[4] MT5 + EA")
    mt5_alive, mt5_pids = proc_running("terminal64.exe")
    print(fmt("terminal64.exe", f"{'YES, pids='+str(mt5_pids) if mt5_alive else 'NOT RUNNING'}", ok=mt5_alive))
    me_alive, me_pids = proc_running("metaeditor64.exe")
    print(fmt("metaeditor64.exe", f"{'YES, pids='+str(me_pids) if me_alive else 'not running'}"))

    # check for compiled EA
    ea_ex5 = MT5_EXPERTS / "AI_SUPERBB_v14_TrendMaster.ex5"
    ea_ex5_alt = ROOT / "AI_SUPERBB_v14_TrendMaster.ex5"
    print(fmt("EA .ex5 in MT5 Experts", f"exists ({ea_ex5.stat().st_size}B)" if ea_ex5.exists() else "MISSING", ok=ea_ex5.exists()))
    print(fmt("EA .ex5 in project root", f"exists ({ea_ex5_alt.stat().st_size}B)" if ea_ex5_alt.exists() else "missing"))

    # ─── 5. market session ──────────────────────────────────────────────
    print("\n[5] MARKETS")
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Mon … 6=Sun
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    is_weekend = weekday >= 5 or (weekday == 4 and now.hour >= 21)
    print(fmt("UTC now", now.strftime("%Y-%m-%d %H:%M %a"), ok=not is_weekend))
    print(fmt("forex sessions open", "NO (weekend)" if is_weekend else "YES (Mon-Fri 24h)"))

    # ─── 6. recent trades / activity ─────────────────────────────────────
    print("\n[6] RECENT ACTIVITY")
    if state_file.exists():
        s = json.loads(state_file.read_text(encoding="utf-8"))
        rr = s.get("recent_results", [])
        if rr:
            last = rr[-1]
            last_ts = last.get("ts", 0)
            age_d = (time.time() - last_ts) / 86400.0
            print(fmt("last trade in recent_results", f"{age_d:.1f} days ago"))
        else:
            print(fmt("recent_results", "EMPTY"))
        if "trading_paused" in s:
            paused = s["trading_paused"]
            print(fmt("trading_paused", paused, ok=not paused))
        if "drawdown_lockout_until" in s:
            lo = s["drawdown_lockout_until"]
            if lo and lo > time.time():
                print(fmt("DRAWDOWN LOCKOUT", f"until ts={lo}", ok=False))
            else:
                print(fmt("drawdown lockout", "none", ok=True))

    print("\n" + "=" * 70)
    print("Summary: see [3] and [4]. If MT5 not running OR signal files absent,")
    print("trades CANNOT fire regardless of brain confidence.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
