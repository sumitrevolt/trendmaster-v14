"""Reset top-5 signal files (and legacy) to a NEUTRAL state so EA doesn't act
on the residual test-BUY signals from earlier verification.

Strategy: rename to .reset_<date> backup. Webhook receiver will recreate them
fresh on the next REAL TV alert fire.
"""
from pathlib import Path
from datetime import datetime
import shutil

MT5_FILES = Path(r"C:\Users\Ratanshila\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files")
TARGETS = [
    "trendmaster_signals.json",          # legacy XAUUSD
    "trendmaster_signals_XAUUSD.json",
    "trendmaster_signals_EURUSD.json",
    "trendmaster_signals_USDJPY.json",
    "trendmaster_signals_GBPUSD.json",
    "trendmaster_signals_BTCUSD.json",
]
SUFFIX = ".reset_2026-05-06"

print(f"=== Resetting top-5 signal files (test-BUY residue) ===")
moved = 0
missing = 0
for name in TARGETS:
    f = MT5_FILES / name
    if not f.exists():
        print(f"  MISSING  {name}")
        missing += 1
        continue
    target = f.with_suffix(SUFFIX)
    try:
        shutil.move(str(f), str(target))
        print(f"  RESET    {name}  ->  {target.name}")
        moved += 1
    except Exception as e:
        print(f"  FAIL     {name}: {e}")

print(f"\n=== Summary: {moved} reset, {missing} missing ===")
print("EA will re-receive signal files only after next REAL TV alert fire.")
