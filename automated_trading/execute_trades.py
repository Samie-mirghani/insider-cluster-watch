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
import yfinance as yf
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
from .execution_metrics import ExecutionMetrics, create_execution_metrics
from .utils import (
    load_json_file,
    save_json_file,
    log_audit_event,
    is_market_hours,
    is_trading_window,
    generate_client_order_id,
    format_currency,
    format_percentage,
    update_trading_calendar
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
        self.execution_metrics: Optional[ExecutionMetrics] = None

        # Track exits for EOD summary (persisted to disk)
        self.exits_today: List[Dict[str, Any]] = self._load_exits_today()

        self._connect()

    def _load_exits_today(self) -> List[Dict[str, Any]]:
        """Load today's exits from disk (persisted across job runs)."""
        data = load_json_file(config.EXITS_TODAY_FILE, default={'date': None, 'exits': []})
        today = datetime.now().strftime('%Y-%m-%d')

        # Only load exits from today; if it's a new day, start fresh
        if data.get('date') == today:
            logger.info(f"Loaded {len(data.get('exits', []))} exits from today")
            return data.get('exits', [])
        else:
            logger.info("New trading day - starting with fresh exits list")
            return []

    def _save_exits_today(self):
        """Save today's exits to disk for persistence across job runs."""
        data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'exits': self.exits_today
        }
        save_json_file(config.EXITS_TODAY_FILE, data)

    def _clear_exits_today(self):
        """Clear exits after EOD summary is sent."""
        self.exits_today = []
        self._save_exits_today()
        logger.info("Cleared exits_today after EOD summary")

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

            # Update trading calendar cache for holiday detection
            update_trading_calendar(self.alpaca_client)

            # Initialize other components
            self.order_manager = create_order_manager()
            self.signal_queue = create_signal_queue()
            self.position_monitor = create_position_monitor(self.alpaca_client)
            self.alert_sender = create_alert_sender()
            self.execution_metrics = create_execution_metrics()

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

        # NEW FILTERS: Cooldown, Single-Insider, Downtrend
        # Extract signal fields
        insider_count = signal.get('insider_count', 0)
        market_cap = signal.get('market_cap')
        buy_value = signal.get('buy_value', 0)

        # Filter 1: Repeat Trade Cooldown (7 calendar days)
        # Read audit log to check for recent position closes
        try:
            audit_log_path = os.path.join(os.path.dirname(__file__), 'data', 'audit_log.jsonl')
            if os.path.exists(audit_log_path):
                cutoff_date = datetime.now() - timedelta(days=7)

                with open(audit_log_path, 'r') as f:
                    for line in f:
                        try:
                            event = json.loads(line.strip())
                            if event.get('event_type') == 'POSITION_CLOSED' and event.get('ticker') == ticker:
                                # Parse timestamp
                                timestamp_str = event.get('timestamp', '')
                                try:
                                    event_date = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                except:
                                    continue

                                if event_date >= cutoff_date:
                                    close_date = event_date.strftime('%Y-%m-%d')
                                    return False, f"Cooldown: {ticker} closed on {close_date}, 7-day cooldown required"
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            # File doesn't exist or can't be parsed - skip cooldown check
            logger.debug(f"Cooldown check skipped for {ticker}: {e}")
            pass

        # Filter 2: Single Insider Micro-Cap
        if insider_count == 1:
            # Check 1: Micro-cap with low score
            if market_cap is not None and market_cap < 100_000_000:
                if signal_score < 9.0:
                    return False, f"Single insider micro-cap: score {signal_score:.2f} < 9.0 required (mkt cap ${market_cap/1e6:.1f}M)"

            # Check 2: Weak conviction (low buy value)
            if buy_value < 500_000:
                return False, f"Single insider weak conviction: buy_value ${buy_value:,.0f} < $500K minimum"

            # Check 3: Likely go-private transaction
            if market_cap and market_cap > 0 and buy_value > 10_000_000:
                pct_of_cap = buy_value / market_cap
                if pct_of_cap > 0.3:
                    return False, f"Likely go-private: single insider buying {pct_of_cap*100:.0f}% of market cap — skipping"

        # Filter 3: Downtrend Detection
        try:
            # Get 7 days of history
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)
            hist = yf.download(ticker, start=start_date, end=end_date, progress=False)

            if not hist.empty and len(hist) >= 5:
                # Compute 5-day SMA of closing prices
                last_5_closes = hist['Close'].tail(5)
                sma_5 = last_5_closes.mean()

                if sma_5 and entry_price < sma_5 * 0.97:
                    # Price is >3% below 5-day SMA - downtrend
                    pct_below = ((entry_price - sma_5) / sma_5) * 100
                    return False, f"Downtrend: {ticker} price ${entry_price:.2f} is {abs(pct_below):.1f}% below 5-day SMA ${sma_5:.2f}"
            # If yfinance call fails or insufficient data, log warning but DO NOT block
            elif hist.empty:
                logger.warning(f"{ticker}: No price history available for downtrend check, allowing trade")

        except Exception as e:
            # yfinance call failed - log warning but DO NOT block the trade
            logger.warning(f"{ticker}: Downtrend check failed ({str(e)}), allowing trade")

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
        """
        Calculate position value for a signal using score-weighted sizing.

        Higher signal scores get larger positions within the configured range.
        This allows the signal strength (not tier) to determine position size.
        """
        signal_score = signal.get('signal_score') or signal.get('rank_score', 0)

        if config.ENABLE_SCORE_WEIGHTED_SIZING:
            # Score-weighted position sizing
            # Maps signal score to position size between min and max percentages
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

        position_value = portfolio_value * position_pct

        logger.info(
            f"Position sizing: score={signal_score:.1f} → "
            f"{position_pct*100:.1f}% of portfolio = ${position_value:.2f}"
        )

        return position_value

    # =========================================================================
    # Trade Execution
    # =========================================================================

    def execute_buy_signal(
        self,
        signal: Dict[str, Any],
        send_alert: bool = True,
        is_redeployment: bool = False
    ) -> Tuple[bool, str]:
        """
        Execute a buy signal via Alpaca.

        Args:
            signal: Signal dictionary with ticker, entry_price, etc.
            send_alert: Whether to send individual email alert (default: True)
            is_redeployment: Whether this is an intraday redeployment (default: False)

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

        # Generate idempotent order ID
        client_order_id = generate_client_order_id(ticker, 'BUY')

        # Check if order already exists
        existing_order = self.alpaca_client.get_order_by_client_id(client_order_id)
        if existing_order:
            logger.warning(f"Order {client_order_id} already exists")
            return False, "Duplicate order"

        # Determine order type and limit price
        if config.USE_LIMIT_ORDERS:
            # Use limit order with cushion to protect against slippage
            limit_price = entry_price * (1 + config.LIMIT_ORDER_CUSHION_PCT / 100)
            order_type = "LIMIT"
        else:
            # Market order (immediate fill, no price protection)
            limit_price = entry_price
            order_type = "MARKET"

        # Create order record
        order, error = self.order_manager.create_buy_order(
            ticker=ticker,
            shares=shares,
            limit_price=limit_price,
            signal_data=signal,
            order_type=order_type
        )

        if not order:
            logger.warning(f"❌ {ticker}: {error}")
            return False, error

        try:
            # Submit to Alpaca
            if config.USE_LIMIT_ORDERS:
                logger.info(
                    f"Submitting LIMIT order: {ticker} x{shares} @ ${limit_price:.2f} "
                    f"(signal: ${entry_price:.2f}, cushion: {config.LIMIT_ORDER_CUSHION_PCT}%)"
                )
                alpaca_order = self.alpaca_client.submit_limit_buy(
                    symbol=ticker,
                    qty=shares,
                    limit_price=limit_price,
                    client_order_id=client_order_id
                )
            else:
                logger.info(f"Submitting MARKET order: {ticker} x{shares} @ market price")
                alpaca_order = self.alpaca_client.submit_market_buy(
                    symbol=ticker,
                    qty=shares,
                    client_order_id=client_order_id
                )

            # Update order manager
            self.order_manager.mark_order_submitted(
                order,
                alpaca_order['order_id'],
                alpaca_order['status']
            )

            # Record order execution for daily trade limit tracking
            self.position_monitor.circuit_breaker.record_order_executed(ticker, 'BUY')

            logger.info(f"Order submitted: {alpaca_order['order_id']}")
            logger.info(f"Status: {alpaca_order['status']}")

            # Send alert (only for intraday redeployment)
            if send_alert:
                if is_redeployment:
                    # Use special redeployment alert
                    self.alert_sender.send_intraday_redeployment_alert(
                        ticker=ticker,
                        shares=shares,
                        price=entry_price,
                        total_value=shares * entry_price,
                        reason="Capital redeployed from position exit"
                    )
                else:
                    # Individual trade alert (legacy - not used for morning trades)
                    self.alert_sender.send_trade_executed_alert(
                        ticker=ticker,
                        action='BUY',
                        shares=shares,
                        price=entry_price,
                        total_value=shares * entry_price
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

            # Record order execution for daily trade limit tracking
            self.position_monitor.circuit_breaker.record_order_executed(ticker, 'SELL')

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

            # Track exit for EOD summary (persisted to disk for cross-job continuity)
            self.exits_today.append({
                'ticker': ticker,
                'shares': shares,
                'entry_price': entry_price,
                'exit_price': current_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'reason': reason,
                'time': datetime.now().isoformat()
            })
            self._save_exits_today()  # Persist immediately

            logger.info(f"Exit tracked for EOD summary: {ticker} ({reason}) - P&L: ${pnl:+,.2f}")

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
        # CRITICAL FIX: Pass daily_pnl which includes both realized AND unrealized P&L
        # This ensures circuit breaker catches losses from open positions, not just closed ones
        daily_pnl = self.alpaca_client.get_daily_pnl()
        is_halted, halt_reason = self.position_monitor.circuit_breaker.check_circuit_breakers(
            portfolio_value,
            daily_pnl=daily_pnl
        )
        if is_halted:
            results['errors'].append(f"Circuit breaker active: {halt_reason}")
            logger.warning(f"Circuit breaker active: {halt_reason}")
            return results

        # Sync with broker BEFORE trading to ensure positions.json is accurate
        # This prevents duplicate investments and ensures all positions are tracked
        logger.info("Syncing with broker before trading...")
        sync_results = self.position_monitor.sync_with_broker()

        if sync_results.get('synced') and sync_results.get('total_corrections', 0) > 0:
            corrections = sync_results['corrections']
            logger.info(f"✅ Position sync complete:")
            if corrections['added']:
                logger.info(f"   ➕ Added {len(corrections['added'])} positions")
            if corrections['removed']:
                logger.info(f"   ➖ Removed {len(corrections['removed'])} positions")
            if corrections['updated']:
                logger.info(f"   🔄 Updated {len(corrections['updated'])} quantities")
            logger.info("This prevents duplicate investments in existing positions")

        # Run reconciliation for reporting (sync already fixed any issues)
        is_synced, discrepancies = self.position_monitor.reconciler.reconcile(
            self.position_monitor.positions,
            self.alpaca_client
        )
        if not is_synced:
            logger.warning(f"Reconciliation found {len(discrepancies)} discrepancies after sync")
            self.alert_sender.send_reconciliation_alert(
                [d.to_dict() for d in discrepancies]
            )

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

        # Execute signals (collect trades for batch email)
        executed_trades = []

        for signal in signals:
            ticker = signal.get('ticker')

            # Validate
            is_valid, reason = self.validate_signal(signal)

            if is_valid:
                results['signals_validated'] += 1

                # Execute WITHOUT individual alert (batch email at end)
                success, message = self.execute_buy_signal(
                    signal,
                    send_alert=False,  # No individual alerts for morning trades
                    is_redeployment=False
                )

                if success:
                    results['orders_submitted'] += 1

                    # Track trade for batch email (match execute_buy_signal calculation)
                    entry_price = signal.get('entry_price') or signal.get('currentPrice')
                    portfolio_value = self.alpaca_client.get_portfolio_value()
                    position_value = self._calculate_position_value(signal, portfolio_value)
                    shares = int(position_value / entry_price)  # Divide by entry_price (not limit_price)
                    limit_price = round(entry_price * (1 + config.LIMIT_ORDER_CUSHION_PCT / 100), 2)

                    executed_trades.append({
                        'ticker': ticker,
                        'shares': shares,
                        'price': limit_price,
                        'total_value': shares * limit_price
                    })
                else:
                    results['orders_failed'] += 1

                    # Queue for potential intraday redeployment
                    if 'Insufficient cash' in message or 'Max positions' in message:
                        self.signal_queue.add_signal(signal, reason=message)
                        results['queued_for_later'] += 1
            else:
                logger.info(f"Skipping {ticker}: {reason}")
                # Queue signals rejected ONLY due to max positions — they become
                # redeployment candidates if a position exits intraday
                if 'Max positions' in reason:
                    self.signal_queue.add_signal(signal, reason=reason)
                    results['queued_for_later'] += 1
                    logger.info(f"  Queued {ticker} for intraday redeployment")

        # Send ONE consolidated batch email for all morning trades
        if executed_trades:
            logger.info(f"Sending batch email for {len(executed_trades)} morning trades")
            self.alert_sender.send_morning_trades_batch_alert(
                trades=executed_trades,
                summary=results
            )

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
            # Update pending orders and track execution metrics
            order_results = self.order_manager.update_orders_from_broker(
                self.alpaca_client,
                on_fill_callback=self._on_order_filled,
                execution_metrics=self.execution_metrics
            )
            results['orders_filled'] = [o['ticker'] for o in order_results['filled']]

            # Check circuit breaker
            portfolio_value = self.alpaca_client.get_portfolio_value()
            # CRITICAL FIX: Pass daily_pnl which includes both realized AND unrealized P&L
            # This ensures circuit breaker catches losses from open positions, not just closed ones
            daily_pnl = self.alpaca_client.get_daily_pnl()
            is_halted, halt_reason = self.position_monitor.circuit_breaker.check_circuit_breakers(
                portfolio_value,
                daily_pnl=daily_pnl
            )

            if is_halted:
                results['circuit_breaker'] = {
                    'triggered': True,
                    'reason': halt_reason
                }

                self.alert_sender.send_circuit_breaker_alert(
                    reason=halt_reason,
                    daily_pnl=daily_pnl,  # Use actual daily P&L instead of only realized
                    portfolio_value=portfolio_value,
                    action_taken="New positions blocked, monitoring continues"
                )

            # Update trailing stops
            trailing_updates = self.position_monitor.update_trailing_stops()
            if trailing_updates:
                results['trailing_stop_updates'] = trailing_updates

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

        # Calculate tier-based stop loss
        # NOTE: Higher conviction (tier1) gets WIDER stops (12% - more room to move)
        #       Lower conviction (tier4) gets TIGHTER stops (6% - fail fast)
        # This is intentional risk management - we give high-conviction trades
        # more room to work while cutting losses quickly on lower-conviction trades.
        stop_loss_pct = config.STOP_LOSS_PCT
        tier = signal_data.get('multi_signal_tier', 'none')
        if tier in config.MULTI_SIGNAL_STOP_LOSS:
            stop_loss_pct = config.MULTI_SIGNAL_STOP_LOSS[tier]
            logger.info(f"Applied {tier} stop-loss: {stop_loss_pct*100:.0f}%")

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
            excluded_tickers=excluded,
            is_asset_tradeable_func=self.alpaca_client.is_asset_tradeable
        )

        if not candidate:
            logger.debug("No suitable redeployment candidate")
            return

        ticker = candidate['ticker']
        logger.info(f"Redeployment candidate found: {ticker}")

        # Execute with intraday redeployment alert (separate email)
        success, message = self.execute_buy_signal(
            candidate['signal_data'],
            send_alert=True,  # Send alert for redeployment
            is_redeployment=True  # Use redeployment alert format
        )

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

        # Get total daily P&L (realized + unrealized)
        # This uses Alpaca's equity difference which includes both
        # - Realized P&L from closed positions
        # - Unrealized P&L changes from open positions
        daily_pnl = self.alpaca_client.get_daily_pnl()

        # Get actual trades count (all filled orders today)
        filled_orders_today = self.alpaca_client.get_filled_orders_today()
        trades_today = len(filled_orders_today)

        open_positions = len(self.position_monitor.positions)

        # Cleanup and track unfilled orders
        self.order_manager.cleanup_expired_orders(execution_metrics=self.execution_metrics)
        self.signal_queue.cleanup_stale_signals()

        # Send daily summary (includes exits to reduce email volume)
        logger.info(f"Sending EOD summary with {len(self.exits_today)} exits")
        self.alert_sender.send_daily_summary_alert(
            portfolio_value=portfolio_value,
            daily_pnl=daily_pnl,
            trades_executed=trades_today,
            open_positions=open_positions,
            circuit_breaker_status=self.position_monitor.circuit_breaker.get_status(),
            exits_today=self.exits_today  # Include exits in EOD summary
        )

        # Clear exits after EOD email is sent (they've been reported)
        exits_count = len(self.exits_today)
        self._clear_exits_today()

        summary = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'portfolio_value': portfolio_value,
            'daily_pnl': daily_pnl,
            'trades_executed': trades_today,
            'open_positions': open_positions,
            'exits_reported': exits_count,
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
            print(engine.position_monitor.format_position_dashboard())

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
