"""
Configuration module for Binance Futures Screener + Auto-Trader.
All tunable parameters are centralized here.
Reads from environment variables first, falls back to defaults.
"""

import os

# ─── Binance API (public endpoints only, no keys needed for market data) ───
API_KEY = os.getenv("API_KEY", "")
API_SECRET = os.getenv("API_SECRET", "")

# ─── Universe Selection ───
TOP_N_COINS = int(os.getenv("TOP_N_COINS", "50"))
QUOTE_ASSET = "USDT"

# ─── Timeframe & Candle Settings ───
KLINE_INTERVAL = os.getenv("KLINE_INTERVAL", "15m")
KLINE_LIMIT = int(os.getenv("KLINE_LIMIT", "250"))

# ─── Technical Indicator Parameters ───
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
RSI_OVERSOLD = int(os.getenv("RSI_OVERSOLD", "30"))
RSI_OVERBOUGHT = int(os.getenv("RSI_OVERBOUGHT", "70"))

MACD_FAST = int(os.getenv("MACD_FAST", "12"))
MACD_SLOW = int(os.getenv("MACD_SLOW", "26"))
MACD_SIGNAL = int(os.getenv("MACD_SIGNAL", "9"))

EMA_TREND_PERIOD = int(os.getenv("EMA_TREND_PERIOD", "200"))
USE_EMA_FILTER = os.getenv("USE_EMA_FILTER", "true").lower() == "true"

# ─── Scheduler ───
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))

# ─── Rate Limit Handling ───
API_CALL_DELAY = float(os.getenv("API_CALL_DELAY", "0.12"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_BACKOFF = int(os.getenv("RETRY_BACKOFF", "5"))

# ─── Telegram Notifications ───
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "true").lower() == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8735125668:AAG3wr-YGiYKMS_C8BuzxTAtZH-mJNqVkng")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8768863516")

# ═══════════════════════════════════════════════════════════════════════
#  AUTO-TRADE MODULE (Testnet Paper Trading)
# ═══════════════════════════════════════════════════════════════════════

# ─── Auto-Trade Toggle ───
AUTO_TRADE_ENABLED = os.getenv("AUTO_TRADE_ENABLED", "false").lower() == "true"

# ─── Testnet API Credentials ───
# Get from: https://testnet.binancefuture.com
TESTNET_API_KEY = os.getenv("TESTNET_API_KEY", "")
TESTNET_API_SECRET = os.getenv("TESTNET_API_SECRET", "")
TESTNET_BASE_URL = "https://testnet.binancefuture.com"

# ─── Position & Leverage ───
MARGIN_TYPE = os.getenv("MARGIN_TYPE", "ISOLATED")           # ISOLATED or CROSSED
LEVERAGE = int(os.getenv("LEVERAGE", "10"))                  # Default 10x leverage

# ─── Position Sizing ───
MARGIN_PER_TRADE_USDT = float(os.getenv("MARGIN_PER_TRADE_USDT", "10.0"))  # $10 USDT margin per trade
# Notional = MARGIN_PER_TRADE_USDT * LEVERAGE = $100 at 10x

# ─── Risk Management (TP / SL) ───
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "2.0"))   # 2% TP
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "1.0"))       # 1% SL

# ─── Safety ───
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "5"))  # Max simultaneous positions
