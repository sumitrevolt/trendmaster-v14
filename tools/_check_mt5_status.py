"""Quick MT5 connection + spread sanity check."""
import MetaTrader5 as mt5

mt5.initialize()
ti = mt5.terminal_info()
ai = mt5.account_info()
print("Terminal connected:", ti.connected if ti else "NO INFO")
print("Trade allowed:", ti.trade_allowed if ti else "?")
print("Build:", ti.build if ti else "?")
print("Account:", ai.login if ai else "NONE", "balance:", ai.balance if ai else None,
      "equity:", ai.equity if ai else None)
print()
print("=== Current spreads on 8 attached pairs ===")
for sym in ["AUDUSD","NZDUSD","USDCHF","EURUSD","USDJPY","USDCAD","GBPUSD","XNGUSD"]:
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if info and tick:
        spread_pts = (tick.ask - tick.bid) / info.point
        print(f"  {sym}: bid={tick.bid} ask={tick.ask} spread={spread_pts:.0f}pts "
              f"trade_mode={info.trade_mode} time={tick.time}")
    else:
        print(f"  {sym}: NO INFO/TICK")
mt5.shutdown()
