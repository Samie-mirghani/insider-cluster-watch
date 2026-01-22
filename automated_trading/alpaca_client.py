# automated_trading/alpaca_client.py
"""
Alpaca API Client Wrapper

Provides a safe, robust interface to Alpaca trading API with:
- Automatic retry logic with exponential backoff
- Comprehensive error handling
- Market hours validation
- Rate limiting protection
- Audit logging
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from decimal import Decimal

# Alpaca SDK
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        MarketOrderRequest,
        LimitOrderRequest,
        StopLimitOrderRequest,
        GetOrdersRequest
    )
    from alpaca.trading.enums import (
        OrderSide,
        OrderType,
        TimeInForce,
        OrderStatus,
        QueryOrderStatus
    )
    from alpaca.common.exceptions import APIError
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    APIError = Exception  # Fallback

from . import config
from .utils import log_audit_event

logger = logging.getLogger(__name__)


class AlpacaClientError(Exception):
    """Custom exception for Alpaca client errors."""
    pass


class AlpacaTradingClient:
    """
    Safe wrapper around Alpaca Trading API.

    Features:
    - Automatic connection management
    - Retry logic with exponential backoff
    - Market hours validation
    - Account and position queries
    - Order submission with safety checks
    """

    def __init__(self, paper: bool = True):
        """
        Initialize Alpaca client.

        Args:
            paper: If True, use paper trading API. If False, use live API.
        """
        if not ALPACA_AVAILABLE:
            raise AlpacaClientError(
                "Alpaca SDK not installed. Run: pip install alpaca-py"
            )

        self.paper = paper
        self.client = None
        self._last_account_fetch = None
        self._cached_account = None
        self._connect()

    def _connect(self):
        """Establish connection to Alpaca API."""
        creds = config.get_api_credentials()

        if not creds['api_key'] or not creds['secret_key']:
            raise AlpacaClientError(
                f"Missing API credentials for {'paper' if self.paper else 'live'} trading. "
                f"Set ALPACA_{'PAPER' if self.paper else 'LIVE'}_API_KEY and "
                f"ALPACA_{'PAPER' if self.paper else 'LIVE'}_SECRET_KEY environment variables."
            )

        try:
            self.client = TradingClient(
                api_key=creds['api_key'],
                secret_key=creds['secret_key'],
                paper=self.paper
            )
            logger.info(f"Connected to Alpaca {'paper' if self.paper else 'LIVE'} trading API")

            # Verify connection by fetching account
            account = self.get_account()
            logger.info(f"Account verified: ${float(account.portfolio_value):,.2f} portfolio value")

        except Exception as e:
            raise AlpacaClientError(f"Failed to connect to Alpaca API: {e}")

    def _retry_operation(self, operation, operation_name: str, max_retries: int = 3):
        """
        Execute an operation with retry logic.

        Args:
            operation: Callable to execute
            operation_name: Name for logging
            max_retries: Maximum retry attempts

        Returns:
            Result of the operation
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                result = operation()
                return result
            except APIError as e:
                last_error = e
                error_str = str(e)

                # Don't retry certain errors
                if '403' in error_str or 'forbidden' in error_str.lower():
                    logger.error(f"{operation_name} forbidden: {e}")
                    raise
                if '404' in error_str:
                    logger.error(f"{operation_name} not found: {e}")
                    raise

                # Retry with backoff
                wait_time = 2 ** attempt
                logger.warning(
                    f"{operation_name} failed (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)

            except Exception as e:
                last_error = e
                wait_time = 2 ** attempt
                logger.warning(
                    f"{operation_name} error (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)

        raise AlpacaClientError(f"{operation_name} failed after {max_retries} attempts: {last_error}")

    # =========================================================================
    # Account Operations
    # =========================================================================

    def get_account(self, force_refresh: bool = False):
        """
        Get account information with caching.

        Args:
            force_refresh: If True, bypass cache

        Returns:
            Account object with balance, buying power, etc.
        """
        # Use cache if recent (< 60 seconds)
        if not force_refresh and self._cached_account:
            if self._last_account_fetch and \
               (datetime.now() - self._last_account_fetch).seconds < 60:
                return self._cached_account

        account = self._retry_operation(
            lambda: self.client.get_account(),
            "Get account"
        )

        self._cached_account = account
        self._last_account_fetch = datetime.now()

        return account

    def get_portfolio_value(self) -> float:
        """Get current portfolio value."""
        account = self.get_account(force_refresh=True)
        return float(account.portfolio_value)

    def get_cash(self) -> float:
        """Get available cash."""
        account = self.get_account(force_refresh=True)
        return float(account.cash)

    def get_buying_power(self) -> float:
        """Get buying power (may differ from cash for margin accounts)."""
        account = self.get_account(force_refresh=True)
        return float(account.buying_power)

    # =========================================================================
    # Market Status
    # =========================================================================

    def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        try:
            clock = self._retry_operation(
                lambda: self.client.get_clock(),
                "Get market clock"
            )
            return clock.is_open
        except Exception as e:
            logger.error(f"Failed to get market clock: {e}")
            return False

    def get_market_clock(self) -> Dict[str, Any]:
        """Get market clock with open/close times."""
        clock = self._retry_operation(
            lambda: self.client.get_clock(),
            "Get market clock"
        )
        return {
            'is_open': clock.is_open,
            'next_open': clock.next_open,
            'next_close': clock.next_close,
            'timestamp': datetime.now()
        }

    def get_next_market_open(self) -> datetime:
        """Get the next market open time."""
        clock = self._retry_operation(
            lambda: self.client.get_clock(),
            "Get market clock"
        )
        return clock.next_open

    # =========================================================================
    # Position Operations
    # =========================================================================

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """
        Get all current positions.

        Returns:
            List of position dictionaries with standardized keys
        """
        positions = self._retry_operation(
            lambda: self.client.get_all_positions(),
            "Get all positions"
        )

        result = []
        for pos in positions:
            result.append({
                'symbol': pos.symbol,
                'qty': int(pos.qty),
                'side': str(pos.side),
                'market_value': float(pos.market_value),
                'cost_basis': float(pos.cost_basis),
                'unrealized_pl': float(pos.unrealized_pl),
                'unrealized_plpc': float(pos.unrealized_plpc),
                'current_price': float(pos.current_price),
                'avg_entry_price': float(pos.avg_entry_price),
                'change_today': float(pos.change_today) if pos.change_today else 0.0
            })

        return result

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific position.

        Args:
            symbol: Ticker symbol

        Returns:
            Position dictionary or None if not found
        """
        try:
            pos = self.client.get_open_position(symbol)
            return {
                'symbol': pos.symbol,
                'qty': int(pos.qty),
                'side': str(pos.side),
                'market_value': float(pos.market_value),
                'cost_basis': float(pos.cost_basis),
                'unrealized_pl': float(pos.unrealized_pl),
                'unrealized_plpc': float(pos.unrealized_plpc),
                'current_price': float(pos.current_price),
                'avg_entry_price': float(pos.avg_entry_price)
            }
        except APIError as e:
            if '404' in str(e) or 'position does not exist' in str(e).lower():
                return None
            raise

    def close_position(self, symbol: str) -> Dict[str, Any]:
        """
        Close an entire position at market price.

        Args:
            symbol: Ticker symbol to close

        Returns:
            Order response
        """
        logger.info(f"Closing position: {symbol}")

        order = self._retry_operation(
            lambda: self.client.close_position(symbol),
            f"Close position {symbol}"
        )

        log_audit_event('POSITION_CLOSED', {
            'symbol': symbol,
            'order_id': str(order.id),
            'client_order_id': order.client_order_id
        })

        return {
            'order_id': str(order.id),
            'client_order_id': order.client_order_id,
            'symbol': order.symbol,
            'status': str(order.status)
        }

    # =========================================================================
    # Order Operations
    # =========================================================================

    def submit_limit_buy(
        self,
        symbol: str,
        qty: int,
        limit_price: float,
        client_order_id: str,
        time_in_force: str = 'day'
    ) -> Dict[str, Any]:
        """
        Submit a limit buy order.

        Args:
            symbol: Ticker symbol
            qty: Number of shares
            limit_price: Maximum price to pay
            client_order_id: Unique idempotency key
            time_in_force: 'day' or 'gtc'

        Returns:
            Order response dictionary
        """
        # Validate inputs
        if qty <= 0:
            raise AlpacaClientError(f"Invalid quantity: {qty}")
        if limit_price <= 0:
            raise AlpacaClientError(f"Invalid limit price: {limit_price}")

        tif = TimeInForce.DAY if time_in_force.lower() == 'day' else TimeInForce.GTC

        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            limit_price=round(limit_price, 2),
            time_in_force=tif,
            client_order_id=client_order_id
        )

        logger.info(f"Submitting LIMIT BUY: {symbol} x{qty} @ ${limit_price:.2f}")

        order = self._retry_operation(
            lambda: self.client.submit_order(order_data),
            f"Submit limit buy {symbol}"
        )

        log_audit_event('ORDER_SUBMITTED', {
            'type': 'LIMIT_BUY',
            'symbol': symbol,
            'qty': qty,
            'limit_price': limit_price,
            'order_id': str(order.id),
            'client_order_id': client_order_id,
            'status': str(order.status)
        })

        return self._format_order_response(order)

    def submit_limit_sell(
        self,
        symbol: str,
        qty: int,
        limit_price: float,
        client_order_id: str,
        time_in_force: str = 'gtc'
    ) -> Dict[str, Any]:
        """
        Submit a limit sell order.

        Args:
            symbol: Ticker symbol
            qty: Number of shares
            limit_price: Minimum price to accept
            client_order_id: Unique idempotency key
            time_in_force: 'day' or 'gtc'

        Returns:
            Order response dictionary
        """
        tif = TimeInForce.DAY if time_in_force.lower() == 'day' else TimeInForce.GTC

        order_data = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            limit_price=round(limit_price, 2),
            time_in_force=tif,
            client_order_id=client_order_id
        )

        logger.info(f"Submitting LIMIT SELL: {symbol} x{qty} @ ${limit_price:.2f}")

        order = self._retry_operation(
            lambda: self.client.submit_order(order_data),
            f"Submit limit sell {symbol}"
        )

        log_audit_event('ORDER_SUBMITTED', {
            'type': 'LIMIT_SELL',
            'symbol': symbol,
            'qty': qty,
            'limit_price': limit_price,
            'order_id': str(order.id),
            'client_order_id': client_order_id,
            'status': str(order.status)
        })

        return self._format_order_response(order)

    def submit_stop_limit_sell(
        self,
        symbol: str,
        qty: int,
        stop_price: float,
        limit_price: float,
        client_order_id: str,
        time_in_force: str = 'gtc'
    ) -> Dict[str, Any]:
        """
        Submit a stop-limit sell order (for stop losses).

        Args:
            symbol: Ticker symbol
            qty: Number of shares
            stop_price: Price that triggers the order
            limit_price: Minimum price to accept after triggered
            client_order_id: Unique idempotency key
            time_in_force: 'day' or 'gtc'

        Returns:
            Order response dictionary
        """
        tif = TimeInForce.DAY if time_in_force.lower() == 'day' else TimeInForce.GTC

        order_data = StopLimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            type=OrderType.STOP_LIMIT,
            stop_price=round(stop_price, 2),
            limit_price=round(limit_price, 2),
            time_in_force=tif,
            client_order_id=client_order_id
        )

        logger.info(
            f"Submitting STOP-LIMIT SELL: {symbol} x{qty} "
            f"stop=${stop_price:.2f} limit=${limit_price:.2f}"
        )

        order = self._retry_operation(
            lambda: self.client.submit_order(order_data),
            f"Submit stop-limit sell {symbol}"
        )

        log_audit_event('ORDER_SUBMITTED', {
            'type': 'STOP_LIMIT_SELL',
            'symbol': symbol,
            'qty': qty,
            'stop_price': stop_price,
            'limit_price': limit_price,
            'order_id': str(order.id),
            'client_order_id': client_order_id,
            'status': str(order.status)
        })

        return self._format_order_response(order)

    def submit_market_buy(
        self,
        symbol: str,
        qty: int,
        client_order_id: str
    ) -> Dict[str, Any]:
        """
        Submit a market buy order (immediate execution at current price).

        Args:
            symbol: Ticker symbol
            qty: Number of shares
            client_order_id: Unique idempotency key

        Returns:
            Order response dictionary
        """
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id
        )

        logger.info(f"Submitting MARKET BUY: {symbol} x{qty}")

        order = self._retry_operation(
            lambda: self.client.submit_order(order_data),
            f"Submit market buy {symbol}"
        )

        log_audit_event('ORDER_SUBMITTED', {
            'type': 'MARKET_BUY',
            'symbol': symbol,
            'qty': qty,
            'order_id': str(order.id),
            'client_order_id': client_order_id,
            'status': str(order.status)
        })

        return self._format_order_response(order)

    def submit_market_sell(
        self,
        symbol: str,
        qty: int,
        client_order_id: str
    ) -> Dict[str, Any]:
        """
        Submit a market sell order (for urgent exits).

        Args:
            symbol: Ticker symbol
            qty: Number of shares
            client_order_id: Unique idempotency key

        Returns:
            Order response dictionary
        """
        order_data = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id
        )

        logger.info(f"Submitting MARKET SELL: {symbol} x{qty}")

        order = self._retry_operation(
            lambda: self.client.submit_order(order_data),
            f"Submit market sell {symbol}"
        )

        log_audit_event('ORDER_SUBMITTED', {
            'type': 'MARKET_SELL',
            'symbol': symbol,
            'qty': qty,
            'order_id': str(order.id),
            'client_order_id': client_order_id,
            'status': str(order.status)
        })

        return self._format_order_response(order)

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get order by ID.

        Args:
            order_id: Alpaca order ID

        Returns:
            Order dictionary or None if not found
        """
        try:
            order = self.client.get_order_by_id(order_id)
            return self._format_order_response(order)
        except APIError as e:
            if '404' in str(e):
                return None
            raise

    def get_order_by_client_id(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get order by client order ID (idempotency key).

        Args:
            client_order_id: Our client-generated order ID

        Returns:
            Order dictionary or None if not found
        """
        try:
            # Alpaca SDK doesn't have get_order_by_client_order_id
            # Instead, get all orders and filter by client_order_id
            request = GetOrdersRequest(
                status=QueryOrderStatus.ALL,
                limit=500
            )
            orders = self.client.get_orders(request)

            # Find order with matching client_order_id
            for order in orders:
                if order.client_order_id == client_order_id:
                    return self._format_order_response(order)

            # Not found
            return None
        except APIError as e:
            if '404' in str(e) or 'order not found' in str(e).lower():
                return None
            raise

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Alpaca order ID

        Returns:
            True if cancelled, False otherwise
        """
        try:
            self.client.cancel_order_by_id(order_id)
            log_audit_event('ORDER_CANCELLED', {'order_id': order_id})
            logger.info(f"Order cancelled: {order_id}")
            return True
        except APIError as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all open orders, optionally filtered by symbol.

        Args:
            symbol: Optional ticker symbol to filter

        Returns:
            List of order dictionaries
        """
        request = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            symbols=[symbol] if symbol else None
        )

        orders = self._retry_operation(
            lambda: self.client.get_orders(request),
            "Get open orders"
        )

        return [self._format_order_response(o) for o in orders]

    def _format_order_response(self, order) -> Dict[str, Any]:
        """Format order object to dictionary."""
        return {
            'order_id': str(order.id),
            'client_order_id': order.client_order_id,
            'symbol': order.symbol,
            'qty': int(order.qty) if order.qty else 0,
            'filled_qty': int(order.filled_qty) if order.filled_qty else 0,
            'side': str(order.side),
            'type': str(order.type),
            'status': str(order.status),
            'limit_price': float(order.limit_price) if order.limit_price else None,
            'stop_price': float(order.stop_price) if order.stop_price else None,
            'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None,
            'submitted_at': order.submitted_at,
            'filled_at': order.filled_at,
            'time_in_force': str(order.time_in_force)
        }

    # =========================================================================
    # Asset Validation
    # =========================================================================

    def is_asset_tradeable(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if an asset is tradeable.

        Args:
            symbol: Ticker symbol

        Returns:
            Tuple of (is_tradeable, message)
            - (True, "") - Fully tradeable with no restrictions
            - (True, "⚠️ warning") - Tradeable but with caveats (e.g., minimum order size)
            - (False, "reason") - Not tradeable

            Callers should check BOTH values:
            - If is_tradeable is False, reject the trade
            - If is_tradeable is True but message is not empty, log the warning
        """
        try:
            asset = self.client.get_asset(symbol)

            if not asset.tradable:
                return False, "Asset is not tradeable"
            if asset.status != 'active':
                return False, f"Asset status is {asset.status}"

            # Check for restrictions that don't block trading but need attention
            if not asset.fractionable and asset.min_order_size and asset.min_order_size > 1:
                return True, f"⚠️ Minimum order size: {asset.min_order_size} shares (not fractionable)"

            return True, ""  # Fully tradeable with no warnings

        except APIError as e:
            if '404' in str(e):
                return False, "Asset not found"
            return False, f"Error checking asset: {e}"

    def get_latest_quote(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        Get the latest quote for a symbol.

        Note: This uses the trading client's data. For more comprehensive
        market data, consider using Alpaca's data client separately.

        Args:
            symbol: Ticker symbol

        Returns:
            Dictionary with bid/ask/last prices or None
        """
        # Get from position if we have one
        pos = self.get_position(symbol)
        if pos:
            return {
                'current_price': pos['current_price'],
                'source': 'position'
            }

        # Otherwise try to get from asset
        try:
            tradeable, _ = self.is_asset_tradeable(symbol)
            if tradeable:
                # Alpaca trading client doesn't provide direct quotes
                # Return None and let caller use yfinance as fallback
                return None
        except Exception:
            pass

        return None


def create_alpaca_client() -> AlpacaTradingClient:
    """
    Factory function to create Alpaca client based on config.

    Returns:
        Configured AlpacaTradingClient instance
    """
    paper = config.TRADING_MODE == 'paper'
    return AlpacaTradingClient(paper=paper)


if __name__ == '__main__':
    # Test connection
    try:
        client = create_alpaca_client()
        print(f"Connected successfully!")
        print(f"Portfolio Value: ${client.get_portfolio_value():,.2f}")
        print(f"Cash: ${client.get_cash():,.2f}")
        print(f"Market Open: {client.is_market_open()}")
        print(f"Positions: {len(client.get_all_positions())}")
    except Exception as e:
        print(f"Connection failed: {e}")
