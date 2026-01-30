# automated_trading/execution_metrics.py
"""
Execution Metrics Tracker

Tracks and analyzes order execution quality:
- Slippage (difference between signal price and fill price)
- Fill rates (percentage of limit orders that fill)
- Execution timing
- Daily/weekly statistics

This data helps optimize LIMIT_ORDER_CUSHION_PCT and EXECUTION_START_TIME.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from statistics import mean, median, stdev

from . import config
from .utils import (
    load_json_file,
    save_json_file,
    log_audit_event
)

logger = logging.getLogger(__name__)


class ExecutionMetrics:
    """
    Tracks order execution quality metrics.

    Key Metrics:
    - Slippage: Difference between expected price and actual fill price
    - Fill Rate: Percentage of limit orders that execute
    - Time to Fill: How long orders take to fill
    - Price Impact: How much we move the market
    """

    def __init__(self):
        """Initialize execution metrics tracker."""
        self.executions: List[Dict] = []
        self.daily_stats: Dict[str, Dict] = {}
        self._load_state()

    def _load_state(self):
        """Load execution history from disk."""
        data = load_json_file(config.EXECUTION_METRICS_FILE, default={})
        self.executions = data.get('executions', [])
        self.daily_stats = data.get('daily_stats', {})

        # Keep only last 90 days of executions
        cutoff = (datetime.now() - timedelta(days=90)).isoformat()
        self.executions = [
            e for e in self.executions
            if e.get('timestamp', '') >= cutoff
        ]

        logger.info(f"Loaded {len(self.executions)} execution records")

    def _save_state(self):
        """Save execution history to disk."""
        data = {
            'executions': self.executions,
            'daily_stats': self.daily_stats,
            'last_updated': datetime.now().isoformat()
        }
        save_json_file(config.EXECUTION_METRICS_FILE, data)

    # =========================================================================
    # Recording Executions
    # =========================================================================

    def record_execution(
        self,
        ticker: str,
        side: str,
        signal_price: float,
        limit_price: Optional[float],
        filled_price: float,
        shares: int,
        order_type: str,
        submitted_at: str,
        filled_at: str
    ) -> Dict[str, Any]:
        """
        Record an executed order with slippage calculation.

        Args:
            ticker: Stock ticker
            side: 'BUY' or 'SELL'
            signal_price: Expected price from signal
            limit_price: Limit price set (None for market orders)
            filled_price: Actual fill price
            shares: Number of shares
            order_type: 'MARKET' or 'LIMIT'
            submitted_at: When order was submitted (ISO format)
            filled_at: When order filled (ISO format)

        Returns:
            Execution record with calculated metrics
        """
        # Calculate slippage
        if side == 'BUY':
            # For buys, positive slippage = paid more than expected (bad)
            slippage_dollars = filled_price - signal_price
        else:
            # For sells, positive slippage = received less than expected (bad)
            slippage_dollars = signal_price - filled_price

        slippage_pct = (slippage_dollars / signal_price * 100) if signal_price > 0 else 0

        # Calculate time to fill
        try:
            submitted = datetime.fromisoformat(submitted_at)
            filled = datetime.fromisoformat(filled_at)
            time_to_fill_seconds = (filled - submitted).total_seconds()
        except:
            time_to_fill_seconds = 0

        # Calculate cost of slippage
        slippage_cost = slippage_dollars * shares

        execution = {
            'timestamp': filled_at,
            'date': datetime.fromisoformat(filled_at).strftime('%Y-%m-%d'),
            'ticker': ticker,
            'side': side,
            'order_type': order_type,
            'shares': shares,
            'signal_price': signal_price,
            'limit_price': limit_price,
            'filled_price': filled_price,
            'slippage_dollars': slippage_dollars,
            'slippage_pct': slippage_pct,
            'slippage_cost': slippage_cost,
            'time_to_fill_seconds': time_to_fill_seconds,
            'execution_time': datetime.fromisoformat(filled_at).strftime('%H:%M:%S')
        }

        self.executions.append(execution)
        self._save_state()

        # Log significant slippage
        if abs(slippage_pct) > config.MAX_SLIPPAGE_ALERT_PCT:
            log_audit_event('HIGH_SLIPPAGE_DETECTED', {
                'ticker': ticker,
                'side': side,
                'signal_price': signal_price,
                'filled_price': filled_price,
                'slippage_pct': round(slippage_pct, 2),
                'slippage_cost': round(slippage_cost, 2)
            }, outcome='WARNING')

            logger.warning(
                f"⚠️ HIGH SLIPPAGE: {ticker} {side} "
                f"{slippage_pct:+.2f}% (${slippage_cost:+.2f})"
            )

        logger.info(
            f"Execution recorded: {ticker} {side} x{shares} @ ${filled_price:.2f} "
            f"(slippage: {slippage_pct:+.2f}%)"
        )

        return execution

    def record_unfilled_order(
        self,
        ticker: str,
        side: str,
        signal_price: float,
        limit_price: float,
        shares: int,
        reason: str,
        submitted_at: str,
        expired_at: str
    ) -> Dict[str, Any]:
        """
        Record a limit order that did not fill.

        This helps track fill rate and understand why orders don't execute.

        Args:
            ticker: Stock ticker
            side: 'BUY' or 'SELL'
            signal_price: Expected price from signal
            limit_price: Limit price that was set
            shares: Number of shares
            reason: Why order didn't fill (EXPIRED, CANCELLED, etc.)
            submitted_at: When order was submitted
            expired_at: When order expired/cancelled

        Returns:
            Unfilled order record
        """
        unfilled = {
            'timestamp': expired_at,
            'date': datetime.fromisoformat(expired_at).strftime('%Y-%m-%d'),
            'ticker': ticker,
            'side': side,
            'order_type': 'LIMIT',
            'shares': shares,
            'signal_price': signal_price,
            'limit_price': limit_price,
            'filled': False,
            'reason': reason,
            'time_pending_seconds': (
                (datetime.fromisoformat(expired_at) -
                 datetime.fromisoformat(submitted_at)).total_seconds()
            )
        }

        self.executions.append(unfilled)
        self._save_state()

        logger.info(f"Unfilled order recorded: {ticker} {side} @ ${limit_price:.2f} - {reason}")

        return unfilled

    # =========================================================================
    # Statistics and Analysis
    # =========================================================================

    def get_slippage_stats(
        self,
        days: int = 30,
        side: Optional[str] = None,
        order_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate slippage statistics for recent executions.

        Args:
            days: Number of days to analyze
            side: Optional filter by BUY/SELL
            order_type: Optional filter by MARKET/LIMIT

        Returns:
            Dictionary with slippage statistics
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        # Filter executions
        filtered = [
            e for e in self.executions
            if e.get('timestamp', '') >= cutoff
            and e.get('filled', True)  # Only filled orders
        ]

        if side:
            filtered = [e for e in filtered if e['side'] == side]

        if order_type:
            filtered = [e for e in filtered if e['order_type'] == order_type]

        if not filtered:
            return {
                'count': 0,
                'avg_slippage_pct': 0,
                'median_slippage_pct': 0,
                'total_slippage_cost': 0
            }

        slippages = [e['slippage_pct'] for e in filtered]
        costs = [e['slippage_cost'] for e in filtered]

        stats = {
            'count': len(filtered),
            'avg_slippage_pct': mean(slippages),
            'median_slippage_pct': median(slippages),
            'std_slippage_pct': stdev(slippages) if len(slippages) > 1 else 0,
            'min_slippage_pct': min(slippages),
            'max_slippage_pct': max(slippages),
            'total_slippage_cost': sum(costs),
            'avg_slippage_cost': mean(costs),
            'worst_executions': sorted(
                filtered,
                key=lambda x: abs(x['slippage_pct']),
                reverse=True
            )[:5]
        }

        return stats

    def get_fill_rate(
        self,
        days: int = 30,
        side: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate fill rate for limit orders.

        Args:
            days: Number of days to analyze
            side: Optional filter by BUY/SELL

        Returns:
            Fill rate statistics
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        # Get all limit orders
        limit_orders = [
            e for e in self.executions
            if e.get('timestamp', '') >= cutoff
            and e.get('order_type') == 'LIMIT'
        ]

        if side:
            limit_orders = [e for e in limit_orders if e['side'] == side]

        if not limit_orders:
            return {
                'total_orders': 0,
                'filled_orders': 0,
                'fill_rate_pct': 0
            }

        filled = [e for e in limit_orders if e.get('filled', True)]
        unfilled = [e for e in limit_orders if not e.get('filled', True)]

        fill_rate_pct = (len(filled) / len(limit_orders) * 100)

        return {
            'total_orders': len(limit_orders),
            'filled_orders': len(filled),
            'unfilled_orders': len(unfilled),
            'fill_rate_pct': fill_rate_pct,
            'unfilled_reasons': self._count_unfilled_reasons(unfilled)
        }

    def _count_unfilled_reasons(self, unfilled: List[Dict]) -> Dict[str, int]:
        """Count reasons why orders didn't fill."""
        reasons = {}
        for order in unfilled:
            reason = order.get('reason', 'UNKNOWN')
            reasons[reason] = reasons.get(reason, 0) + 1
        return reasons

    def get_daily_summary(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get execution summary for a specific date.

        Args:
            date: Date string (YYYY-MM-DD), defaults to today

        Returns:
            Daily execution summary
        """
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')

        day_executions = [
            e for e in self.executions
            if e.get('date') == date
        ]

        filled = [e for e in day_executions if e.get('filled', True)]
        unfilled = [e for e in day_executions if not e.get('filled', True)]

        if not filled:
            return {
                'date': date,
                'total_executions': 0,
                'total_slippage_cost': 0
            }

        return {
            'date': date,
            'total_orders': len(day_executions),
            'filled_orders': len(filled),
            'unfilled_orders': len(unfilled),
            'fill_rate_pct': len(filled) / len(day_executions) * 100 if day_executions else 0,
            'total_slippage_cost': sum(e['slippage_cost'] for e in filled),
            'avg_slippage_pct': mean([e['slippage_pct'] for e in filled]),
            'worst_slippage': max([abs(e['slippage_pct']) for e in filled]) if filled else 0,
            'market_orders': len([e for e in filled if e['order_type'] == 'MARKET']),
            'limit_orders': len([e for e in filled if e['order_type'] == 'LIMIT'])
        }

    def get_performance_report(self, days: int = 30) -> str:
        """
        Generate a human-readable performance report.

        Args:
            days: Number of days to analyze

        Returns:
            Formatted report string
        """
        slippage = self.get_slippage_stats(days)
        fill_rate = self.get_fill_rate(days)

        report_lines = [
            "",
            "=" * 70,
            f"  EXECUTION QUALITY REPORT (Last {days} Days)",
            "=" * 70,
            "",
            f"SLIPPAGE ANALYSIS:",
            f"  Executions: {slippage['count']}",
            f"  Average Slippage: {slippage['avg_slippage_pct']:+.3f}%",
            f"  Median Slippage: {slippage['median_slippage_pct']:+.3f}%",
            f"  Std Dev: {slippage['std_slippage_pct']:.3f}%",
            f"  Total Cost: ${slippage['total_slippage_cost']:+,.2f}",
            "",
            f"FILL RATE (Limit Orders):",
            f"  Total Orders: {fill_rate['total_orders']}",
            f"  Filled: {fill_rate['filled_orders']}",
            f"  Unfilled: {fill_rate['unfilled_orders']}",
            f"  Fill Rate: {fill_rate['fill_rate_pct']:.1f}%",
            "",
        ]

        # Show worst executions
        if slippage['worst_executions']:
            report_lines.append("WORST SLIPPAGES:")
            for i, exec in enumerate(slippage['worst_executions'][:3], 1):
                report_lines.append(
                    f"  {i}. {exec['ticker']} {exec['side']}: "
                    f"{exec['slippage_pct']:+.2f}% (${exec['slippage_cost']:+.2f})"
                )
            report_lines.append("")

        report_lines.append("=" * 70)
        report_lines.append("")

        return "\n".join(report_lines)


# Factory function
def create_execution_metrics() -> ExecutionMetrics:
    """Create and return an ExecutionMetrics instance."""
    return ExecutionMetrics()


if __name__ == '__main__':
    # Test execution metrics
    metrics = create_execution_metrics()

    # Show recent stats
    print(metrics.get_performance_report(30))
