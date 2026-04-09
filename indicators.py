"""
Technical Indicators Module
────────────────────────────
Computes RSI, MACD, and EMA on a DataFrame of OHLCV candles,
then evaluates LONG / SHORT signal conditions.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import ta

import config

logger = logging.getLogger(__name__)


@dataclass
class SignalResult:
    """Container for a detected signal on a single symbol."""
    symbol: str
    signal: str          # "LONG" or "SHORT"
    price: float
    rsi: float
    macd: float
    macd_signal: float
    ema_200: float
    ema_confirmed: bool  # True if EMA trend aligns with signal direction


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Append RSI, MACD (line, signal, histogram), and EMA-200 columns
    to the given OHLCV DataFrame.
    """
    # RSI
    df["rsi"] = ta.momentum.RSIIndicator(
        close=df["close"], window=config.RSI_PERIOD
    ).rsi()

    # MACD
    macd_obj = ta.trend.MACD(
        close=df["close"],
        window_slow=config.MACD_SLOW,
        window_fast=config.MACD_FAST,
        window_sign=config.MACD_SIGNAL,
    )
    df["macd"] = macd_obj.macd()
    df["macd_signal"] = macd_obj.macd_signal()
    df["macd_hist"] = macd_obj.macd_diff()

    # EMA 200 (trend filter)
    df["ema_200"] = ta.trend.EMAIndicator(
        close=df["close"], window=config.EMA_TREND_PERIOD
    ).ema_indicator()

    return df


def detect_signal(symbol: str, df: pd.DataFrame) -> Optional[SignalResult]:
    """
    Evaluate the most recent 2 candles for LONG or SHORT conditions.

    LONG conditions:
      1. RSI < 30 (oversold)
      2. MACD bullish crossover (prev hist ≤ 0 AND current hist > 0)
      3. (Optional) Close > EMA 200

    SHORT conditions:
      1. RSI > 70 (overbought)
      2. MACD bearish crossover (prev hist ≥ 0 AND current hist < 0)
      3. (Optional) Close < EMA 200
    """
    if df is None or len(df) < 2:
        return None

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    price = curr["close"]
    rsi = curr["rsi"]
    macd_val = curr["macd"]
    macd_sig = curr["macd_signal"]
    ema_200 = curr["ema_200"]

    # Skip if indicators contain NaN
    if pd.isna(rsi) or pd.isna(macd_val) or pd.isna(ema_200):
        return None

    macd_hist_curr = curr["macd_hist"]
    macd_hist_prev = prev["macd_hist"]

    # ── LONG check ─────────────────────────────────────────────────────
    rsi_oversold = rsi < config.RSI_OVERSOLD
    macd_bullish_cross = (macd_hist_prev <= 0) and (macd_hist_curr > 0)
    ema_long_ok = price > ema_200

    if rsi_oversold and macd_bullish_cross:
        if not config.USE_EMA_FILTER or ema_long_ok:
            return SignalResult(
                symbol=symbol,
                signal="🟢 LONG",
                price=price,
                rsi=rsi,
                macd=macd_val,
                macd_signal=macd_sig,
                ema_200=ema_200,
                ema_confirmed=ema_long_ok,
            )

    # ── SHORT check ────────────────────────────────────────────────────
    rsi_overbought = rsi > config.RSI_OVERBOUGHT
    macd_bearish_cross = (macd_hist_prev >= 0) and (macd_hist_curr < 0)
    ema_short_ok = price < ema_200

    if rsi_overbought and macd_bearish_cross:
        if not config.USE_EMA_FILTER or ema_short_ok:
            return SignalResult(
                symbol=symbol,
                signal="🔴 SHORT",
                price=price,
                rsi=rsi,
                macd=macd_val,
                macd_signal=macd_sig,
                ema_200=ema_200,
                ema_confirmed=ema_short_ok,
            )

    return None
