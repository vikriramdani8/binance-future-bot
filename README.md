# 🚀 Binance Futures Screener + Auto-Trader

A modular Python bot that screens **Binance USDT-Margined Futures** for LONG/SHORT opportunities using technical indicators (RSI, MACD, EMA-200), sends real-time alerts to **Telegram**, and optionally auto-executes trades on **Binance Futures Testnet**.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Binance](https://img.shields.io/badge/Binance-Futures-F0B90B?logo=binance&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Alerts-26A5E4?logo=telegram&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

| Feature | Description |
|---|---|
| 📡 **Smart Screener** | Scans top 50/100 coins by 24h volume on any timeframe |
| 📊 **Technical Signals** | RSI oversold/overbought + MACD crossover + EMA-200 trend filter |
| 📱 **Telegram Alerts** | Instant notifications with detailed signal info |
| ⚡ **Auto-Trade (Testnet)** | Paper trading with automatic market orders, TP & SL |
| 🛡️ **Risk Management** | Configurable TP/SL, isolated margin, max position limits |
| 🐳 **Docker Ready** | One-command deployment for VPS |
| 🔄 **Scheduled Scanning** | Runs automatically every N minutes |

## 📐 Signal Logic

### 🟢 LONG Signal
- RSI < 30 (oversold)
- MACD bullish crossover (histogram flips positive)
- Price above EMA-200 *(optional filter)*

### 🔴 SHORT Signal
- RSI > 70 (overbought)
- MACD bearish crossover (histogram flips negative)
- Price below EMA-200 *(optional filter)*

## 🏗️ Architecture

```
binance-future-bots/
├── main.py             # Entry point, scheduler, graceful shutdown
├── config.py           # Centralized config (reads from .env)
├── data_fetcher.py     # Binance API interaction + retry logic
├── indicators.py       # RSI, MACD, EMA computation + signal detection
├── screener.py         # Orchestrator: fetch → analyze → display → trade
├── trader.py           # Auto-trade engine (testnet)
├── notifier.py         # Telegram notification module
├── .env                # Environment variables (secrets)
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container image
├── docker-compose.yml  # Docker deployment config
└── .gitignore
```

## ⚡ Quick Start

### Prerequisites
- Python 3.10+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### 1. Clone & Install

```bash
git clone https://github.com/vikriramdani8/binance-future-bot.git
cd binance-future-bot
pip install -r requirements.txt
```

### 2. Configure

Copy and edit your `.env` file:

```bash
cp .env.example .env
```

Set your Telegram credentials:
```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. Run

```bash
python main.py
```

## 🐳 Docker Deployment (VPS)

```bash
# Build & run in background
docker compose up -d --build

# View logs
docker compose logs -f screener

# Stop
docker compose down

# Restart after config change
docker compose up -d --build
```

## ⚙️ Configuration

All parameters are configured via the `.env` file:

### Screener Settings

| Variable | Default | Description |
|---|---|---|
| `TOP_N_COINS` | `50` | Number of top coins by 24h volume to screen |
| `KLINE_INTERVAL` | `15m` | Candlestick timeframe (`1m`, `5m`, `15m`, `1h`, `4h`) |
| `SCAN_INTERVAL_MINUTES` | `15` | How often to run the screener |
| `USE_EMA_FILTER` | `true` | Require EMA-200 trend confirmation |

### Technical Indicators

| Variable | Default | Description |
|---|---|---|
| `RSI_PERIOD` | `14` | RSI look-back period |
| `RSI_OVERSOLD` | `30` | RSI threshold for LONG signal |
| `RSI_OVERBOUGHT` | `70` | RSI threshold for SHORT signal |
| `MACD_FAST` | `12` | MACD fast EMA period |
| `MACD_SLOW` | `26` | MACD slow EMA period |
| `MACD_SIGNAL` | `9` | MACD signal line period |

### Telegram

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_ENABLED` | `true` | Enable/disable Telegram alerts |
| `TELEGRAM_BOT_TOKEN` | — | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | — | Your chat/group/channel ID |

### Auto-Trade (Testnet)

| Variable | Default | Description |
|---|---|---|
| `AUTO_TRADE_ENABLED` | `false` | Enable auto-trade on testnet |
| `TESTNET_API_KEY` | — | Testnet API key |
| `TESTNET_API_SECRET` | — | Testnet API secret |
| `LEVERAGE` | `10` | Leverage multiplier |
| `MARGIN_TYPE` | `ISOLATED` | `ISOLATED` or `CROSSED` |
| `MARGIN_PER_TRADE_USDT` | `10` | USDT margin per trade |
| `TAKE_PROFIT_PCT` | `2.0` | Take profit percentage |
| `STOP_LOSS_PCT` | `1.0` | Stop loss percentage |
| `MAX_OPEN_POSITIONS` | `5` | Max simultaneous positions |

## 📱 Telegram Setup

1. Chat [@BotFather](https://t.me/BotFather) → `/newbot` → follow instructions
2. Copy the **Bot Token**
3. Start a chat with your bot (send `/start`)
4. Get your **Chat ID**:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
5. Update `.env` with your token and chat ID

## 🧪 Testnet Auto-Trade Setup

> ⚠️ **Always test on Testnet first before using real funds.**

1. Go to [testnet.binancefuture.com](https://testnet.binancefuture.com)
2. Register/login and create API keys
3. Update `.env`:
   ```env
   AUTO_TRADE_ENABLED=true
   TESTNET_API_KEY=your_testnet_key
   TESTNET_API_SECRET=your_testnet_secret
   ```

### Trade Execution Flow

```
Signal Detected → Check Duplicate Position → Check Max Positions
→ Set ISOLATED Margin → Set Leverage → Calculate Quantity
→ Market Order → Place TP (+2%) → Place SL (-1%)
→ Telegram Notification
```

### Safety Features

- ✅ **Duplicate prevention** — Won't open a second position on the same symbol
- ✅ **Max position limit** — Caps total open positions
- ✅ **Precision handling** — Respects tick size, step size, min notional
- ✅ **TP/SL brackets** — Auto-placed after every entry
- ✅ **Mark price** — TP/SL trigger on mark price (avoids wick manipulation)
- ✅ **Rate limit handling** — Exponential backoff on API throttling

## 📦 Dependencies

| Package | Purpose |
|---|---|
| `python-binance` | Binance API wrapper |
| `pandas` | OHLCV data manipulation |
| `ta` | Technical indicators (RSI, MACD, EMA) |
| `tabulate` | Pretty terminal tables |
| `colorama` | Colored terminal output |
| `schedule` | Lightweight job scheduling |

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## ⚠️ Disclaimer

This software is for **educational and testing purposes only**. Cryptocurrency trading involves substantial risk. The authors are not responsible for any financial losses incurred through the use of this bot. Always test thoroughly on testnet before considering any live trading.

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
