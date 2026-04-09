"""
Data Fetcher Module
───────────────────
Handles all interactions with the Binance Futures API:
  • Fetches available USDT-margined symbols
  • Retrieves 24h ticker data for volume ranking
  • Downloads historical kline (candlestick) data
"""

import time
import logging
from typing import List, Dict, Optional

import pandas as pd
import requests.exceptions
from binance.client import Client
from binance.exceptions import BinanceAPIException

import config

logger = logging.getLogger(__name__)


class BinanceDataFetcher:
    """Encapsulates Binance Futures market data retrieval with retry logic."""

    def __init__(self):
        self.client = Client(
            api_key=config.API_KEY or "",
            api_secret=config.API_SECRET or "",
        )
        # Switch to futures endpoints
        self.client.API_URL = "https://fapi.binance.com/fapi"

    # ── Retry wrapper ──────────────────────────────────────────────────────
    def _retry(self, func, *args, **kwargs):
        """Execute `func` with exponential backoff on transient errors."""
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except BinanceAPIException as e:
                if e.status_code == 429:  # Rate limit
                    wait = config.RETRY_BACKOFF * attempt
                    logger.warning(
                        f"Rate limited (429). Backing off {wait}s "
                        f"(attempt {attempt}/{config.MAX_RETRIES})"
                    )
                    time.sleep(wait)
                elif e.status_code >= 500:  # Server error
                    wait = config.RETRY_BACKOFF * attempt
                    logger.warning(
                        f"Server error {e.status_code}. Retrying in {wait}s "
                        f"(attempt {attempt}/{config.MAX_RETRIES})"
                    )
                    time.sleep(wait)
                else:
                    logger.error(f"Binance API error: {e}")
                    raise
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                ConnectionError,
                OSError,
            ) as e:
                wait = config.RETRY_BACKOFF * attempt
                logger.warning(
                    f"Network error: {type(e).__name__}. Retrying in {wait}s "
                    f"(attempt {attempt}/{config.MAX_RETRIES})"
                )
                time.sleep(wait)
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                raise
        logger.error(f"Max retries ({config.MAX_RETRIES}) exceeded for {func.__name__}")
        return None

    # ── Universe Selection ─────────────────────────────────────────────────
    def get_top_symbols(self, top_n: int = None) -> List[str]:
        """
        Return the top N USDT-margined futures symbols ranked by 24h quote volume.

        Steps:
        1. Fetch all futures exchange info to find USDT-margined perpetual contracts.
        2. Fetch 24h tickers for volume data.
        3. Filter, rank, and return the top symbols.
        """
        top_n = top_n or config.TOP_N_COINS

        # Step 1: Get valid perpetual USDT-margined symbols
        info = self._retry(self.client.futures_exchange_info)
        if not info:
            logger.error("Failed to fetch exchange info")
            return []

        valid_symbols = set()
        for s in info["symbols"]:
            if (
                s.get("quoteAsset") == config.QUOTE_ASSET
                and s.get("contractType") == "PERPETUAL"
                and s.get("status") == "TRADING"
            ):
                valid_symbols.add(s["symbol"])

        logger.info(f"Found {len(valid_symbols)} active USDT perpetual contracts")

        # Step 2: Fetch 24h tickers
        tickers = self._retry(self.client.futures_ticker)
        if not tickers:
            logger.error("Failed to fetch 24h tickers")
            return []

        # Step 3: Filter & rank by quoteVolume
        volume_data: List[Dict] = []
        for t in tickers:
            sym = t["symbol"]
            if sym in valid_symbols:
                try:
                    volume_data.append({
                        "symbol": sym,
                        "quoteVolume": float(t["quoteVolume"]),
                    })
                except (KeyError, ValueError):
                    continue

        volume_data.sort(key=lambda x: x["quoteVolume"], reverse=True)
        top_symbols = [d["symbol"] for d in volume_data[:top_n]]

        logger.info(
            f"Top {top_n} symbols selected. "
            f"Highest volume: {volume_data[0]['symbol']} "
            f"(${volume_data[0]['quoteVolume']:,.0f})"
        )
        return top_symbols

    # ── Kline / Candlestick Data ───────────────────────────────────────────
    def get_klines(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Fetch historical klines for a symbol and return as a clean DataFrame.

        Columns: open, high, low, close, volume (all float64).
        Index: datetime (UTC).
        """
        time.sleep(config.API_CALL_DELAY)  # Throttle to avoid rate limits

        raw = self._retry(
            self.client.futures_klines,
            symbol=symbol,
            interval=config.KLINE_INTERVAL,
            limit=config.KLINE_LIMIT,
        )
        if not raw:
            logger.warning(f"Failed to fetch klines for {symbol}")
            return None

        df = pd.DataFrame(raw, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ])

        # Convert to proper types
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df.set_index("open_time", inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        # Keep only what we need
        df = df[["open", "high", "low", "close", "volume"]]
        return df
