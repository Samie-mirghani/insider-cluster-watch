"""
Execution Analyzer - Analyzes trade execution quality.

Analyzes today's execution quality including fill rate and slippage
from the execution_metrics.json file.
"""

import json
from pathlib import Path


class ExecutionAnalyzer:
    """Analyzes trade execution quality."""

    def __init__(self):
        """Initialize the execution analyzer."""
        self.base_dir = Path(__file__).parent.parent.parent

    def analyze(self):
        """
        Lightweight execution analysis.

        Returns:
            dict: Execution quality metrics
        """
        try:
            # Get today's execution data
            today_data = self._get_today_executions()

            if not today_data:
                return {'orders_today': 0}

            orders = today_data.get('total_orders', 0)
            filled = today_data.get('filled_orders', 0)
            fill_rate = today_data.get('fill_rate_pct', 0)
            slippage = today_data.get('avg_slippage_pct', 0)

            # Simple quality score (10 = perfect)
            quality = 10.0
            if fill_rate < 100:
                quality -= (100 - fill_rate) / 10
            quality -= min(abs(slippage) * 10, 3)  # Penalty for slippage

            return {
                'orders_today': orders,
                'fill_rate': round(fill_rate, 1),
                'avg_slippage_pct': round(slippage, 2),
                'quality_score': round(max(quality, 0), 1)
            }
        except Exception as e:
            import traceback
            return {'error': str(e), 'traceback': traceback.format_exc()}

    def _get_today_executions(self):
        """
        Get today's execution statistics.

        Returns:
            dict: Today's execution metrics or empty dict
        """
        from datetime import datetime

        metrics_file = self.base_dir / 'automated_trading' / 'data' / 'execution_metrics.json'

        if not metrics_file.exists():
            return {}

        try:
            with open(metrics_file, 'r') as f:
                data = json.load(f)

            # Get today's date
            today = datetime.now().strftime('%Y-%m-%d')

            # Get all executions for today
            executions = data.get('executions', [])
            today_execs = [e for e in executions if e.get('date') == today]

            if not today_execs:
                return {'total_orders': 0}

            # Calculate metrics - only count as filled if explicitly True
            filled = [e for e in today_execs if e.get('filled') is True]
            unfilled = [e for e in today_execs if e.get('filled') is False]
            unknown = [e for e in today_execs if 'filled' not in e]

            total_orders = len(today_execs)
            filled_count = len(filled)
            fill_rate = (filled_count / total_orders * 100) if total_orders > 0 else 0

            # Calculate average slippage from filled orders
            avg_slippage = 0
            if filled:
                slippages = [e.get('slippage_pct', 0) for e in filled]
                avg_slippage = sum(slippages) / len(slippages)

            return {
                'total_orders': total_orders,
                'filled_orders': filled_count,
                'unfilled_orders': len(unfilled),
                'unknown_status': len(unknown),
                'fill_rate_pct': fill_rate,
                'avg_slippage_pct': avg_slippage
            }

        except Exception as e:
            import traceback
            print(f"  [DEBUG] Error loading execution metrics: {e}")
            return {}
