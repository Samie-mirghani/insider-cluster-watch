"""
Filter Analyzer - Analyzes filter effectiveness for AI insights.

Analyzes how well the trading filters (cooldown, downtrend, micro-cap, go-private)
are working by checking today's audit log for rejections.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path


class FilterAnalyzer:
    """Analyzes filter effectiveness - today only."""

    def __init__(self):
        """Initialize the filter analyzer."""
        self.base_dir = Path(__file__).parent.parent.parent

    def analyze(self):
        """
        Lightweight filter analysis - today only.

        Returns:
            dict: Filter effectiveness metrics
        """
        try:
            # Count rejections from today's audit log
            rejections = self._count_todays_rejections()

            # Find most significant rejection
            key_rejection = self._find_key_rejection(rejections)

            return {
                'total_blocks_today': len(rejections),
                'cooldown_blocks': sum(1 for r in rejections if 'cooldown' in r.lower()),
                'downtrend_blocks': sum(1 for r in rejections if 'downtrend' in r.lower()),
                'micro_cap_blocks': sum(1 for r in rejections if 'micro' in r.lower()),
                'go_private_blocks': sum(1 for r in rejections if 'go-private' in r.lower() or 'likely' in r.lower()),
                'key_rejection': key_rejection
            }
        except Exception as e:
            return {'error': str(e)}

    def _count_todays_rejections(self):
        """
        Stream audit log to find today's rejections.

        Returns:
            list: List of rejection reasons
        """
        rejections = []
        today = datetime.now().strftime('%Y-%m-%d')

        audit_file = self.base_dir / 'automated_trading' / 'data' / 'audit_log.jsonl'
        if not audit_file.exists():
            return rejections

        with open(audit_file, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    # Check if event is from today and is a rejection
                    if event.get('timestamp', '').startswith(today):
                        if event.get('event_type') == 'SIGNAL_REJECTED':
                            reason = event.get('data', {}).get('reason', '')
                            if reason:
                                rejections.append(reason)
                except:
                    continue

        return rejections

    def _find_key_rejection(self, rejections):
        """
        Identify most significant rejection.

        Args:
            rejections: List of rejection reasons

        Returns:
            dict or None: Key rejection info
        """
        if not rejections:
            return None

        # Prioritize go-private > downtrend > cooldown > micro-cap
        for r in rejections:
            if 'go-private' in r.lower() or 'likely' in r.lower():
                return {'reason': 'go-private', 'impact': 'prevented false positive'}

        for r in rejections:
            if 'downtrend' in r.lower():
                return {'reason': 'downtrend', 'impact': 'likely saved loss'}

        return {'reason': 'various', 'impact': 'maintained quality'}
