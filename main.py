"""
╔══════════════════════════════════════════════════════════════════════╗
║           BINANCE FUTURES SCREENER + AUTO-TRADER                   ║
║                                                                    ║
║  Detects LONG / SHORT opportunities based on:                      ║
║    • RSI oversold / overbought                                     ║
║    • MACD bullish / bearish crossover                              ║
║    • EMA-200 trend confirmation (optional)                         ║
║                                                                    ║
║  Optional: Auto-executes trades on Binance Futures Testnet         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import signal
import logging
from datetime import datetime, timezone

import schedule
from colorama import init as colorama_init, Fore, Style

import config
from screener import FuturesScreener
from notifier import TelegramNotifier

# ── Logging Setup ──────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/screener.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


# ── Graceful shutdown ──────────────────────────────────────────────────────
shutdown_flag = False


def handle_shutdown(signum, frame):
    global shutdown_flag
    print(f"\n\n{Fore.YELLOW}⚡ Shutdown signal received. Exiting gracefully...{Style.RESET_ALL}\n")
    shutdown_flag = True


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


# ── Scheduled job ──────────────────────────────────────────────────────────
def screening_job():
    """Single screening cycle wrapped with error handling."""
    try:
        screener = FuturesScreener()
        results = screener.run()

        print(
            f"\n  {Fore.WHITE}Next scan in {config.SCAN_INTERVAL_MINUTES} minutes{Style.RESET_ALL}"
            f" │ Press Ctrl+C to stop"
        )
        print(f"{'─' * 72}\n")

    except Exception as e:
        logger.exception(f"Unhandled error during screening cycle: {e}")


# ── Main Entry Point ──────────────────────────────────────────────────────
def main():
    colorama_init(autoreset=False)

    tg_status = f"{Fore.GREEN}ON{Style.RESET_ALL}" if config.TELEGRAM_ENABLED and config.TELEGRAM_BOT_TOKEN else f"{Fore.RED}OFF{Style.RESET_ALL}"

    if config.AUTO_TRADE_ENABLED:
        trade_status = f"{Fore.YELLOW}TESTNET{Style.RESET_ALL}"
        trade_detail = (
            f"\n"
            f"    Auto-Trade (Testnet):\n"
            f"    ├── Leverage       : {Fore.YELLOW}{config.LEVERAGE}x{Style.RESET_ALL}\n"
            f"    ├── Margin Type    : {config.MARGIN_TYPE}\n"
            f"    ├── Margin/Trade   : ${config.MARGIN_PER_TRADE_USDT} USDT\n"
            f"    ├── Notional/Trade : ${config.MARGIN_PER_TRADE_USDT * config.LEVERAGE} USDT\n"
            f"    ├── Take Profit    : {Fore.GREEN}+{config.TAKE_PROFIT_PCT}%{Style.RESET_ALL}\n"
            f"    ├── Stop Loss      : {Fore.RED}-{config.STOP_LOSS_PCT}%{Style.RESET_ALL}\n"
            f"    └── Max Positions  : {config.MAX_OPEN_POSITIONS}"
        )
    else:
        trade_status = f"{Fore.WHITE}OFF (Screen Only){Style.RESET_ALL}"
        trade_detail = ""

    print(f"""
{Fore.CYAN}
    ╔══════════════════════════════════════════════════════════════╗
    ║         BINANCE FUTURES SCREENER v2.0                       ║
    ║         Signal Detection + Auto-Trade Engine                ║
    ╚══════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}
    Screener:
    ├── Timeframe       : {Fore.YELLOW}{config.KLINE_INTERVAL}{Style.RESET_ALL}
    ├── Universe        : Top {Fore.YELLOW}{config.TOP_N_COINS}{Style.RESET_ALL} by 24h volume
    ├── RSI Oversold    : < {config.RSI_OVERSOLD}
    ├── RSI Overbought  : > {config.RSI_OVERBOUGHT}
    ├── MACD            : {config.MACD_FAST}/{config.MACD_SLOW}/{config.MACD_SIGNAL}
    ├── EMA Filter      : {"Enabled (EMA-" + str(config.EMA_TREND_PERIOD) + ")" if config.USE_EMA_FILTER else "Disabled"}
    ├── Scan Interval   : Every {config.SCAN_INTERVAL_MINUTES} minutes
    ├── Telegram        : {tg_status}
    └── Auto-Trade      : {trade_status}{trade_detail}
    """)

    # Send Telegram startup notification
    notifier = TelegramNotifier()
    if notifier.enabled:
        print(f"  {Fore.WHITE}[→] Sending Telegram startup notification...{Style.RESET_ALL}", end=" ")
        if notifier.send_startup_message():
            print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}✗{Style.RESET_ALL}")

    # Show testnet balance if auto-trade is enabled
    if config.AUTO_TRADE_ENABLED:
        from trader import FuturesTrader
        trader = FuturesTrader()
        if trader.enabled:
            balance = trader.get_account_balance()
            if balance is not None:
                print(f"  {Fore.WHITE}[→] Testnet USDT Balance: {Fore.GREEN}${balance:,.2f}{Style.RESET_ALL}")
            else:
                print(f"  {Fore.RED}[✗] Could not fetch testnet balance{Style.RESET_ALL}")

    # Run immediately on start
    logger.info("Starting initial screening cycle...")
    screening_job()

    # Schedule subsequent runs
    schedule.every(config.SCAN_INTERVAL_MINUTES).minutes.do(screening_job)

    # Event loop
    while not shutdown_flag:
        schedule.run_pending()
        time.sleep(1)

    logger.info("Screener stopped.")
    print(f"{Fore.GREEN}✓ Screener terminated cleanly.{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
