"""
Sector Analyzer - Analyzes sector concentration risk.

Checks current sector concentration to flag if portfolio is over-concentrated
in any single sector (e.g., >35% in Technology).
"""

import json
from pathlib import Path
from collections import Counter


class SectorAnalyzer:
    """Analyzes sector concentration risk."""

    def __init__(self):
        """Initialize the sector analyzer."""
        self.base_dir = Path(__file__).parent.parent.parent

    def analyze(self):
        """
        Lightweight sector analysis.

        Returns:
            dict: Sector concentration metrics
        """
        try:
            positions = self._load_positions()

            if not positions:
                return {'total_positions': 0}

            # Extract sectors - sector is a direct field, NOT nested in signal_data
            sectors = []
            for ticker, position in positions.items():
                # Try both locations for compatibility
                sector = position.get('sector') or position.get('signal_data', {}).get('sector', 'Unknown')
                sectors.append(sector)

            sector_counts = Counter(sectors)
            total = len(positions)

            if not sector_counts:
                return {'total_positions': total}

            top_sector, top_count = sector_counts.most_common(1)[0]
            top_pct = (top_count / total * 100) if total > 0 else 0

            risk = 'HIGH' if top_pct > 35 else 'MEDIUM' if top_pct > 25 else 'LOW'
            warning = f"{top_sector} concentration at {top_pct:.1f}%" if top_pct > 35 else None

            # Breakdown of all sectors for debugging
            sector_breakdown = {
                sector: {
                    'count': count,
                    'percentage': round(count / total * 100, 1)
                }
                for sector, count in sector_counts.items()
            }

            return {
                'total_positions': total,
                'top_sector': top_sector,
                'top_sector_pct': round(top_pct, 1),
                'concentration_risk': risk,
                'warning': warning,
                'sector_breakdown': sector_breakdown
            }
        except Exception as e:
            import traceback
            return {
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def _load_positions(self):
        """
        Load current positions - handles nested structure.

        Returns:
            dict: Current positions dictionary
        """
        positions_file = self.base_dir / 'automated_trading' / 'data' / 'live_positions.json'

        if not positions_file.exists():
            return {}

        with open(positions_file, 'r') as f:
            data = json.load(f)

        # Handle nested structure: {"positions": {...}, "last_updated": "..."}
        # Return just the positions dict
        if isinstance(data, dict) and 'positions' in data:
            return data['positions']

        # Fallback: if it's already just positions
        return data
