"""Historical context analyzer - compares today's metrics against 30-day averages."""

import json
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
            # Load all exits from audit log once for efficiency
            exits_30d = self._load_exits_from_audit_log(days=30)

            if not exits_30d:
                return {'insufficient_data': True, 'sample_size_30d': 0}

            win_rate_30d = self._compute_win_rate(exits_30d)
            avg_pnl_30d = self._compute_avg_daily_pnl(exits_30d)
            today_metrics = self._get_today_metrics(exits_30d)

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

    def _load_exits_from_audit_log(self, days=30):
        """Load POSITION_CLOSED events from audit log for last N days."""
        audit_file = self.base_dir / 'automated_trading' / 'data' / 'audit_log.jsonl'

        if not audit_file.exists():
            return []

        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        exits = []

        with open(audit_file, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line)

                    if event.get('event_type') != 'POSITION_CLOSED':
                        continue

                    timestamp = event.get('timestamp', '')
                    if timestamp[:10] < cutoff_date:
                        continue

                    data = event.get('data', {})
                    if not isinstance(data, dict):
                        data = {}

                    exits.append({
                        'date': timestamp[:10],
                        'ticker': data.get('ticker') or data.get('symbol', 'UNKNOWN'),
                        'pnl': data.get('pnl', 0),
                        'pnl_pct': data.get('pnl_pct', 0),
                        'reason': data.get('reason', 'UNKNOWN'),
                        'time': timestamp
                    })
                except Exception:
                    continue

        return exits

    def _compute_win_rate(self, exits):
        """Calculate win rate from LIVE trade exits."""
        if not exits:
            return 0.0

        wins = sum(1 for e in exits if e.get('pnl', 0) > 0)
        total = len(exits)

        return round((wins / total * 100) if total > 0 else 0, 1)

    def _compute_avg_daily_pnl(self, exits):
        """Calculate average daily P&L from LIVE trade exits."""
        if not exits:
            return 0.0

        daily_pnl = defaultdict(float)
        for e in exits:
            daily_pnl[e['date']] += e.get('pnl', 0)

        if not daily_pnl:
            return 0.0

        return round(sum(daily_pnl.values()) / len(daily_pnl), 2)

    def _get_today_metrics(self, all_exits):
        """Get today's performance metrics from LIVE trade exits."""
        today = datetime.now().strftime('%Y-%m-%d')
        today_exits = [e for e in all_exits if e.get('date') == today]

        wins = sum(1 for e in today_exits if e.get('pnl', 0) > 0)
        total = len(today_exits)
        pnl = sum(e.get('pnl', 0) for e in today_exits)

        win_rate = (wins / total * 100) if total > 0 else 0

        return {
            'win_rate': round(win_rate, 1),
            'pnl': round(pnl, 2),
            'sample_size': total
        }
