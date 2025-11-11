"""
paper_trading_multi_signal.py
Enhanced paper trading that considers politician and institutional signals
"""

import pandas as pd
import json
import os
from datetime import datetime
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

# Data directory
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')


class MultiSignalPaperTrader:
    """
    Paper trading system with multi-signal support
    Adjusts position sizing based on signal strength
    """

    # Position sizing by tier
    POSITION_SIZES = {
        'tier1': 1.0,   # Full position (3+ signals)
        'tier2': 0.75,  # 75% position (2 signals)
        'tier3': 0.50,  # 50% position (1 strong signal)
        'tier4': 0.25   # 25% position (watch list)
    }

    # Risk management
    STOP_LOSS_PCT = {
        'tier1': 0.12,  # -12% stop for highest conviction
        'tier2': 0.10,  # -10% stop
        'tier3': 0.08,  # -8% stop
        'tier4': 0.06   # -6% stop (tighter for lower conviction)
    }

    def __init__(self, portfolio_size: float = 100000):
        """
        Initialize paper trader

        Args:
            portfolio_size: Starting portfolio size
        """
        self.portfolio_size = portfolio_size
        self.positions = []
        self.closed_trades = []

    def evaluate_entry(self, signal: Dict) -> Dict:
        """
        Evaluate whether to enter a position

        Args:
            signal: Signal dictionary from MultiSignalDetector

        Returns:
            Entry decision with position sizing
        """
        ticker = signal['ticker']
        tier = self._determine_tier(signal['signal_count'])

        # Check if already have position
        if self._has_position(ticker):
            logger.info(f"Already have position in {ticker}, skipping")
            return {'action': 'skip', 'reason': 'existing_position'}

        # Calculate position size
        base_size = self.portfolio_size * 0.10  # 10% per position
        tier_multiplier = self.POSITION_SIZES[tier]
        position_size = base_size * tier_multiplier

        # Calculate stop loss
        stop_loss_pct = self.STOP_LOSS_PCT[tier]

        entry = {
            'action': 'enter',
            'ticker': ticker,
            'company': signal['company'],
            'tier': tier,
            'signal_count': signal['signal_count'],
            'combined_score': signal['combined_score'],

            # Position details
            'position_size': position_size,
            'position_pct': tier_multiplier * 0.10,

            # Risk management
            'stop_loss_pct': stop_loss_pct,
            'trailing_stop': True,
            'max_hold_days': 60,

            # Signal details
            'has_insider': True,
            'has_politician': signal['has_politician'],
            'has_institutional': signal['has_institutional'],
            'has_high_short': signal['has_high_short'],

            # Entry metadata
            'entry_date': datetime.now(),
            'entry_reason': self._generate_entry_reason(signal)
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"PAPER TRADE ENTRY: {ticker}")
        logger.info(f"Tier: {tier.upper()}")
        logger.info(f"Position Size: ${position_size:,.0f} ({tier_multiplier*10:.0f}% of base)")
        logger.info(f"Stop Loss: {stop_loss_pct*100:.0f}%")
        logger.info(f"Signals: {signal['signal_count']}")
        logger.info(f"{'='*60}\n")

        return entry

    def _determine_tier(self, signal_count: int) -> str:
        """Determine tier based on signal count"""
        if signal_count >= 3:
            return 'tier1'
        elif signal_count == 2:
            return 'tier2'
        elif signal_count == 1:
            return 'tier3'
        else:
            return 'tier4'

    def _has_position(self, ticker: str) -> bool:
        """Check if already have position"""
        return any(p['ticker'] == ticker for p in self.positions)

    def _generate_entry_reason(self, signal: Dict) -> str:
        """Generate human-readable entry reason"""
        reasons = []

        if signal['has_insider']:
            reasons.append(
                f"{signal['insider_count']} insiders bought "
                f"${signal['insider_value']:,.0f}"
            )

        if signal['has_politician']:
            pol_data = signal['politician_data']
            pols = pol_data['num_politicians']
            bipartisan = " (BIPARTISAN)" if pol_data.get('is_bipartisan') else ""
            reasons.append(
                f"{pols} politicians{bipartisan} bought "
                f"${pol_data['weighted_total']:,.0f}"
            )

        if signal['has_institutional']:
            inst_count = signal['institutional_count']
            reasons.append(
                f"{inst_count} priority institutions hold stock"
            )

        if signal['has_high_short']:
            reasons.append(
                f"High short interest (squeeze potential)"
            )

        return " | ".join(reasons)

    def process_signals(self, signals_by_tier: Dict) -> List[Dict]:
        """
        Process all signals and generate entry decisions

        Args:
            signals_by_tier: Results from MultiSignalDetector.run_full_scan()

        Returns:
            List of entry decisions
        """
        entries = []

        # Process Tier 1 first (highest conviction)
        for signal in signals_by_tier['tier1']:
            entry = self.evaluate_entry(signal)
            if entry['action'] == 'enter':
                entries.append(entry)
                self.positions.append(entry)

        # Then Tier 2
        for signal in signals_by_tier['tier2']:
            entry = self.evaluate_entry(signal)
            if entry['action'] == 'enter':
                entries.append(entry)
                self.positions.append(entry)

        # Tier 3 (selective)
        tier3_limit = 3  # Max 3 Tier 3 positions
        tier3_count = 0

        for signal in signals_by_tier['tier3']:
            if tier3_count >= tier3_limit:
                break

            # Only take Tier 3 if combined score is high enough
            if signal['combined_score'] >= 7.0:
                entry = self.evaluate_entry(signal)
                if entry['action'] == 'enter':
                    entries.append(entry)
                    self.positions.append(entry)
                    tier3_count += 1

        return entries

    def save_positions(self, filename: str = None):
        """Save positions to file"""
        if filename is None:
            filename = os.path.join(DATA_DIR, 'paper_trades.json')

        # Convert datetime objects to strings
        positions_serializable = []
        for pos in self.positions:
            pos_copy = pos.copy()
            pos_copy['entry_date'] = pos['entry_date'].isoformat()
            positions_serializable.append(pos_copy)

        with open(filename, 'w') as f:
            json.dump(positions_serializable, f, indent=2)

        logger.info(f"Saved {len(self.positions)} positions to {filename}")
