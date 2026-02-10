"""Trend analyzer - detects 7-day trends in key metrics."""

import json
import statistics
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict


class TrendAnalyzer:
    """
    Detect trends over last 7 days.

    Tracks:
    - Win rate trend (improving/declining)
    - P&L trend
    """

    def __init__(self):
        self.base_dir = Path(__file__).parent.parent.parent

    def analyze(self):
        """Detect 7-day trends."""
        try:
            daily_metrics = self._compute_daily_metrics_7d()

            if len(daily_metrics) < 2:
                return {'insufficient_data': True}

            win_rate_trend = self._calculate_trend(
                [d['win_rate'] for d in daily_metrics]
            )
            pnl_trend = self._calculate_trend(
                [d['pnl'] for d in daily_metrics]
            )

            return {
                'win_rate_trend': {
                    'direction': win_rate_trend['direction'],
                    'change': win_rate_trend['change'],
                    'significance': win_rate_trend['significance']
                },
                'pnl_trend': {
                    'direction': pnl_trend['direction'],
                    'change': pnl_trend['change'],
                    'significance': pnl_trend['significance']
                },
                'days_analyzed': len(daily_metrics)
            }
        except Exception as e:
            return {'error': str(e), 'traceback': traceback.format_exc()}

    def _compute_daily_metrics_7d(self):
        """Compute metrics for each of last 7 days from LIVE audit log."""
        audit_file = self.base_dir / 'automated_trading' / 'data' / 'audit_log.jsonl'

        if not audit_file.exists():
            return []

        today = datetime.now()
        dates = [
            (today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)
        ]
        date_set = set(dates)

        daily_data = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': 0.0})

        with open(audit_file, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line)

                    if event.get('event_type') != 'POSITION_CLOSED':
                        continue

                    exit_date = event.get('timestamp', '')[:10]
                    if exit_date not in date_set:
                        continue

                    data = event.get('data', {})
                    if not isinstance(data, dict):
                        data = {}

                    pnl = data.get('pnl', 0)
                    daily_data[exit_date]['total'] += 1
                    daily_data[exit_date]['pnl'] += pnl
                    if pnl > 0:
                        daily_data[exit_date]['wins'] += 1
                except Exception:
                    continue

        metrics = []
        for date in sorted(dates):
            if date in daily_data and daily_data[date]['total'] > 0:
                data = daily_data[date]
                metrics.append({
                    'date': date,
                    'win_rate': (data['wins'] / data['total'] * 100)
                    if data['total'] > 0 else 0,
                    'pnl': data['pnl']
                })

        return metrics

    def _calculate_trend(self, values):
        """Calculate trend direction and magnitude."""
        if len(values) < 2:
            return {'direction': 'stable', 'change': 0, 'significance': 'none'}

        mid = len(values) // 2
        first_half_avg = statistics.mean(values[:mid]) if values[:mid] else 0
        second_half_avg = statistics.mean(values[mid:]) if values[mid:] else 0

        change = second_half_avg - first_half_avg

        # Handle division by zero: if both halves are near zero, no trend
        if abs(first_half_avg) < 0.01 and abs(second_half_avg) < 0.01:
            change_pct = 0
        elif abs(first_half_avg) >= 0.01:
            change_pct = (change / abs(first_half_avg)) * 100
        elif change != 0:
            # First half was ~zero but second half isn't - percentage change
            # is undefined. Use the absolute change directly (capped at ±100)
            # so e.g. win rate going from 0% to 33% shows "+33.0%" not "+100.0%"
            change_pct = max(min(change, 100.0), -100.0)
        else:
            change_pct = 0

        if abs(change_pct) < 5:
            direction = 'stable'
            significance = 'none'
        elif change_pct > 0:
            direction = 'improving'
            significance = 'significant' if abs(change_pct) > 15 else 'moderate'
        else:
            direction = 'declining'
            significance = 'significant' if abs(change_pct) > 15 else 'moderate'

        return {
            'direction': direction,
            'change': round(change_pct, 1),
            'significance': significance
        }
