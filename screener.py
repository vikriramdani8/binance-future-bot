"""
Screener Engine
───────────────
Orchestrates the full screening + trading pipeline:
  1. Fetch top symbols by volume
  2. Download kline data for each symbol
  3. Compute indicators & detect signals
  4. Display results in a formatted table
  5. Send Telegram notifications
  6. Execute auto-trades (if enabled)
"""

import logging
from datetime import datetime, timezone
from typing import List

from tabulate import tabulate
from colorama import Fore, Style

from data_fetcher import BinanceDataFetcher
from indicators import compute_indicators, detect_signal, SignalResult
from notifier import TelegramNotifier
from trader import FuturesTrader, TradeResult
import config

logger = logging.getLogger(__name__)


class FuturesScreener:
    """Main screener class that ties fetching, analysis, display, and trading together."""

    def __init__(self):
        self.fetcher = BinanceDataFetcher()
        self.notifier = TelegramNotifier()
        self.trader = FuturesTrader()

    def run(self) -> List[SignalResult]:
        """
        Execute one full screening cycle.

        Returns a list of SignalResult objects for symbols that triggered.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        mode = f"{Fore.YELLOW}TESTNET AUTO-TRADE{Style.RESET_ALL}" if self.trader.enabled else f"{Fore.WHITE}SCREEN ONLY{Style.RESET_ALL}"

        print(f"\n{'═' * 72}")
        print(
            f"  {Fore.CYAN}BINANCE FUTURES SCREENER{Style.RESET_ALL}  │  "
            f"TF: {Fore.YELLOW}{config.KLINE_INTERVAL}{Style.RESET_ALL}  │  "
            f"Mode: {mode}  │  {now}"
        )
        print(f"{'═' * 72}")

        # Step 1: Universe selection
        total_steps = "4" if self.trader.enabled else "3"
        print(f"\n{Fore.WHITE}[1/{total_steps}] Fetching top {config.TOP_N_COINS} symbols by 24h volume...{Style.RESET_ALL}")
        symbols = self.fetcher.get_top_symbols()
        if not symbols:
            print(f"{Fore.RED}  ✗ No symbols retrieved. Skipping this cycle.{Style.RESET_ALL}")
            return []
        print(f"  {Fore.GREEN}✓{Style.RESET_ALL} {len(symbols)} symbols selected")

        # Step 2: Fetch candles + detect signals
        print(f"{Fore.WHITE}[2/{total_steps}] Analyzing indicators (RSI, MACD, EMA-200)...{Style.RESET_ALL}")
        signals: List[SignalResult] = []
        scanned = 0
        errors = 0

        for i, symbol in enumerate(symbols, 1):
            try:
                df = self.fetcher.get_klines(symbol)
                if df is None or df.empty:
                    errors += 1
                    continue

                df = compute_indicators(df)
                result = detect_signal(symbol, df)
                if result:
                    signals.append(result)
                scanned += 1

                # Progress indicator every 10 symbols
                if i % 10 == 0 or i == len(symbols):
                    pct = (i / len(symbols)) * 100
                    print(f"  Scanned {i}/{len(symbols)} ({pct:.0f}%)", end="\r")

            except Exception as e:
                errors += 1
                logger.debug(f"Error processing {symbol}: {e}")
                continue

        print(f"  {Fore.GREEN}✓{Style.RESET_ALL} Scanned {scanned} symbols, {errors} errors")

        # Step 3: Display results + Telegram
        print(f"{Fore.WHITE}[3/{total_steps}] Signal results:{Style.RESET_ALL}\n")
        self._display_signals(signals)

        if signals:
            print(f"\n{Fore.WHITE}[→] Sending Telegram notification...{Style.RESET_ALL}", end=" ")
            if self.notifier.send_signals(signals):
                print(f"{Fore.GREEN}✓ Sent!{Style.RESET_ALL}")
            else:
                if self.notifier.enabled:
                    print(f"{Fore.RED}✗ Failed{Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}⊘ Disabled{Style.RESET_ALL}")

        # Step 4: Auto-trade execution (if enabled)
        if self.trader.enabled and signals:
            print(f"\n{Fore.WHITE}[4/{total_steps}] Executing auto-trades on TESTNET...{Style.RESET_ALL}")
            trade_results = self._execute_trades(signals)
            self._display_trade_results(trade_results)
            self._notify_trades(trade_results)

        return signals

    # ══════════════════════════════════════════════════════════════════════
    #  AUTO-TRADE EXECUTION
    # ══════════════════════════════════════════════════════════════════════

    def _execute_trades(self, signals: List[SignalResult]) -> List[TradeResult]:
        """Execute trades for all detected signals."""
        results: List[TradeResult] = []

        for signal in signals:
            try:
                result = self.trader.execute_signal(signal)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"Trade execution failed for {signal.symbol}: {e}")

        return results

    def _display_trade_results(self, results: List[TradeResult]):
        """Display trade execution results in a table."""
        if not results:
            print(f"  {Fore.YELLOW}⚠  No trades executed.{Style.RESET_ALL}")
            return

        table_data = []
        for r in results:
            if r.error:
                status = f"{Fore.RED}✗ {r.error[:30]}{Style.RESET_ALL}"
            else:
                status = f"{Fore.GREEN}✓ Filled{Style.RESET_ALL}"

            signal_color = Fore.GREEN if r.signal == "LONG" else Fore.RED
            table_data.append([
                f"{Fore.WHITE}{r.symbol}{Style.RESET_ALL}",
                f"{signal_color}{r.signal}{Style.RESET_ALL}",
                f"${r.entry_price:,.4f}" if r.entry_price else "—",
                f"{r.quantity}" if r.quantity else "—",
                f"${r.tp_price:,.4f}" if r.tp_price else "—",
                f"${r.sl_price:,.4f}" if r.sl_price else "—",
                status,
            ])

        headers = [
            f"{Fore.CYAN}Symbol{Style.RESET_ALL}",
            f"{Fore.CYAN}Side{Style.RESET_ALL}",
            f"{Fore.CYAN}Entry{Style.RESET_ALL}",
            f"{Fore.CYAN}Qty{Style.RESET_ALL}",
            f"{Fore.CYAN}TP ({config.TAKE_PROFIT_PCT}%){Style.RESET_ALL}",
            f"{Fore.CYAN}SL ({config.STOP_LOSS_PCT}%){Style.RESET_ALL}",
            f"{Fore.CYAN}Status{Style.RESET_ALL}",
        ]

        print(f"\n  {Fore.CYAN}Trade Execution Results:{Style.RESET_ALL}")
        print(tabulate(table_data, headers=headers, tablefmt="rounded_grid", stralign="right"))

        filled = sum(1 for r in results if not r.error)
        failed = sum(1 for r in results if r.error)
        print(f"\n  Filled: {Fore.GREEN}{filled}{Style.RESET_ALL} │ Failed: {Fore.RED}{failed}{Style.RESET_ALL}")

    def _notify_trades(self, results: List[TradeResult]):
        """Send trade execution results to Telegram."""
        filled = [r for r in results if not r.error]
        if not filled or not self.notifier.enabled:
            return

        lines = [
            "━━━━━━━━━━━━━━━━━━━━━",
            "⚡ <b>AUTO-TRADE EXECUTED</b> (Testnet)",
            "━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]

        for r in filled:
            icon = "🟢" if r.signal == "LONG" else "🔴"
            lines.append(
                f"{icon} <b>{r.symbol}</b> — {r.signal}\n"
                f"    📊 Entry: <code>${r.entry_price:,.4f}</code>\n"
                f"    📦 Qty: <code>{r.quantity}</code>\n"
                f"    💰 Notional: <code>${r.notional_usdt:,.2f}</code>\n"
                f"    🎯 TP: <code>${r.tp_price:,.4f}</code> (+{config.TAKE_PROFIT_PCT}%)\n"
                f"    🛡️ SL: <code>${r.sl_price:,.4f}</code> (-{config.STOP_LOSS_PCT}%)\n"
                f"    ⚙️ Leverage: {r.leverage}x | Margin: ${r.margin_usdt}"
            )
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"<i>📝 Total trades: {len(filled)}</i>")

        self.notifier._send_message("\n".join(lines))

    # ══════════════════════════════════════════════════════════════════════
    #  SIGNAL DISPLAY (unchanged from before)
    # ══════════════════════════════════════════════════════════════════════

    def _display_signals(self, signals: List[SignalResult]):
        """Pretty-print detected signals as a formatted table."""
        if not signals:
            print(f"  {Fore.YELLOW}⚠  No signals detected in this scan.{Style.RESET_ALL}")
            print(f"     Criteria: RSI {'<'}{config.RSI_OVERSOLD} or {'>'}{config.RSI_OVERBOUGHT} "
                  f"+ MACD crossover"
                  f"{' + EMA-200 filter' if config.USE_EMA_FILTER else ''}")
            return

        # Prepare table data
        table_data = []
        for s in signals:
            ema_status = (
                f"{Fore.GREEN}✓ Above{Style.RESET_ALL}" if s.ema_confirmed and "LONG" in s.signal
                else f"{Fore.RED}✓ Below{Style.RESET_ALL}" if s.ema_confirmed and "SHORT" in s.signal
                else f"{Fore.YELLOW}✗{Style.RESET_ALL}"
            )
            table_data.append([
                f"{Fore.WHITE}{s.symbol}{Style.RESET_ALL}",
                s.signal,
                f"${s.price:,.4f}",
                f"{s.rsi:.2f}",
                f"{s.macd:.6f}",
                f"{s.macd_signal:.6f}",
                ema_status,
            ])

        headers = [
            f"{Fore.CYAN}Symbol{Style.RESET_ALL}",
            f"{Fore.CYAN}Signal{Style.RESET_ALL}",
            f"{Fore.CYAN}Price{Style.RESET_ALL}",
            f"{Fore.CYAN}RSI{Style.RESET_ALL}",
            f"{Fore.CYAN}MACD{Style.RESET_ALL}",
            f"{Fore.CYAN}MACD Signal{Style.RESET_ALL}",
            f"{Fore.CYAN}EMA-200{Style.RESET_ALL}",
        ]

        print(tabulate(table_data, headers=headers, tablefmt="rounded_grid", stralign="right"))
        print(f"\n  Total signals: {Fore.GREEN}{len(signals)}{Style.RESET_ALL}")
        print(f"  LONG: {sum(1 for s in signals if 'LONG' in s.signal)} │ "
              f"SHORT: {sum(1 for s in signals if 'SHORT' in s.signal)}")
