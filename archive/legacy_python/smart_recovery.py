"""
SMART TRADE RECOVERY & ACTIVE POSITION MANAGEMENT
====================================================
Don't just sit on losing trades — take SMART action.

CORE PHILOSOPHY:
- If trend changes AGAINST our trade → close early, don't wait for SL
- If trend reverses strongly → close losing trade + open reverse trade
- If trade is stuck (no movement) → close after timeout, free up capital
- If sentiment shifts against us → tighten SL immediately
- NEVER average down (add to losers) — that's gambling, not trading

RECOVERY STRATEGIES:
1. EARLY EXIT    — H1 trend flips against us → close immediately (save capital)
2. SMART REVERSE — H4+H1 both flip → close losing + open reverse (recover loss)
3. TIGHTEN SL    — Sentiment turns negative → move SL closer (reduce max loss)
4. TIME EXIT     — Trade stuck for too long → close at current P&L
5. BREAKEVEN+    — If trade was profitable then drops back → close at BE+spread

SENTIMENT ENGINE:
- Tracks real-time sentiment from news, institutional flow, cross-market
- Updates every 60 seconds
- Posts warnings to AgentCommunicationBus
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Will be populated by main.py at runtime
MT5_AVAILABLE = False
mt5 = None

try:
    import MetaTrader5 as _mt5
    MT5_AVAILABLE = True
    mt5 = _mt5
except ImportError:
    pass

try:
    from institutional_agents import AgentCommunicationBus
except ImportError:
    AgentCommunicationBus = None

try:
    from agent_training import TrainingEngine
except ImportError:
    TrainingEngine = None


class SentimentTracker:
    """
    Real-time market sentiment aggregator.
    Combines signals from all sources into a single sentiment score.

    Score range: -100 (extreme bearish) to +100 (extreme bullish)
    """

    _sentiment: Dict[str, Dict] = {}  # symbol → {score, direction, reasons, updated}

    @classmethod
    def update(cls, symbol: str, news_score: int = 0, news_sentiment: str = "NEUTRAL",
               institutional_dir: str = "NEUTRAL", institutional_conf: int = 50,
               cross_market_bias: str = "NEUTRAL",
               h1_trend: str = "SIDEWAYS", h4_trend: str = "SIDEWAYS",
               rsi: float = 50, adx: float = 20):
        """
        Update sentiment for a symbol by combining all inputs.
        Called every analysis cycle from main.py.
        """
        score = 0
        reasons = []

        # News sentiment (weight: 15%)
        if news_sentiment == "BULLISH":
            score += min(15, news_score * 5)
            reasons.append(f"📰 News bullish ({news_score:+d})")
        elif news_sentiment == "BEARISH":
            score -= min(15, abs(news_score) * 5)
            reasons.append(f"📰 News bearish ({news_score:+d})")

        # Institutional direction (weight: 25%)
        if institutional_dir == "BUY":
            inst_score = int((institutional_conf - 50) * 0.5)
            score += max(5, min(25, inst_score))
            reasons.append(f"🏦 Institutions buying ({institutional_conf}%)")
        elif institutional_dir == "SELL":
            inst_score = int((institutional_conf - 50) * 0.5)
            score -= max(5, min(25, inst_score))
            reasons.append(f"🏦 Institutions selling ({institutional_conf}%)")

        # Cross-market (weight: 15%)
        if cross_market_bias == "BUY":
            score += 15
            reasons.append("💲 Cross-market bullish")
        elif cross_market_bias == "SELL":
            score -= 15
            reasons.append("💲 Cross-market bearish")

        # H4 + H1 trend (weight: 30%)
        if h4_trend == "BULLISH" and h1_trend == "BULLISH":
            score += 30
            reasons.append("📈 H4+H1 both BULLISH")
        elif h4_trend == "BEARISH" and h1_trend == "BEARISH":
            score -= 30
            reasons.append("📉 H4+H1 both BEARISH")
        elif h4_trend != "SIDEWAYS" and h4_trend != h1_trend:
            reasons.append(f"⚠️ H4 ({h4_trend}) conflicts H1 ({h1_trend})")

        # RSI extremes (weight: 10%)
        if rsi > 75:
            score -= 10
            reasons.append(f"🔴 RSI overbought ({rsi:.0f})")
        elif rsi < 25:
            score += 10
            reasons.append(f"🟢 RSI oversold ({rsi:.0f})")

        # ADX strength (weight: 5%)
        if adx > 30:
            # Strong trend — sentiment in trend direction gets boost
            if score > 0:
                score += 5
            elif score < 0:
                score -= 5
            reasons.append(f"💪 Strong trend (ADX {adx:.0f})")

        # Clamp to -100 to +100
        score = max(-100, min(100, score))

        direction = "BULLISH" if score > 20 else "BEARISH" if score < -20 else "NEUTRAL"

        cls._sentiment[symbol] = {
            "score": score,
            "direction": direction,
            "reasons": reasons,
            "updated": datetime.utcnow(),
        }

        return cls._sentiment[symbol]

    @classmethod
    def get(cls, symbol: str) -> Dict:
        """Get current sentiment for a symbol."""
        return cls._sentiment.get(symbol, {
            "score": 0, "direction": "NEUTRAL", "reasons": [], "updated": None
        })

    @classmethod
    def is_against_trade(cls, symbol: str, trade_direction: str) -> bool:
        """Check if current sentiment is against an open trade."""
        sent = cls.get(symbol)
        if trade_direction == "BUY" and sent["score"] < -30:
            return True
        if trade_direction == "SELL" and sent["score"] > 30:
            return True
        return False

    @classmethod
    def report(cls) -> str:
        """Sentiment report for all tracked symbols."""
        if not cls._sentiment:
            return "No sentiment data yet"
        lines = []
        for sym, s in sorted(cls._sentiment.items()):
            icon = "🟢" if s["score"] > 20 else "🔴" if s["score"] < -20 else "🟡"
            age = ""
            if s.get("updated"):
                age_sec = (datetime.utcnow() - s["updated"]).total_seconds()
                age = f" ({int(age_sec/60)}m ago)"
            lines.append(f"{icon} {sym}: {s['direction']} ({s['score']:+d}){age}")
        return " | ".join(lines)


class SmartRecoveryManager:
    """
    Actively manages open trades — doesn't just wait for SL/TP.

    CHECKS EVERY CYCLE:
    1. Has the H1 trend flipped against our trade? → EARLY EXIT
    2. Has H4+H1 both reversed? → CLOSE + REVERSE
    3. Is sentiment now strongly against us? → TIGHTEN SL
    4. Is the trade stuck (low P&L after long time)? → TIME EXIT
    5. Was the trade in profit but now flat? → BREAKEVEN EXIT
    """

    # Track which tickets we've already acted on (prevent double action)
    _acted_tickets: set = set()
    # Track peak profit per ticket (for breakeven+ detection)
    _peak_profit: Dict[str, float] = {}

    @classmethod
    def check_and_act(cls, positions: list, h1_trends: Dict[str, str],
                      h4_trends: Dict[str, str]) -> List[Dict]:
        """
        Main function: check all open positions and take smart action.

        Args:
            positions: List of MT5 position objects
            h1_trends: {symbol: "BULLISH"/"BEARISH"/"SIDEWAYS"}
            h4_trends: {symbol: "BULLISH"/"BEARISH"/"SIDEWAYS"}

        Returns: List of actions taken [{action, ticket, symbol, reason}]
        """
        if not MT5_AVAILABLE or not positions:
            return []

        actions = []

        for pos in positions:
            if pos.comment not in ("AI_SWARM_AGENT", "AI_PARTIAL_TP1"):
                continue  # Only manage our trades

            ticket = pos.ticket
            symbol = pos.symbol
            entry = pos.price_open
            sl = pos.sl
            tp = pos.tp
            is_buy = pos.type == 0
            trade_dir = "BUY" if is_buy else "SELL"
            volume = pos.volume
            profit = pos.profit
            open_time = datetime.fromtimestamp(pos.time)
            age_minutes = (datetime.utcnow() - open_time).total_seconds() / 60

            # Get current price
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                continue
            current = tick.bid if is_buy else tick.ask
            sym_info = mt5.symbol_info(symbol)
            if not sym_info:
                continue
            digits = sym_info.digits

            # Track peak profit
            peak_key = str(ticket)
            if peak_key not in cls._peak_profit:
                cls._peak_profit[peak_key] = profit
            else:
                cls._peak_profit[peak_key] = max(cls._peak_profit[peak_key], profit)

            peak = cls._peak_profit[peak_key]

            # Get trends
            h1_dir = h1_trends.get(symbol, "SIDEWAYS")
            h4_dir = h4_trends.get(symbol, "SIDEWAYS")

            # ── CHECK 1: H1 TREND FLIP → EARLY EXIT ─────────────────
            # If H1 trend has FULLY flipped against our trade → close immediately
            h1_against = (trade_dir == "BUY" and h1_dir == "BEARISH") or \
                         (trade_dir == "SELL" and h1_dir == "BULLISH")

            if h1_against and profit < 0 and f"{ticket}_h1flip" not in cls._acted_tickets:
                # H1 flipped against us AND we're in a loss
                action = cls._close_position(pos, sym_info)
                if action:
                    cls._acted_tickets.add(f"{ticket}_h1flip")
                    action["reason"] = (
                        f"🔄 SMART EXIT: H1 trend flipped to {h1_dir} against our {trade_dir}. "
                        f"Closed at ${profit:.2f} loss instead of waiting for SL (saved capital)"
                    )
                    action["recovery_type"] = "H1_FLIP_EXIT"
                    actions.append(action)
                    logger.warning(
                        f"🔄 RECOVERY: Closed {trade_dir} {symbol} #{ticket} — "
                        f"H1 flipped {h1_dir}, P&L: ${profit:.2f}"
                    )
                    continue

            # ── CHECK 2: H4+H1 BOTH REVERSED → CLOSE + REVERSE SIGNAL ──
            h4_against = (trade_dir == "BUY" and h4_dir == "BEARISH") or \
                         (trade_dir == "SELL" and h4_dir == "BULLISH")

            if h4_against and h1_against and f"{ticket}_reverse" not in cls._acted_tickets:
                # Both H4 and H1 are now against us — strong reversal
                action = cls._close_position(pos, sym_info)
                if action:
                    cls._acted_tickets.add(f"{ticket}_reverse")
                    reverse_dir = "SELL" if trade_dir == "BUY" else "BUY"
                    action["reason"] = (
                        f"⚡ SMART REVERSE: H4+H1 BOTH flipped to {h4_dir}. "
                        f"Closed {trade_dir} at ${profit:.2f}. "
                        f"REVERSE SIGNAL: {reverse_dir} {symbol} (follow the new trend)"
                    )
                    action["recovery_type"] = "SMART_REVERSE"
                    action["reverse_signal"] = reverse_dir
                    actions.append(action)

                    # Post reverse signal to bus
                    if AgentCommunicationBus:
                        AgentCommunicationBus.post(
                            agent="SmartRecovery",
                            symbol=symbol,
                            msg_type="SIGNAL",
                            direction=reverse_dir,
                            confidence=70,
                            message=f"Reverse after H4+H1 flip: {reverse_dir} {symbol}",
                            ttl_minutes=15,
                        )

                    logger.warning(
                        f"⚡ REVERSE: Closed {trade_dir} {symbol} #{ticket} "
                        f"→ Reverse signal: {reverse_dir} (H4+H1 both {h4_dir})"
                    )
                    continue

            # ── CHECK 3: SENTIMENT AGAINST US → TIGHTEN SL ──────────
            sent_against = SentimentTracker.is_against_trade(symbol, trade_dir)
            if sent_against and profit < 0 and f"{ticket}_tighten" not in cls._acted_tickets:
                sent = SentimentTracker.get(symbol)
                # Tighten SL by 30% (reduce max loss)
                if is_buy and sl > 0:
                    sl_dist = entry - sl
                    new_sl = round(entry - sl_dist * 0.7, digits)  # 30% tighter
                    if new_sl > sl:  # Only if actually tighter
                        result = cls._modify_sl(pos, new_sl, sym_info)
                        if result:
                            cls._acted_tickets.add(f"{ticket}_tighten")
                            actions.append({
                                "action": "TIGHTEN_SL",
                                "ticket": ticket,
                                "symbol": symbol,
                                "old_sl": sl,
                                "new_sl": new_sl,
                                "reason": (
                                    f"📉 SENTIMENT SHIFT: {sent['direction']} ({sent['score']:+d}) "
                                    f"against our {trade_dir}. SL tightened {sl:.{digits}f} → {new_sl:.{digits}f}"
                                ),
                            })
                elif not is_buy and sl > 0:
                    sl_dist = sl - entry
                    new_sl = round(entry + sl_dist * 0.7, digits)
                    if new_sl < sl:
                        result = cls._modify_sl(pos, new_sl, sym_info)
                        if result:
                            cls._acted_tickets.add(f"{ticket}_tighten")
                            actions.append({
                                "action": "TIGHTEN_SL",
                                "ticket": ticket,
                                "symbol": symbol,
                                "old_sl": sl,
                                "new_sl": new_sl,
                                "reason": (
                                    f"📉 SENTIMENT SHIFT: {sent['direction']} ({sent['score']:+d}) "
                                    f"against our {trade_dir}. SL tightened"
                                ),
                            })

            # ── CHECK 4: TIME EXIT — Trade stuck too long ────────────
            max_age = 150  # 150 minutes = 2.5 hours max for a scalp
            if age_minutes > max_age and abs(profit) < 1.0 and f"{ticket}_timeout" not in cls._acted_tickets:
                action = cls._close_position(pos, sym_info)
                if action:
                    cls._acted_tickets.add(f"{ticket}_timeout")
                    action["reason"] = (
                        f"⏰ TIME EXIT: Trade open {int(age_minutes)} min with only "
                        f"${profit:.2f} P&L — no momentum, freeing capital for better setups"
                    )
                    action["recovery_type"] = "TIME_EXIT"
                    actions.append(action)

            # ── CHECK 5: BREAKEVEN+ EXIT — Was in profit, now flat ──
            if peak > 2.0 and profit <= 0.5 and f"{ticket}_bepeak" not in cls._acted_tickets:
                # Was at least $2 in profit, now dropped to breakeven or small profit
                action = cls._close_position(pos, sym_info)
                if action:
                    cls._acted_tickets.add(f"{ticket}_bepeak")
                    action["reason"] = (
                        f"🔒 PROTECT PROFIT: Was +${peak:.2f} in profit, now only +${profit:.2f}. "
                        f"Closing to preserve gains instead of risking a full reversal"
                    )
                    action["recovery_type"] = "BREAKEVEN_PROTECT"
                    actions.append(action)

        # Cleanup old acted tickets (keep last 200)
        if len(cls._acted_tickets) > 200:
            cls._acted_tickets = set(list(cls._acted_tickets)[-100:])
        if len(cls._peak_profit) > 200:
            keys = list(cls._peak_profit.keys())
            cls._peak_profit = {k: cls._peak_profit[k] for k in keys[-100:]}

        return actions

    @classmethod
    def _close_position(cls, pos, sym_info) -> Optional[Dict]:
        """Close a position via MT5."""
        if not MT5_AVAILABLE:
            return None
        try:
            tick = mt5.symbol_info_tick(pos.symbol)
            if not tick:
                return None

            close_price = tick.bid if pos.type == 0 else tick.ask
            digits = sym_info.digits

            # Filling mode
            fm = sym_info.filling_mode
            if fm & 1:
                filling = mt5.ORDER_FILLING_FOK
            elif fm & 2:
                filling = mt5.ORDER_FILLING_IOC
            else:
                filling = mt5.ORDER_FILLING_RETURN

            close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "price": round(close_price, digits),
                "deviation": 20,
                "magic": 234001,
                "comment": "AI_SMART_RECOVERY",
                "type_filling": filling,
            }

            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return {
                    "action": "CLOSE",
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "direction": "BUY" if pos.type == 0 else "SELL",
                    "volume": pos.volume,
                    "close_price": close_price,
                    "profit": pos.profit,
                }
            else:
                err = result.comment if result else "Unknown"
                logger.warning(f"Smart recovery close failed [{pos.symbol}]: {err}")
                return None
        except Exception as e:
            logger.error(f"Smart recovery close error: {e}")
            return None

    @classmethod
    def _modify_sl(cls, pos, new_sl: float, sym_info) -> bool:
        """Modify SL on an open position."""
        if not MT5_AVAILABLE:
            return False
        try:
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "sl": new_sl,
                "tp": pos.tp,
            }
            result = mt5.order_send(request)
            return result and result.retcode == mt5.TRADE_RETCODE_DONE
        except Exception as e:
            logger.error(f"SL modify error: {e}")
            return False


# ═════════════════════════════════════════════════════════════════════
# ASYNC WRAPPERS for main.py integration
# ═════════════════════════════════════════════════════════════════════
async def run_smart_recovery(h1_trends: Dict[str, str],
                              h4_trends: Dict[str, str]) -> List[Dict]:
    """
    Main entry point — called by admin loop every cycle.
    Fetches open positions and runs all recovery checks.
    """
    if not MT5_AVAILABLE:
        return []

    try:
        from concurrent.futures import ThreadPoolExecutor
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=1)

        def _sync():
            positions = mt5.positions_get()
            if not positions:
                return []
            # Filter to our trades only
            our_positions = [p for p in positions if p.comment in
                            ("AI_SWARM_AGENT", "AI_PARTIAL_TP1")]
            if not our_positions:
                return []
            return SmartRecoveryManager.check_and_act(
                our_positions, h1_trends, h4_trends
            )

        return await loop.run_in_executor(executor, _sync)
    except Exception as e:
        logger.error(f"Smart recovery error: {e}")
        return []


def update_sentiment(symbol: str, **kwargs):
    """Update sentiment for a symbol (called from main.py)."""
    return SentimentTracker.update(symbol, **kwargs)


def get_sentiment_report() -> str:
    """Get sentiment report for dashboard."""
    return SentimentTracker.report()
