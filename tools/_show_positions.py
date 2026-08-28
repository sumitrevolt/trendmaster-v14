"""Pretty-print account + open positions."""
import MetaTrader5 as mt5

mt5.initialize()
ai = mt5.account_info()
pos = mt5.positions_get() or []
total = sum(p.profit for p in pos)
print("=== ACCOUNT ===")
print(f"  Balance:        ${ai.balance:.2f}")
print(f"  Equity:         ${ai.equity:.2f}")
print(f"  Margin used:    ${ai.margin:.2f}")
print(f"  Margin free:    ${ai.margin_free:.2f}")
print(f"  Floating P/L:   {total:+.2f}")
print(f"  Open positions: {len(pos)}")
print()
print("=== POSITIONS ===")
print(f"{'Symbol':<10} {'Dir':<5} {'Lots':<6} {'Open':<13} {'Now':<13} {'P/L':>8}")
print("-" * 60)
for p in sorted(pos, key=lambda x: x.symbol):
    d = "BUY" if p.type == 0 else "SELL"
    print(f"{p.symbol:<10} {d:<5} {p.volume:<6.2f} {p.price_open:<13.5f} {p.price_current:<13.5f} {p.profit:>+8.2f}")
mt5.shutdown()
