"""Check EA attachment + read experts log in UTF-16."""
import os, sys, json, time
from pathlib import Path
from datetime import datetime, timezone

os.chdir(r"C:\Users\Ratanshila\Documents\autmated trading")
sys.path.insert(0, os.getcwd())

print("=" * 72)
print("  EA ATTACHMENT + LOG DIAGNOSIS")
print("=" * 72)

# 1. Which symbol charts are open in MT5? Check profiles dir.
mql_base = Path(os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal"))
terms = [t for t in mql_base.iterdir() if t.is_dir()] if mql_base.exists() else []
print(f"\n[1] MT5 terminals found: {len(terms)}")
for t in terms:
    print(f"  terminal: {t.name}")
    profiles = t / "profiles" / "Templates"
    if profiles.exists():
        for tpl in profiles.glob("*.tpl"):
            print(f"    template: {tpl.name}")
    # Check which charts are in the CURRENT profile.
    cur = t / "profiles" / "current"
    if cur.exists():
        for f in cur.iterdir():
            print(f"    current profile file: {f.name}")
    # Check config/accounts.
    cfg = t / "config" / "servers.dat"

# 2. Read experts log in UTF-16 LE (MT5's default).
print("\n[2] EA entries in latest Experts log (UTF-16 aware)")
experts_dirs = []
for t in terms:
    ex = t / "MQL5" / "Logs"
    if ex.exists():
        experts_dirs.append(ex)

for ex_dir in experts_dirs:
    logs = sorted(ex_dir.glob("*.log"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        continue
    # Pick today's log or the latest.
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    today_log = ex_dir / f"{today}.log"
    target = today_log if today_log.exists() else logs[0]
    age = int(time.time() - target.stat().st_mtime)
    print(f"\n  log: {target}  ({age}s ago, {target.stat().st_size} bytes)")

    # Try multiple encodings.
    content = ""
    for enc in ("utf-16-le", "utf-16", "utf-8", "latin-1"):
        try:
            content = target.read_text(encoding=enc, errors="replace")
            if content and "\x00" not in content:
                print(f"  encoded as {enc}")
                break
        except Exception:
            continue
    if not content:
        print("  (could not decode)")
        continue

    lines = content.splitlines()
    print(f"  {len(lines)} total lines")

    # EA-related filter.
    ea_keys = ("AI_SUPERBB", "SuperBB", "TrendMaster", "InpMagic",
               "20260420", "20260422", "XTIUSD", "signals.json",
               "trendmaster_signals", "BUY", "SELL", "C1", "C2", "C3")
    hits = []
    for line in lines:
        if any(k in line for k in ea_keys):
            hits.append(line)
    print(f"  {len(hits)} EA-related / order lines")
    for l in hits[-30:]:
        safe = "".join(c if 32 <= ord(c) < 128 else "?" for c in l)
        print(f"    {safe[:200]}")
    break   # one terminal is enough

# 3. Is trading allowed for current symbols?
print("\n[3] Per-symbol trade/margin state for XTIUSD + its EA chart")
try:
    import MetaTrader5 as mt5
    mt5.initialize()
    for sym in ("XTIUSD", "XAUUSD"):
        info = mt5.symbol_info(sym)
        if info is None:
            print(f"  {sym}: symbol not found in MT5")
            continue
        print(f"  {sym}: visible={info.visible} trade_mode={info.trade_mode} "
              f"spread={info.spread}pts min_vol={info.volume_min} "
              f"step={info.volume_step}")
    mt5.shutdown()
except Exception as e:
    print(f"  MT5 probe failed: {e}")

print("\n" + "=" * 72)
