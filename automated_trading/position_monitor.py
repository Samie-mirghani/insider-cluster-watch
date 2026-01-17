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

    def __init__(self):
        self.daily_pnl: float = 0.0
        self.consecutive_losses: int = 0
        self.is_halted: bool = False
        self.halt_reason: Optional[str] = None
        self.trades_today: List[Dict] = []
        self.last_reset_date: Optional[str] = None
        self._load_state()

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
            self.last_reset_date = today
            logger.info("New trading day - circuit breakers reset")
        else:
            self.daily_pnl = data.get('daily_pnl', 0.0)
            self.consecutive_losses = data.get('consecutive_losses', 0)
            self.is_halted = data.get('is_halted', False)
            self.halt_reason = data.get('halt_reason')
            self.trades_today = data.get('trades_today', [])
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

    def check_circuit_breakers(self, portfolio_value: float) -> Tuple[bool, Optional[str]]:
        """
        Check if any circuit breakers are triggered.

        Args:
            portfolio_value: Current portfolio value

        Returns:
            Tuple of (is_triggered, reason)
        """
        # Already halted
        if self.is_halted:
            return True, self.halt_reason

        # Daily loss limit
        daily_loss_limit = config.get_daily_loss_limit_dollars(portfolio_value)
        if self.daily_pnl <= -daily_loss_limit:
            self._trigger_halt(
                f"DAILY_LOSS_LIMIT: ${abs(self.daily_pnl):,.2f} loss exceeds ${daily_loss_limit:,.2f} limit"
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

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            'is_halted': self.is_halted,
            'halt_reason': self.halt_reason,
            'daily_pnl': self.daily_pnl,
            'consecutive_losses': self.consecutive_losses,
            'trades_today': len(self.trades_today)
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
        self.circuit_breaker = CircuitBreakerState()
        self.reconciler = Reconciler()
        self._load_positions()

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

        for ticker, pos in self.positions.items():
            current_price = self.get_current_price(ticker)
            if not current_price:
                logger.warning(f"Cannot get price for {ticker}, skipping exit check")
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
            if not current_price:
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

        if updated:
            self.save_positions()

        return updated

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
                is_halted, halt_reason = self.circuit_breaker.check_circuit_breakers(portfolio_value)

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

        # Run reconciliation periodically
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
