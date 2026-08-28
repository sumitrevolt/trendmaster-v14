#!/usr/bin/env python3
"""
start_brain_live.py — Live Brain Launcher
Runs tick loop for all TRADING_PAIRS, writes signal files every 3 seconds.
"""
import sys
import time
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("brain_live")

def main():
    from config import settings
    from ai_trading_agents.trend_master_brain import TrendMasterBrain

    pairs = settings.TRADING_PAIRS
    logger.info("Starting brain for %d pairs: %s", len(pairs), pairs)

    brain = TrendMasterBrain()
    logger.info("Brain initialized — starting tick loop")

    tick_count = 0
    signal_count = 0

    while True:
        try:
            for sym in pairs:
                result = brain.tick_once(sym)
                tick_count += 1

                if result is None:
                    continue

                d = result.get("direction", "NONE")
                if d not in ("NONE", "none", ""):
                    signal_count += 1
                    logger.info(
                        "SIGNAL %s %s conf=%.3f (total signals: %d)",
                        sym, d, result.get("confidence", 0), signal_count,
                    )

            time.sleep(3)

        except KeyboardInterrupt:
            logger.info("Shutdown requested")
            break
        except Exception as e:
            logger.error("Tick error: %s", e, exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
