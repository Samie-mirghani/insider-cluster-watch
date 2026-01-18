# automated_trading/order_manager.py
"""
Order Management System

Handles order lifecycle management with:
- Order state tracking (pending -> filled -> closed)
- Idempotent order submission (prevents duplicates)
- Pending order monitoring
- Order history tracking
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from . import config
from .utils import (
    load_json_file,
    save_json_file,
    generate_client_order_id,
    log_audit_event
)

logger = logging.getLogger(__name__)


class OrderState(str, Enum):
    """Order lifecycle states."""
    PENDING_SUBMIT = 'pending_submit'    # Created, not yet sent
    SUBMITTED = 'submitted'              # Sent to broker
    ACCEPTED = 'accepted'                # Broker accepted
    PARTIALLY_FILLED = 'partially_filled'  # Some shares filled
    FILLED = 'filled'                    # Completely filled
    REJECTED = 'rejected'                # Broker rejected
    CANCELLED = 'cancelled'              # Order cancelled
    EXPIRED = 'expired'                  # Order expired (DAY order)
    FAILED = 'failed'                    # Submission failed


def normalize_order_status(status: Any) -> str:
    """
    Normalize Alpaca order status to consistent lowercase format.

    Handles multiple formats:
    - 'OrderStatus.FILLED' (enum string representation)
    - 'filled' (lowercase string)
    - 'FILLED' (uppercase string)

    Args:
        status: Order status in any format

    Returns:
        Normalized lowercase status string
    """
    if status is None:
        logger.warning("⚠️ Received None as order status")
        return 'unknown'

    # Convert to string and normalize
    status_str = str(status).lower()

    # Handle enum format: 'OrderStatus.FILLED' -> 'filled'
    if '.' in status_str:
        status_str = status_str.split('.')[-1]

    # Map variations to standard names
    status_mapping = {
        'canceled': 'cancelled',  # US vs UK spelling
    }

    status_str = status_mapping.get(status_str, status_str)

    # Log if we got an unexpected format
    known_statuses = {
        'pending', 'submitted', 'accepted', 'partially_filled',
        'filled', 'rejected', 'cancelled', 'expired', 'failed',
        'new', 'pending_new', 'done_for_day', 'replaced', 'suspended'
    }

    if status_str not in known_statuses:
        logger.warning(f"⚠️ Unexpected order status format: {status} -> normalized to: {status_str}")

    return status_str


class OrderManager:
    """
    Manages order lifecycle and state tracking.

    Responsibilities:
    - Track pending orders awaiting fill
    - Generate idempotent client order IDs
    - Prevent duplicate order submission
    - Update order states based on broker responses
    """

    def __init__(self):
        """Initialize order manager."""
        self.pending_orders: Dict[str, Dict] = {}  # client_order_id -> order_info
        self._load_state()

    def _load_state(self):
        """Load pending orders from disk."""
        data = load_json_file(config.PENDING_ORDERS_FILE, default={})
        self.pending_orders = data.get('orders', {})
        logger.info(f"Loaded {len(self.pending_orders)} pending orders")

    def _save_state(self):
        """Save pending orders to disk."""
        data = {
            'orders': self.pending_orders,
            'last_updated': datetime.now().isoformat()
        }
        save_json_file(config.PENDING_ORDERS_FILE, data)

    # =========================================================================
    # Order Creation and Submission
    # =========================================================================

    def create_buy_order(
        self,
        ticker: str,
        shares: int,
        limit_price: float,
        signal_data: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Create a buy order record (before submission).

        Args:
            ticker: Stock ticker
            shares: Number of shares
            limit_price: Limit price for buy
            signal_data: Original signal information

        Returns:
            Tuple of (order_record, error_message)
            - (order_dict, None) on success
            - (None, error_message) on failure (e.g., duplicate order)
        """
        client_order_id = generate_client_order_id(ticker, 'BUY')

        # Check for existing order with same ticker today
        if self._has_pending_order_for_ticker(ticker, 'BUY'):
            error_msg = f"Duplicate order rejected: {ticker} already has pending BUY order"
            logger.warning(f"⚠️ {error_msg}")
            return None, error_msg

        order = {
            'client_order_id': client_order_id,
            'order_id': None,  # Set after submission
            'ticker': ticker,
            'side': 'BUY',
            'shares': shares,
            'limit_price': limit_price,
            'filled_shares': 0,
            'filled_price': None,
            'state': OrderState.PENDING_SUBMIT.value,
            'created_at': datetime.now().isoformat(),
            'submitted_at': None,
            'filled_at': None,
            'signal_score': signal_data.get('signal_score', 0),
            'signal_data': signal_data,
            'error_message': None
        }

        logger.info(f"✅ Created BUY order: {ticker} x{shares} @ ${limit_price:.2f}")
        return order, None

    def create_sell_order(
        self,
        ticker: str,
        shares: int,
        order_type: str,
        stop_price: Optional[float] = None,
        limit_price: Optional[float] = None,
        reason: str = 'MANUAL'
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Create a sell order record.

        Args:
            ticker: Stock ticker
            shares: Number of shares
            order_type: 'LIMIT', 'STOP_LIMIT', or 'MARKET'
            stop_price: Stop price (for stop orders)
            limit_price: Limit price
            reason: Exit reason (STOP_LOSS, TAKE_PROFIT, TIME_EXIT, etc.)

        Returns:
            Tuple of (order_record, error_message)
            - (order_dict, None) on success
            - (None, error_message) on failure
        """
        client_order_id = generate_client_order_id(ticker, 'SELL')

        # Check for duplicate pending sell orders
        if self._has_pending_order_for_ticker(ticker, 'SELL'):
            error_msg = f"Duplicate order rejected: {ticker} already has pending SELL order"
            logger.warning(f"⚠️ {error_msg}")
            return None, error_msg

        order = {
            'client_order_id': client_order_id,
            'order_id': None,
            'ticker': ticker,
            'side': 'SELL',
            'order_type': order_type,
            'shares': shares,
            'stop_price': stop_price,
            'limit_price': limit_price,
            'filled_shares': 0,
            'filled_price': None,
            'state': OrderState.PENDING_SUBMIT.value,
            'created_at': datetime.now().isoformat(),
            'submitted_at': None,
            'filled_at': None,
            'reason': reason,
            'error_message': None
        }

        logger.info(f"✅ Created SELL order: {ticker} x{shares} ({reason})")
        return order, None

    def mark_order_submitted(
        self,
        order: Dict[str, Any],
        alpaca_order_id: str,
        status: str
    ) -> None:
        """
        Mark an order as submitted to broker.

        Args:
            order: Order record
            alpaca_order_id: Alpaca's order ID
            status: Order status from Alpaca
        """
        client_order_id = order['client_order_id']

        order['order_id'] = alpaca_order_id
        order['submitted_at'] = datetime.now().isoformat()

        # Map Alpaca status to our state
        if status in ['new', 'accepted', 'pending_new']:
            order['state'] = OrderState.SUBMITTED.value
        elif status == 'partially_filled':
            order['state'] = OrderState.PARTIALLY_FILLED.value
        elif status == 'filled':
            order['state'] = OrderState.FILLED.value
        elif status in ['rejected', 'canceled', 'cancelled']:
            order['state'] = OrderState.REJECTED.value
        else:
            order['state'] = OrderState.SUBMITTED.value

        # Track in pending orders
        self.pending_orders[client_order_id] = order
        self._save_state()

        log_audit_event('ORDER_SUBMITTED', {
            'client_order_id': client_order_id,
            'order_id': alpaca_order_id,
            'ticker': order['ticker'],
            'side': order['side'],
            'shares': order['shares'],
            'status': status
        })

    def mark_order_filled(
        self,
        client_order_id: str,
        filled_shares: int,
        filled_price: float
    ) -> Dict[str, Any]:
        """
        Mark an order as filled.

        Args:
            client_order_id: Our client order ID
            filled_shares: Number of shares filled
            filled_price: Average fill price

        Returns:
            Updated order record
        """
        if client_order_id not in self.pending_orders:
            logger.warning(f"Order {client_order_id} not found in pending orders")
            return None

        order = self.pending_orders[client_order_id]
        order['filled_shares'] = filled_shares
        order['filled_price'] = filled_price
        order['filled_at'] = datetime.now().isoformat()
        order['state'] = OrderState.FILLED.value

        # Remove from pending
        del self.pending_orders[client_order_id]
        self._save_state()

        log_audit_event('ORDER_FILLED', {
            'client_order_id': client_order_id,
            'order_id': order.get('order_id'),
            'ticker': order['ticker'],
            'side': order['side'],
            'filled_shares': filled_shares,
            'filled_price': filled_price
        })

        logger.info(
            f"Order filled: {order['ticker']} {order['side']} "
            f"x{filled_shares} @ ${filled_price:.2f}"
        )

        return order

    def mark_order_rejected(
        self,
        client_order_id: str,
        error_message: str
    ) -> Dict[str, Any]:
        """
        Mark an order as rejected.

        Args:
            client_order_id: Our client order ID
            error_message: Rejection reason

        Returns:
            Updated order record
        """
        if client_order_id not in self.pending_orders:
            logger.warning(f"Order {client_order_id} not found")
            return None

        order = self.pending_orders[client_order_id]
        order['state'] = OrderState.REJECTED.value
        order['error_message'] = error_message

        # Remove from pending
        del self.pending_orders[client_order_id]
        self._save_state()

        log_audit_event('ORDER_REJECTED', {
            'client_order_id': client_order_id,
            'ticker': order['ticker'],
            'side': order['side'],
            'error': error_message
        }, outcome='FAILURE')

        logger.error(f"Order rejected: {order['ticker']} - {error_message}")

        return order

    def mark_order_cancelled(self, client_order_id: str) -> Dict[str, Any]:
        """
        Mark an order as cancelled.

        Args:
            client_order_id: Our client order ID

        Returns:
            Updated order record
        """
        if client_order_id not in self.pending_orders:
            return None

        order = self.pending_orders[client_order_id]
        order['state'] = OrderState.CANCELLED.value

        del self.pending_orders[client_order_id]
        self._save_state()

        log_audit_event('ORDER_CANCELLED', {
            'client_order_id': client_order_id,
            'ticker': order['ticker']
        })

        return order

    # =========================================================================
    # Order Queries
    # =========================================================================

    def has_order_been_submitted(self, client_order_id: str) -> bool:
        """
        Check if an order with this ID has already been submitted.

        Used for idempotency - prevents duplicate orders.

        Args:
            client_order_id: Client order ID to check

        Returns:
            True if order exists (submitted or pending)
        """
        return client_order_id in self.pending_orders

    def _has_pending_order_for_ticker(self, ticker: str, side: str) -> bool:
        """
        Check if there's already a pending order for this ticker.

        Args:
            ticker: Stock ticker
            side: BUY or SELL

        Returns:
            True if pending order exists
        """
        for order in self.pending_orders.values():
            if order['ticker'] == ticker and order['side'] == side:
                # Check if still pending (not expired)
                created = datetime.fromisoformat(order['created_at'])
                if datetime.now() - created < timedelta(hours=24):
                    return True
        return False

    def get_pending_orders(self, side: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all pending orders.

        Args:
            side: Optional filter by BUY or SELL

        Returns:
            List of pending order records
        """
        orders = list(self.pending_orders.values())

        if side:
            orders = [o for o in orders if o['side'] == side]

        return orders

    def get_pending_order(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific pending order.

        Args:
            client_order_id: Client order ID

        Returns:
            Order record or None
        """
        return self.pending_orders.get(client_order_id)

    def get_pending_orders_for_ticker(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Get all pending orders for a ticker.

        Args:
            ticker: Stock ticker

        Returns:
            List of pending orders
        """
        return [
            o for o in self.pending_orders.values()
            if o['ticker'] == ticker
        ]

    # =========================================================================
    # Order Cleanup
    # =========================================================================

    def cleanup_expired_orders(self) -> List[Dict[str, Any]]:
        """
        Remove orders that are older than 24 hours.

        Returns:
            List of removed orders
        """
        removed = []
        cutoff = datetime.now() - timedelta(hours=24)

        for client_order_id in list(self.pending_orders.keys()):
            order = self.pending_orders[client_order_id]
            created = datetime.fromisoformat(order['created_at'])

            if created < cutoff:
                order['state'] = OrderState.EXPIRED.value
                removed.append(order)
                del self.pending_orders[client_order_id]
                logger.info(f"Expired order removed: {order['ticker']} {order['side']}")

        if removed:
            self._save_state()

        return removed

    def update_orders_from_broker(
        self,
        alpaca_client,
        on_fill_callback=None
    ) -> Dict[str, List[Dict]]:
        """
        Update pending orders from broker status.

        Args:
            alpaca_client: AlpacaTradingClient instance
            on_fill_callback: Callback function(order) when order fills

        Returns:
            Dictionary with 'filled', 'rejected', 'unchanged' lists
        """
        results = {
            'filled': [],
            'rejected': [],
            'unchanged': []
        }

        for client_order_id in list(self.pending_orders.keys()):
            order = self.pending_orders[client_order_id]

            # Skip if no Alpaca order ID yet
            if not order.get('order_id'):
                results['unchanged'].append(order)
                continue

            try:
                # Get current status from Alpaca
                broker_order = alpaca_client.get_order(order['order_id'])

                if not broker_order:
                    logger.warning(f"Order {order['order_id']} not found at broker")
                    results['unchanged'].append(order)
                    continue

                status = normalize_order_status(broker_order['status'])

                # Handle fill
                if status == 'filled':
                    filled_order = self.mark_order_filled(
                        client_order_id,
                        broker_order['filled_qty'],
                        broker_order['filled_avg_price']
                    )
                    results['filled'].append(filled_order)

                    if on_fill_callback:
                        on_fill_callback(filled_order)

                # Handle rejection/cancellation
                elif status in ['rejected', 'cancelled']:
                    rejected_order = self.mark_order_rejected(
                        client_order_id,
                        f"Broker status: {status}"
                    )
                    results['rejected'].append(rejected_order)

                # Handle partial fill
                elif status == 'partially_filled':
                    order['filled_shares'] = broker_order['filled_qty']
                    order['state'] = OrderState.PARTIALLY_FILLED.value
                    results['unchanged'].append(order)

                else:
                    results['unchanged'].append(order)

            except Exception as e:
                logger.error(f"Error updating order {client_order_id}: {e}")
                results['unchanged'].append(order)

        return results

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_order_stats(self) -> Dict[str, int]:
        """Get statistics about pending orders."""
        buy_orders = [o for o in self.pending_orders.values() if o['side'] == 'BUY']
        sell_orders = [o for o in self.pending_orders.values() if o['side'] == 'SELL']

        return {
            'total_pending': len(self.pending_orders),
            'pending_buys': len(buy_orders),
            'pending_sells': len(sell_orders)
        }


# Factory function
def create_order_manager() -> OrderManager:
    """Create and return an OrderManager instance."""
    return OrderManager()


if __name__ == '__main__':
    # Test order manager
    manager = OrderManager()

    # Create test order
    test_order = manager.create_buy_order(
        ticker='AAPL',
        shares=10,
        limit_price=150.00,
        signal_data={'signal_score': 12.5}
    )

    print(f"Created order: {test_order['client_order_id']}")
    print(f"Pending orders: {manager.get_order_stats()}")
