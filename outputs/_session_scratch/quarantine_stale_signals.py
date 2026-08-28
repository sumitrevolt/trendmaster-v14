"""Move stale trendmaster_signals_*.json files (non-top-5 pairs) so EA can't act on them.

Top-5 KEPT: XAUUSD, EURUSD, USDJPY, GBPUSD, BTCUSD + legacy trendmaster_signals.json
All others moved to .stale_2026-05-06 suffix.
"""
from pathlib import Path
from datetime import datetime
import shutil

MT5_FILES = Path(r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files")
KEEP = {"XAUUSD", "EURUSD", "USDJPY", "GBPUSD", "BTCUSD"}
SUFFIX = ".stale_2026-05-06"

print(f"=== Quarantining stale signal files in {MT5_FILES} ===")
moved = 0
kept = 0
for f in MT5_FILES.glob("trendmaster_signals*.json"):
    name = f.name
    # Legacy single-file (no symbol suffix) -> keep but reset to neutral
    if name == "trendmaster_signals.json":
        # Legacy file -- keep but log
        age_min = (datetime.now().timestamp() - f.stat().st_mtime) / 60
        print(f"  KEEP (legacy)  {name}  age={age_min:.1f}min")
        kept += 1
        continue
    # Per-symbol files: name pattern trendmaster_signals_<SYM>.json
    if not name.startswith("trendmaster_signals_") or not name.endswith(".json"):
        continue
    sym = name[len("trendmaster_signals_"):-len(".json")]
    if sym in KEEP:
        age_min = (datetime.now().timestamp() - f.stat().st_mtime) / 60
        print(f"  KEEP  (top-5)  {name}  sym={sym}  age={age_min:.1f}min")
        kept += 1
    else:
        target = f.with_suffix(SUFFIX)
        try:
            shutil.move(str(f), str(target))
            age_min = (datetime.now().timestamp() - target.stat().st_mtime) / 60
            print(f"  MOVED          {name}  ->  {target.name}  (sym={sym}, was {age_min:.1f}min old)")
            moved += 1
        except Exception as e:
            print(f"  FAIL           {name}: {e}")

print(f"\n=== Summary: {kept} kept, {moved} quarantined ===")
