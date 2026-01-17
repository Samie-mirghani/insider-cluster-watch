# automated_trading/execute_trades.py
"""
Trade Execution Engine

Main orchestration for executing trades via Alpaca API.
This module handles:
- Daily signal execution at market open
- Position monitoring during market hours
- Intraday capital redeployment
- Daily summary generation

Designed to be run as:
1. Morning job (execute_morning_trades) - Run at 9:35 AM ET
2. Monitor job (run_monitoring_cycle) - Run every 5 minutes during market hours
3. End of day job (run_end_of_day) - Run at 4:30 PM ET
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from . import config
from .alpaca_client import AlpacaTradingClient, create_alpaca_client, AlpacaClientError
from .order_manager import OrderManager, create_order_manager
from .signal_queue import SignalQueue, create_signal_queue
from .position_monitor import PositionMonitor, create_position_monitor, CircuitBreakerState
from .reconciliation import Reconciler
from .alerts import AlertSender, create_alert_sender
from .utils import (
    load_json_file,
    save_json_file,
    log_audit_event,
    is_market_hours,
    is_trading_window,
    generate_client_order_id,
    format_currency,
    format_percentage
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradingEngine:
    """
    Main trading engine orchestrator.

    Coordinates all trading components:
    - Alpaca API client
    - Order management
    - Position monitoring
    - Signal queue
    - Alerts
    """

    def __init__(self):
        """Initialize trading engine."""
        logger.info(f"{'='*60}")
        logger.info(f"INITIALIZING TRADING ENGINE")
        logger.info(f"Mode: {config.TRADING_MODE.upper()}")
        logger.info(f"Trading Enabled: {config.TRADING_ENABLED}")
        logger.info(f"{'='*60}")

        # Validate configuration
        errors = config.validate_config()
        if errors:
            for err in errors:
                logger.error(f"Config error: {err}")
            raise RuntimeError("Configuration validation failed")

        # Initialize components
        self.alpaca_client: Optional[AlpacaTradingClient] = None
        self.order_manager: Optional[OrderManager] = None
        self.signal_queue: Optional[SignalQueue] = None
        self.position_monitor: Optional[PositionMonitor] = None
        self.alert_sender: Optional[AlertSender] = None

        self._connect()

    def _connect(self):
        """Connect to Alpaca and initialize components."""
        try:
            # Connect to Alpaca
            self.alpaca_client = create_alpaca_client()
            logger.info(f"Connected to Alpaca ({config.TRADING_MODE} mode)")

            # Get account info
            account = self.alpaca_client.get_account()
            logger.info(f"Account verified:")
            logger.info(f"  Portfolio Value: ${float(account.portfolio_value):,.2f}")
            logger.info(f"  Cash: ${float(account.cash):,.2f}")
            logger.info(f"  Buying Power: ${float(account.buying_power):,.2f}")

            # Initialize other components
            self.order_manager = create_order_manager()
            self.signal_queue = create_signal_queue()
            self.position_monitor = create_position_monitor(self.alpaca_client)
            self.alert_sender = create_alert_sender()

            logger.info("All components initialized successfully")

        except AlpacaClientError as e:
            logger.error(f"Failed to connect to Alpaca: {e}")
            raise
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            raise

    # =========================================================================
    # Signal Loading and Validation
    # =========================================================================

    def load_approved_signals(self) -> List[Dict[str, Any]]:
        """
        Load approved signals from the main pipeline.

        Looks for signals in the standard data directory.

        Returns:
            List of approved signal dictionaries
        """
        # Check multiple possible signal file locations
        signal_paths = [
            os.path.join(os.path.dirname(__file__), '..', 'data', 'approved_signals.json'),
            os.path.join(os.path.dirname(__file__), '..', 'data', 'cluster_signals.json'),
            os.path.join(os.path.dirname(__file__), '..', 'data', 'today_signals.json'),
        ]

        for path in signal_paths:
            if os.path.exists(path):
                data = load_json_file(path)
                if data:
                    signals = data if isinstance(data, list) else data.get('signals', [])
                    logger.info(f"Loaded {len(signals)} signals from {path}")
                    return signals

        logger.warning("No signal file found")
        return []

    def validate_signal(self, signal: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate a signal before execution.

        Args:
            signal: Signal dictionary

        Returns:
            Tuple of (is_valid, reason)
        """
        ticker = signal.get('ticker')
        entry_price = signal.get('entry_price') or signal.get('currentPrice')
        signal_score = signal.get('signal_score') or signal.get('rank_score', 0)

        # Basic validation
        if not ticker:
            return False, "Missing ticker"

        if not entry_price or entry_price <= 0:
            return False, "Invalid entry price"

        if signal_score < config.MIN_SIGNAL_SCORE_THRESHOLD:
            return False, f"Score {signal_score} below threshold {config.MIN_SIGNAL_SCORE_THRESHOLD}"

        # Check if already have position
        if ticker in self.position_monitor.positions:
            return False, "Already have position"

        # Check if tradeable at Alpaca
        is_tradeable, message = self.alpaca_client.is_asset_tradeable(ticker)
        if not is_tradeable:
            return False, f"Not tradeable: {message}"
        # Log warning if tradeable but with restrictions
        if message:
            logger.warning(f"{ticker}: {message}")

        # Check portfolio constraints
        portfolio_value = self.alpaca_client.get_portfolio_value()
        cash = self.alpaca_client.get_cash()

        # Max positions
        current_positions = len(self.position_monitor.positions)
        if current_positions >= config.MAX_POSITIONS:
            return False, f"Max positions ({config.MAX_POSITIONS}) reached"

        # Calculate position size
        position_value = self._calculate_position_value(signal, portfolio_value)
        if position_value > cash * 0.95:
            return False, f"Insufficient cash (need ${position_value:.2f}, have ${cash:.2f})"

        return True, "Valid"

    def _calculate_position_value(
        self,
        signal: Dict[str, Any],
        portfolio_value: float
    ) -> float:
        """Calculate position value for a signal."""
        signal_score = signal.get('signal_score') or signal.get('rank_score', 0)

        if config.ENABLE_SCORE_WEIGHTED_SIZING:
            # Score-weighted position sizing
            score_range = config.SCORE_WEIGHT_MAX_SCORE - config.SCORE_WEIGHT_MIN_SCORE
            if score_range > 0:
                clamped_score = max(
                    config.SCORE_WEIGHT_MIN_SCORE,
                    min(signal_score, config.SCORE_WEIGHT_MAX_SCORE)
                )
                normalized = (clamped_score - config.SCORE_WEIGHT_MIN_SCORE) / score_range
                position_pct = config.SCORE_WEIGHT_MIN_POSITION_PCT + (
                    normalized * (config.SCORE_WEIGHT_MAX_POSITION_PCT - config.SCORE_WEIGHT_MIN_POSITION_PCT)
                )
            else:
                position_pct = config.MAX_POSITION_PCT
        else:
            position_pct = config.MAX_POSITION_PCT

        return portfolio_value * position_pct

    # =========================================================================
    # Trade Execution
    # =========================================================================

    def execute_buy_signal(self, signal: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Execute a buy signal via Alpaca.

        Args:
            signal: Signal dictionary with ticker, entry_price, etc.

        Returns:
            Tuple of (success, message)
        """
        ticker = signal.get('ticker')
        entry_price = signal.get('entry_price') or signal.get('currentPrice')

        logger.info(f"\n{'='*50}")
        logger.info(f"EXECUTING BUY: {ticker}")
        logger.info(f"{'='*50}")

        # Validate
        is_valid, reason = self.validate_signal(signal)
        if not is_valid:
            logger.warning(f"Signal rejected: {reason}")
            return False, reason

        # Calculate position size
        portfolio_value = self.alpaca_client.get_portfolio_value()
        position_value = self._calculate_position_value(signal, portfolio_value)
        shares = int(position_value / entry_price)

        if shares <= 0:
            return False, "Cannot afford any shares"

        # Calculate limit price (with cushion)
        limit_price = round(entry_price * (1 + config.LIMIT_ORDER_CUSHION_PCT / 100), 2)

        # Generate idempotent order ID
        client_order_id = generate_client_order_id(ticker, 'BUY')

        # Check if order already exists
        existing_order = self.alpaca_client.get_order_by_client_id(client_order_id)
        if existing_order:
            logger.warning(f"Order {client_order_id} already exists")
            return False, "Duplicate order"

        # Create order record
        order, error = self.order_manager.create_buy_order(
            ticker=ticker,
            shares=shares,
            limit_price=limit_price,
            signal_data=signal
        )

        if not order:
            logger.warning(f"❌ {ticker}: {error}")
            return False, error

        try:
            # Submit to Alpaca
            logger.info(f"Submitting order: {ticker} x{shares} @ ${limit_price:.2f}")

            alpaca_order = self.alpaca_client.submit_limit_buy(
                symbol=ticker,
                qty=shares,
                limit_price=limit_price,
                client_order_id=client_order_id,
                time_in_force='day'
            )

            # Update order manager
            self.order_manager.mark_order_submitted(
                order,
                alpaca_order['order_id'],
                alpaca_order['status']
            )

            logger.info(f"Order submitted: {alpaca_order['order_id']}")
            logger.info(f"Status: {alpaca_order['status']}")

            # Send alert
            self.alert_sender.send_trade_executed_alert(
                ticker=ticker,
                action='BUY',
                shares=shares,
                price=limit_price,
                total_value=shares * limit_price
            )

            return True, f"Order submitted: {alpaca_order['order_id']}"

        except Exception as e:
            logger.error(f"Order submission failed: {e}")
            self.order_manager.mark_order_rejected(client_order_id, str(e))
            return False, f"Order failed: {e}"

    def execute_sell(
        self,
        ticker: str,
        reason: str,
        order_type: str = 'MARKET'
    ) -> Tuple[bool, str]:
        """
        Execute a sell order.

        Args:
            ticker: Stock ticker
            reason: Exit reason (STOP_LOSS, TAKE_PROFIT, etc.)
            order_type: MARKET or LIMIT

        Returns:
            Tuple of (success, message)
        """
        logger.info(f"\n{'='*50}")
        logger.info(f"EXECUTING SELL: {ticker} ({reason})")
        logger.info(f"{'='*50}")

        # Get position
        pos = self.position_monitor.get_position(ticker)
        if not pos:
            logger.warning(f"No position found for {ticker}")
            return False, "No position"

        shares = pos['shares']
        entry_price = pos['entry_price']

        # Generate order ID
        client_order_id = generate_client_order_id(ticker, 'SELL')

        try:
            # Use close_position for simplicity (market order)
            result = self.alpaca_client.close_position(ticker)

            logger.info(f"Position closed: {result}")

            # Calculate P&L (approximate - actual fill may differ)
            current_price = self.position_monitor.get_current_price(ticker)
            if current_price is None or current_price <= 0:
                logger.warning(f"Could not get current price for {ticker}, using entry price for P&L calc")
                current_price = entry_price
            pnl = (current_price - entry_price) * shares
            pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

            # Update circuit breaker
            self.position_monitor.circuit_breaker.record_trade(pnl, ticker)

            # Remove from local tracking
            self.position_monitor.remove_position(ticker)

            # Send alert
            self.alert_sender.send_trade_executed_alert(
                ticker=ticker,
                action='SELL',
                shares=shares,
                price=current_price,
                total_value=shares * current_price,
                reason=reason,
                pnl=pnl,
                pnl_pct=pnl_pct
            )

            return True, f"Position closed"

        except Exception as e:
            logger.error(f"Sell failed: {e}")
            return False, f"Sell failed: {e}"

    # =========================================================================
    # Main Execution Functions
    # =========================================================================

    def execute_morning_trades(self) -> Dict[str, Any]:
        """
        Execute morning trades at market open.

        This should be called once per day around 9:35 AM ET.

        Returns:
            Execution summary dictionary
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"MORNING TRADE EXECUTION")
        logger.info(f"Time: {datetime.now()}")
        logger.info(f"{'='*60}")

        results = {
            'timestamp': datetime.now().isoformat(),
            'signals_loaded': 0,
            'signals_validated': 0,
            'orders_submitted': 0,
            'orders_failed': 0,
            'queued_for_later': 0,
            'errors': []
        }

        # Check if trading is enabled
        if not config.TRADING_ENABLED:
            results['errors'].append("Trading is disabled")
            logger.warning("Trading is disabled - skipping execution")
            return results

        # Check market hours
        if not is_market_hours():
            results['errors'].append("Market is closed")
            logger.warning("Market is closed - skipping execution")
            return results

        # Check circuit breaker
        portfolio_value = self.alpaca_client.get_portfolio_value()
        is_halted, halt_reason = self.position_monitor.circuit_breaker.check_circuit_breakers(
            portfolio_value
        )
        if is_halted:
            results['errors'].append(f"Circuit breaker active: {halt_reason}")
            logger.warning(f"Circuit breaker active: {halt_reason}")
            return results

        # Run reconciliation first
        is_synced, discrepancies = self.position_monitor.reconciler.reconcile(
            self.position_monitor.positions,
            self.alpaca_client
        )
        if not is_synced:
            logger.warning(f"Reconciliation found {len(discrepancies)} discrepancies")
            self.alert_sender.send_reconciliation_alert(
                [d.to_dict() for d in discrepancies]
            )
            # Continue anyway - discrepancies don't block trading

        # Load signals
        signals = self.load_approved_signals()
        results['signals_loaded'] = len(signals)

        if not signals:
            logger.info("No signals to execute")
            return results

        # Sort by score (highest first)
        signals.sort(
            key=lambda x: x.get('signal_score') or x.get('rank_score', 0),
            reverse=True
        )

        # Execute signals
        for signal in signals:
            ticker = signal.get('ticker')

            # Validate
            is_valid, reason = self.validate_signal(signal)

            if is_valid:
                results['signals_validated'] += 1

                # Execute
                success, message = self.execute_buy_signal(signal)

                if success:
                    results['orders_submitted'] += 1
                else:
                    results['orders_failed'] += 1

                    # Queue for potential intraday redeployment
                    if 'Insufficient cash' in message or 'Max positions' in message:
                        self.signal_queue.add_signal(signal, reason=message)
                        results['queued_for_later'] += 1
            else:
                logger.info(f"Skipping {ticker}: {reason}")

        logger.info(f"\n{'='*60}")
        logger.info(f"MORNING EXECUTION COMPLETE")
        logger.info(f"Signals: {results['signals_loaded']} loaded, {results['signals_validated']} validated")
        logger.info(f"Orders: {results['orders_submitted']} submitted, {results['orders_failed']} failed")
        logger.info(f"Queued: {results['queued_for_later']}")
        logger.info(f"{'='*60}")

        return results

    def run_monitoring_cycle(self) -> Dict[str, Any]:
        """
        Run a monitoring cycle.

        This should be called every 5 minutes during market hours.

        Returns:
            Cycle results dictionary
        """
        logger.info(f"\n--- Monitoring Cycle: {datetime.now().strftime('%H:%M:%S')} ---")

        results = {
            'timestamp': datetime.now().isoformat(),
            'exits_triggered': [],
            'orders_filled': [],
            'redeployments': [],
            'circuit_breaker': None,
            'errors': []
        }

        if not is_market_hours():
            results['skipped'] = 'Market closed'
            return results

        try:
            # Update pending orders
            order_results = self.order_manager.update_orders_from_broker(
                self.alpaca_client,
                on_fill_callback=self._on_order_filled
            )
            results['orders_filled'] = [o['ticker'] for o in order_results['filled']]

            # Check circuit breaker
            portfolio_value = self.alpaca_client.get_portfolio_value()
            is_halted, halt_reason = self.position_monitor.circuit_breaker.check_circuit_breakers(
                portfolio_value
            )

            if is_halted:
                results['circuit_breaker'] = {
                    'triggered': True,
                    'reason': halt_reason
                }

                self.alert_sender.send_circuit_breaker_alert(
                    reason=halt_reason,
                    daily_pnl=self.position_monitor.circuit_breaker.daily_pnl,
                    portfolio_value=portfolio_value,
                    action_taken="New positions blocked, monitoring continues"
                )

            # Update trailing stops
            self.position_monitor.update_trailing_stops()

            # Check for exits
            exits = self.position_monitor.check_exits()

            for exit_info in exits:
                ticker = exit_info['ticker']
                reason = exit_info['reason']

                success, message = self.execute_sell(ticker, reason)

                if success:
                    results['exits_triggered'].append({
                        'ticker': ticker,
                        'reason': reason,
                        'pnl_pct': exit_info.get('pnl_pct', 0)
                    })

                    # Check for intraday redeployment opportunity
                    if config.ENABLE_INTRADAY_REDEPLOYMENT and not is_halted:
                        self._check_redeployment_opportunity(results)

        except Exception as e:
            logger.error(f"Monitoring cycle error: {e}")
            results['errors'].append(str(e))

        return results

    def _on_order_filled(self, order: Dict[str, Any]) -> None:
        """Callback when an order is filled."""
        ticker = order['ticker']
        shares = order['filled_shares']
        price = order['filled_price']

        logger.info(f"Order filled: {ticker} x{shares} @ ${price:.2f}")

        # Get signal data
        signal_data = order.get('signal_data', {})

        # Calculate stops
        stop_loss_pct = config.STOP_LOSS_PCT
        tier = signal_data.get('multi_signal_tier', 'none')
        if tier in config.MULTI_SIGNAL_STOP_LOSS:
            stop_loss_pct = config.MULTI_SIGNAL_STOP_LOSS[tier]

        stop_loss = price * (1 - stop_loss_pct)
        take_profit = price * (1 + config.TAKE_PROFIT_PCT)

        # Add to position monitor
        self.position_monitor.add_position(
            ticker=ticker,
            shares=shares,
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_data=signal_data
        )

    def _check_redeployment_opportunity(self, results: Dict) -> None:
        """Check if freed capital can be redeployed."""
        cash = self.alpaca_client.get_cash()

        can_redeploy, reason = self.signal_queue.can_redeploy_capital(cash)

        if not can_redeploy:
            logger.debug(f"Cannot redeploy: {reason}")
            return

        # Get best candidate
        excluded = list(self.position_monitor.positions.keys())

        candidate = self.signal_queue.get_best_redeployment_candidate(
            available_capital=cash,
            current_price_func=self.position_monitor.get_current_price,
            excluded_tickers=excluded
        )

        if not candidate:
            logger.debug("No suitable redeployment candidate")
            return

        ticker = candidate['ticker']
        logger.info(f"Redeployment candidate found: {ticker}")

        # Execute
        success, message = self.execute_buy_signal(candidate['signal_data'])

        if success:
            self.signal_queue.mark_redeployment_used(ticker)
            results['redeployments'].append(ticker)
            logger.info(f"Capital redeployed to {ticker}")

    def run_end_of_day(self) -> Dict[str, Any]:
        """
        Run end of day tasks.

        This should be called at 4:30 PM ET after market close.

        Returns:
            Summary dictionary
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"END OF DAY SUMMARY")
        logger.info(f"{'='*60}")

        # Get final stats
        portfolio_value = self.alpaca_client.get_portfolio_value()
        daily_pnl = self.position_monitor.circuit_breaker.daily_pnl
        trades_today = len(self.position_monitor.circuit_breaker.trades_today)
        open_positions = len(self.position_monitor.positions)

        # Cleanup
        self.order_manager.cleanup_expired_orders()
        self.signal_queue.cleanup_stale_signals()

        # Send daily summary
        self.alert_sender.send_daily_summary_alert(
            portfolio_value=portfolio_value,
            daily_pnl=daily_pnl,
            trades_executed=trades_today,
            open_positions=open_positions,
            circuit_breaker_status=self.position_monitor.circuit_breaker.get_status()
        )

        summary = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'portfolio_value': portfolio_value,
            'daily_pnl': daily_pnl,
            'trades_executed': trades_today,
            'open_positions': open_positions,
            'circuit_breaker': self.position_monitor.circuit_breaker.get_status()
        }

        logger.info(f"Portfolio Value: ${portfolio_value:,.2f}")
        logger.info(f"Daily P&L: ${daily_pnl:+,.2f}")
        logger.info(f"Trades Today: {trades_today}")
        logger.info(f"Open Positions: {open_positions}")
        logger.info(f"{'='*60}")

        return summary


def main():
    """Main entry point for the trading engine."""
    import argparse

    parser = argparse.ArgumentParser(description='Alpaca Automated Trading Engine')
    parser.add_argument('command', choices=['morning', 'monitor', 'eod', 'status'],
                       help='Command to run')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run without executing trades')

    args = parser.parse_args()

    try:
        engine = TradingEngine()

        if args.command == 'morning':
            results = engine.execute_morning_trades()
            print(json.dumps(results, indent=2, default=str))

        elif args.command == 'monitor':
            results = engine.run_monitoring_cycle()
            print(json.dumps(results, indent=2, default=str))

        elif args.command == 'eod':
            results = engine.run_end_of_day()
            print(json.dumps(results, indent=2, default=str))

        elif args.command == 'status':
            status = engine.position_monitor.get_status()
            print(json.dumps(status, indent=2, default=str))

    except Exception as e:
        logger.error(f"Engine error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
