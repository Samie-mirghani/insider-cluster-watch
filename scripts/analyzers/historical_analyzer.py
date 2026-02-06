"""Historical context analyzer - compares today's metrics against 30-day averages."""

import csv
import traceback
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

            today_wr = today_metrics['win_rate']
            delta = round(today_wr - win_rate_30d, 1)

            if delta > 0:
                status = 'above'
            elif delta < 0:
                status = 'below'
            else:
                status = 'at'

            today_pnl = today_metrics['pnl']
            pnl_delta = round(today_pnl - avg_pnl_30d, 2)

            if pnl_delta > 0:
                pnl_status = 'above'
            elif pnl_delta < 0:
                pnl_status = 'below'
            else:
                pnl_status = 'at'

            return {
                'win_rate': {
                    'today': today_wr,
                    'avg_30d': win_rate_30d,
                    'delta': delta,
                    'status': status
                },
                'daily_pnl': {
                    'today': today_pnl,
                    'avg_30d': avg_pnl_30d,
                    'delta': pnl_delta,
                    'status': pnl_status
                },
                'sample_size_30d': today_metrics['sample_size']
            }
        except Exception as e:
            return {'error': str(e), 'traceback': traceback.format_exc()}

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
                if row.get('action') != 'SELL':
                    continue
                exit_date = row.get('exit_date', '')[:10]
                if exit_date >= cutoff_date:
                    total += 1
                    profit = float(row.get('profit', 0) or 0)
                    if profit > 0:
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
                if row.get('action') != 'SELL':
                    continue
                exit_date = row.get('exit_date', '')[:10]
                if exit_date >= cutoff_date:
                    profit = float(row.get('profit', 0) or 0)
                    daily_pnl[exit_date] += profit

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
                    if row.get('action') != 'SELL':
                        continue
                    exit_date = row.get('exit_date', '')[:10]
                    if exit_date == today:
                        total += 1
                        trade_pnl = float(row.get('profit', 0) or 0)
                        pnl += trade_pnl
                        if trade_pnl > 0:
                            wins += 1

        win_rate = (wins / total * 100) if total > 0 else 0

        return {
            'win_rate': round(win_rate, 1),
            'pnl': round(pnl, 2),
            'sample_size': total
        }
