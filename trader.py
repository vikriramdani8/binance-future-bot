"""
Auto-Trade Execution Module (Testnet)
──────────────────────────────────────
Handles all order execution on Binance Futures Testnet:
  • Testnet client initialization
  • Symbol precision (tick size, step size, min notional)
  • Margin type & leverage setup
  • Position size calculation from fixed USDT margin
  • Market order execution (LONG / SHORT)
  • Bracket orders (Take Profit + Stop Loss)
  • Open position checking (duplicate prevention)
  • Trade notification via Telegram
"""

import math
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import requests.exceptions
from binance.client import Client
from binance.exceptions import BinanceAPIException

import config
from indicators import SignalResult

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """Container for an executed trade."""
    symbol: str
    side: str               # "BUY" or "SELL"
    signal: str             # "LONG" or "SHORT"
    quantity: float
    entry_price: float
    tp_price: float
    sl_price: float
    leverage: int
    margin_usdt: float
    notional_usdt: float
    order_id: int
    tp_order_id: Optional[int] = None
    sl_order_id: Optional[int] = None
    error: Optional[str] = None


class FuturesTrader:
    """
    Executes trades on Binance Futures Testnet based on screener signals.

    Architecture:
      1. Connects to Testnet via separate Client instance
      2. Caches symbol precision info (tick_size, step_size, min_qty)
      3. Before each trade: checks open positions, sets margin/leverage
      4. Executes market entry → places TP & SL bracket orders
    """

    def __init__(self):
        self.enabled = config.AUTO_TRADE_ENABLED
        self.client: Optional[Client] = None
        self._symbol_info_cache: Dict[str, Dict] = {}

        if not self.enabled:
            logger.info("Auto-trade is DISABLED")
            return

        if not config.TESTNET_API_KEY or not config.TESTNET_API_SECRET:
            logger.error(
                "Auto-trade enabled but TESTNET_API_KEY or TESTNET_API_SECRET is empty. "
                "Disabling auto-trade."
            )
            self.enabled = False
            return

        # Initialize Testnet client
        try:
            self.client = Client(
                api_key=config.TESTNET_API_KEY,
                api_secret=config.TESTNET_API_SECRET,
                testnet=True,
            )
            # Override to futures testnet
            self.client.API_URL = config.TESTNET_BASE_URL + "/fapi"
            logger.info(f"Testnet client initialized → {config.TESTNET_BASE_URL}")

            # Pre-load symbol info
            self._load_symbol_info()

        except Exception as e:
            logger.error(f"Failed to initialize testnet client: {e}")
            self.enabled = False

    # ══════════════════════════════════════════════════════════════════════
    #  SYMBOL PRECISION INFO
    # ══════════════════════════════════════════════════════════════════════

    def _load_symbol_info(self):
        """
        Load exchange info and cache precision data for all USDT perpetual symbols.
        Extracts: pricePrecision, quantityPrecision, tickSize, stepSize, minQty, minNotional.
        """
        try:
            info = self.client.futures_exchange_info()
            for s in info["symbols"]:
                if s.get("quoteAsset") != "USDT" or s.get("status") != "TRADING":
                    continue

                symbol = s["symbol"]
                filters = {f["filterType"]: f for f in s.get("filters", [])}

                price_filter = filters.get("PRICE_FILTER", {})
                lot_filter = filters.get("LOT_SIZE", {})
                min_notional = filters.get("MIN_NOTIONAL", {})

                self._symbol_info_cache[symbol] = {
                    "pricePrecision": s.get("pricePrecision", 2),
                    "quantityPrecision": s.get("quantityPrecision", 3),
                    "tickSize": float(price_filter.get("tickSize", "0.01")),
                    "stepSize": float(lot_filter.get("stepSize", "0.001")),
                    "minQty": float(lot_filter.get("minQty", "0.001")),
                    "maxQty": float(lot_filter.get("maxQty", "1000000")),
                    "minNotional": float(min_notional.get("notional", "5")),
                }

            logger.info(f"Cached precision info for {len(self._symbol_info_cache)} symbols")

        except Exception as e:
            logger.error(f"Failed to load symbol info: {e}")

    def _get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get cached symbol precision info."""
        info = self._symbol_info_cache.get(symbol)
        if not info:
            logger.warning(f"No precision info for {symbol}. Reloading...")
            self._load_symbol_info()
            info = self._symbol_info_cache.get(symbol)
        return info

    # ══════════════════════════════════════════════════════════════════════
    #  PRECISION HELPERS
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _round_step(value: float, step: float) -> float:
        """Round a value down to the nearest step increment."""
        precision = max(0, int(round(-math.log10(step))))
        return round(math.floor(value / step) * step, precision)

    @staticmethod
    def _round_tick(value: float, tick: float) -> float:
        """Round a price to the nearest tick size."""
        precision = max(0, int(round(-math.log10(tick))))
        return round(round(value / tick) * tick, precision)

    # ══════════════════════════════════════════════════════════════════════
    #  POSITION & MARGIN MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════

    def get_open_positions(self) -> List[Dict]:
        """Get all currently open positions (positionAmt != 0)."""
        try:
            positions = self.client.futures_position_information()
            open_pos = []
            for p in positions:
                amt = float(p.get("positionAmt", 0))
                if amt != 0:
                    open_pos.append({
                        "symbol": p["symbol"],
                        "side": "LONG" if amt > 0 else "SHORT",
                        "quantity": abs(amt),
                        "entryPrice": float(p.get("entryPrice", 0)),
                        "unrealizedPnl": float(p.get("unRealizedProfit", 0)),
                        "leverage": int(p.get("leverage", 1)),
                        "marginType": p.get("marginType", ""),
                    })
            return open_pos
        except Exception as e:
            logger.error(f"Failed to fetch open positions: {e}")
            return []

    def has_open_position(self, symbol: str) -> bool:
        """Check if there's already an open position for this symbol."""
        positions = self.get_open_positions()
        return any(p["symbol"] == symbol for p in positions)

    def _setup_margin_and_leverage(self, symbol: str) -> bool:
        """
        Set margin type to ISOLATED and leverage before trading.
        Returns True on success.
        """
        # Set margin type
        try:
            self.client.futures_change_margin_type(
                symbol=symbol,
                marginType=config.MARGIN_TYPE,
            )
            logger.debug(f"{symbol}: Margin type set to {config.MARGIN_TYPE}")
        except BinanceAPIException as e:
            # -4046 = "No need to change margin type" (already set)
            if e.code == -4046:
                logger.debug(f"{symbol}: Margin type already {config.MARGIN_TYPE}")
            else:
                logger.error(f"{symbol}: Failed to set margin type: {e}")
                return False

        # Set leverage
        try:
            self.client.futures_change_leverage(
                symbol=symbol,
                leverage=config.LEVERAGE,
            )
            logger.debug(f"{symbol}: Leverage set to {config.LEVERAGE}x")
        except BinanceAPIException as e:
            logger.error(f"{symbol}: Failed to set leverage: {e}")
            return False

        return True

    # ══════════════════════════════════════════════════════════════════════
    #  POSITION SIZING
    # ══════════════════════════════════════════════════════════════════════

    def _calculate_quantity(self, symbol: str, price: float) -> Optional[float]:
        """
        Calculate order quantity from fixed USDT margin.

        Formula:
          notional = margin * leverage
          quantity = notional / price
          quantity = round_down(quantity, stepSize)

        Validates against:
          - minQty / maxQty
          - minNotional
        """
        info = self._get_symbol_info(symbol)
        if not info:
            logger.error(f"{symbol}: Cannot calculate qty — no symbol info")
            return None

        notional = config.MARGIN_PER_TRADE_USDT * config.LEVERAGE
        raw_qty = notional / price

        # Round down to step size
        qty = self._round_step(raw_qty, info["stepSize"])

        # Validate
        if qty < info["minQty"]:
            logger.warning(
                f"{symbol}: Calculated qty {qty} < minQty {info['minQty']}. "
                f"Increase MARGIN_PER_TRADE_USDT or LEVERAGE."
            )
            return None

        if qty > info["maxQty"]:
            qty = self._round_step(info["maxQty"], info["stepSize"])

        actual_notional = qty * price
        if actual_notional < info["minNotional"]:
            logger.warning(
                f"{symbol}: Notional ${actual_notional:.2f} < minNotional ${info['minNotional']}. "
                f"Increase MARGIN_PER_TRADE_USDT or LEVERAGE."
            )
            return None

        return qty

    # ══════════════════════════════════════════════════════════════════════
    #  ORDER EXECUTION
    # ══════════════════════════════════════════════════════════════════════

    def execute_signal(self, signal: SignalResult) -> Optional[TradeResult]:
        """
        Full trade execution pipeline for a signal:
          1. Safety check — skip if position already open
          2. Setup margin type & leverage
          3. Calculate position size
          4. Execute market entry order
          5. Place TP & SL bracket orders
        """
        if not self.enabled:
            return None

        symbol = signal.symbol
        is_long = "LONG" in signal.signal
        direction = "LONG" if is_long else "SHORT"
        entry_side = "BUY" if is_long else "SELL"
        close_side = "SELL" if is_long else "BUY"

        logger.info(f"{'─' * 50}")
        logger.info(f"⚡ Executing {direction} signal for {symbol}")

        # ── Step 1: Duplicate check ────────────────────────────────────
        if self.has_open_position(symbol):
            logger.warning(f"{symbol}: Position already open — SKIPPING")
            return TradeResult(
                symbol=symbol, side=entry_side, signal=direction,
                quantity=0, entry_price=0, tp_price=0, sl_price=0,
                leverage=config.LEVERAGE, margin_usdt=0, notional_usdt=0,
                order_id=0, error="Position already open"
            )

        # ── Step 2: Check max positions ────────────────────────────────
        open_positions = self.get_open_positions()
        if len(open_positions) >= config.MAX_OPEN_POSITIONS:
            logger.warning(
                f"Max open positions ({config.MAX_OPEN_POSITIONS}) reached — SKIPPING {symbol}"
            )
            return TradeResult(
                symbol=symbol, side=entry_side, signal=direction,
                quantity=0, entry_price=0, tp_price=0, sl_price=0,
                leverage=config.LEVERAGE, margin_usdt=0, notional_usdt=0,
                order_id=0, error=f"Max positions ({config.MAX_OPEN_POSITIONS}) reached"
            )

        # ── Step 3: Setup margin & leverage ────────────────────────────
        if not self._setup_margin_and_leverage(symbol):
            return TradeResult(
                symbol=symbol, side=entry_side, signal=direction,
                quantity=0, entry_price=0, tp_price=0, sl_price=0,
                leverage=config.LEVERAGE, margin_usdt=0, notional_usdt=0,
                order_id=0, error="Failed to set margin/leverage"
            )

        # ── Step 4: Calculate quantity ─────────────────────────────────
        price = signal.price
        qty = self._calculate_quantity(symbol, price)
        if qty is None:
            return TradeResult(
                symbol=symbol, side=entry_side, signal=direction,
                quantity=0, entry_price=price, tp_price=0, sl_price=0,
                leverage=config.LEVERAGE, margin_usdt=config.MARGIN_PER_TRADE_USDT,
                notional_usdt=0, order_id=0, error="Quantity calculation failed"
            )

        notional = qty * price
        logger.info(
            f"{symbol}: {direction} | Qty={qty} | Price≈${price:,.4f} | "
            f"Notional=${notional:,.2f} | Margin=${config.MARGIN_PER_TRADE_USDT} | "
            f"Leverage={config.LEVERAGE}x"
        )

        # ── Step 5: Execute market entry ───────────────────────────────
        try:
            entry_order = self.client.futures_create_order(
                symbol=symbol,
                side=entry_side,
                type="MARKET",
                quantity=qty,
            )
            order_id = entry_order.get("orderId", 0)
            logger.info(f"{symbol}: Market {entry_side} filled — Order ID: {order_id}")

        except BinanceAPIException as e:
            error_msg = self._handle_order_error(symbol, e)
            return TradeResult(
                symbol=symbol, side=entry_side, signal=direction,
                quantity=qty, entry_price=price, tp_price=0, sl_price=0,
                leverage=config.LEVERAGE, margin_usdt=config.MARGIN_PER_TRADE_USDT,
                notional_usdt=notional, order_id=0, error=error_msg
            )

        # ── Step 6: Get actual fill price ──────────────────────────────
        time.sleep(0.5)  # Small delay to ensure position is reflected
        entry_price = self._get_avg_fill_price(symbol, order_id, fallback=price)

        # ── Step 7: Place TP & SL bracket orders ──────────────────────
        info = self._get_symbol_info(symbol)
        tick_size = info["tickSize"] if info else 0.01

        tp_price, sl_price = self._calculate_tp_sl(entry_price, is_long, tick_size)

        tp_order_id = self._place_tp_order(symbol, close_side, qty, tp_price)
        sl_order_id = self._place_sl_order(symbol, close_side, qty, sl_price)

        result = TradeResult(
            symbol=symbol, side=entry_side, signal=direction,
            quantity=qty, entry_price=entry_price,
            tp_price=tp_price, sl_price=sl_price,
            leverage=config.LEVERAGE,
            margin_usdt=config.MARGIN_PER_TRADE_USDT,
            notional_usdt=qty * entry_price,
            order_id=order_id,
            tp_order_id=tp_order_id,
            sl_order_id=sl_order_id,
        )

        logger.info(
            f"{symbol}: Trade complete — Entry=${entry_price:,.4f} | "
            f"TP=${tp_price:,.4f} | SL=${sl_price:,.4f}"
        )

        return result

    # ══════════════════════════════════════════════════════════════════════
    #  TP / SL CALCULATION & PLACEMENT
    # ══════════════════════════════════════════════════════════════════════

    def _calculate_tp_sl(self, entry: float, is_long: bool, tick_size: float):
        """Calculate Take Profit and Stop Loss prices."""
        tp_pct = config.TAKE_PROFIT_PCT / 100
        sl_pct = config.STOP_LOSS_PCT / 100

        if is_long:
            tp_price = entry * (1 + tp_pct)
            sl_price = entry * (1 - sl_pct)
        else:
            tp_price = entry * (1 - tp_pct)
            sl_price = entry * (1 + sl_pct)

        tp_price = self._round_tick(tp_price, tick_size)
        sl_price = self._round_tick(sl_price, tick_size)

        return tp_price, sl_price

    def _place_tp_order(self, symbol: str, side: str, qty: float, price: float) -> Optional[int]:
        """Place a Take Profit limit order (reduceOnly)."""
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type="TAKE_PROFIT_MARKET",
                stopPrice=price,
                closePosition="true",
                timeInForce="GTE_GTC",
                workingType="MARK_PRICE",
            )
            order_id = order.get("orderId", 0)
            logger.info(f"{symbol}: TP order placed @ ${price:,.4f} — ID: {order_id}")
            return order_id
        except BinanceAPIException as e:
            logger.error(f"{symbol}: Failed to place TP order: {e}")
            # Fallback: try LIMIT order with reduceOnly
            return self._place_tp_fallback(symbol, side, qty, price)

    def _place_tp_fallback(self, symbol: str, side: str, qty: float, price: float) -> Optional[int]:
        """Fallback TP using LIMIT order with reduceOnly."""
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type="LIMIT",
                price=price,
                quantity=qty,
                timeInForce="GTC",
                reduceOnly="true",
            )
            order_id = order.get("orderId", 0)
            logger.info(f"{symbol}: TP fallback LIMIT order @ ${price:,.4f} — ID: {order_id}")
            return order_id
        except BinanceAPIException as e:
            logger.error(f"{symbol}: TP fallback also failed: {e}")
            return None

    def _place_sl_order(self, symbol: str, side: str, qty: float, price: float) -> Optional[int]:
        """Place a Stop Loss market order (reduceOnly)."""
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type="STOP_MARKET",
                stopPrice=price,
                closePosition="true",
                timeInForce="GTE_GTC",
                workingType="MARK_PRICE",
            )
            order_id = order.get("orderId", 0)
            logger.info(f"{symbol}: SL order placed @ ${price:,.4f} — ID: {order_id}")
            return order_id
        except BinanceAPIException as e:
            logger.error(f"{symbol}: Failed to place SL order: {e}")
            # Fallback: try STOP_MARKET with reduceOnly and quantity
            return self._place_sl_fallback(symbol, side, qty, price)

    def _place_sl_fallback(self, symbol: str, side: str, qty: float, price: float) -> Optional[int]:
        """Fallback SL using STOP_MARKET with reduceOnly + quantity."""
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type="STOP_MARKET",
                stopPrice=price,
                quantity=qty,
                timeInForce="GTE_GTC",
                reduceOnly="true",
                workingType="MARK_PRICE",
            )
            order_id = order.get("orderId", 0)
            logger.info(f"{symbol}: SL fallback order @ ${price:,.4f} — ID: {order_id}")
            return order_id
        except BinanceAPIException as e:
            logger.error(f"{symbol}: SL fallback also failed: {e}")
            return None

    # ══════════════════════════════════════════════════════════════════════
    #  UTILITY METHODS
    # ══════════════════════════════════════════════════════════════════════

    def _get_avg_fill_price(self, symbol: str, order_id: int, fallback: float) -> float:
        """Get the average fill price from an executed order."""
        try:
            order = self.client.futures_get_order(symbol=symbol, orderId=order_id)
            avg_price = float(order.get("avgPrice", 0))
            if avg_price > 0:
                return avg_price
        except Exception as e:
            logger.debug(f"Could not fetch fill price for {symbol}: {e}")
        return fallback

    def _handle_order_error(self, symbol: str, error: BinanceAPIException) -> str:
        """Map common Binance error codes to actionable messages."""
        code = error.code
        msg = error.message

        error_map = {
            -1111: f"Precision error — check tick/step size for {symbol}",
            -2019: "Insufficient margin — increase MARGIN_PER_TRADE_USDT or check balance",
            -4003: "Quantity too small — increase MARGIN_PER_TRADE_USDT or LEVERAGE",
            -4014: f"Price precision error for {symbol}",
            -4015: f"Invalid price for {symbol} — outside allowed range",
            -2022: "TP/SL order rejected — reduceOnly failed",
            -1102: "Mandatory parameter missing in order request",
            -1015: "Too many orders — rate limited",
            -4164: "Min notional not met — increase trade size",
        }

        readable = error_map.get(code, f"Binance error {code}: {msg}")
        logger.error(f"{symbol}: {readable}")
        return readable

    def get_account_balance(self) -> Optional[float]:
        """Get USDT balance on testnet account."""
        try:
            balances = self.client.futures_account_balance()
            for b in balances:
                if b["asset"] == "USDT":
                    return float(b.get("availableBalance", 0))
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
        return None
