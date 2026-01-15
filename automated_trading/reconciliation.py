# automated_trading/reconciliation.py
"""
Broker State Reconciliation

Ensures local position state matches broker (Alpaca) state.
Critical for detecting:
- Manual trades in Alpaca UI
- Corporate actions (splits, mergers)
- System crashes/restarts
- Order fills that weren't recorded
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

from . import config
from .utils import log_audit_event, load_json_file, save_json_file

logger = logging.getLogger(__name__)


class PositionDiscrepancy:
    """Represents a discrepancy between local and broker state."""

    MISSING_LOCAL = 'missing_local'      # Position in broker, not locally
    MISSING_BROKER = 'missing_broker'    # Position locally, not in broker
    QTY_MISMATCH = 'qty_mismatch'        # Quantities don't match
    PRICE_MISMATCH = 'price_mismatch'    # Entry prices significantly different

    def __init__(
        self,
        discrepancy_type: str,
        ticker: str,
        local_qty: int,
        broker_qty: int,
        details: Optional[Dict] = None
    ):
        self.type = discrepancy_type
        self.ticker = ticker
        self.local_qty = local_qty
        self.broker_qty = broker_qty
        self.details = details or {}
        self.detected_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.type,
            'ticker': self.ticker,
            'local_qty': self.local_qty,
            'broker_qty': self.broker_qty,
            'details': self.details,
            'detected_at': self.detected_at.isoformat()
        }

    def __str__(self) -> str:
        if self.type == self.MISSING_LOCAL:
            return f"{self.ticker}: Found at broker ({self.broker_qty} shares) but not locally"
        elif self.type == self.MISSING_BROKER:
            return f"{self.ticker}: Exists locally ({self.local_qty} shares) but not at broker"
        elif self.type == self.QTY_MISMATCH:
            return f"{self.ticker}: Qty mismatch - Local: {self.local_qty}, Broker: {self.broker_qty}"
        else:
            return f"{self.ticker}: {self.type}"


class Reconciler:
    """
    Reconciles local position state with broker state.

    Should be run:
    - At startup
    - Every monitoring cycle
    - After any trade execution
    - After any system error
    """

    def __init__(self):
        """Initialize reconciler."""
        self.last_reconciliation: Optional[datetime] = None
        self.discrepancies: List[PositionDiscrepancy] = []
        self.reconciliation_history: List[Dict] = []

    def reconcile(
        self,
        local_positions: Dict[str, Dict],
        alpaca_client
    ) -> Tuple[bool, List[PositionDiscrepancy]]:
        """
        Reconcile local positions with broker state.

        Args:
            local_positions: Dictionary of local position data
            alpaca_client: AlpacaTradingClient instance

        Returns:
            Tuple of (is_synced, list_of_discrepancies)
        """
        logger.info("Starting position reconciliation...")
        self.discrepancies = []

        try:
            # Get broker positions
            broker_positions = alpaca_client.get_all_positions()
            broker_map = {p['symbol']: p for p in broker_positions}

        except Exception as e:
            logger.error(f"Failed to fetch broker positions: {e}")
            log_audit_event('RECONCILIATION_FAILED', {
                'error': str(e)
            }, outcome='ERROR')
            return False, []

        # Get all unique tickers
        all_tickers = set(local_positions.keys()) | set(broker_map.keys())

        for ticker in all_tickers:
            local_pos = local_positions.get(ticker)
            broker_pos = broker_map.get(ticker)

            # Case 1: Position exists at broker but not locally
            if broker_pos and not local_pos:
                self.discrepancies.append(PositionDiscrepancy(
                    PositionDiscrepancy.MISSING_LOCAL,
                    ticker,
                    local_qty=0,
                    broker_qty=broker_pos['qty'],
                    details={
                        'broker_market_value': broker_pos['market_value'],
                        'broker_avg_price': broker_pos['avg_entry_price'],
                        'suggested_action': 'ADD_TO_LOCAL or INVESTIGATE'
                    }
                ))

            # Case 2: Position exists locally but not at broker
            elif local_pos and not broker_pos:
                self.discrepancies.append(PositionDiscrepancy(
                    PositionDiscrepancy.MISSING_BROKER,
                    ticker,
                    local_qty=local_pos.get('shares', 0),
                    broker_qty=0,
                    details={
                        'local_entry_price': local_pos.get('entry_price'),
                        'local_entry_date': local_pos.get('entry_date'),
                        'suggested_action': 'REMOVE_FROM_LOCAL or INVESTIGATE'
                    }
                ))

            # Case 3: Both exist - check quantities
            elif local_pos and broker_pos:
                local_qty = local_pos.get('shares', 0)
                broker_qty = broker_pos['qty']

                if local_qty != broker_qty:
                    self.discrepancies.append(PositionDiscrepancy(
                        PositionDiscrepancy.QTY_MISMATCH,
                        ticker,
                        local_qty=local_qty,
                        broker_qty=broker_qty,
                        details={
                            'difference': broker_qty - local_qty,
                            'suggested_action': 'SYNC_QUANTITIES'
                        }
                    ))

        # Log results
        self.last_reconciliation = datetime.now()

        reconciliation_result = {
            'timestamp': self.last_reconciliation.isoformat(),
            'local_positions': len(local_positions),
            'broker_positions': len(broker_map),
            'discrepancies': len(self.discrepancies),
            'is_synced': len(self.discrepancies) == 0
        }
        self.reconciliation_history.append(reconciliation_result)

        if self.discrepancies:
            logger.critical(f"RECONCILIATION FAILED: {len(self.discrepancies)} discrepancies found")
            for d in self.discrepancies:
                logger.critical(f"  - {d}")

            log_audit_event('RECONCILIATION_FAILED', {
                'discrepancy_count': len(self.discrepancies),
                'discrepancies': [d.to_dict() for d in self.discrepancies]
            }, outcome='FAILURE')

            return False, self.discrepancies
        else:
            logger.info(f"Reconciliation PASSED: {len(broker_map)} positions match")

            log_audit_event('RECONCILIATION_SUCCESS', {
                'positions_verified': len(broker_map)
            })

            return True, []

    def get_auto_fix_actions(self) -> List[Dict[str, Any]]:
        """
        Generate suggested auto-fix actions for discrepancies.

        IMPORTANT: Auto-fixes should be reviewed before execution.
        Some discrepancies require manual investigation.

        Returns:
            List of suggested fix actions
        """
        actions = []

        for d in self.discrepancies:
            if d.type == PositionDiscrepancy.MISSING_LOCAL:
                # Position at broker not locally tracked
                # This could be a manual trade or system error
                actions.append({
                    'action': 'ADD_POSITION_LOCALLY',
                    'ticker': d.ticker,
                    'qty': d.broker_qty,
                    'details': d.details,
                    'risk_level': 'MEDIUM',
                    'requires_review': True,
                    'note': 'Position found at broker but not tracked locally. May be manual trade.'
                })

            elif d.type == PositionDiscrepancy.MISSING_BROKER:
                # Position tracked locally but not at broker
                # The position was likely sold or never bought
                actions.append({
                    'action': 'REMOVE_POSITION_LOCALLY',
                    'ticker': d.ticker,
                    'qty': d.local_qty,
                    'details': d.details,
                    'risk_level': 'LOW',
                    'requires_review': True,
                    'note': 'Position tracked locally but not at broker. May have been manually sold.'
                })

            elif d.type == PositionDiscrepancy.QTY_MISMATCH:
                # Quantities don't match
                actions.append({
                    'action': 'SYNC_QUANTITY',
                    'ticker': d.ticker,
                    'local_qty': d.local_qty,
                    'broker_qty': d.broker_qty,
                    'details': d.details,
                    'risk_level': 'MEDIUM',
                    'requires_review': True,
                    'note': f'Quantity mismatch. Difference: {d.broker_qty - d.local_qty} shares'
                })

        return actions

    def sync_position(
        self,
        ticker: str,
        broker_position: Dict[str, Any],
        local_positions: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """
        Sync a single position from broker to local state.

        Args:
            ticker: Stock ticker
            broker_position: Position data from broker
            local_positions: Reference to local positions dict (will be modified)

        Returns:
            Sync result dictionary
        """
        if ticker in local_positions:
            # Update existing
            local_positions[ticker]['shares'] = broker_position['qty']
            action = 'UPDATED'
        else:
            # Add new position
            local_positions[ticker] = {
                'shares': broker_position['qty'],
                'entry_price': broker_position['avg_entry_price'],
                'entry_date': datetime.now(),  # We don't know actual entry date
                'cost_basis': broker_position['cost_basis'],
                'source': 'BROKER_SYNC',
                'synced_at': datetime.now().isoformat()
            }
            action = 'ADDED'

        log_audit_event('POSITION_SYNCED', {
            'ticker': ticker,
            'action': action,
            'broker_qty': broker_position['qty'],
            'broker_avg_price': broker_position['avg_entry_price']
        })

        return {
            'ticker': ticker,
            'action': action,
            'qty': broker_position['qty']
        }

    def remove_phantom_position(
        self,
        ticker: str,
        local_positions: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """
        Remove a position that exists locally but not at broker.

        Args:
            ticker: Stock ticker
            local_positions: Reference to local positions dict

        Returns:
            Removal result dictionary
        """
        if ticker in local_positions:
            removed = local_positions.pop(ticker)

            log_audit_event('PHANTOM_POSITION_REMOVED', {
                'ticker': ticker,
                'local_qty': removed.get('shares', 0),
                'reason': 'Not found at broker'
            })

            return {
                'ticker': ticker,
                'action': 'REMOVED',
                'removed_qty': removed.get('shares', 0)
            }

        return {
            'ticker': ticker,
            'action': 'NOT_FOUND',
            'removed_qty': 0
        }


class CashReconciler:
    """
    Reconciles cash balance between local and broker state.
    """

    @staticmethod
    def reconcile_cash(
        local_cash: float,
        alpaca_client,
        tolerance_pct: float = 1.0
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Reconcile local cash balance with broker.

        Args:
            local_cash: Local cash balance
            alpaca_client: AlpacaTradingClient instance
            tolerance_pct: Acceptable difference percentage

        Returns:
            Tuple of (is_synced, details_dict)
        """
        try:
            broker_cash = alpaca_client.get_cash()

            diff = abs(broker_cash - local_cash)
            diff_pct = (diff / broker_cash * 100) if broker_cash > 0 else 0

            is_synced = diff_pct <= tolerance_pct

            details = {
                'local_cash': local_cash,
                'broker_cash': broker_cash,
                'difference': diff,
                'difference_pct': diff_pct,
                'is_synced': is_synced,
                'tolerance_pct': tolerance_pct
            }

            if not is_synced:
                logger.warning(
                    f"Cash mismatch: Local ${local_cash:,.2f} vs "
                    f"Broker ${broker_cash:,.2f} (diff: {diff_pct:.2f}%)"
                )

                log_audit_event('CASH_MISMATCH', details, outcome='WARNING')
            else:
                logger.debug(f"Cash reconciled: ${broker_cash:,.2f}")

            return is_synced, details

        except Exception as e:
            logger.error(f"Failed to reconcile cash: {e}")
            return False, {'error': str(e)}


def create_reconciler() -> Reconciler:
    """Create and return a Reconciler instance."""
    return Reconciler()


if __name__ == '__main__':
    # Test reconciliation logic
    reconciler = Reconciler()

    # Mock data
    local = {
        'AAPL': {'shares': 10, 'entry_price': 175.00},
        'MSFT': {'shares': 5, 'entry_price': 380.00}
    }

    # Simulated broker response would come from actual API call
    print(f"Reconciler initialized. Last run: {reconciler.last_reconciliation}")
