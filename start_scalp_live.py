"""
Scalping Mode Brain Launcher
=============================
Starts TrendMaster brain in scalping mode:
- 8 pairs, 2s ticks, agents-primary signals
- Runs detached from terminal via pythonw.exe
- Logs to logs/scalp_brain.log
"""
import sys, os, subprocess, time
from pathlib import Path

ROOT = Path(__file__).parent
PYW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
LAUNCHER = ROOT / "main.py"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "scalp_brain.log"

def is_alive():
    """Check if brain process is running."""
    import json
    info_dir = None
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            info = mt5.terminal_info()
            if info:
                info_dir = Path(info.data_path) / "MQL5" / "Files"
            mt5.shutdown()
    except Exception:
        pass
    if not info_dir:
        return False
    for f in info_dir.glob("trendmaster_signals*.json"):
        age = time.time() - os.path.getmtime(str(f))
        if age < 10:
            return True
    return False

print("=" * 60)
print("  SCALPING MODE BRAIN LAUNCHER")
print("=" * 60)

if is_alive():
    print("  Brain already alive and ticking!")
    sys.exit(0)

print(f"  Python:  {PYW}")
print(f"  Launcher: {LAUNCHER}")
print(f"  Log:     {LOG_FILE}")
print()

# Launch detached
proc = subprocess.Popen(
    [str(PYW), str(LAUNCHER), "run"],
    cwd=str(ROOT),
    stdout=open(str(LOG_FILE), "a"),
    stderr=subprocess.STDOUT,
    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
)

print(f"  Launched PID: {proc.pid}")
print(f"  Waiting 10s for first tick...")

time.sleep(10)

if is_alive():
    print("  Brain is ALIVE and ticking! Signals firing.")
else:
    print("  WARNING: Brain not ticking yet. Check logs:")
    print(f"    {LOG_FILE}")

# Check signal files
try:
    import MetaTrader5 as mt5
    if mt5.initialize():
        info = mt5.terminal_info()
        if info:
            sig_dir = Path(info.data_path) / "MQL5" / "Files"
            import json
            for f in sorted(sig_dir.glob("trendmaster_signals*.json")):
                try:
                    data = json.loads(f.read_text())
                    pair = data.get("symbol", "?")
                    d = data.get("direction", "NONE")
                    c = data.get("confidence", 0)
                    age = time.time() - os.path.getmtime(str(f))
                    print(f"    {pair}: {d} conf={c:.3f} (age={age:.0f}s)")
                except Exception:
                    pass
        mt5.shutdown()
except Exception as e:
    print(f"  Could not check signals: {e}")

print("\nDone!")
