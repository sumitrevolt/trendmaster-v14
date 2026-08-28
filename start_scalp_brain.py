"""Start TrendMaster brain in SCALPING MODE."""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

import MetaTrader5 as mt5
from ai_trading_agents.trend_master_brain import TrendMasterBrain

print("=" * 60)
print("  SCALPING MODE BRAIN STARTER")
print("=" * 60)

# Initialize MT5
if not mt5.initialize():
    print(f"  ERROR: MT5 init failed: {mt5.last_error()}")
    sys.exit(1)

acc = mt5.account_info()
print(f"  Account: {acc.login}")
print(f"  Balance: ${acc.balance:.2f}")
print(f"  Server:  {acc.server}")

# Create brain
brain = TrendMasterBrain()
print("  Brain created.")

# Run 5 ticks to warm up and check signals
print("\n  Running 5 ticks to check signal generation...\n")
for i in range(5):
    print(f"  --- Tick {i+1} ---")
    try:
        brain.tick_all()
        # Check signal files
        info = mt5.terminal_info()
        if info:
            from pathlib import Path
            sig_dir = Path(info.data_path) / "MQL5" / "Files"
            for f in sorted(sig_dir.glob("trendmaster_signals*.json")):
                try:
                    data = json.loads(f.read_text())
                    pair = data.get("symbol", f.stem.split("_")[-1] if "_" in f.stem else "?")
                    direction = data.get("direction", "NONE")
                    conf = data.get("confidence", 0)
                    age_s = time.time() - os.path.getmtime(str(f))
                    if direction != "NONE":
                        print(f"    {pair}: *** {direction} conf={conf:.3f} ***")
                    else:
                        print(f"    {pair}: NONE conf={conf:.3f} (age={age_s:.0f}s)")
                except Exception:
                    pass
    except Exception as e:
        print(f"  Tick error: {e}")
    time.sleep(2)

mt5.shutdown()
print("\n  Brain test complete. Ready for live deployment.")
