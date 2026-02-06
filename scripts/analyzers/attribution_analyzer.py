"""Attribution analyzer - attributes P&L to sectors and signal score brackets."""

import json
import traceback
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
            return {'error': str(e), 'traceback': traceback.format_exc()}

    def _load_sector_map(self):
        """Load sector data from live_positions.json."""
        positions_file = self.base_dir / 'automated_trading' / 'data' / 'live_positions.json'

        sector_map = {}
        if positions_file.exists():
            try:
                with open(positions_file, 'r') as f:
                    data = json.load(f)

                positions = data.get('positions', {})
                for ticker, pos in positions.items():
                    sector = pos.get('sector', '')
                    if sector:
                        sector_map[ticker] = sector
            except Exception:
                pass

        return sector_map

    def _load_trades_30d(self):
        """Load trades from last 30 days using LIVE audit log and live_positions.json for sectors."""
        audit_file = self.base_dir / 'automated_trading' / 'data' / 'audit_log.jsonl'

        if not audit_file.exists():
            return []

        cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        # Load sector map from live_positions.json
        sector_map = self._load_sector_map()

        # Load POSITION_CLOSED events from audit log
        trades = []
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

                    ticker = data.get('ticker') or data.get('symbol', 'UNKNOWN')

                    # Get sector: first from event data, then from live_positions
                    sector = data.get('sector', '') or sector_map.get(ticker, 'Unknown')
                    if not sector:
                        sector = 'Unknown'

                    try:
                        pnl = float(data.get('pnl', 0))
                    except (ValueError, TypeError):
                        pnl = 0.0

                    try:
                        pnl_pct = float(data.get('pnl_pct', 0))
                    except (ValueError, TypeError):
                        pnl_pct = 0.0

                    try:
                        score = float(data.get('signal_score', 0))
                    except (ValueError, TypeError):
                        score = 0

                    trades.append({
                        'ticker': ticker,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'sector': sector,
                        'score': score
                    })
                except Exception:
                    continue

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
