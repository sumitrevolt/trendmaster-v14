"""Direct Windows-side cleanup of stale MT5 signal files.

Earlier glob-based cleanup found 0 files but executor keeps reporting 6 stale
signals. The Linux-mount/Glob view of the Windows filesystem may be stale.
This runs ON WINDOWS via the venv Python so it sees the same view as the
executor process.

For each known symbol, check both:
  - file path (signal JSON exists?)
  - file mtime + JSON ts content
  - if stale → rename to .skipped_<TS> so executor stops seeing it
"""
import json
import os
import time
from pathlib import Path

MT5_DIR = Path(r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files")
SIGNAL_MAX_AGE_S = 90

# Same SYMBOLS list as python_signal_executor uses
SYMBOLS = [
    "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
    "NZDUSD", "USDCAD", "USDCHF", "EURJPY", "GBPJPY", "AUDJPY",
    "CADJPY", "EURGBP", "EURAUD", "BTCUSD", "ETHUSD",
    "XTIUSD", "XBRUSD", "XNGUSD",
]

print(f"=== Cleanup stale signals (Python direct) ===")
print(f"Target dir: {MT5_DIR}")
print(f"Dir exists: {MT5_DIR.exists()}")
print()

# List all files in MT5 dir
all_files = sorted(MT5_DIR.iterdir())
print(f"Total entries in dir: {len(all_files)}")
for f in all_files:
    if f.is_file():
        age = int(time.time() - f.stat().st_mtime)
        print(f"  - {f.name} ({age}s old, {f.stat().st_size} bytes)")

print()
print("=== Per-symbol check ===")
now = time.time()
acted = []
for symbol in SYMBOLS:
    if symbol == "XAUUSD":
        path = MT5_DIR / "trendmaster_signals.json"
    else:
        path = MT5_DIR / f"trendmaster_signals_{symbol}.json"

    if not path.exists():
        continue  # no_file — fine

    try:
        text = path.read_text(encoding="utf-8")
        sig = json.loads(text)
        ts = sig.get("ts", 0)
        age = int(now - ts)
        if age > SIGNAL_MAX_AGE_S:
            # Rename out of the way
            new_name = path.with_suffix(f".stale_{int(now)}")
            path.rename(new_name)
            acted.append((symbol, age, new_name.name))
            print(f"  RENAMED stale {symbol}: age={age}s -> {new_name.name}")
    except Exception as e:
        print(f"  ERROR reading {path.name}: {e}")
        # Move broken file aside
        try:
            broken = path.with_suffix(f".broken_{int(now)}")
            path.rename(broken)
            acted.append((symbol, -1, broken.name))
            print(f"    moved broken to: {broken.name}")
        except Exception as e2:
            print(f"    rename failed: {e2}")

print()
print(f"=== Result: {len(acted)} files cleaned up ===")
print("Executor should now report no_file=20 stale=0 for these symbols.")
