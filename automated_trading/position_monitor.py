# automated_trading/position_monitor.py
"""
Position Monitor

Continuously monitors positions for:
- Stop loss triggers
- Take profit targets
- Trailing stop updates
- Time-based exits
- Circuit breaker conditions

Also handles:
- Position reconciliation with broker
- Order status updates
- Intraday capital redeployment
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

import yfinance as yf

from . import config
from .utils import (
    load_json_file,
    save_json_file,
    log_audit_event,
    is_market_hours,
    is_trading_window,
    format_currency,
    format_percentage,
    calculate_pnl_pct
)
from .reconciliation import Reconciler, CashReconciler

logger = logging.getLogger(__name__)


class CircuitBreakerState:
    """Tracks circuit breaker state for the day."""

    # File-based reset flag for manual intervention
    RESET_FLAG_FILE = os.path.join(config.DATA_DIR, 'circuit_breaker_reset.flag')

    def __init__(self):
        self.daily_pnl: float = 0.0
        self.consecutive_losses: int = 0
        self.is_halted: bool = False
        self.halt_reason: Optional[str] = None
        self.trades_today: List[Dict] = []
        self.total_trades_today: int = 0  # Total buys + sells (for daily trade limit)
        self.last_reset_date: Optional[str] = None
        self._load_state()
        self.check_reset_flag()  # Check for manual reset request

    def _load_state(self):
        """Load daily state from disk."""
        data = load_json_file(config.DAILY_STATE_FILE, default={})

        today = datetime.now().strftime('%Y-%m-%d')

        # Reset if new day
        if data.get('date') != today:
            self.daily_pnl = 0.0
            self.consecutive_losses = 0
            self.is_halted = False
            self.halt_reason = None
            self.trades_today = []
            self.total_trades_today = 0
            self.last_reset_date = today
            logger.info("New trading day - circuit breakers reset")
        else:
            self.daily_pnl = data.get('daily_pnl', 0.0)
            self.consecutive_losses = data.get('consecutive_losses', 0)
            self.is_halted = data.get('is_halted', False)
            self.halt_reason = data.get('halt_reason')
            self.trades_today = data.get('trades_today', [])
            self.total_trades_today = data.get('total_trades_today', 0)
            self.last_reset_date = data.get('date')

    def save_state(self):
        """Save daily state to disk."""
        data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'daily_pnl': self.daily_pnl,
            'consecutive_losses': self.consecutive_losses,
            'is_halted': self.is_halted,
            'halt_reason': self.halt_reason,
            'trades_today': self.trades_today,
            'total_trades_today': self.total_trades_today,
            'last_updated': datetime.now().isoformat()
        }
        save_json_file(config.DAILY_STATE_FILE, data)

    def record_trade(self, pnl: float, ticker: str) -> None:
        """
        Record a trade and update circuit breaker state.

        Args:
            pnl: Profit/loss from the trade
            ticker: Stock ticker
        """
        self.daily_pnl += pnl
        self.trades_today.append({
            'ticker': ticker,
            'pnl': pnl,
            'time': datetime.now().isoformat()
        })

        # Update consecutive losses
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        self.save_state()
        logger.info(f"Trade recorded: {ticker} ${pnl:+,.2f} | Daily P&L: ${self.daily_pnl:+,.2f}")

    def record_order_executed(self, ticker: str, order_type: str) -> None:
        """
        Record that an order was executed (for daily trade limit tracking).

        Args:
            ticker: Stock ticker
            order_type: 'BUY' or 'SELL'
        """
        self.total_trades_today += 1
        self.save_state()
        logger.info(
            f"Order executed: {order_type} {ticker} | "
            f"Total trades today: {self.total_trades_today}/{config.MAX_TRADES_PER_DAY}"
        )

    def check_circuit_breakers(
        self,
        portfolio_value: float,
        daily_pnl: Optional[float] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if any circuit breakers are triggered.

        Args:
            portfolio_value: Current portfolio value
            daily_pnl: Total daily P&L (realized + unrealized). If None, uses self.daily_pnl
                      CRITICAL: Pass alpaca_client.get_daily_pnl() to include unrealized losses

        Returns:
            Tuple of (is_triggered, reason)
        """
        # Already halted
        if self.is_halted:
            return True, self.halt_reason

        # Use provided daily_pnl (which includes unrealized) or fall back to self.daily_pnl (realized only)
        # IMPORTANT: Caller should pass alpaca_client.get_daily_pnl() to include unrealized P&L
        pnl_to_check = daily_pnl if daily_pnl is not None else self.daily_pnl

        # Daily loss limit
        daily_loss_limit = config.get_daily_loss_limit_dollars(portfolio_value)
        if pnl_to_check <= -daily_loss_limit:
            self._trigger_halt(
                f"DAILY_LOSS_LIMIT: ${abs(pnl_to_check):,.2f} loss (realized + unrealized) exceeds ${daily_loss_limit:,.2f} limit"
            )
            return True, self.halt_reason

        # Daily trade limit
        if self.total_trades_today >= config.MAX_TRADES_PER_DAY:
            self._trigger_halt(
                f"MAX_TRADES_PER_DAY: {self.total_trades_today} trades executed (limit: {config.MAX_TRADES_PER_DAY})"
            )
            return True, self.halt_reason

        # Consecutive losses
        if self.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            self._trigger_halt(
                f"CONSECUTIVE_LOSSES: {self.consecutive_losses} consecutive losing trades"
            )
            return True, self.halt_reason

        return False, None

    def _trigger_halt(self, reason: str) -> None:
        """Trigger trading halt."""
        self.is_halted = True
        self.halt_reason = reason
        self.save_state()

        log_audit_event('CIRCUIT_BREAKER_TRIGGERED', {
            'reason': reason,
            'daily_pnl': self.daily_pnl,
            'consecutive_losses': self.consecutive_losses
        }, outcome='CRITICAL')

        logger.critical(f"CIRCUIT BREAKER TRIGGERED: {reason}")

    def reset(self, reason: str = "Manual reset") -> None:
        """
        Reset circuit breaker state.

        This clears the halt flag and resets counters. Use with caution!
        Should only be called after understanding and resolving the issue
        that triggered the circuit breaker.

        Args:
            reason: Reason for the reset
        """
        old_halt_reason = self.halt_reason
        old_daily_pnl = self.daily_pnl

        self.is_halted = False
        self.halt_reason = None
        # Note: We do NOT reset daily_pnl or consecutive_losses
        # This is intentional - we want to preserve the state while
        # allowing trading to resume. A full reset only happens at midnight.

        self.save_state()

        log_audit_event('CIRCUIT_BREAKER_RESET', {
            'reset_reason': reason,
            'previous_halt_reason': old_halt_reason,
            'daily_pnl': old_daily_pnl,
            'consecutive_losses': self.consecutive_losses
        }, outcome='WARNING')

        logger.warning(
            f"🔄 CIRCUIT BREAKER RESET: {reason}\n"
            f"   Previous halt reason: {old_halt_reason}\n"
            f"   Daily P&L: ${old_daily_pnl:+,.2f}\n"
            f"   Consecutive losses: {self.consecutive_losses}\n"
            f"   ⚠️ Trading will resume - monitor closely!"
        )

    def check_reset_flag(self) -> None:
        """
        Check if manual reset is requested via flag file.

        To manually reset the circuit breaker, create a file at:
        automated_trading/data/circuit_breaker_reset.flag

        The file can contain a reason (optional). The reset will be
        logged to the audit trail.

        Example:
            echo "Investigated and resolved issue" > automated_trading/data/circuit_breaker_reset.flag
        """
        if not os.path.exists(self.RESET_FLAG_FILE):
            return

        try:
            # Read reason from file (if provided)
            with open(self.RESET_FLAG_FILE, 'r') as f:
                content = f.read().strip()
                reason = content if content else "Manual reset via flag file"

            # Delete the flag file
            os.remove(self.RESET_FLAG_FILE)

            # Perform reset
            self.reset(reason)

            logger.info(f"✅ Processed reset flag file successfully")

        except Exception as e:
            logger.error(f"❌ Failed to process reset flag file: {e}")
            # Don't re-raise - we don't want to crash the system over this

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            'is_halted': self.is_halted,
            'halt_reason': self.halt_reason,
            'daily_pnl': self.daily_pnl,
            'consecutive_losses': self.consecutive_losses,
            'trades_today': len(self.trades_today),
            'total_trades_today': self.total_trades_today,
            'trades_remaining': max(0, config.MAX_TRADES_PER_DAY - self.total_trades_today)
        }


class PositionMonitor:
    """
    Monitors positions and manages exits.

    Responsibilities:
    - Track all open positions
    - Check for exit conditions (stops, targets, time)
    - Update trailing stops
    - Handle intraday redeployment
    - Reconcile with broker
    """

    def __init__(self, alpaca_client=None):
        """
        Initialize position monitor.

        Args:
            alpaca_client: Optional AlpacaTradingClient instance
        """
        self.alpaca_client = alpaca_client
        self.positions: Dict[str, Dict] = {}
        self.signal_history: Dict[str, Dict] = {}
        self.circuit_breaker = CircuitBreakerState()
        self.reconciler = Reconciler()
        self._load_positions()
        self._load_signal_history()

        # CRITICAL: Sync from broker on initialization
        # This ensures we monitor positions even after system restart or data loss
        if self.alpaca_client is not None:
            # Always sync on startup to ensure positions.json is accurate
            sync_results = self.sync_with_broker()
            if sync_results.get('total_corrections', 0) > 0:
                logger.info("Position sync completed on initialization")

    def _load_positions(self):
        """Load positions from disk."""
        data = load_json_file(config.LIVE_POSITIONS_FILE, default={})
        self.positions = data.get('positions', {})

        # Convert date strings back to datetime
        for ticker, pos in self.positions.items():
            if isinstance(pos.get('entry_date'), str):
                try:
                    pos['entry_date'] = datetime.fromisoformat(pos['entry_date'])
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to parse entry_date for {ticker}: {e}. Using current time as fallback.")
                    pos['entry_date'] = datetime.now()

        logger.info(f"Loaded {len(self.positions)} positions")

    def _load_signal_history(self):
        """Load signal history from disk."""
        data = load_json_file(config.SIGNAL_HISTORY_FILE, default={})
        self.signal_history = data.get('signals', {})
        logger.info(f"Loaded signal history for {len(self.signal_history)} tickers")

    def _save_signal_history(self):
        """Save signal history to disk."""
        data = {
            'signals': self.signal_history,
            'last_updated': datetime.now().isoformat()
        }
        save_json_file(config.SIGNAL_HISTORY_FILE, data)

    def _save_to_signal_history(self, ticker: str, signal_data: Dict) -> None:
        """
        Save signal data to history for future reference.

        This allows us to preserve tier/signal information when syncing from broker.

        Args:
            ticker: Stock ticker
            signal_data: Original signal data dictionary
        """
        if not signal_data:
            return

        self.signal_history[ticker] = {
            'signal_score': signal_data.get('signal_score', 0),
            'multi_signal_tier': signal_data.get('multi_signal_tier', 'none'),
            'sector': signal_data.get('sector', 'Unknown'),
            'entry_price': signal_data.get('entry_price') or signal_data.get('currentPrice', 0),
            'saved_at': datetime.now().isoformat()
        }
        self._save_signal_history()
        logger.debug(f"Saved signal history for {ticker}")

    def _lookup_signal_info(self, ticker: str) -> Optional[Dict]:
        """
        Look up signal information for a ticker.

        Checks signal history first, then approved signals file.

        Args:
            ticker: Stock ticker

        Returns:
            Signal info dict or None
        """
        # First check signal history
        if ticker in self.signal_history:
            return self.signal_history[ticker]

        # Then check approved signals file
        try:
            signals = load_json_file(config.APPROVED_SIGNALS_FILE, default=[])
            if isinstance(signals, list):
                for signal in signals:
                    if signal.get('ticker') == ticker:
                        return {
                            'signal_score': signal.get('signal_score', 0),
                            'multi_signal_tier': signal.get('multi_signal_tier', 'none'),
                            'sector': signal.get('sector', 'Unknown'),
                            'entry_price': signal.get('entry_price', 0)
                        }
        except Exception as e:
            logger.debug(f"Could not lookup signal for {ticker}: {e}")

        return None

    def _sync_positions_from_broker(self):
        """
        Sync positions from broker to local tracking.

        Called automatically when local positions are empty but broker has positions.
        This ensures positions are protected even after system restart or data loss.
        """
        try:
            logger.warning("Local positions empty - syncing from broker...")
            broker_positions = self.alpaca_client.get_all_positions()

            if not broker_positions:
                logger.info("No positions at broker to sync")
                return

            logger.info(f"Found {len(broker_positions)} positions at broker")

            synced_count = 0
            for broker_pos in broker_positions:
                ticker = broker_pos['symbol']
                shares = broker_pos['qty']
                avg_entry = broker_pos['avg_entry_price']

                # Look up signal history for tier-based stops
                signal_info = self._lookup_signal_info(ticker)

                if signal_info:
                    tier = signal_info.get('multi_signal_tier', 'none')
                    signal_score = signal_info.get('signal_score', 0)
                    sector = signal_info.get('sector', 'Unknown')

                    # Use tier-based stop loss if available
                    if tier in config.MULTI_SIGNAL_STOP_LOSS:
                        stop_loss_pct = config.MULTI_SIGNAL_STOP_LOSS[tier]
                        logger.info(f"  Using {tier} stop-loss ({stop_loss_pct*100:.0f}%) for {ticker}")
                    else:
                        stop_loss_pct = config.STOP_LOSS_PCT
                else:
                    tier = 'none'
                    signal_score = 0
                    sector = 'Unknown'
                    stop_loss_pct = config.STOP_LOSS_PCT

                stop_loss = avg_entry * (1 - stop_loss_pct)
                take_profit = avg_entry * (1 + config.TAKE_PROFIT_PCT)

                # Add position with broker data
                self.positions[ticker] = {
                    'shares': shares,
                    'entry_price': avg_entry,
                    'entry_date': datetime.now(),  # Unknown, use current time
                    'cost_basis': shares * avg_entry,
                    'stop_loss': stop_loss,
                    'initial_stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'highest_price': broker_pos.get('current_price', avg_entry),
                    'trailing_enabled': False,
                    'signal_score': signal_score,
                    'multi_signal_tier': tier,
                    'sector': sector,
                    'source': 'broker_sync',
                    'synced_at': datetime.now().isoformat()
                }

                logger.info(
                    f"  Synced: {ticker} ({shares} shares @ ${avg_entry:.2f}) "
                    f"- Stop: ${stop_loss:.2f}, Target: ${take_profit:.2f}, Tier: {tier}"
                )
                synced_count += 1

            self.save_positions()
            logger.info(f"✅ Synced {synced_count} positions from broker - NOW MONITORING")
            logger.info("Stop losses and take profits are now ACTIVE")

        except Exception as e:
            logger.error(f"Failed to sync positions from broker: {e}")
            # Don't raise - we want monitoring to continue even if sync fails

    def save_positions(self):
        """Save positions to disk."""
        # Convert datetime to strings for JSON
        save_data = {}
        for ticker, pos in self.positions.items():
            pos_copy = pos.copy()
            if isinstance(pos_copy.get('entry_date'), datetime):
                pos_copy['entry_date'] = pos_copy['entry_date'].isoformat()
            save_data[ticker] = pos_copy

        data = {
            'positions': save_data,
            'last_updated': datetime.now().isoformat()
        }
        save_json_file(config.LIVE_POSITIONS_FILE, data)

    # =========================================================================
    # Position Management
    # =========================================================================

    def add_position(
        self,
        ticker: str,
        shares: int,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        signal_data: Optional[Dict] = None
    ) -> None:
        """
        Add a new position.

        Args:
            ticker: Stock ticker
            shares: Number of shares
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            signal_data: Original signal data
        """
        self.positions[ticker] = {
            'shares': shares,
            'entry_price': entry_price,
            'entry_date': datetime.now(),
            'cost_basis': shares * entry_price,
            'stop_loss': stop_loss,
            'initial_stop_loss': stop_loss,
            'take_profit': take_profit,
            'highest_price': entry_price,
            'trailing_enabled': False,
            'signal_score': signal_data.get('signal_score', 0) if signal_data else 0,
            'multi_signal_tier': signal_data.get('multi_signal_tier', 'none') if signal_data else 'none',
            'sector': signal_data.get('sector', 'Unknown') if signal_data else 'Unknown'
        }

        # Save to signal history for future broker sync reference
        if signal_data:
            self._save_to_signal_history(ticker, signal_data)

        self.save_positions()
        logger.info(f"Position added: {ticker} x{shares} @ ${entry_price:.2f}")

    def remove_position(self, ticker: str) -> Optional[Dict]:
        """
        Remove a position.

        Args:
            ticker: Stock ticker

        Returns:
            Removed position data or None
        """
        if ticker in self.positions:
            pos = self.positions.pop(ticker)
            self.save_positions()
            return pos
        return None

    def get_position(self, ticker: str) -> Optional[Dict]:
        """Get a specific position."""
        return self.positions.get(ticker)

    def get_all_positions(self) -> Dict[str, Dict]:
        """Get all positions."""
        return self.positions.copy()

    # =========================================================================
    # Price and P&L Tracking
    # =========================================================================

    def get_current_price(self, ticker: str) -> Optional[float]:
        """
        Get current price for a ticker.

        Args:
            ticker: Stock ticker

        Returns:
            Current price or None
        """
        # Try Alpaca first if we have a position
        if self.alpaca_client:
            broker_pos = self.alpaca_client.get_position(ticker)
            if broker_pos:
                return broker_pos['current_price']

        # Fallback to yfinance
        try:
            ticker_obj = yf.Ticker(ticker)
            price = ticker_obj.info.get('currentPrice')
            if price and price > 0:
                return price

            # Try bid/ask if no current price
            price = ticker_obj.info.get('bid') or ticker_obj.info.get('ask')
            if price and price > 0:
                return price

        except Exception as e:
            logger.warning(f"Failed to get price for {ticker}: {e}")

        return None

    def calculate_position_pnl(self, ticker: str) -> Dict[str, float]:
        """
        Calculate P&L for a position.

        Args:
            ticker: Stock ticker

        Returns:
            Dictionary with pnl_dollars and pnl_pct
        """
        pos = self.positions.get(ticker)
        if not pos:
            return {'pnl_dollars': 0, 'pnl_pct': 0}

        current_price = self.get_current_price(ticker)
        if not current_price:
            current_price = pos['entry_price']

        entry_price = pos['entry_price']
        shares = pos['shares']

        pnl_dollars = (current_price - entry_price) * shares
        pnl_pct = calculate_pnl_pct(entry_price, current_price)

        return {
            'pnl_dollars': pnl_dollars,
            'pnl_pct': pnl_pct,
            'current_price': current_price,
            'entry_price': entry_price,
            'shares': shares,
            'current_value': current_price * shares
        }

    def calculate_total_pnl(self) -> Dict[str, float]:
        """Calculate total portfolio P&L."""
        total_pnl_dollars = 0
        total_cost = 0
        total_value = 0

        for ticker in self.positions:
            pnl = self.calculate_position_pnl(ticker)
            total_pnl_dollars += pnl['pnl_dollars']
            total_cost += pnl['entry_price'] * pnl['shares']
            total_value += pnl['current_value']

        total_pnl_pct = (total_pnl_dollars / total_cost * 100) if total_cost > 0 else 0

        return {
            'total_pnl_dollars': total_pnl_dollars,
            'total_pnl_pct': total_pnl_pct,
            'total_cost': total_cost,
            'total_value': total_value
        }

    # =========================================================================
    # Exit Condition Checking
    # =========================================================================

    def check_exits(self) -> List[Dict[str, Any]]:
        """
        Check all positions for exit conditions.

        Returns:
            List of positions to exit with reasons
        """
        exits_needed = []
        positions_updated = False

        for ticker, pos in self.positions.items():
            current_price = self.get_current_price(ticker)
            if current_price:
                # Cache successful price lookups for fallback during outages
                if pos.get('last_known_price') != current_price:
                    pos['last_known_price'] = current_price
                    positions_updated = True
            else:
                # Use last known price as fallback — never skip exit checks entirely
                fallback_price = pos.get('last_known_price') or pos.get('entry_price')
                if fallback_price:
                    current_price = fallback_price
                    logger.warning(
                        f"Cannot get live price for {ticker}, using last known "
                        f"price ${fallback_price:.2f} for exit checks"
                    )
                else:
                    logger.error(f"No price data available for {ticker}, skipping exit check")
                    continue

            entry_price = pos['entry_price']
            pnl_pct = calculate_pnl_pct(entry_price, current_price)
            days_held = (datetime.now() - pos['entry_date']).days

            exit_info = None

            # Check stop loss
            if current_price <= pos['stop_loss']:
                trailing_tag = " (TRAILING)" if pos.get('trailing_enabled') else ""
                exit_info = {
                    'ticker': ticker,
                    'reason': f'STOP_LOSS{trailing_tag}',
                    'current_price': current_price,
                    'trigger_price': pos['stop_loss'],
                    'pnl_pct': pnl_pct
                }

            # Check take profit
            elif current_price >= pos['take_profit']:
                exit_info = {
                    'ticker': ticker,
                    'reason': 'TAKE_PROFIT',
                    'current_price': current_price,
                    'trigger_price': pos['take_profit'],
                    'pnl_pct': pnl_pct
                }

            # Check time-based exits
            elif days_held >= config.MAX_HOLD_LOSS_DAYS and pnl_pct < 0:
                exit_info = {
                    'ticker': ticker,
                    'reason': 'MAX_HOLD_LOSS',
                    'current_price': current_price,
                    'days_held': days_held,
                    'pnl_pct': pnl_pct
                }

            elif days_held >= config.MAX_HOLD_STAGNANT_DAYS and pnl_pct < config.MAX_HOLD_STAGNANT_THRESHOLD:
                exit_info = {
                    'ticker': ticker,
                    'reason': 'MAX_HOLD_STAGNANT',
                    'current_price': current_price,
                    'days_held': days_held,
                    'pnl_pct': pnl_pct
                }

            elif days_held >= config.MAX_HOLD_EXTREME_DAYS and pnl_pct < config.MAX_HOLD_EXTREME_EXCEPTION:
                exit_info = {
                    'ticker': ticker,
                    'reason': 'MAX_HOLD_EXTREME',
                    'current_price': current_price,
                    'days_held': days_held,
                    'pnl_pct': pnl_pct
                }

            if exit_info:
                exits_needed.append(exit_info)
                logger.info(
                    f"Exit triggered for {ticker}: {exit_info['reason']} "
                    f"@ ${current_price:.2f} ({pnl_pct:+.2f}%)"
                )

        if positions_updated:
            self.save_positions()

        return exits_needed

    def update_trailing_stops(self) -> List[Dict[str, Any]]:
        """
        Update trailing stops for profitable positions.

        Returns:
            List of positions with updated stops
        """
        updated = []

        for ticker, pos in self.positions.items():
            current_price = self.get_current_price(ticker)
            if current_price:
                pos['last_known_price'] = current_price
            else:
                # Use last known price as fallback for trailing stop updates
                fallback_price = pos.get('last_known_price')
                if fallback_price:
                    current_price = fallback_price
                    logger.warning(
                        f"Cannot get live price for {ticker}, using last known "
                        f"price ${fallback_price:.2f} for trailing stop update"
                    )
                else:
                    continue

            entry_price = pos['entry_price']
            pnl_pct = calculate_pnl_pct(entry_price, current_price)

            # Track highest price
            if current_price > pos.get('highest_price', 0):
                pos['highest_price'] = current_price

            # Enable trailing stop after threshold gain
            if not pos.get('trailing_enabled'):
                if pnl_pct >= config.TRAILING_TRIGGER_PCT * 100:
                    pos['trailing_enabled'] = True
                    logger.info(f"{ticker}: Trailing stop ENABLED at +{pnl_pct:.1f}%")

                    # Audit log trailing stop activation
                    log_audit_event('TRAILING_STOP_ENABLED', {
                        'ticker': ticker,
                        'trigger_pnl_pct': round(pnl_pct, 2),
                        'current_price': round(current_price, 2),
                        'entry_price': round(entry_price, 2),
                        'current_stop': round(pos['stop_loss'], 2)
                    })

            # Update trailing stop
            if pos.get('trailing_enabled'):
                # Determine trailing percentage based on gain
                if pnl_pct > config.HUGE_WINNER_THRESHOLD:
                    trailing_pct = config.HUGE_WINNER_STOP_PCT
                elif pnl_pct > config.BIG_WINNER_THRESHOLD:
                    trailing_pct = config.BIG_WINNER_STOP_PCT
                else:
                    trailing_pct = config.TRAILING_STOP_PCT

                new_stop = current_price * (1 - trailing_pct)

                # Only raise stop, never lower
                if new_stop > pos['stop_loss']:
                    old_stop = pos['stop_loss']
                    pos['stop_loss'] = new_stop

                    updated.append({
                        'ticker': ticker,
                        'old_stop': old_stop,
                        'new_stop': new_stop,
                        'trailing_pct': trailing_pct * 100,
                        'pnl_pct': pnl_pct
                    })

                    logger.info(
                        f"{ticker}: Stop raised ${old_stop:.2f} -> ${new_stop:.2f} "
                        f"(trailing {trailing_pct*100:.0f}%)"
                    )

                    # Audit log the trailing stop update for historical tracking
                    log_audit_event('TRAILING_STOP_UPDATED', {
                        'ticker': ticker,
                        'old_stop': round(old_stop, 2),
                        'new_stop': round(new_stop, 2),
                        'trailing_pct': round(trailing_pct * 100, 1),
                        'current_price': round(current_price, 2),
                        'highest_price': round(pos.get('highest_price', current_price), 2),
                        'entry_price': round(entry_price, 2),
                        'pnl_pct': round(pnl_pct, 2)
                    })

        if updated:
            self.save_positions()

        return updated

    # =========================================================================
    # Position Synchronization
    # =========================================================================

    def sync_with_broker(self) -> Dict[str, Any]:
        """
        Cross-check and sync positions with broker.

        This ensures positions.json always matches broker state by:
        - Adding positions that exist at broker but not locally
        - Removing positions that exist locally but not at broker
        - Updating quantities that differ

        Returns:
            Sync results with corrections made
        """
        if not self.alpaca_client:
            return {'synced': False, 'reason': 'No alpaca client'}

        try:
            broker_positions = self.alpaca_client.get_all_positions()
            broker_tickers = {pos['symbol']: pos for pos in broker_positions}
            local_tickers = set(self.positions.keys())

            corrections = {
                'added': [],
                'removed': [],
                'updated': []
            }

            # Find positions at broker but not local (ADD)
            for ticker, broker_pos in broker_tickers.items():
                if ticker not in local_tickers:
                    # Add missing position
                    shares = broker_pos['qty']
                    avg_entry = broker_pos['avg_entry_price']

                    # Look up signal history for tier-based stops
                    signal_info = self._lookup_signal_info(ticker)

                    if signal_info:
                        tier = signal_info.get('multi_signal_tier', 'none')
                        signal_score = signal_info.get('signal_score', 0)
                        sector = signal_info.get('sector', 'Unknown')

                        # Use tier-based stop loss if available
                        if tier in config.MULTI_SIGNAL_STOP_LOSS:
                            stop_loss_pct = config.MULTI_SIGNAL_STOP_LOSS[tier]
                            logger.info(f"  Using {tier} stop-loss ({stop_loss_pct*100:.0f}%) for {ticker}")
                        else:
                            stop_loss_pct = config.STOP_LOSS_PCT
                    else:
                        tier = 'none'
                        signal_score = 0
                        sector = 'Unknown'
                        stop_loss_pct = config.STOP_LOSS_PCT
                        logger.info(f"  No signal history for {ticker}, using default {stop_loss_pct*100:.0f}% stop")

                    stop_loss = avg_entry * (1 - stop_loss_pct)
                    take_profit = avg_entry * (1 + config.TAKE_PROFIT_PCT)

                    self.positions[ticker] = {
                        'shares': shares,
                        'entry_price': avg_entry,
                        'entry_date': datetime.now(),
                        'cost_basis': shares * avg_entry,
                        'stop_loss': stop_loss,
                        'initial_stop_loss': stop_loss,
                        'take_profit': take_profit,
                        'highest_price': broker_pos.get('current_price', avg_entry),
                        'trailing_enabled': False,
                        'signal_score': signal_score,
                        'multi_signal_tier': tier,
                        'sector': sector,
                        'source': 'broker_sync',
                        'synced_at': datetime.now().isoformat()
                    }

                    corrections['added'].append({
                        'ticker': ticker,
                        'shares': shares,
                        'entry_price': avg_entry,
                        'tier': tier,
                        'stop_loss_pct': stop_loss_pct * 100
                    })
                    logger.info(f"  ➕ Added {ticker}: {shares} shares @ ${avg_entry:.2f} (stop: ${stop_loss:.2f})")

                elif self.positions[ticker]['shares'] != broker_pos['qty']:
                    # Update quantity mismatch
                    old_qty = self.positions[ticker]['shares']
                    new_qty = broker_pos['qty']
                    self.positions[ticker]['shares'] = new_qty
                    self.positions[ticker]['cost_basis'] = new_qty * self.positions[ticker]['entry_price']

                    corrections['updated'].append({
                        'ticker': ticker,
                        'old_qty': old_qty,
                        'new_qty': new_qty
                    })
                    logger.info(f"  🔄 Updated {ticker}: {old_qty} → {new_qty} shares")

            # Find positions local but not at broker (REMOVE)
            for ticker in local_tickers:
                if ticker not in broker_tickers:
                    removed_pos = self.positions[ticker]
                    del self.positions[ticker]

                    corrections['removed'].append({
                        'ticker': ticker,
                        'shares': removed_pos['shares']
                    })
                    logger.info(f"  ➖ Removed {ticker}: no longer at broker")

            # Always save after sync so live_positions.json exists for analyzers
            total_corrections = len(corrections['added']) + len(corrections['removed']) + len(corrections['updated'])
            self.save_positions()
            if total_corrections > 0:
                logger.info(f"✅ Synced {total_corrections} corrections to positions.json")

            return {
                'synced': True,
                'corrections': corrections,
                'total_corrections': total_corrections
            }

        except Exception as e:
            logger.error(f"Failed to sync with broker: {e}")
            return {'synced': False, 'error': str(e)}

    # =========================================================================
    # Monitoring Cycle
    # =========================================================================

    def run_monitoring_cycle(
        self,
        on_exit_callback=None,
        on_halt_callback=None
    ) -> Dict[str, Any]:
        """
        Run a complete monitoring cycle.

        This should be called periodically (e.g., every 5 minutes).

        Args:
            on_exit_callback: Callback(exit_info) when exit is triggered
            on_halt_callback: Callback(halt_reason) when circuit breaker triggers

        Returns:
            Cycle results dictionary
        """
        cycle_start = datetime.now()
        results = {
            'timestamp': cycle_start.isoformat(),
            'market_open': is_market_hours(),
            'positions_checked': len(self.positions),
            'exits_triggered': [],
            'stops_updated': [],
            'reconciliation': None,
            'sync': None,
            'circuit_breaker': None,
            'errors': []
        }

        # Skip if market is closed
        if not is_market_hours():
            results['skipped'] = 'Market closed'
            return results

        # Check circuit breakers first
        if self.alpaca_client:
            try:
                portfolio_value = self.alpaca_client.get_portfolio_value()
                # CRITICAL FIX: Pass daily_pnl which includes both realized AND unrealized P&L
                daily_pnl = self.alpaca_client.get_daily_pnl()
                is_halted, halt_reason = self.circuit_breaker.check_circuit_breakers(
                    portfolio_value,
                    daily_pnl=daily_pnl
                )

                if is_halted:
                    results['circuit_breaker'] = {
                        'triggered': True,
                        'reason': halt_reason
                    }

                    if on_halt_callback:
                        on_halt_callback(halt_reason)

                    logger.warning(f"Trading halted: {halt_reason}")
                    # Don't exit - still need to monitor existing positions

            except Exception as e:
                results['errors'].append(f"Circuit breaker check failed: {e}")

        # Sync with broker to ensure positions.json is accurate
        if self.alpaca_client:
            try:
                sync_results = self.sync_with_broker()
                results['sync'] = sync_results

                if sync_results.get('total_corrections', 0) > 0:
                    logger.info(f"📊 Position sync: {sync_results['total_corrections']} corrections made")
            except Exception as e:
                results['errors'].append(f"Broker sync failed: {e}")

        # Run reconciliation periodically (for reporting only now, sync handles corrections)
        if self.alpaca_client:
            try:
                is_synced, discrepancies = self.reconciler.reconcile(
                    self.positions,
                    self.alpaca_client
                )
                results['reconciliation'] = {
                    'synced': is_synced,
                    'discrepancies': len(discrepancies)
                }
            except Exception as e:
                results['errors'].append(f"Reconciliation failed: {e}")

        # Update trailing stops
        try:
            stops_updated = self.update_trailing_stops()
            results['stops_updated'] = stops_updated
        except Exception as e:
            results['errors'].append(f"Trailing stop update failed: {e}")

        # Check for exits
        try:
            exits = self.check_exits()
            results['exits_triggered'] = exits

            for exit_info in exits:
                if on_exit_callback:
                    on_exit_callback(exit_info)

        except Exception as e:
            results['errors'].append(f"Exit check failed: {e}")

        results['duration_seconds'] = (datetime.now() - cycle_start).total_seconds()
        return results

    # =========================================================================
    # Status and Statistics
    # =========================================================================

    def format_position_dashboard(self) -> str:
        """
        Build a human-readable position dashboard for monitor job logs.

        Returns:
            Formatted multi-line string with portfolio summary and per-position
            breakdown of price, P&L, stops, targets, trailing status, and warnings.
        """
        if not self.positions:
            return (
                "\n"
                "=" * 70 + "\n"
                "  POSITION DASHBOARD\n"
                "=" * 70 + "\n"
                f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  No open positions\n"
                "=" * 70 + "\n"
            )

        # Gather per-position data
        rows = []
        total_cost = 0.0
        total_value = 0.0
        total_pnl = 0.0

        for ticker, pos in self.positions.items():
            current_price = self.get_current_price(ticker)
            if not current_price:
                current_price = pos['entry_price']

            entry_price = pos['entry_price']
            shares = pos['shares']
            pnl_pct = calculate_pnl_pct(entry_price, current_price)
            pnl_dollars = (current_price - entry_price) * shares
            cost = entry_price * shares
            value = current_price * shares
            days_held = (datetime.now() - pos['entry_date']).days if isinstance(pos.get('entry_date'), datetime) else 0

            stop_loss = pos.get('stop_loss', entry_price * (1 - config.STOP_LOSS_PCT))
            take_profit = pos.get('take_profit', entry_price * (1 + config.TAKE_PROFIT_PCT))
            highest_price = pos.get('highest_price', current_price)
            trailing_enabled = pos.get('trailing_enabled', False)

            stop_dist = ((current_price - stop_loss) / current_price * 100) if current_price > 0 else 0
            target_dist = ((take_profit - current_price) / current_price * 100) if current_price > 0 else 0

            # Trailing tier label
            if trailing_enabled:
                if pnl_pct > config.HUGE_WINNER_THRESHOLD:
                    trail_label = f"ACTIVE  {config.HUGE_WINNER_STOP_PCT*100:.0f}% huge-winner"
                elif pnl_pct > config.BIG_WINNER_THRESHOLD:
                    trail_label = f"ACTIVE  {config.BIG_WINNER_STOP_PCT*100:.0f}% big-winner"
                else:
                    trail_label = f"ACTIVE  {config.TRAILING_STOP_PCT*100:.0f}% standard"
            else:
                pct_to_trigger = config.TRAILING_TRIGGER_PCT * 100 - pnl_pct
                if pct_to_trigger > 0:
                    trail_label = f"OFF  (need +{pct_to_trigger:.1f}% to activate)"
                else:
                    trail_label = "OFF"

            # Time-based warnings
            warnings = []
            if pnl_pct < 0 and days_held >= config.MAX_HOLD_LOSS_DAYS - 5:
                remaining = config.MAX_HOLD_LOSS_DAYS - days_held
                warnings.append(f"LOSS EXIT in {remaining}d" if remaining > 0 else "LOSS EXIT DUE")
            if 0 <= pnl_pct < config.MAX_HOLD_STAGNANT_THRESHOLD and days_held >= config.MAX_HOLD_STAGNANT_DAYS - 7:
                remaining = config.MAX_HOLD_STAGNANT_DAYS - days_held
                warnings.append(f"STAGNANT EXIT in {remaining}d" if remaining > 0 else "STAGNANT EXIT DUE")
            if days_held >= config.MAX_HOLD_EXTREME_DAYS - 7 and pnl_pct < config.MAX_HOLD_EXTREME_EXCEPTION:
                remaining = config.MAX_HOLD_EXTREME_DAYS - days_held
                warnings.append(f"MAX HOLD EXIT in {remaining}d" if remaining > 0 else "MAX HOLD EXIT DUE")

            total_cost += cost
            total_value += value
            total_pnl += pnl_dollars

            rows.append({
                'ticker': ticker,
                'shares': shares,
                'entry': entry_price,
                'current': current_price,
                'pnl_pct': pnl_pct,
                'pnl_dollars': pnl_dollars,
                'cost': cost,
                'value': value,
                'days': days_held,
                'stop': stop_loss,
                'stop_dist': stop_dist,
                'target': take_profit,
                'target_dist': target_dist,
                'trail_label': trail_label,
                'trailing_enabled': trailing_enabled,
                'highest': highest_price,
                'tier': pos.get('tier', '?'),
                'warnings': warnings,
            })

        # Sort best to worst
        rows.sort(key=lambda r: r['pnl_pct'], reverse=True)

        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Build output
        w = 70
        lines = []
        lines.append("")
        lines.append("=" * w)
        lines.append("  POSITION DASHBOARD")
        lines.append("=" * w)
        lines.append(f"  {now_str}  |  {len(rows)} position(s)")
        lines.append(f"  Portfolio Value: ${total_value:,.2f}  |  "
                      f"Cost Basis: ${total_cost:,.2f}")
        pnl_sign = "+" if total_pnl >= 0 else ""
        lines.append(f"  Total P&L: {pnl_sign}${total_pnl:,.2f}  "
                      f"({pnl_sign}{total_pnl_pct:.2f}%)")
        lines.append("=" * w)

        for i, r in enumerate(rows):
            if i > 0:
                lines.append("-" * w)

            sign = "+" if r['pnl_pct'] >= 0 else ""
            dsign = "+" if r['pnl_dollars'] >= 0 else ""

            lines.append(
                f"  {r['ticker']:<6}  "
                f"{r['shares']} shares  |  "
                f"Tier: {r['tier']}  |  "
                f"Day {r['days']}"
            )
            lines.append(
                f"    Price    : ${r['entry']:.2f} -> ${r['current']:.2f}  "
                f"({sign}{r['pnl_pct']:.2f}% / {dsign}${r['pnl_dollars']:.2f})"
            )
            lines.append(
                f"    Stop Loss: ${r['stop']:.2f}  "
                f"({r['stop_dist']:.1f}% below current)"
            )
            lines.append(
                f"    Target   : ${r['target']:.2f}  "
                f"({r['target_dist']:.1f}% above current)"
            )
            trail_line = f"    Trailing : {r['trail_label']}"
            if r['trailing_enabled']:
                trail_line += f"  |  High: ${r['highest']:.2f}"
            lines.append(trail_line)

            if r['warnings']:
                lines.append(f"    *** {' | '.join(r['warnings'])} ***")

        lines.append("=" * w)
        lines.append("")

        return "\n".join(lines)

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive monitor status."""
        total_pnl = self.calculate_total_pnl()

        status = {
            'timestamp': datetime.now().isoformat(),
            'market_open': is_market_hours(),
            'trading_window': is_trading_window(),
            'positions': {
                'count': len(self.positions),
                'tickers': list(self.positions.keys()),
                'total_value': total_pnl['total_value'],
                'total_pnl_dollars': total_pnl['total_pnl_dollars'],
                'total_pnl_pct': total_pnl['total_pnl_pct']
            },
            'circuit_breaker': self.circuit_breaker.get_status(),
            'last_reconciliation': (
                self.reconciler.last_reconciliation.isoformat()
                if self.reconciler.last_reconciliation else None
            )
        }

        return status


def create_position_monitor(alpaca_client=None) -> PositionMonitor:
    """Create and return a PositionMonitor instance."""
    return PositionMonitor(alpaca_client)


if __name__ == '__main__':
    # Test position monitor
    monitor = PositionMonitor()
    print(f"Status: {json.dumps(monitor.get_status(), indent=2, default=str)}")
