"""Delete stale MT5 signal JSON files (>5 min old)."""
import time
from pathlib import Path

MT5_DIR = Path(r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files")
now = time.time()
deleted = []
kept = []
for f in MT5_DIR.glob("trendmaster_signals*.json"):
    age = now - f.stat().st_mtime
    if age > 300:
        try:
            f.unlink()
            deleted.append((f.name, int(age)))
        except Exception as e:
            print(f"FAIL delete {f.name}: {e}")
    else:
        kept.append((f.name, int(age)))

print(f"Deleted {len(deleted)} stale files:")
for n, a in deleted:
    print(f"  - {n} ({a}s old)")
print(f"\nKept {len(kept)} fresh files:")
for n, a in kept:
    print(f"  + {n} ({a}s old)")
