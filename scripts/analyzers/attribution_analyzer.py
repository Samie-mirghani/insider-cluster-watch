"""Attribution analyzer - attributes P&L to sectors and signal score brackets."""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict


class AttributionAnalyzer:
    """
    Attribute performance to:
    - Sectors
    - Signal score brackets
    """

    def __init__(self):
        self.base_dir = Path(__file__).parent.parent.parent

    def analyze(self):
        """Compute performance attribution for last 30 days."""
        try:
            trades = self._load_trades_30d()

            if not trades:
                return {'insufficient_data': True}

            sector_pnl = self._attribute_by_sector(trades)
            score_pnl = self._attribute_by_score(trades)

            best_sector = (
                max(sector_pnl.items(), key=lambda x: x[1]['total_pnl'])
                if sector_pnl else None
            )
            worst_sector = (
                min(sector_pnl.items(), key=lambda x: x[1]['total_pnl'])
                if sector_pnl else None
            )

            return {
                'sector_attribution': sector_pnl,
                'score_attribution': score_pnl,
                'best_sector': {
                    'sector': best_sector[0],
                    'pnl': best_sector[1]['total_pnl'],
                    'trades': best_sector[1]['count']
                } if best_sector else None,
                'worst_sector': {
                    'sector': worst_sector[0],
                    'pnl': worst_sector[1]['total_pnl'],
                    'trades': worst_sector[1]['count']
                } if worst_sector else None
            }
        except Exception as e:
            return {'error': str(e)}

    def _load_trades_30d(self):
        """Load trades from last 30 days with sector info."""
        trades_file = self.base_dir / 'data' / 'paper_trades.csv'
        signals_file = self.base_dir / 'data' / 'signals_history.csv'

        if not trades_file.exists() or not signals_file.exists():
            return []

        cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        # Load signals to get sector info
        signal_sectors = {}
        signal_scores = {}

        with open(signals_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row.get('ticker')
                date = row.get('date', '')
                if date >= cutoff_date:
                    signal_sectors[f"{ticker}_{date}"] = row.get(
                        'sector', 'Unknown'
                    )
                    signal_scores[f"{ticker}_{date}"] = float(
                        row.get('signal_score', 0)
                    )

        # Load trades and enrich with sector
        trades = []
        with open(trades_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if (row.get('action') == 'SELL'
                        and row.get('date', '') >= cutoff_date):
                    ticker = row.get('ticker')
                    date = row.get('date')

                    key = f"{ticker}_{date}"
                    sector = signal_sectors.get(key, 'Unknown')
                    score = signal_scores.get(key, 0)

                    trades.append({
                        'ticker': ticker,
                        'pnl': float(row.get('pnl', 0)),
                        'pnl_pct': float(row.get('pnl_pct', 0)),
                        'sector': sector,
                        'score': score
                    })

        return trades

    def _attribute_by_sector(self, trades):
        """Attribute P&L by sector."""
        sector_pnl = defaultdict(
            lambda: {'total_pnl': 0.0, 'count': 0, 'wins': 0}
        )

        for trade in trades:
            sector = trade['sector']
            pnl = trade['pnl']

            sector_pnl[sector]['total_pnl'] += pnl
            sector_pnl[sector]['count'] += 1
            if pnl > 0:
                sector_pnl[sector]['wins'] += 1

        result = {}
        for sector, data in sector_pnl.items():
            result[sector] = {
                'total_pnl': round(data['total_pnl'], 2),
                'count': data['count'],
                'win_rate': round(
                    (data['wins'] / data['count'] * 100)
                    if data['count'] > 0 else 0, 1
                )
            }

        return result

    def _attribute_by_score(self, trades):
        """Attribute P&L by score bracket."""
        brackets = {
            '10.0+': [],
            '9.0-9.9': [],
            '8.0-8.9': [],
            '7.0-7.9': []
        }

        for trade in trades:
            score = trade['score']
            pnl = trade['pnl']

            if score >= 10.0:
                brackets['10.0+'].append(pnl)
            elif score >= 9.0:
                brackets['9.0-9.9'].append(pnl)
            elif score >= 8.0:
                brackets['8.0-8.9'].append(pnl)
            elif score >= 7.0:
                brackets['7.0-7.9'].append(pnl)

        result = {}
        for bracket, pnls in brackets.items():
            if pnls:
                result[bracket] = {
                    'total_pnl': round(sum(pnls), 2),
                    'count': len(pnls),
                    'win_rate': round(
                        (sum(1 for p in pnls if p > 0) / len(pnls) * 100), 1
                    )
                }

        return result
