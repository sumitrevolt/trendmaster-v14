"""Simulate flip logic without actually placing orders.
Shows exactly what would happen if a reverse signal arrived for any
currently-open position."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import MetaTrader5 as mt5
from tools.python_signal_executor import (
    has_position_in_dir, positions_for_symbol, in_cooldown,
    MAGIC_QUICK, MAGIC_TREND, _OUR_MAGICS,
)

mt5.initialize()
pos = mt5.positions_get() or []
print(f"Open positions: {len(pos)}\n")

print("=" * 75)
print("  SIMULATION: What happens if reverse signal arrives for each pair?")
print("=" * 75)
print()

# Group by symbol
by_sym = {}
for p in pos:
    by_sym.setdefault(p.symbol, []).append(p)

for sym, plist in sorted(by_sym.items()):
    cur_dir = "BUY" if plist[0].type == 0 else "SELL"
    rev_dir = "SELL" if cur_dir == "BUY" else "BUY"
    print(f"{sym}  (currently {cur_dir} × {len(plist)}):")
    print(f"  If Rocket Prime fires {rev_dir} signal:")

    # Check 1: cooldown
    cooldown_block = in_cooldown(sym, rev_dir)
    print(f"    [{'X' if cooldown_block else '✓'}] cooldown(SELL)? = {cooldown_block}  {'BLOCKED' if cooldown_block else 'fresh, can fire'}")

    # Check 2: has same direction
    same_dir = has_position_in_dir(sym, rev_dir == "BUY")
    print(f"    [{'X' if same_dir else '✓'}] has_position_in_dir({rev_dir})? = {same_dir}  {'SKIP (already in)' if same_dir else 'no, can fire'}")

    # Action 3: would close opposite
    opposite = [p for p in plist if (p.magic in _OUR_MAGICS) and ((p.type == 0) != (rev_dir == "BUY"))]
    print(f"    [→] close_opposite_positions:")
    for p in opposite:
        leg = "QUICK" if p.magic == MAGIC_QUICK else "TREND" if p.magic == MAGIC_TREND else f"magic={p.magic}"
        print(f"          will close {leg}: {p.symbol} {('BUY' if p.type==0 else 'SELL')} 0.{int(p.volume*100):02d} @ {p.price_open:.5f} → realize {p.profit:+.2f}")

    # Action 4: open new legs
    print(f"    [→] then open Quick {rev_dir} + Trend {rev_dir}")
    print()

mt5.shutdown()
