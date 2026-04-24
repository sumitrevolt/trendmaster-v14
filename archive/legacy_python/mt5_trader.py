"""
=============================================================
  MT5 Trader Module
  Handles all MetaTrader 5 operations:
  - Connect / disconnect
  - Execute BUY / SELL
  - Calculate lot size by risk %
  - SL / TP management
  - Close trades
=============================================================
"""

import MetaTrader5 as mt5
import logging
from datetime import datetime

log = logging.getLogger(__name__)

# ── Risk / trade settings ─────────────────────────────────────────────
RISK_PCT        = 1.0     # % of balance to risk per trade
MAX_OPEN_TRADES = 3       # max simultaneous trades
SL_POINTS       = 150     # 15 pips for Gold (1 pip = 10 points)
TP_POINTS       = 300     # 30 pips (2:1 RR)
MAGIC_NUMBER    = 20240101
SLIPPAGE        = 10


class MT5Trader:
    def __init__(self):
        self.connected = False

    # ── Connect ───────────────────────────────────────────────────────
    def connect(self):
        if not mt5.initialize():
            log.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False
        self.connected = True
        log.info("MT5 connected")
        return True

    def disconnect(self):
        mt5.shutdown()
        self.connected = False

    # ── Account info ──────────────────────────────────────────────────
    def get_account_info(self):
        if not self.connected:
            return None
        info = mt5.account_info()
        if info is None:
            return None
        return {
            "login":    info.login,
            "balance":  info.balance,
            "equity":   info.equity,
            "leverage": info.leverage,
            "currency": info.currency,
            "server":   info.server,
        }

    # ── Count open trades ─────────────────────────────────────────────
    def count_open_trades(self, symbol=None):
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None:
            return 0
        # Only count our bot's trades (by magic number)
        return sum(1 for p in positions if p.magic == MAGIC_NUMBER)

    # ── Calculate lot size by risk % ──────────────────────────────────
    def calc_lot_size(self, symbol, sl_points):
        """Risk RISK_PCT% of balance on each trade"""
        info = mt5.account_info()
        if info is None:
            return 0.01

        balance    = info.balance
        risk_money = balance * (RISK_PCT / 100.0)

        sym_info = mt5.symbol_info(symbol)
        if sym_info is None:
            return 0.01

        # For XAUUSD: tick_value = value of 1 pip per 0.01 lot
        # lot_size = risk_money / (sl_points * tick_value_per_lot)
        tick_value = sym_info.trade_tick_value
        tick_size  = sym_info.trade_tick_size

        if tick_value <= 0 or tick_size <= 0 or sl_points <= 0:
            return 0.01

        # Value per lot per point
        point       = sym_info.point
        pip_value   = (tick_value / tick_size) * point

        lot = risk_money / (sl_points * pip_value)

        # Clamp to broker limits
        min_lot  = sym_info.volume_min
        max_lot  = sym_info.volume_max
        step_lot = sym_info.volume_step

        lot = max(min_lot, min(max_lot, lot))
        # Round to step
        lot = round(lot / step_lot) * step_lot
        lot = round(lot, 2)

        log.info(f"Lot calc: balance={balance:.2f} risk={risk_money:.2f} sl_pts={sl_points} lot={lot}")
        return lot

    # ── Get current price ─────────────────────────────────────────────
    def get_price(self, symbol, action):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return 0.0
        return tick.ask if action == "BUY" else tick.bid

    # ── Execute trade ─────────────────────────────────────────────────
    def execute_trade(self, symbol, action, sl_price=0, tp_price=0, comment="TV Bot"):
        if not self.connected:
            if not self.connect():
                return {"status": "error", "reason": "MT5 not connected"}

        symbol = symbol.upper()

        # Check max open trades
        open_count = self.count_open_trades(symbol)
        if open_count >= MAX_OPEN_TRADES:
            msg = f"Max trades reached ({open_count}/{MAX_OPEN_TRADES}) — signal skipped"
            log.warning(msg)
            return {"status": "skipped", "reason": msg}

        # Ensure symbol is available
        if not mt5.symbol_select(symbol, True):
            return {"status": "error", "reason": f"Symbol {symbol} not found"}

        sym_info = mt5.symbol_info(symbol)
        if sym_info is None:
            return {"status": "error", "reason": f"Symbol info failed for {symbol}"}

        point  = sym_info.point
        digits = sym_info.digits

        # Current price
        price = self.get_price(symbol, action)
        if price <= 0:
            return {"status": "error", "reason": "Could not get current price"}

        # SL / TP — use provided price levels if given, else calculate from points
        if sl_price > 0 and tp_price > 0:
            sl = round(sl_price, digits)
            tp = round(tp_price, digits)
        else:
            if action == "BUY":
                sl = round(price - SL_POINTS * point, digits)
                tp = round(price + TP_POINTS * point, digits)
            else:
                sl = round(price + SL_POINTS * point, digits)
                tp = round(price - TP_POINTS * point, digits)

        # Lot size
        lot = self.calc_lot_size(symbol, SL_POINTS)

        # Order type
        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       lot,
            "type":         order_type,
            "price":        price,
            "sl":           sl,
            "tp":           tp,
            "deviation":    SLIPPAGE,
            "magic":        MAGIC_NUMBER,
            "comment":      comment,
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        log.info(f"Sending order: {action} {symbol} lot={lot} price={price} sl={sl} tp={tp}")

        result = mt5.order_send(request)

        if result is None:
            err = mt5.last_error()
            log.error(f"order_send returned None: {err}")
            return {"status": "error", "reason": f"order_send failed: {err}"}

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            log.info(f"✅ Trade opened: ticket={result.order} {action} {symbol} lot={lot}")
            return {
                "status":  "success",
                "action":  action,
                "symbol":  symbol,
                "lot":     lot,
                "price":   price,
                "sl":      sl,
                "tp":      tp,
                "ticket":  result.order,
                "time":    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        else:
            log.error(f"❌ Trade failed: retcode={result.retcode} comment={result.comment}")
            return {
                "status":  "failed",
                "retcode": result.retcode,
                "comment": result.comment
            }

    # ── Close all trades ──────────────────────────────────────────────
    def close_all_trades(self, symbol=None):
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if not positions:
            return {"status": "ok", "closed": 0}

        closed = 0
        errors = []

        for pos in positions:
            if pos.magic != MAGIC_NUMBER:
                continue

            close_type  = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            close_price = mt5.symbol_info_tick(pos.symbol)
            if close_price is None:
                continue
            price = close_price.bid if pos.type == mt5.ORDER_TYPE_BUY else close_price.ask

            req = {
                "action":       mt5.TRADE_ACTION_DEAL,
                "symbol":       pos.symbol,
                "volume":       pos.volume,
                "type":         close_type,
                "position":     pos.ticket,
                "price":        price,
                "deviation":    SLIPPAGE,
                "magic":        MAGIC_NUMBER,
                "comment":      "TV Bot close",
                "type_time":    mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(req)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                closed += 1
                log.info(f"Closed ticket {pos.ticket}")
            else:
                errors.append(pos.ticket)

        return {"status": "ok", "closed": closed, "errors": errors}

    # ── Get open positions ────────────────────────────────────────────
    def get_positions(self):
        positions = mt5.positions_get()
        if not positions:
            return []
        result = []
        for p in positions:
            if p.magic == MAGIC_NUMBER:
                result.append({
                    "ticket":  p.ticket,
                    "symbol":  p.symbol,
                    "type":    "BUY" if p.type == 0 else "SELL",
                    "volume":  p.volume,
                    "price":   p.price_open,
                    "profit":  p.profit,
                    "sl":      p.sl,
                    "tp":      p.tp,
                })
        return result
