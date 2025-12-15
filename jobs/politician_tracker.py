"""
Politician Performance Tracker with Time-Decay System

Tracks politician trading activity and applies time-decay weighting for retiring/retired politicians.
Instead of immediately deleting trades from politicians leaving office, this system gradually
reduces their weight over time while preserving historical performance data.

Key Features:
- Time-decay for retiring politicians (gradual weight reduction)
- Historical performance preservation (valuable for analysis)
- "Lame duck" trading pattern analysis
- Support for politicians returning to office
- Bipartisan signal detection

Time-Decay Strategy:
- Active politicians: Full base weight
- Retiring politicians (announced, not yet left): BOOST weight (lame duck urgency)
- Recently retired (0-180 days): Exponential decay from 100% to 20%
- Long-term retired (180+ days): Minimum weight (20% of base)
- Never reaches zero (preserves historical value)
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Data paths
DATA_DIR = Path(__file__).parent.parent / 'data'
POLITICIAN_REGISTRY_PATH = DATA_DIR / 'politician_registry.json'
POLITICIAN_TRADES_HISTORY_PATH = DATA_DIR / 'politician_trades_history.csv'


class PoliticianTracker:
    """
    Tracks politician trading activity with time-decay weighting for retiring/retired politicians.
    """

    def __init__(
        self,
        decay_half_life_days: int = 90,
        min_weight_fraction: float = 0.2,
        retiring_boost: float = 1.5,
        default_weight: float = 1.0
    ):
        """
        Initialize the politician tracker.

        Args:
            decay_half_life_days: Half-life for exponential decay (default: 90 days)
                                 After this period, weight is reduced to 50% of original
            min_weight_fraction: Minimum weight fraction for retired politicians (default: 0.2 = 20%)
                                Never decay below this to preserve historical value
            retiring_boost: Weight multiplier for politicians in "lame duck" period (default: 1.5)
                           Applied when retirement announced but not yet effective
            default_weight: Default weight for unknown politicians (default: 1.0)
        """
        self.decay_half_life_days = decay_half_life_days
        self.min_weight_fraction = min_weight_fraction
        self.retiring_boost = retiring_boost
        self.default_weight = default_weight

        self.registry = self._load_registry()
        self.trades_history = self._load_trades_history()

        logger.info(f"PoliticianTracker initialized with {len(self.registry.get('politicians', {}))} politicians")
        logger.info(f"Time-decay settings: half_life={decay_half_life_days}d, min_weight={min_weight_fraction*100}%")

    def _load_registry(self) -> Dict:
        """Load politician registry from JSON file."""
        if POLITICIAN_REGISTRY_PATH.exists():
            try:
                with open(POLITICIAN_REGISTRY_PATH, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Could not parse {POLITICIAN_REGISTRY_PATH}: {e}")
                return self._create_default_registry()
        logger.warning(f"Registry not found at {POLITICIAN_REGISTRY_PATH}, creating default")
        return self._create_default_registry()

    def _create_default_registry(self) -> Dict:
        """Create a default registry structure."""
        return {
            "politicians": {},
            "metadata": {
                "last_updated": datetime.now().isoformat(),
                "version": "1.0.0"
            }
        }

    def _save_registry(self):
        """Save politician registry to JSON file."""
        POLITICIAN_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.registry['metadata']['last_updated'] = datetime.now().isoformat()
        with open(POLITICIAN_REGISTRY_PATH, 'w') as f:
            json.dump(self.registry, f, indent=2)
        logger.info(f"Registry saved to {POLITICIAN_REGISTRY_PATH}")

    def _load_trades_history(self) -> pd.DataFrame:
        """Load politician trades history from CSV file."""
        if POLITICIAN_TRADES_HISTORY_PATH.exists():
            try:
                df = pd.read_csv(POLITICIAN_TRADES_HISTORY_PATH, parse_dates=['trade_date'])
                logger.info(f"Loaded {len(df)} historical politician trades")
                return df
            except Exception as e:
                logger.error(f"Could not load {POLITICIAN_TRADES_HISTORY_PATH}: {e}")
                return self._create_empty_trades_df()
        return self._create_empty_trades_df()

    def _create_empty_trades_df(self) -> pd.DataFrame:
        """Create an empty trades history DataFrame with the correct schema."""
        return pd.DataFrame(columns=[
            'trade_date', 'politician', 'ticker', 'transaction_type', 'amount',
            'conviction_score', 'party', 'office', 'status_at_trade',
            'weight_at_trade', 'last_updated'
        ])

    def _save_trades_history(self):
        """Save politician trades history to CSV file."""
        POLITICIAN_TRADES_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.trades_history.to_csv(POLITICIAN_TRADES_HISTORY_PATH, index=False)
        logger.info(f"Trades history saved to {POLITICIAN_TRADES_HISTORY_PATH}")

    def calculate_time_decay_weight(
        self,
        politician_name: str,
        current_date: Optional[datetime] = None
    ) -> float:
        """
        Calculate the time-decayed weight for a politician based on their retirement status.

        Args:
            politician_name: Name of the politician
            current_date: Reference date (defaults to today)

        Returns:
            Calculated weight (base_weight * decay_factor * status_multiplier)

        Weight Calculation Logic:
        1. Active: base_weight * 1.0 (full weight)
        2. Retiring: base_weight * retiring_boost (e.g., 1.5x - lame duck urgency!)
        3. Retired: base_weight * exponential_decay (50% after half_life_days)
           - Decay formula: max(min_weight_fraction, exp(-days_retired / half_life_days))
           - Never goes below min_weight_fraction (preserves historical value)
        """
        if current_date is None:
            current_date = datetime.now()

        politician = self.registry.get('politicians', {}).get(politician_name)

        if not politician:
            logger.debug(f"Politician '{politician_name}' not in registry, using default weight")
            return self.default_weight

        base_weight = politician.get('base_weight', self.default_weight)
        status = politician.get('current_status', 'active')

        # Active politicians get full weight
        if status == 'active':
            return base_weight

        # Retiring politicians (announced but not yet left) get BOOST
        # This captures "lame duck" trading patterns which can be highly valuable
        if status == 'retiring':
            logger.debug(f"{politician_name} is retiring - applying {self.retiring_boost}x boost")
            return base_weight * self.retiring_boost

        # Retired politicians get exponential decay
        if status == 'retired':
            term_ended = politician.get('term_ended')
            if term_ended:
                try:
                    end_date = datetime.fromisoformat(term_ended)
                    days_since_retirement = (current_date - end_date).days

                    if days_since_retirement < 0:
                        # Future retirement date? Treat as retiring
                        logger.warning(f"{politician_name} has future term_ended date, treating as retiring")
                        return base_weight * self.retiring_boost

                    # Exponential decay: weight = base * exp(-days / half_life)
                    # Clamped to min_weight_fraction to preserve historical value
                    decay_factor = np.exp(-days_since_retirement / self.decay_half_life_days)
                    final_decay = max(self.min_weight_fraction, decay_factor)

                    final_weight = base_weight * final_decay

                    logger.debug(
                        f"{politician_name}: retired {days_since_retirement}d ago, "
                        f"decay={final_decay:.2f}, final_weight={final_weight:.2f}"
                    )

                    return final_weight

                except (ValueError, TypeError) as e:
                    logger.error(f"Invalid term_ended date for {politician_name}: {e}")
                    # If we can't parse the date, apply minimum weight
                    return base_weight * self.min_weight_fraction
            else:
                # Retired but no term_ended date - apply minimum weight
                logger.warning(f"{politician_name} is retired but has no term_ended date")
                return base_weight * self.min_weight_fraction

        # Unknown status - use base weight
        logger.warning(f"{politician_name} has unknown status '{status}'")
        return base_weight

    def get_all_weights(self, current_date: Optional[datetime] = None) -> Dict[str, float]:
        """
        Get current weights for all politicians in the registry.

        Args:
            current_date: Reference date (defaults to today)

        Returns:
            Dictionary mapping politician names to their current weights
        """
        if current_date is None:
            current_date = datetime.now()

        weights = {}
        for politician_name in self.registry.get('politicians', {}).keys():
            weights[politician_name] = self.calculate_time_decay_weight(politician_name, current_date)

        return weights

    def get_politician_info(self, politician_name: str) -> Optional[Dict]:
        """
        Get full information for a politician from the registry.

        Args:
            politician_name: Name of the politician

        Returns:
            Dictionary with politician info or None if not found
        """
        return self.registry.get('politicians', {}).get(politician_name)

    def update_politician_status(
        self,
        politician_name: str,
        status: str,
        term_ended: Optional[str] = None,
        retirement_announced: Optional[str] = None
    ):
        """
        Update a politician's status in the registry.

        Args:
            politician_name: Name of the politician
            status: New status ('active', 'retiring', 'retired')
            term_ended: ISO format date when term ends/ended (optional)
            retirement_announced: ISO format date when retirement was announced (optional)
        """
        if politician_name not in self.registry.get('politicians', {}):
            logger.error(f"Cannot update status for unknown politician: {politician_name}")
            return

        politician = self.registry['politicians'][politician_name]
        old_status = politician.get('current_status', 'unknown')

        politician['current_status'] = status
        if term_ended:
            politician['term_ended'] = term_ended
        if retirement_announced:
            politician['retirement_announced'] = retirement_announced

        self._save_registry()
        logger.info(f"Updated {politician_name}: {old_status} -> {status}")

    def add_politician(
        self,
        full_name: str,
        party: str,
        office: str,
        state: str,
        base_weight: float = 1.0,
        status: str = 'active',
        **kwargs
    ):
        """
        Add a new politician to the registry.

        Args:
            full_name: Politician's full name
            party: Political party ('D', 'R', 'I')
            office: Office held ('House', 'Senate', 'Spouse')
            state: State abbreviation
            base_weight: Base weight for signal calculation
            status: Current status ('active', 'retiring', 'retired')
            **kwargs: Additional fields (district, term_started, etc.)
        """
        if full_name in self.registry.get('politicians', {}):
            logger.warning(f"Politician {full_name} already exists in registry")
            return

        politician_data = {
            'full_name': full_name,
            'party': party,
            'current_status': status,
            'office': office,
            'state': state,
            'base_weight': base_weight,
            'performance_score': 50.0,  # Default neutral score
            'total_trades_tracked': 0,
            **kwargs
        }

        if 'politicians' not in self.registry:
            self.registry['politicians'] = {}

        self.registry['politicians'][full_name] = politician_data
        self._save_registry()
        logger.info(f"Added new politician: {full_name} ({party}-{state})")

    def add_trades(self, trades_df: pd.DataFrame):
        """
        Add new politician trades to the tracking system.

        Args:
            trades_df: DataFrame with columns: trade_date, politician, ticker,
                      transaction_type, amount, conviction_score, party
        """
        if trades_df.empty:
            return

        trades_df = trades_df.copy()
        new_trades = []

        for _, row in trades_df.iterrows():
            # Skip duplicates
            if not self.trades_history.empty:
                existing = self.trades_history[
                    (self.trades_history['ticker'] == row['ticker']) &
                    (self.trades_history['politician'] == row['politician']) &
                    (self.trades_history['trade_date'] == pd.to_datetime(row['trade_date']))
                ]
                if not existing.empty:
                    continue

            # Get politician info
            politician_info = self.get_politician_info(row['politician'])
            status = politician_info.get('current_status', 'active') if politician_info else 'unknown'
            office = politician_info.get('office', 'Unknown') if politician_info else 'Unknown'

            # Calculate weight at time of trade
            trade_date = pd.to_datetime(row['trade_date'])
            weight = self.calculate_time_decay_weight(row['politician'], trade_date)

            new_trade = {
                'trade_date': trade_date,
                'politician': row['politician'],
                'ticker': row['ticker'],
                'transaction_type': row.get('transaction_type', 'Buy'),
                'amount': row.get('amount', 0),
                'conviction_score': row.get('conviction_score', 0),
                'party': row.get('party', ''),
                'office': office,
                'status_at_trade': status,
                'weight_at_trade': weight,
                'last_updated': datetime.now().isoformat()
            }
            new_trades.append(new_trade)

        if new_trades:
            new_df = pd.DataFrame(new_trades)
            if self.trades_history.empty:
                self.trades_history = new_df
            else:
                # Check if new_df is not empty before concatenating to avoid FutureWarning
                if not new_df.empty:
                    self.trades_history = pd.concat([self.trades_history, new_df], ignore_index=True)

            self._save_trades_history()
            logger.info(f"Added {len(new_trades)} new politician trades to tracking system")

    def get_active_politicians(self) -> List[str]:
        """Get list of all active politicians."""
        active = []
        for name, info in self.registry.get('politicians', {}).items():
            if info.get('current_status') == 'active':
                active.append(name)
        return active

    def get_retiring_politicians(self) -> List[str]:
        """Get list of retiring politicians (announced but not yet left)."""
        retiring = []
        for name, info in self.registry.get('politicians', {}).items():
            if info.get('current_status') == 'retiring':
                retiring.append(name)
        return retiring

    def get_retired_politicians(self) -> List[str]:
        """Get list of retired politicians."""
        retired = []
        for name, info in self.registry.get('politicians', {}).items():
            if info.get('current_status') == 'retired':
                retired.append(name)
        return retired

    def analyze_lame_duck_patterns(self, days_before_retirement: int = 180) -> pd.DataFrame:
        """
        Analyze trading patterns of politicians in their final days in office.

        Args:
            days_before_retirement: Look at trades within this many days before retirement

        Returns:
            DataFrame with lame duck trading analysis
        """
        if self.trades_history.empty:
            return pd.DataFrame()

        lame_duck_trades = []

        for name, info in self.registry.get('politicians', {}).items():
            if info.get('current_status') != 'retired':
                continue

            term_ended = info.get('term_ended')
            if not term_ended:
                continue

            try:
                end_date = datetime.fromisoformat(term_ended)
                cutoff_date = end_date - timedelta(days=days_before_retirement)

                # Find trades in lame duck period
                politician_trades = self.trades_history[
                    (self.trades_history['politician'] == name) &
                    (self.trades_history['trade_date'] >= cutoff_date) &
                    (self.trades_history['trade_date'] <= end_date)
                ]

                if not politician_trades.empty:
                    lame_duck_trades.append(politician_trades)

            except (ValueError, TypeError):
                continue

        if lame_duck_trades:
            # Fix for pandas FutureWarning: filter out empty DataFrames before concat
            non_empty_trades = [df for df in lame_duck_trades if not df.empty]
            if non_empty_trades:
                result = pd.concat(non_empty_trades, ignore_index=True)
                logger.info(f"Found {len(result)} lame duck trades from {len(non_empty_trades)} politicians")
                return result

        return pd.DataFrame()

    def get_summary_stats(self) -> Dict:
        """Get summary statistics about tracked politicians."""
        politicians = self.registry.get('politicians', {})

        stats = {
            'total_politicians': len(politicians),
            'active': len(self.get_active_politicians()),
            'retiring': len(self.get_retiring_politicians()),
            'retired': len(self.get_retired_politicians()),
            'total_trades': len(self.trades_history),
            'avg_base_weight': np.mean([p.get('base_weight', 1.0) for p in politicians.values()]) if politicians else 0,
            'top_performers': [],
            'recently_retired': []
        }

        # Top 5 performers by base weight
        sorted_politicians = sorted(
            politicians.items(),
            key=lambda x: x[1].get('base_weight', 0),
            reverse=True
        )
        stats['top_performers'] = [
            {'name': name, 'weight': info.get('base_weight', 0)}
            for name, info in sorted_politicians[:5]
        ]

        # Recently retired (last 90 days)
        cutoff = datetime.now() - timedelta(days=90)
        for name, info in politicians.items():
            if info.get('current_status') == 'retired':
                term_ended = info.get('term_ended')
                if term_ended:
                    try:
                        end_date = datetime.fromisoformat(term_ended)
                        if end_date >= cutoff:
                            stats['recently_retired'].append({
                                'name': name,
                                'term_ended': term_ended,
                                'days_ago': (datetime.now() - end_date).days
                            })
                    except (ValueError, TypeError):
                        pass

        return stats


# Convenience function for easy import
def create_politician_tracker(
    decay_half_life_days: int = 90,
    min_weight_fraction: float = 0.2,
    retiring_boost: float = 1.5
) -> PoliticianTracker:
    """
    Create and return a PoliticianTracker instance with specified parameters.

    Args:
        decay_half_life_days: Half-life for exponential decay (default: 90 days)
        min_weight_fraction: Minimum weight fraction (default: 0.2)
        retiring_boost: Boost for retiring politicians (default: 1.5)

    Returns:
        Initialized PoliticianTracker instance
    """
    return PoliticianTracker(
        decay_half_life_days=decay_half_life_days,
        min_weight_fraction=min_weight_fraction,
        retiring_boost=retiring_boost
    )
