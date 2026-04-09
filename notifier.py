"""
Telegram Notifier Module
─────────────────────────
Sends signal alerts to a Telegram chat via the Bot API.
Uses raw HTTP requests (no extra dependency needed).
"""

import logging
from typing import List
from datetime import datetime, timezone

import requests

import config
from indicators import SignalResult

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends formatted signal messages to Telegram."""

    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.enabled = config.TELEGRAM_ENABLED

        if self.enabled and (not self.token or not self.chat_id):
            logger.warning(
                "Telegram enabled but BOT_TOKEN or CHAT_ID is empty. "
                "Notifications will be skipped."
            )
            self.enabled = False

    # ── Send raw message ───────────────────────────────────────────────────
    def _send_message(self, text: str) -> bool:
        """Send a message via Telegram Bot API. Returns True on success."""
        if not self.enabled:
            return False

        url = f"{self.BASE_URL.format(token=self.token)}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()

            if resp.status_code == 200 and data.get("ok"):
                logger.debug("Telegram message sent successfully")
                return True
            elif resp.status_code == 429:
                retry_after = data.get("parameters", {}).get("retry_after", 30)
                logger.warning(f"Telegram rate limited. Retry after {retry_after}s")
                return False
            else:
                logger.error(
                    f"Telegram API error {resp.status_code}: "
                    f"{data.get('description', 'Unknown error')}"
                )
                return False

        except requests.exceptions.Timeout:
            logger.warning("Telegram API request timed out")
            return False
        except requests.exceptions.ConnectionError:
            logger.warning("Telegram API connection failed")
            return False
        except Exception as e:
            logger.error(f"Unexpected Telegram error: {e}")
            return False

    # ── Format & send signals ──────────────────────────────────────────────
    def send_signals(self, signals: List[SignalResult]) -> bool:
        """
        Format a list of signals into a Telegram message and send it.
        Returns True if message was sent.
        """
        if not self.enabled or not signals:
            return False

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        message = self._format_signals_message(signals, now)
        return self._send_message(message)

    def _format_signals_message(self, signals: List[SignalResult], timestamp: str) -> str:
        """Build a rich HTML-formatted Telegram message."""
        long_signals = [s for s in signals if "LONG" in s.signal]
        short_signals = [s for s in signals if "SHORT" in s.signal]

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━",
            "📡 <b>BINANCE FUTURES SCREENER</b>",
            "━━━━━━━━━━━━━━━━━━━━━",
            f"⏰ {timestamp}",
            f"📊 Timeframe: <b>{config.KLINE_INTERVAL}</b>",
            f"🏆 Universe: Top {config.TOP_N_COINS} by volume",
            "",
        ]

        # ── LONG signals ──
        if long_signals:
            lines.append(f"🟢 <b>LONG SIGNALS ({len(long_signals)})</b>")
            lines.append("")
            for s in long_signals:
                ema_icon = "✅" if s.ema_confirmed else "⚠️"
                lines.append(
                    f"  <b>{s.symbol}</b>\n"
                    f"    💰 Price: <code>${s.price:,.4f}</code>\n"
                    f"    📉 RSI: <code>{s.rsi:.2f}</code> (oversold)\n"
                    f"    📈 MACD: <code>{s.macd:.6f}</code>\n"
                    f"    {ema_icon} EMA-200: {'Above ✓' if s.ema_confirmed else 'Below ✗'}"
                )
                lines.append("")

        # ── SHORT signals ──
        if short_signals:
            lines.append(f"🔴 <b>SHORT SIGNALS ({len(short_signals)})</b>")
            lines.append("")
            for s in short_signals:
                ema_icon = "✅" if s.ema_confirmed else "⚠️"
                lines.append(
                    f"  <b>{s.symbol}</b>\n"
                    f"    💰 Price: <code>${s.price:,.4f}</code>\n"
                    f"    📈 RSI: <code>{s.rsi:.2f}</code> (overbought)\n"
                    f"    📉 MACD: <code>{s.macd:.6f}</code>\n"
                    f"    {ema_icon} EMA-200: {'Below ✓' if s.ema_confirmed else 'Above ✗'}"
                )
                lines.append("")

        # ── Summary ──
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        lines.append(
            f"📋 Total: {len(signals)} │ "
            f"🟢 Long: {len(long_signals)} │ "
            f"🔴 Short: {len(short_signals)}"
        )
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(
            f"<i>Indicators: RSI({'<'}{config.RSI_OVERSOLD}/{'>'}{config.RSI_OVERBOUGHT}) "
            f"+ MACD crossover"
            f"{' + EMA-200' if config.USE_EMA_FILTER else ''}</i>"
        )

        return "\n".join(lines)

    # ── Startup notification ───────────────────────────────────────────────
    def send_startup_message(self) -> bool:
        """Send a notification when the screener starts."""
        if not self.enabled:
            return False

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        msg = (
            "🚀 <b>Screener Started</b>\n"
            f"⏰ {now}\n"
            f"📊 Timeframe: {config.KLINE_INTERVAL}\n"
            f"🏆 Universe: Top {config.TOP_N_COINS}\n"
            f"🔄 Scan interval: {config.SCAN_INTERVAL_MINUTES} min\n"
            f"📐 EMA filter: {'ON' if config.USE_EMA_FILTER else 'OFF'}\n"
            "\n<i>Bot is now monitoring Binance Futures...</i>"
        )
        return self._send_message(msg)
