import MetaTrader5 as mt5
from datetime import datetime
import time

if not mt5.initialize():
    print(f'MT5 initialize() failed, error code: {mt5.last_error()}')
    quit()

positions = mt5.positions_get()
if positions is None:
    print(f'No positions, error code: {mt5.last_error()}')
    mt5.shutdown()
    quit()

now = datetime.now()
closed_count = 0

for pos in positions:
    open_time = datetime.fromtimestamp(pos.time)
    days_open = (now - open_time).days
    
    if days_open >= 14 and pos.symbol == 'XAUUSD':
        print(f'Closing aged position {pos.ticket} ({days_open} days old)...')
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick:
            close_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": close_price,
                "deviation": 20,
                # Try with 0 magic number first, or leave it out so it closes regardless
                "comment": "AI_SWARM_AUTO_CLOSE_AGED",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f'Closed {pos.ticket} successfully')
                closed_count += 1
            else:
                print(f'Failed to close {pos.ticket}: {result.retcode if result else "N/A"}')

print(f'Closed {closed_count} XAUUSD positions.')
mt5.shutdown()
