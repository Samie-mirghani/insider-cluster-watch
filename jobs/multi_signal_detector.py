"""
multi_signal_detector.py
Combines insider trades, politician trades, 13F holdings, and short interest
Generates tiered signals with different conviction levels
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging

# Setup logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import your existing modules
from capitol_trades_scraper import CapitolTradesScraper
from sec_13f_parser import SEC13FParser

# Import politician tracker for time-decay weighting
try:
    from politician_tracker import PoliticianTracker
    POLITICIAN_TRACKER_AVAILABLE = True
except ImportError:
    POLITICIAN_TRACKER_AVAILABLE = False
    logger.warning("PoliticianTracker not available. Using static weights.")


class MultiSignalDetector:
    """
    Multi-signal detection system
    Combines:
    1. Insider cluster trades (your existing pipeline)
    2. Politician trades (Capitol Trades scraper)
    3. 13F institutional holdings (free SEC data)
    4. Short interest data (FINRA)
    """

    # Signal tier thresholds
    TIER_1_MIN_SIGNALS = 3  # Need 3+ signals for Tier 1
    TIER_2_MIN_SIGNALS = 2  # Need 2+ signals for Tier 2

    # Conviction scoring weights
    WEIGHTS = {
        'insider': 0.35,
        'politician': 0.30,
        'institutional': 0.20,
        'short_interest': 0.15
    }

    def __init__(self, sec_user_agent: str, politician_tracker: Optional['PoliticianTracker'] = None):
        """
        Initialize detector

        Args:
            sec_user_agent: User-Agent for SEC requests
            politician_tracker: Optional PoliticianTracker instance for time-decay weighting
        """
        self.politician_tracker = politician_tracker
        self.politician_scraper = CapitolTradesScraper(politician_tracker=politician_tracker)
        self.sec_parser = SEC13FParser(sec_user_agent)

        # Priority funds for institutional tracking
        self.priority_funds = self.sec_parser.PRIORITY_FUNDS

        if self.politician_tracker:
            logger.info("MultiSignalDetector initialized with PoliticianTracker (time-decay enabled)")
        else:
            logger.info("MultiSignalDetector initialized with static politician weights")

    def run_full_scan(self,
                     insider_clusters: pd.DataFrame,
                     check_13f: bool = False,
                     quarter_year: Optional[int] = None,
                     quarter: Optional[int] = None) -> Dict:
        """
        Run complete multi-signal scan

        Args:
            insider_clusters: DataFrame from your existing insider detection
            check_13f: Whether to include 13F validation
            quarter_year: Year for 13F check
            quarter: Quarter for 13F check

        Returns:
            Dictionary with tiered signals
        """
        logger.info("\n" + "="*60)
        logger.info("MULTI-SIGNAL DETECTION SCAN")
        logger.info("="*60 + "\n")

        # Step 1: Get politician clusters
        logger.info("Step 1: Scraping politician trades...")
        politician_trades = self.politician_scraper.scrape_recent_trades(
            days_back=30,
            max_pages=5
        )

        politician_clusters = self.politician_scraper.detect_politician_clusters(
            politician_trades
        )

        # Step 2: For each insider cluster, check other signals
        results = {
            'tier1': [],  # 3+ signals (HIGHEST)
            'tier2': [],  # 2 signals (HIGH)
            'tier3': [],  # 1 strong signal (MODERATE)
            'tier4': []   # Watch list
        }

        # Tracking for diagnostics
        signal_distribution = {
            'total_analyzed': 0,
            '3_plus_signals': 0,
            '2_signals': 0,
            '1_signal': 0,
            'politician_overlaps': 0,
            'institutional_overlaps': 0,
            'short_interest_flags': 0
        }

        for _, stock in insider_clusters.iterrows():
            signal_distribution['total_analyzed'] += 1
            ticker = stock['ticker']

            logger.info(f"\nAnalyzing {ticker}...")

            # Check politician activity
            has_politician = False
            politician_score = 0
            politician_data = None

            if not politician_clusters.empty and 'ticker' in politician_clusters.columns:
                has_politician = ticker in politician_clusters['ticker'].values

                if has_politician:
                    politician_data = politician_clusters[
                        politician_clusters['ticker'] == ticker
                    ].iloc[0]
                    politician_score = politician_data['conviction_score']
                logger.info(f"  ✓ Politician signal: {politician_data['num_politicians']} politicians")

            # Check institutional (if quarterly check enabled)
            has_institutional = False
            institutional_data = None
            institutional_score = 0

            if check_13f and quarter_year and quarter:
                institutional_data = self.sec_parser.check_institutional_interest(
                    ticker, quarter_year, quarter
                )

                if not institutional_data.empty:
                    has_institutional = len(institutional_data) >= 2
                    institutional_score = len(institutional_data) * 1.5
                    logger.info(f"  ✓ Institutional signal: {len(institutional_data)} priority funds")

            # Check short interest
            has_high_short = False
            short_data = None
            short_score = 0

            # TODO: Implement short interest check
            # For now, placeholder
            # short_data = self.get_short_interest(ticker)
            # has_high_short = short_data.get('short_percent_float', 0) > 15

            # Calculate overall conviction score
            insider_score = self._calculate_insider_score(stock)

            combined_score = (
                insider_score * self.WEIGHTS['insider'] +
                politician_score * self.WEIGHTS['politician'] +
                institutional_score * self.WEIGHTS['institutional'] +
                short_score * self.WEIGHTS['short_interest']
            )

            # Count signals
            signal_count = sum([
                True,  # Always have insider signal
                has_politician,
                has_institutional,
                has_high_short
            ])

            # Track signal distribution
            if has_politician:
                signal_distribution['politician_overlaps'] += 1
            if has_institutional:
                signal_distribution['institutional_overlaps'] += 1
            if has_high_short:
                signal_distribution['short_interest_flags'] += 1

            if signal_count >= 3:
                signal_distribution['3_plus_signals'] += 1
            elif signal_count == 2:
                signal_distribution['2_signals'] += 1
            elif signal_count == 1:
                signal_distribution['1_signal'] += 1

            # Create signal package
            signal = {
                'ticker': ticker,
                'company': stock.get('company', ticker),
                'signal_count': signal_count,
                'combined_score': combined_score,

                # Insider data
                'insider_count': stock.get('cluster_count', 0),
                'insider_value': stock.get('total_value', 0),
                'insider_data': stock,

                # Politician data
                'has_politician': has_politician,
                'politician_count': politician_data['num_politicians'] if has_politician else 0,
                'politician_amount': politician_data['weighted_total'] if has_politician else 0,
                'politician_data': politician_data if has_politician else None,

                # Institutional data
                'has_institutional': has_institutional,
                'institutional_count': len(institutional_data) if has_institutional else 0,
                'institutional_value': institutional_data['value'].sum() if has_institutional else 0,
                'institutional_data': institutional_data if has_institutional else None,

                # Short interest
                'has_high_short': has_high_short,
                'short_data': short_data,

                # Metadata
                'detected_at': datetime.now()
            }

            # Classify into tiers
            if signal_count >= 3:
                results['tier1'].append(signal)
                logger.info(f"  🔥 TIER 1: {signal_count} signals!")

            elif signal_count == 2:
                results['tier2'].append(signal)
                # More descriptive logging for different 2-signal combinations
                if has_politician and has_institutional:
                    logger.info(f"  ⚡ TIER 2: Insider + Politician + Institutional")
                elif has_politician:
                    logger.info(f"  ⚡ TIER 2: Insider + Politician")
                elif has_institutional:
                    logger.info(f"  ⚡ TIER 2: Insider + Institutional (13F)")
                else:
                    logger.info(f"  ⚡ TIER 2: Two signals")

            elif signal_count == 1:
                # Single signal (insider only)
                # Check if it's a strong cluster worthy of Tier 3, otherwise Tier 4
                cluster_count = stock.get('cluster_count', 0)

                if cluster_count >= 5:
                    # Strong cluster: 5+ insiders buying
                    results['tier3'].append(signal)
                    logger.info(f"  ✓ TIER 3: Strong single signal ({cluster_count} insiders)")
                else:
                    # Weaker cluster: watch list
                    results['tier4'].append(signal)
                    logger.info(f"  → TIER 4: Watch list ({cluster_count} insiders)")

        # Log summary with diagnostics
        logger.info("\n" + "="*60)
        logger.info("SCAN COMPLETE")
        logger.info("="*60)
        logger.info(f"📊 Signal Distribution:")
        logger.info(f"   Total stocks analyzed: {signal_distribution['total_analyzed']}")
        logger.info(f"   Politician overlaps found: {signal_distribution['politician_overlaps']}")
        logger.info(f"   Institutional overlaps found: {signal_distribution['institutional_overlaps']}")
        logger.info(f"   Short interest flags: {signal_distribution['short_interest_flags']}")
        logger.info("")
        logger.info(f"🎯 Tier Classification:")
        logger.info(f"   Tier 1 (3+ signals): {len(results['tier1'])}")
        logger.info(f"   Tier 2 (2 signals):  {len(results['tier2'])}")
        logger.info(f"   Tier 3 (1 signal):   {len(results['tier3'])}")
        logger.info(f"   Tier 4 (watch list): {len(results['tier4'])}")
        logger.info("")

        # Validation check
        total_classified = sum([len(results['tier1']), len(results['tier2']),
                               len(results['tier3']), len(results['tier4'])])
        if total_classified != signal_distribution['total_analyzed']:
            logger.warning(f"⚠️  Classification mismatch! Analyzed: {signal_distribution['total_analyzed']}, "
                         f"Classified: {total_classified}")

        # Show top signals from each tier
        if results['tier1']:
            logger.info(f"🔥 Tier 1 stocks: {', '.join([s['ticker'] for s in results['tier1'][:5]])}")
        if results['tier2']:
            logger.info(f"⚡ Tier 2 stocks: {', '.join([s['ticker'] for s in results['tier2'][:5]])}")
        if results['tier3']:
            logger.info(f"✓  Tier 3 stocks: {', '.join([s['ticker'] for s in results['tier3'][:5]])}")
        if results['tier4']:
            logger.info(f"→  Tier 4 stocks: {', '.join([s['ticker'] for s in results['tier4'][:5]])}")

        logger.info("="*60 + "\n")

        return results

    def _calculate_insider_score(self, stock: pd.Series) -> float:
        """Calculate normalized insider conviction score"""
        cluster_count = stock.get('cluster_count', 0)
        total_value = stock.get('total_value', 0)

        # Normalize to 0-10 scale
        count_score = min(cluster_count / 5 * 5, 5)  # Max 5 points
        value_score = min(total_value / 5000000 * 5, 5)  # $5M = 5 points

        return count_score + value_score


def combine_insider_and_politician_signals(
    insider_clusters: pd.DataFrame,
    politician_clusters: pd.DataFrame
) -> pd.DataFrame:
    """
    Simple function to find overlapping signals

    Args:
        insider_clusters: Insider detection results
        politician_clusters: Politician cluster results

    Returns:
        Combined signals DataFrame
    """
    if insider_clusters.empty or politician_clusters.empty:
        return pd.DataFrame()

    # Merge on ticker
    combined = insider_clusters.merge(
        politician_clusters[[
            'ticker', 'num_politicians', 'weighted_total',
            'politician_list', 'is_bipartisan', 'conviction_score'
        ]],
        on='ticker',
        how='inner',
        suffixes=('_insider', '_politician')
    )

    if combined.empty:
        return combined

    # Calculate combined score
    combined['combined_conviction'] = (
        combined.get('insider_score', 0) * 0.6 +
        combined['conviction_score'] * 0.4
    )

    # Add urgency flag
    combined['urgent'] = (
        (combined['num_politicians'] >= 3) |
        combined['is_bipartisan'] |
        (combined.get('cluster_count', 0) >= 5)
    )

    return combined.sort_values('combined_conviction', ascending=False)
