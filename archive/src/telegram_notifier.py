"""
TELEGRAM NOTIFICATION SYSTEM — Real-time Trade Alerts
========================================================
Sends trade signals, openings, closings, and daily summaries to Telegram.

Features:
  - Async HTTP using aiohttp
  - Bot token + Chat ID from .env
  - Graceful failure (doesn't crash if Telegram is down)
  - Emoji-rich formatting for readability
  - Rate-limiting built-in
"""

import os
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Load .env so TELEGRAM_* vars are always available regardless of import order
try:
    from dotenv import load_dotenv
    # Search for .env in project root (up to 3 levels up from this file)
    _here = Path(__file__).resolve().parent
    for _p in [_here, _here.parent, _here.parent.parent]:
        _env = _p / ".env"
        if not _env.exists():
            _env = _p / "config" / ".env"
        if _env.exists():
            load_dotenv(_env, override=False)
            break
except ImportError:
    pass  # dotenv not installed — env vars must be set manually

# Try to import aiohttp for async HTTP
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logger.warning("⚠️ aiohttp not available — Telegram notifications disabled. Run: pip install aiohttp")


class TelegramNotifier:
    """Send trading alerts to Telegram chat."""

    def __init__(self):
        """Initialize from .env variables."""
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"

        # API endpoint
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        # Validation
        if self.enabled and (not self.bot_token or not self.chat_id):
            logger.warning("⚠️ Telegram enabled but BOT_TOKEN or CHAT_ID missing")
            self.enabled = False

        if self.enabled and not AIOHTTP_AVAILABLE:
            logger.warning("⚠️ Telegram enabled but aiohttp not installed")
            self.enabled = False

        if self.enabled:
            logger.info("✅ Telegram notifications enabled")
        else:
            logger.info("ℹ️ Telegram notifications disabled")

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message to Telegram chat.

        Args:
            text: Message text (supports HTML formatting)
            parse_mode: "HTML", "Markdown", or "MarkdownV2"

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled or not AIOHTTP_AVAILABLE:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                }
                async with session.post(self.api_url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        logger.debug(f"📱 Telegram message sent")
                        return True
                    else:
                        logger.warning(f"⚠️ Telegram API error: {resp.status}")
                        return False
        except asyncio.TimeoutError:
            logger.error("❌ Telegram request timed out — check internet connection")
            return False
        except Exception as e:
            logger.error(f"❌ Telegram send failed: {type(e).__name__}: {e}", exc_info=True)
            return False

    async def send_signal(self, symbol: str, direction: str,
                         confidence: int, score: int, reasons: list) -> bool:
        """Send a new trading signal alert."""
        if not self.enabled:
            return False

        direction_emoji = "📈" if direction.upper() == "BUY" else "📉" if direction.upper() == "SELL" else "⏸️"

        text = f"""
<b>{direction_emoji} {symbol} {direction.upper()}</b>
Confidence: <b>{confidence}%</b>
Score: <b>{score}</b>

<b>Reasons:</b>
"""
        for reason in reasons[:5]:  # Limit to 5 reasons
            text += f"• {reason}\n"

        text += f"\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"

        return await self.send_message(text)

    async def send_trade_opened(self, symbol: str, direction: str,
                               entry_price: float, sl: float, tp: float,
                               lot_size: float) -> bool:
        """Send notification when a trade is opened."""
        if not self.enabled:
            return False

        direction_emoji = "📈" if direction.upper() == "BUY" else "📉"

        text = f"""
<b>{direction_emoji} TRADE OPENED</b>

<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction.upper()}
<b>Entry:</b> {entry_price:.5f}
<b>Stop Loss:</b> {sl:.5f}
<b>Take Profit:</b> {tp:.5f}
<b>Lot Size:</b> {lot_size}

⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
        return await self.send_message(text)

    async def send_trade_closed(self, symbol: str, direction: str,
                               entry_price: float, exit_price: float,
                               pnl: float, pnl_pct: float) -> bool:
        """Send notification when a trade is closed."""
        if not self.enabled:
            return False

        result_emoji = "✅ WIN" if pnl > 0 else "❌ LOSS"

        text = f"""
<b>{result_emoji}</b>

<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction.upper()}
<b>Entry:</b> {entry_price:.5f}
<b>Exit:</b> {exit_price:.5f}
<b>P&L:</b> ${pnl:.2f} ({pnl_pct:+.2f}%)

⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
        return await self.send_message(text)

    async def send_daily_summary(self, total_trades: int, wins: int,
                                losses: int, total_pnl: float,
                                win_rate: float) -> bool:
        """Send daily summary report."""
        if not self.enabled:
            return False

        icon = "🟢" if win_rate >= 50 else "🔴"

        text = f"""
<b>{icon} DAILY SUMMARY</b>

<b>Total Trades:</b> {total_trades}
<b>Wins:</b> {wins} ✅
<b>Losses:</b> {losses} ❌
<b>Win Rate:</b> {win_rate:.1f}%
<b>Total P&L:</b> ${total_pnl:+.2f}

⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
        return await self.send_message(text)

    async def send_alert(self, title: str, message: str,
                        emoji: str = "⚠️") -> bool:
        """Send a generic alert."""
        if not self.enabled:
            return False

        text = f"""
<b>{emoji} {title}</b>

{message}

⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
        return await self.send_message(text)


# Global instance
_notifier: Optional[TelegramNotifier] = None


def get_notifier() -> TelegramNotifier:
    """Get the global Telegram notifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier


# Convenience async functions
async def send_signal(symbol: str, direction: str, confidence: int,
                     score: int, reasons: list) -> bool:
    """Send a trading signal."""
    return await get_notifier().send_signal(symbol, direction, confidence, score, reasons)


async def send_trade_opened(symbol: str, direction: str, entry_price: float,
                           sl: float, tp: float, lot_size: float) -> bool:
    """Send trade opened notification."""
    return await get_notifier().send_trade_opened(symbol, direction, entry_price, sl, tp, lot_size)


async def send_trade_closed(symbol: str, direction: str, entry_price: float,
                           exit_price: float, pnl: float, pnl_pct: float) -> bool:
    """Send trade closed notification."""
    return await get_notifier().send_trade_closed(symbol, direction, entry_price, exit_price, pnl, pnl_pct)


async def send_daily_summary(total_trades: int, wins: int, losses: int,
                            total_pnl: float, win_rate: float) -> bool:
    """Send daily summary."""
    return await get_notifier().send_daily_summary(total_trades, wins, losses, total_pnl, win_rate)


async def send_alert(title: str, message: str, emoji: str = "⚠️") -> bool:
    """Send a generic alert."""
    return await get_notifier().send_alert(title, message, emoji)
