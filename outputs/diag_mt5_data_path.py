"""Print the actual MT5 data_path that executor is using."""
import MetaTrader5 as mt5
from pathlib import Path
import json
import time

if not mt5.initialize():
    print(f"FAIL mt5.initialize: {mt5.last_error()}")
    raise SystemExit(1)

ti = mt5.terminal_info()
print(f"terminal_info.data_path: {ti.data_path}")
print(f"terminal_info.commondata_path: {ti.commondata_path}")
print(f"terminal_info.name: {ti.name}")
print(f"terminal_info.path: {ti.path}")

real_dir = Path(ti.data_path) / "MQL5" / "Files"
print(f"\nReal MT5 Files dir: {real_dir}")
print(f"Dir exists: {real_dir.exists()}")
print()

if real_dir.exists():
    files = sorted(real_dir.iterdir())
    print(f"Files in real dir ({len(files)}):")
    now = time.time()
    for f in files:
        if f.is_file():
            age = int(now - f.stat().st_mtime)
            print(f"  - {f.name} ({age}s old)")
            if f.name.startswith("trendmaster_signals") and f.suffix == ".json":
                try:
                    sig = json.loads(f.read_text())
                    sig_ts = sig.get("ts", 0)
                    sig_age = int(now - sig_ts) if sig_ts else None
                    print(f"      sig.ts={sig_ts}, sig_age={sig_age}s, strategy={sig.get('tv_strategy')}")
                except Exception as e:
                    print(f"      json error: {e}")

mt5.shutdown()
