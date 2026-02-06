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
            import traceback
            return {'error': str(e), 'traceback': traceback.format_exc()}

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

        rejection_count = 0
        total_lines = 0

        with open(audit_file, 'r') as f:
            for line in f:
                total_lines += 1
                try:
                    event = json.loads(line)
                    timestamp = event.get('timestamp', '')

                    # Check if today
                    if timestamp.startswith(today):
                        event_type = event.get('event_type', '').lower()

                        # Look for various rejection patterns
                        if any(word in event_type for word in ['reject', 'skip', 'block', 'invalid']):
                            data = event.get('data', {})
                            reason = data.get('reason', '') if isinstance(data, dict) else ''
                            if reason:
                                rejections.append(reason)
                                rejection_count += 1

                except Exception:
                    continue

        # Debug logging
        if total_lines == 0:
            print("  [DEBUG] Audit log is empty")
        else:
            print(f"  [DEBUG] Scanned {total_lines} audit log lines, found {rejection_count} rejections for {today}")

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
