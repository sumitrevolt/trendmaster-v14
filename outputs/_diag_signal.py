"""Diagnose why a Telegram signal didn't translate to an MT5 trade."""
import os, sys, json, time, glob
from pathlib import Path
from datetime import datetime, timezone

os.chdir(r"C:\Users\Ratanshila\Documents\autmated trading")
sys.path.insert(0, os.getcwd())

print("=" * 72)
print("  SIGNAL -> TRADE GAP DIAGNOSIS")
print("=" * 72)

# 1. Where does brain write signal files?
print("\n[1] Signal files — where brain writes them")
mql_files_base = Path(os.path.expandvars(
    r"%APPDATA%\MetaQuotes\Terminal"
))
mql_patterns = [
    "trendmaster_signals.json",
    "trendmaster_signals_*.json",
]
found = []
if mql_files_base.exists():
    for term in mql_files_base.iterdir():
        files_dir = term / "MQL5" / "Files"
        if not files_dir.exists():
            continue
        for pat in mql_patterns:
            for f in files_dir.glob(pat):
                found.append(f)
print(f"  found {len(found)} signal file(s) in MT5 Files dir")
for f in found[:25]:
    try:
        age = int(time.time() - f.stat().st_mtime)
        data = json.loads(f.read_text(encoding="utf-8"))
        d = data.get("direction", "?")
        c = data.get("confidence", 0)
        sym = data.get("symbol", "?")
        mark = "BUY/SELL" if d in ("BUY", "SELL") else "NONE"
        print(f"    [{mark:9s}] {f.name:45s} sym={sym:8s} dir={d:5s} "
              f"conf={c:.2f} age={age}s")
    except Exception as e:
        print(f"    [ERR] {f.name}: {e}")

# 2. What does recent_results say — did trades go through?
print("\n[2] brain_state.json recent_results — last 5 trades")
state_path = Path("logs/brain_state.json")
if state_path.exists():
    state = json.loads(state_path.read_text(encoding="utf-8"))
    results = state.get("recent_results", [])
    for r in results[-5:]:
        if isinstance(r, dict):
            ts = int(r.get("ts", 0))
            ago = int(time.time() - ts) if ts else -1
            print(f"    pnl={r.get('pnl'):+.2f}  sym={r.get('symbol')}  "
                  f"ticket={r.get('deal_id')}  ago={ago}s")
        else:
            print(f"    legacy: {r}")

# 3. Current MT5 positions — is any TrendMaster position open?
print("\n[3] Live MT5 open positions")
try:
    import MetaTrader5 as mt5
    mt5.initialize()
    pos = mt5.positions_get()
    if not pos:
        print("    (none)")
    for p in pos or []:
        print(f"    {p.symbol:8s}  magic={p.magic}  vol={p.volume}  "
              f"profit={p.profit:+.2f}  comment={p.comment}")
    # Also check terminal info.
    ti = mt5.terminal_info()
    if ti:
        print(f"\n    MT5 terminal: connected={ti.connected}, "
              f"trade_allowed={ti.trade_allowed}")
    ai = mt5.account_info()
    if ai:
        print(f"    account: login={ai.login}, "
              f"margin_free=${ai.margin_free:.2f}, "
              f"equity=${ai.equity:.2f}")
    mt5.shutdown()
except Exception as e:
    print(f"    MT5 probe failed: {e}")

# 4. EA experts log — look for AI_SUPERBB entries
print("\n[4] MT5 Experts log — AI_SUPERBB_v14 entries")
term_logs = []
for term in (mql_files_base.iterdir() if mql_files_base.exists() else []):
    logs_dir = term / "MQL5" / "Logs"
    if logs_dir.exists():
        term_logs.extend(logs_dir.glob("*.log"))
# Pick the most recent log.
if term_logs:
    term_logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest = term_logs[0]
    print(f"    latest log: {latest.name}  "
          f"({int(time.time()-latest.stat().st_mtime)}s old)")
    try:
        content = latest.read_text(encoding="utf-16-le", errors="replace")
    except Exception:
        try:
            content = latest.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            content = ""
            print(f"    couldn't read: {e}")
    if content:
        lines = content.splitlines()
        ea_lines = [l for l in lines if
                    "SUPERBB" in l.upper() or "TrendMaster" in l
                    or "AI_SUPERBB" in l or "20260420" in l]
        print(f"    {len(ea_lines)} EA-related line(s)")
        for l in ea_lines[-15:]:
            # Strip first timestamp + keep meaningful part.
            print(f"    {l[:200]}")
else:
    print("    no Logs dir found")

print("\n" + "=" * 72)
print("  DIAGNOSIS DONE")
print("=" * 72)
