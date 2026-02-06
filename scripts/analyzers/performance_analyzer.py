"""
Performance Analyzer - Analyzes today's trading performance.

Analyzes today's exits only (not historical) to provide quick insights
on win rate and P&L for the AI summary.
"""

import json
from datetime import datetime
from pathlib import Path


class PerformanceAnalyzer:
    """Analyzes trading performance - today only."""

    def __init__(self):
        """Initialize the performance analyzer."""
        self.base_dir = Path(__file__).parent.parent.parent

    def analyze(self):
        """
        Lightweight performance analysis - today only.

        Returns:
            dict: Performance metrics for today's exits
        """
        try:
            exits = self._load_exits_today()

            if not exits:
                return {'exits_today': 0}

            winners = [e for e in exits if e.get('pnl', 0) > 0]
            losers = [e for e in exits if e.get('pnl', 0) <= 0]

            total_pnl = sum(e.get('pnl', 0) for e in exits)

            best = max(exits, key=lambda x: x.get('pnl_pct', 0)) if exits else None
            worst = min(exits, key=lambda x: x.get('pnl_pct', 0)) if exits else None

            return {
                'exits_today': len(exits),
                'winners': len(winners),
                'losers': len(losers),
                'total_pnl': round(total_pnl, 2),
                'best_trade': {
                    'ticker': best.get('ticker'),
                    'pnl_pct': round(best.get('pnl_pct', 0), 1)
                } if best else None,
                'worst_trade': {
                    'ticker': worst.get('ticker'),
                    'pnl_pct': round(worst.get('pnl_pct', 0), 1)
                } if worst else None
            }
        except Exception as e:
            import traceback
            return {'error': str(e), 'traceback': traceback.format_exc()}

    def _load_exits_today(self):
        """
        Load today's exits from audit log (LIVE trade data).

        Returns:
            list: List of exit dictionaries
        """
        # Use audit log directly - this is the source of truth for LIVE trades
        print("  [DEBUG] Loading exits from audit log (LIVE trades)")
        return self._load_exits_from_audit_log()

    def _load_exits_from_audit_log(self):
        """
        Extract exits from audit log for today.

        Returns:
            list: List of exit dictionaries
        """
        audit_file = self.base_dir / 'automated_trading' / 'data' / 'audit_log.jsonl'

        if not audit_file.exists():
            return []

        today = datetime.now().strftime('%Y-%m-%d')
        exits = []

        with open(audit_file, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line)

                    if event.get('timestamp', '').startswith(today):
                        if event.get('event_type') == 'POSITION_CLOSED':
                            details = event.get('details', {})
                            if not isinstance(details, dict):
                                details = {}

                            exits.append({
                                'ticker': details.get('ticker', 'UNKNOWN'),
                                'pnl': details.get('pnl', 0),
                                'pnl_pct': details.get('pnl_pct', 0),
                                'reason': details.get('reason', 'UNKNOWN'),
                                'time': event.get('timestamp')
                            })
                except Exception:
                    continue

        print(f"  [DEBUG] Found {len(exits)} exits in audit log for {today}")
        return exits
