"""Historical context analyzer - compares today's metrics against 30-day averages."""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict


class HistoricalAnalyzer:
    """
    Compute historical context metrics.

    Provides 30-day averages and comparisons for:
    - Win rate
    - Daily P&L
    """

    def __init__(self):
        self.base_dir = Path(__file__).parent.parent.parent

    def analyze(self):
        """Compute historical context - today vs 30-day averages."""
        try:
            win_rate_30d = self._compute_win_rate_30d()
            avg_pnl_30d = self._compute_avg_daily_pnl_30d()
            today_metrics = self._get_today_metrics()

            return {
                'win_rate': {
                    'today': today_metrics['win_rate'],
                    'avg_30d': win_rate_30d,
                    'delta': round(today_metrics['win_rate'] - win_rate_30d, 1),
                    'status': 'above' if today_metrics['win_rate'] > win_rate_30d else 'below'
                },
                'daily_pnl': {
                    'today': today_metrics['pnl'],
                    'avg_30d': avg_pnl_30d,
                    'delta': round(today_metrics['pnl'] - avg_pnl_30d, 2),
                    'status': 'above' if today_metrics['pnl'] > avg_pnl_30d else 'below'
                },
                'sample_size_30d': today_metrics['sample_size']
            }
        except Exception as e:
            return {'error': str(e)}

    def _compute_win_rate_30d(self):
        """Calculate 30-day win rate from paper trades."""
        trades_file = self.base_dir / 'data' / 'paper_trades.csv'

        if not trades_file.exists():
            return 0.0

        cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        wins = 0
        total = 0

        with open(trades_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('action') == 'SELL' and row.get('date', '') >= cutoff_date:
                    total += 1
                    pnl = float(row.get('pnl', 0))
                    if pnl > 0:
                        wins += 1

        return round((wins / total * 100) if total > 0 else 0, 1)

    def _compute_avg_daily_pnl_30d(self):
        """Calculate average daily P&L from paper trades."""
        trades_file = self.base_dir / 'data' / 'paper_trades.csv'

        if not trades_file.exists():
            return 0.0

        cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        daily_pnl = defaultdict(float)

        with open(trades_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('action') == 'SELL' and row.get('date', '') >= cutoff_date:
                    date = row.get('date')
                    pnl = float(row.get('pnl', 0))
                    daily_pnl[date] += pnl

        if not daily_pnl:
            return 0.0

        return round(sum(daily_pnl.values()) / len(daily_pnl), 2)

    def _get_today_metrics(self):
        """Get today's performance metrics."""
        trades_file = self.base_dir / 'data' / 'paper_trades.csv'
        today = datetime.now().strftime('%Y-%m-%d')

        wins = 0
        total = 0
        pnl = 0.0

        if trades_file.exists():
            with open(trades_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('action') == 'SELL' and row.get('date') == today:
                        total += 1
                        trade_pnl = float(row.get('pnl', 0))
                        pnl += trade_pnl
                        if trade_pnl > 0:
                            wins += 1

        win_rate = (wins / total * 100) if total > 0 else 0

        return {
            'win_rate': round(win_rate, 1),
            'pnl': round(pnl, 2),
            'sample_size': total
        }
