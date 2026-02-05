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
            metrics = self._load_metrics()

            if not metrics:
                return {'orders_today': 0}

            # Get today's metrics
            today = metrics.get('daily_metrics', {}).get('today', {})

            orders = today.get('orders_submitted', 0)
            filled = today.get('orders_filled', 0)
            fill_rate = (filled / orders * 100) if orders > 0 else 0

            slippage = today.get('avg_slippage_pct', 0)

            # Simple quality score (10 = perfect)
            quality = 10.0
            if fill_rate < 100:
                quality -= (100 - fill_rate) / 10
            quality -= min(slippage * 10, 3)  # Penalty for slippage

            return {
                'orders_today': orders,
                'fill_rate': round(fill_rate, 1),
                'avg_slippage_pct': round(slippage, 2),
                'quality_score': round(max(quality, 0), 1)
            }
        except Exception as e:
            return {'error': str(e)}

    def _load_metrics(self):
        """
        Load execution metrics.

        Returns:
            dict: Execution metrics dictionary
        """
        metrics_file = self.base_dir / 'automated_trading' / 'data' / 'execution_metrics.json'

        if not metrics_file.exists():
            return {}

        with open(metrics_file, 'r') as f:
            return json.load(f)
