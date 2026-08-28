"""Patch ai_trading_agents/trade_tracker.py to filter MT5 deal history
by `state["last_processed_deal_ts"]` so a state-file reset actually
sticks across brain restarts.

ROOT CAUSE — current behavior:
  trade_tracker.poll() pulls ALL deals from the last `lookback_days`
  (default 1 day) of MT5 history every restart. _seen_deal_ids starts
  empty, so even after the operator clears `recent_results` to [], the
  next poll re-adds every deal from the last 24h. This makes
  `loss_streak_cooldown` impossible to reset cleanly — the only
  workarounds are raising the cap or accumulating winning trades.

FIX:
  Use `state["last_processed_deal_ts"]` as a hard FLOOR for the deal
  fetch window. If the operator sets it to NOW (or to just after a bad
  deal cluster), trade_tracker will only accept deals AFTER that point.

  This makes the bookmark field actually load-bearing instead of just
  a metric.

This script:
  1. Locates the canonical ai_trading_agents/trade_tracker.py via the
     junction at <repo>/ai_trading_agents/.
  2. Backs it up.
  3. Applies the patch (single line change).
  4. Verifies syntax via py_compile.
  5. Reports diff.

The brain reloads modules on restart — any change here takes effect
when start_brain_clean.cmd is next run.
"""
from __future__ import annotations

import py_compile
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "ai_trading_agents" / "trade_tracker.py"

OLD = '            since = int(now - self.lookback_days * 86400)\n            until = int(now + 60)'
NEW = '''            # 2026-05-09 patch: respect state.last_processed_deal_ts as a
            # hard floor so a recent_results reset actually sticks. Without
            # this, trade_tracker re-pulls 24h of MT5 history on every
            # restart and re-adds the deals the operator just cleared.
            lookback_floor = int(now - self.lookback_days * 86400)
            bookmark_floor = int(state.get("last_processed_deal_ts", 0) or 0)
            since = max(lookback_floor, bookmark_floor)
            until = int(now + 60)'''


def main() -> int:
    print(f"=== patch trade_tracker.py min_deal_ts filter ===")
    print(f"target: {TARGET}")

    if not TARGET.exists():
        print(f"[X] target missing")
        return 1

    text = TARGET.read_text(encoding="utf-8")
    if NEW.split("\n")[1].strip() in text:
        print(f"[OK] patch already applied — no-op")
        return 0
    if OLD not in text:
        print(f"[X] expected OLD pattern not found — file may have changed since 2026-05-09")
        # Show context around line 126
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if "lookback_days" in line and "86400" in line:
                start = max(0, i - 2)
                end = min(len(lines), i + 4)
                print("Context found:")
                for j in range(start, end):
                    print(f"  {j+1}: {lines[j]}")
        return 2

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TARGET.with_name(f"trade_tracker.py.bak.{ts}")
    shutil.copy2(TARGET, backup)
    print(f"[OK] backup: {backup.name}")

    # Apply patch
    new_text = text.replace(OLD, NEW, 1)
    if new_text == text:
        print("[X] replace was no-op?")
        return 3

    # Write to temp + atomic rename
    tmp = TARGET.with_suffix(".py.tmp")
    tmp.write_text(new_text, encoding="utf-8")

    # Verify syntax
    try:
        py_compile.compile(str(tmp), doraise=True)
        print(f"[OK] syntax check passed")
    except py_compile.PyCompileError as e:
        print(f"[X] syntax check FAILED: {e}")
        tmp.unlink()
        return 4

    tmp.replace(TARGET)
    print(f"[OK] patch applied to {TARGET.name}")
    print()
    print("Restore with:")
    print(f"  copy /Y \"{backup.name}\" \"trade_tracker.py\"")
    print()
    print("Brain restart needed to load patched module:")
    print("  start_brain_clean.cmd")
    print()
    print("After restart, set last_processed_deal_ts in brain_state.json to")
    print("a recent timestamp (e.g., NOW) to skip historical losses:")
    print("  python -c \"import json,time;p='logs/brain_state.json';s=json.load(open(p));s['last_processed_deal_ts']=int(time.time());s['recent_results']=[];json.dump(s,open(p,'w'),separators=(',',':'))\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
