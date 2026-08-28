"""Reset the loss_streak counter that's blocking BTCUSD (and any other
symbol) signals. The brain's profit_gate computes loss_streak from
state.recent_results — trimming or clearing that array drops the
counter to 0.

CONTEXT 2026-05-09: brain log line shows
  [BTCUSD] profit_gate veto: loss_streak: loss streak 50 >= cap 3
This 50 consecutive losses came from today-morning's 4-dupe-executor
era (deal_ids 733164586..733166121, 50 entries from 03:30-04:30 IST,
all -$0.10 to -$0.29 micro-losses caused by same signal placed 4×).

This script:
  1. Backs up logs/brain_state.json with a timestamp.
  2. Loads JSON, trims recent_results to empty list.
  3. Writes back atomically (temp file + rename).
  4. Prints what changed.

DOES NOT restart brain. Brain will pick up the trimmed state on its
next tick (state_store reloads on each save, and writes are partial-
state — so brain's in-memory recent_results may take 1 tick to clear).
For an immediate effect, run start_brain_clean.cmd after this script.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "logs" / "brain_state.json"


def main() -> int:
    if not STATE_FILE.exists():
        print(f"[X] brain_state.json missing: {STATE_FILE}")
        return 1

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = STATE_FILE.with_name(f"brain_state.bak.before_loss_streak_reset_{ts}.json")
    shutil.copy2(STATE_FILE, backup)
    print(f"[OK] backup written: {backup.name}")

    # Load
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    rr = state.get("recent_results", [])
    print(f"[INFO] current recent_results count: {len(rr)}")
    if rr:
        first = rr[0]
        last = rr[-1]
        print(f"       oldest: ts={first.get('ts')} sym={first.get('symbol')} pnl={first.get('pnl')}")
        print(f"       newest: ts={last.get('ts')} sym={last.get('symbol')} pnl={last.get('pnl')}")
        loss_count = sum(1 for r in rr if r.get("pnl", 0) < 0)
        print(f"       loss count: {loss_count}/{len(rr)}")

    # Trim
    state["recent_results"] = []

    # Atomic write via temp file
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    tmp.replace(STATE_FILE)
    print(f"[OK] reset complete — recent_results = []")
    print()
    print("Next steps:")
    print("  1. (optional) start_brain_clean.cmd     # force brain to reload")
    print("  2. Verify in next tick: 'profit_gate veto loss_streak' should disappear")
    print()
    print(f"Backup of pre-reset state: {backup.name}")
    print("Restore with: copy /Y \"%s\" \"%s\"" % (backup.name, STATE_FILE.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
