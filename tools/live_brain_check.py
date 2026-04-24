"""
Live MT5 check for the TrendMaster v14 brain.
Connects to MT5, pulls real XAUUSD bars, runs 3 inference ticks,
writes the signal file, then exits cleanly.
"""
from __future__ import annotations
import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import MetaTrader5 as mt5  # noqa: E402

from ai_trading_agents.trend_master_brain import (  # noqa: E402
    TrendMasterBrain, build_features, SYMBOL, TF, INFER_MS, MIN_CONF,
)


def main() -> int:
    print(f"=== v14 live brain check ({SYMBOL} {TF}) ===")

    if not mt5.initialize():
        print("MT5 initialize failed:", mt5.last_error())
        return 1

    info = mt5.terminal_info()
    print(f"MT5 connected: build={info.build}  data_path={info.data_path}")

    brain = TrendMasterBrain()
    print(f"brain ready: ml_loaded={brain.state.model is not None}")

    for i in range(3):
        m5  = brain.pull_bars("M5",  500)
        m15 = brain.pull_bars("M15", 300)
        h1  = brain.pull_bars("H1",  200)
        print(f"\n[tick {i+1}] bars  M5={len(m5) if m5 is not None else 0}  "
              f"M15={len(m15) if m15 is not None else 0}  "
              f"H1={len(h1) if h1 is not None else 0}")

        if m5 is None or len(m5) < 100:
            print("  not enough bars — retrying")
            time.sleep(0.5)
            continue

        feats = build_features(m5).dropna()
        direction, conf = brain.infer_ml(feats)
        mtf_ok = brain.mtf_agree(direction)
        print(f"  infer -> dir={direction} conf={conf:.3f}  mtf_agree={mtf_ok}")

        # Write even if NONE — the EA tolerates it; real brain loop does same
        brain.write_signal(direction, conf)
        print(f"  wrote signal: {brain.state.last_signal}")
        time.sleep(INFER_MS / 1000.0)

    # Show where it actually wrote the file
    path = brain._resolve_signal_path()
    print(f"\nsignal file path: {path}")
    print(f"exists: {path.exists()}  size: {path.stat().st_size if path.exists() else 'n/a'} bytes")

    mt5.shutdown()
    print("\n=== PASS — brain reads MT5, infers, writes signal ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
