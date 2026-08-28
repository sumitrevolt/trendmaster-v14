"""Delete stale signal JSON files in MT5 file dir so executor stops
wasting log lines on age-based rejects.

A signal is "stale" if last-modified > 90 seconds ago. The TV webhook
overwrites these files with fresh content on each new alert, so anything
older than that is effectively dead — the EA already saw it once and
moved on.

Safe: backs up to logs/stale_signals_backup_<ts>/ before delete.
"""
from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MT5_FILES = Path(r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files")
STALE_THRESHOLD_SEC = 90  # matches python_signal_executor's age limit


def main() -> int:
    print(f"=== cleanup_stale_signal_files ({datetime.now()}) ===")
    if not MT5_FILES.exists():
        print(f"[X] MT5 files dir missing: {MT5_FILES}")
        return 1

    # Find stale signal files
    now = time.time()
    candidates = []
    for f in MT5_FILES.glob("trendmaster_signals_*.json"):
        try:
            age = now - f.stat().st_mtime
            if age > STALE_THRESHOLD_SEC:
                candidates.append((f, age))
        except Exception as e:
            print(f"  skip {f.name}: {e}")

    if not candidates:
        print("[OK] no stale signal files to clean")
        return 0

    print(f"Found {len(candidates)} stale signal file(s):")
    for f, age in candidates:
        age_min = age / 60
        print(f"  {f.name}  age={age_min:.1f} min")

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ROOT / "logs" / f"stale_signals_backup_{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nBackup dir: {backup_dir}")

    deleted = 0
    for f, _ in candidates:
        try:
            shutil.copy2(f, backup_dir / f.name)
            f.unlink()
            print(f"  [OK] deleted {f.name}")
            deleted += 1
        except Exception as e:
            print(f"  [X] failed {f.name}: {e}")

    print(f"\nDone — {deleted}/{len(candidates)} deleted, backups in {backup_dir.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
