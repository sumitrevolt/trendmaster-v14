"""
ORPHANED TRADE CLEANUP UTILITY
================================
Finds and closes orphaned/stuck trades in MT5.

PROBLEM: 14 XAUUSD SELL trades opened Feb 12-13, 2026 are still open.
         These were never closed by the bot (bot went offline).

USAGE:
  python tools/cleanup_orphans.py              # DRY RUN (show only)
  python tools/cleanup_orphans.py --close      # Actually close them
  python tools/cleanup_orphans.py --close --symbol XAUUSD  # Close only XAUUSD

SAFETY:
  - Dry run by default (shows what would be closed)
  - Requires --close flag to actually execute
  - Filters by magic number (only bot trades)
  - Shows P&L before closing
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 package not installed")
    sys.exit(1)

from config import settings


def get_orphaned_positions(symbol_filter=None, max_age_hours=24):
    """Find all positions that are older than max_age_hours."""
    positions = mt5.positions_get()
    if positions is None:
        return []

    orphans = []
    now = datetime.now()
    magic = getattr(settings, "ORDER", {}).get("magic_number", 234000)
    # Also match AI_SWARM_AGENT trades (magic 234001)
    allowed_magics = {magic, 234000, 234001}

    for pos in positions:
        # Only our bot's trades (any of our magic numbers)
        if pos.magic not in allowed_magics:
            continue

        # Filter by symbol
        if symbol_filter and pos.symbol != symbol_filter:
            continue

        # Check age
        open_time = datetime.fromtimestamp(pos.time)
        age_hours = (now - open_time).total_seconds() / 3600

        if age_hours > max_age_hours:
            orphans.append(
                {
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": "BUY" if pos.type == 0 else "SELL",
                    "volume": pos.volume,
                    "open_price": pos.price_open,
                    "current_price": pos.price_current,
                    "profit": pos.profit,
                    "swap": pos.swap,
                    "open_time": open_time.strftime("%Y-%m-%d %H:%M"),
                    "age_hours": round(age_hours, 1),
                    "age_days": round(age_hours / 24, 1),
                    "magic": pos.magic,
                    "comment": pos.comment,
                }
            )

    return orphans


def close_position(ticket, symbol, volume, pos_type):
    """Close a specific position by ticket."""
    # Determine close action (reverse of open)
    if pos_type == "BUY":
        action = mt5.ORDER_TYPE_SELL
    else:
        action = mt5.ORDER_TYPE_BUY

    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return False, f"Symbol {symbol} not found"

    price = sym_info.ask if action == mt5.ORDER_TYPE_BUY else sym_info.bid

    # Detect supported filling mode for this symbol
    # OctaFX: filling_mode=1 means FOK only, filling_mode=2 means IOC, etc.
    fm = sym_info.filling_mode
    if fm == 1:
        filling_mode = mt5.ORDER_FILLING_FOK  # Bit 0 = FOK
    elif fm == 2:
        filling_mode = mt5.ORDER_FILLING_IOC  # Bit 1 = IOC
    elif fm & 2:
        filling_mode = mt5.ORDER_FILLING_IOC
    elif fm & 4:
        filling_mode = mt5.ORDER_FILLING_RETURN
    else:
        filling_mode = mt5.ORDER_FILLING_FOK  # Default to FOK

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": action,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": 234000,
        "comment": "orphan_cleanup",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }

    result = mt5.order_send(request)
    if result is None:
        return False, "Order send returned None"
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return False, f"Error {result.retcode}: {result.comment}"

    return True, f"Closed ticket #{ticket} at {price}"


def main():
    parser = argparse.ArgumentParser(description="Close orphaned trades in MT5")
    parser.add_argument("--close", action="store_true", help="Actually close trades (default: dry run)")
    parser.add_argument("--symbol", type=str, default=None, help="Filter by symbol (e.g., XAUUSD)")
    parser.add_argument("--max-age", type=int, default=24, help="Max age in hours (default: 24)")
    args = parser.parse_args()

    print("=" * 70)
    print("  ORPHANED TRADE CLEANUP UTILITY")
    print("=" * 70)

    # Initialize MT5
    if not mt5.initialize():
        print(f"ERROR: MT5 initialization failed: {mt5.last_error()}")
        print("Make sure MetaTrader 5 terminal is running!")
        sys.exit(1)

    account = mt5.account_info()
    if account:
        print(f"Account: {account.login} | Balance: ${account.balance:.2f} | Equity: ${account.equity:.2f}")
    print()

    # Find orphans
    orphans = get_orphaned_positions(
        symbol_filter=args.symbol,
        max_age_hours=args.max_age,
    )

    if not orphans:
        print(f"No orphaned positions found (older than {args.max_age}h)")
        mt5.shutdown()
        return

    # Display orphans
    total_profit = 0
    total_swap = 0
    print(f"Found {len(orphans)} orphaned positions:\n")
    print(
        f"{'Ticket':>10} {'Symbol':>8} {'Type':>5} {'Vol':>6} {'Open Price':>12} {'Current':>12} {'P&L':>10} {'Swap':>8} {'Age':>8}"
    )
    print("-" * 95)

    for o in orphans:
        total_profit += o["profit"]
        total_swap += o["swap"]
        pnl_str = f"${o['profit']:.2f}"
        swap_str = f"${o['swap']:.2f}"
        print(
            f"{o['ticket']:>10} {o['symbol']:>8} {o['type']:>5} {o['volume']:>6.2f} "
            f"{o['open_price']:>12.2f} {o['current_price']:>12.2f} "
            f"{pnl_str:>10} {swap_str:>8} "
            f"{o['age_days']:.0f}d"
        )

    print("-" * 95)
    total_pnl_str = f"${total_profit:.2f}"
    total_swap_str = f"${total_swap:.2f}"
    print(f"{'TOTAL':>10} {'':>8} {'':>5} {'':>6} {'':>12} {'':>12} {total_pnl_str:>10} {total_swap_str:>8}")
    print()

    if not args.close:
        print("DRY RUN — no trades closed. Use --close to actually close them.")
        print(f"  Example: python tools/cleanup_orphans.py --close")
        if args.symbol:
            print(f"  (Filtered to {args.symbol} only)")
    else:
        print(f"CLOSING {len(orphans)} orphaned positions...")
        closed = 0
        failed = 0
        for o in orphans:
            success, msg = close_position(o["ticket"], o["symbol"], o["volume"], o["type"])
            if success:
                closed += 1
                print(f"  CLOSED: {msg}")
            else:
                failed += 1
                print(f"  FAILED: #{o['ticket']} — {msg}")

        print(f"\nResult: {closed} closed, {failed} failed")
        print(f"Total P&L realized: ${total_profit:.2f} (+ ${total_swap:.2f} swap)")

    mt5.shutdown()


if __name__ == "__main__":
    main()
