# automated_trading/signal_queue.py
"""
Signal Queue Manager

Manages the queue of signals waiting for capital deployment.
Supports intraday capital redeployment when positions are sold.

Features:
- Queue approved signals that couldn't be executed due to capital limits
- Prioritize signals by score
- Handle intraday redeployment of freed capital
- Track signal freshness and validity
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from . import config
from .utils import (
    load_json_file,
    save_json_file,
    log_audit_event,
    is_trading_window,
    minutes_until_market_close
)

logger = logging.getLogger(__name__)


class SignalQueue:
    """
    Manages a queue of signals waiting for capital.

    When capital is freed (position sold), queued signals can be
    deployed if conditions are met:
    - Price is within tolerance of original signal
    - Sufficient time before market close
    - Daily redeployment limit not exceeded
    """

    def __init__(self):
        """Initialize signal queue."""
        self.queued_signals: Dict[str, Dict] = {}  # ticker -> signal_info
        self.daily_redeployments: int = 0
        self.last_reset_date: Optional[str] = None
        self._load_state()

    def _load_state(self):
        """Load queued signals from disk."""
        data = load_json_file(config.QUEUED_SIGNALS_FILE, default={})
        self.queued_signals = data.get('signals', {})
        self.daily_redeployments = data.get('daily_redeployments', 0)
        self.last_reset_date = data.get('last_reset_date')

        # Reset daily counter if new day
        today = datetime.now().strftime('%Y-%m-%d')
        if self.last_reset_date != today:
            self.daily_redeployments = 0
            self.last_reset_date = today
            self._save_state()

        logger.info(f"Loaded {len(self.queued_signals)} queued signals")

    def _save_state(self):
        """Save queued signals to disk."""
        data = {
            'signals': self.queued_signals,
            'daily_redeployments': self.daily_redeployments,
            'last_reset_date': self.last_reset_date or datetime.now().strftime('%Y-%m-%d'),
            'last_updated': datetime.now().isoformat()
        }
        save_json_file(config.QUEUED_SIGNALS_FILE, data)

    # =========================================================================
    # Signal Queue Management
    # =========================================================================

    def add_signal(self, signal: Dict[str, Any], reason: str = 'INSUFFICIENT_CAPITAL') -> bool:
        """
        Add a signal to the queue.

        Args:
            signal: Signal data dictionary
            reason: Why signal is queued (INSUFFICIENT_CAPITAL, MAX_POSITIONS, etc.)

        Returns:
            True if added successfully
        """
        ticker = signal.get('ticker')
        if not ticker:
            logger.warning("Cannot queue signal without ticker")
            return False

        # Don't queue if already in queue
        if ticker in self.queued_signals:
            # Update with newer signal if score is higher
            existing = self.queued_signals[ticker]
            if signal.get('signal_score', 0) > existing.get('signal_score', 0):
                logger.info(f"Updating queued signal for {ticker} with higher score")
            else:
                logger.debug(f"Signal for {ticker} already queued with same/higher score")
                return False

        queue_entry = {
            'ticker': ticker,
            'signal_score': signal.get('signal_score', 0),
            'entry_price': signal.get('entry_price'),
            'original_price': signal.get('entry_price'),  # Track original for tolerance check
            'queued_at': datetime.now().isoformat(),
            'queued_reason': reason,
            'signal_data': signal,
            'eligible_for_redeployment': config.ENABLE_INTRADAY_REDEPLOYMENT
        }

        self.queued_signals[ticker] = queue_entry
        self._save_state()

        log_audit_event('SIGNAL_QUEUED', {
            'ticker': ticker,
            'score': signal.get('signal_score'),
            'reason': reason
        })

        logger.info(f"Signal queued: {ticker} (score: {signal.get('signal_score', 0):.2f}) - {reason}")
        return True

    def remove_signal(self, ticker: str, reason: str = 'MANUAL') -> Optional[Dict[str, Any]]:
        """
        Remove a signal from the queue.

        Args:
            ticker: Stock ticker
            reason: Why signal is being removed

        Returns:
            Removed signal or None
        """
        if ticker not in self.queued_signals:
            return None

        signal = self.queued_signals.pop(ticker)
        self._save_state()

        log_audit_event('SIGNAL_DEQUEUED', {
            'ticker': ticker,
            'reason': reason
        })

        return signal

    def get_queued_signal(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get a specific queued signal."""
        return self.queued_signals.get(ticker)

    def get_all_queued_signals(self) -> List[Dict[str, Any]]:
        """Get all queued signals sorted by score (highest first)."""
        signals = list(self.queued_signals.values())
        return sorted(signals, key=lambda x: x.get('signal_score', 0), reverse=True)

    def get_queue_size(self) -> int:
        """Get number of signals in queue."""
        return len(self.queued_signals)

    # =========================================================================
    # Intraday Redeployment
    # =========================================================================

    def can_redeploy_capital(self, freed_capital: float) -> Tuple[bool, str]:
        """
        Check if capital can be redeployed to queued signals.

        Args:
            freed_capital: Amount of capital freed from position sale

        Returns:
            Tuple of (can_redeploy, reason)
        """
        # Check if redeployment is enabled
        if not config.ENABLE_INTRADAY_REDEPLOYMENT:
            return False, "Intraday redeployment is disabled"

        # Check if any signals are queued
        if not self.queued_signals:
            return False, "No signals in queue"

        # Check daily limit
        if self.daily_redeployments >= config.REDEPLOYMENT_MAX_PER_DAY:
            return False, f"Daily redeployment limit reached ({config.REDEPLOYMENT_MAX_PER_DAY})"

        # Check if within trading window
        if not is_trading_window():
            return False, "Outside trading window"

        # Check time until close
        minutes_to_close = minutes_until_market_close()
        if minutes_to_close < config.REDEPLOYMENT_MIN_TIME_BEFORE_CLOSE:
            return False, f"Too close to market close ({minutes_to_close} min remaining)"

        # Check minimum capital
        if freed_capital < config.REDEPLOYMENT_MIN_FREED_CAPITAL:
            return False, f"Freed capital (${freed_capital:.2f}) below minimum (${config.REDEPLOYMENT_MIN_FREED_CAPITAL})"

        return True, "Redeployment allowed"

    def get_best_redeployment_candidate(
        self,
        available_capital: float,
        current_price_func,
        excluded_tickers: Optional[List[str]] = None,
        is_asset_tradeable_func=None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the best queued signal for capital redeployment.

        Args:
            available_capital: Capital available for redeployment
            current_price_func: Function to get current price for ticker
            excluded_tickers: Tickers to exclude (e.g., already held positions)
            is_asset_tradeable_func: Optional function to check if asset is tradeable

        Returns:
            Best candidate signal or None
        """
        excluded = set(excluded_tickers or [])
        candidates = []

        for ticker, signal in self.queued_signals.items():
            # Skip excluded tickers
            if ticker in excluded:
                continue

            # Skip if not eligible
            if not signal.get('eligible_for_redeployment', True):
                continue

            # Check if signal is still fresh (queued within last 24 hours)
            queued_at = datetime.fromisoformat(signal['queued_at'])
            if datetime.now() - queued_at > timedelta(hours=24):
                logger.debug(f"Skipping stale signal: {ticker}")
                continue

            # Check if asset is still tradeable (prevents deploying to halted/delisted stocks)
            if is_asset_tradeable_func:
                try:
                    is_tradeable, tradeable_msg = is_asset_tradeable_func(ticker)
                    if not is_tradeable:
                        logger.debug(f"Skipping {ticker}: not tradeable - {tradeable_msg}")
                        continue
                    if tradeable_msg:
                        logger.warning(f"{ticker} tradeable but with restrictions: {tradeable_msg}")
                except Exception as e:
                    logger.warning(f"Could not check tradeability for {ticker}: {e}")
                    continue

            # Get current price
            original_price = signal.get('original_price', 0)
            if original_price <= 0:
                continue

            try:
                current_price = current_price_func(ticker)
                if current_price is None or current_price <= 0:
                    continue

                # Check price tolerance
                price_diff_pct = abs(current_price - original_price) / original_price * 100
                if price_diff_pct > config.REDEPLOYMENT_PRICE_TOLERANCE_PCT:
                    logger.debug(
                        f"Skipping {ticker}: price moved {price_diff_pct:.1f}% "
                        f"(tolerance: {config.REDEPLOYMENT_PRICE_TOLERANCE_PCT}%)"
                    )
                    continue

                # Calculate position size
                position_value = available_capital * 0.95  # Leave 5% buffer
                shares = int(position_value / current_price)

                if shares <= 0:
                    continue

                # Add to candidates with updated info
                candidate = {
                    **signal,
                    'current_price': current_price,
                    'price_diff_pct': price_diff_pct,
                    'potential_shares': shares,
                    'potential_value': shares * current_price
                }
                candidates.append(candidate)

            except Exception as e:
                logger.error(f"Error evaluating {ticker} for redeployment: {e}")
                continue

        if not candidates:
            return None

        # Return highest score candidate
        return max(candidates, key=lambda x: x.get('signal_score', 0))

    def mark_redeployment_used(self, ticker: str) -> None:
        """
        Mark that a redeployment was executed.

        Args:
            ticker: Ticker that was redeployed
        """
        self.daily_redeployments += 1
        self.remove_signal(ticker, reason='REDEPLOYED')

        log_audit_event('CAPITAL_REDEPLOYED', {
            'ticker': ticker,
            'daily_count': self.daily_redeployments
        })

        logger.info(
            f"Redeployment executed: {ticker} "
            f"(daily count: {self.daily_redeployments}/{config.REDEPLOYMENT_MAX_PER_DAY})"
        )

    # =========================================================================
    # Queue Cleanup
    # =========================================================================

    def cleanup_stale_signals(self, max_age_hours: int = 48) -> List[Dict[str, Any]]:
        """
        Remove signals older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours

        Returns:
            List of removed signals
        """
        removed = []
        cutoff = datetime.now() - timedelta(hours=max_age_hours)

        for ticker in list(self.queued_signals.keys()):
            signal = self.queued_signals[ticker]
            queued_at = datetime.fromisoformat(signal['queued_at'])

            if queued_at < cutoff:
                removed_signal = self.remove_signal(ticker, reason='STALE')
                if removed_signal:
                    removed.append(removed_signal)
                    logger.info(f"Removed stale signal: {ticker}")

        return removed

    def reset_daily_counters(self) -> None:
        """Reset daily redeployment counters (called at start of new trading day)."""
        self.daily_redeployments = 0
        self.last_reset_date = datetime.now().strftime('%Y-%m-%d')
        self._save_state()
        logger.info("Daily redeployment counters reset")

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get statistics about the signal queue."""
        signals = list(self.queued_signals.values())

        avg_score = (
            sum(s.get('signal_score', 0) for s in signals) / len(signals)
            if signals else 0
        )

        return {
            'queue_size': len(signals),
            'daily_redeployments_used': self.daily_redeployments,
            'daily_redeployments_remaining': max(0, config.REDEPLOYMENT_MAX_PER_DAY - self.daily_redeployments),
            'redeployment_enabled': config.ENABLE_INTRADAY_REDEPLOYMENT,
            'average_score': avg_score,
            'top_ticker': signals[0]['ticker'] if signals else None,
            'top_score': signals[0].get('signal_score', 0) if signals else 0
        }


# Factory function
def create_signal_queue() -> SignalQueue:
    """Create and return a SignalQueue instance."""
    return SignalQueue()


if __name__ == '__main__':
    # Test signal queue
    queue = SignalQueue()

    # Add test signals
    test_signal = {
        'ticker': 'AAPL',
        'signal_score': 12.5,
        'entry_price': 175.00
    }

    queue.add_signal(test_signal, reason='TEST')

    print(f"Queue stats: {queue.get_queue_stats()}")
    print(f"Can redeploy: {queue.can_redeploy_capital(500.00)}")
