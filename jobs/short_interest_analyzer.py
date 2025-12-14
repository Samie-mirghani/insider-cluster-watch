"""
Short Interest Analyzer Module

Fetches and analyzes short interest data from yfinance to enhance insider trading signals.
Provides squeeze score calculation and conviction adjustments based on short interest levels.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class ShortInterestAnalyzer:
    """
    Analyzes short interest data to enhance insider trading signal conviction.

    Features:
    - Fetches short interest metrics from yfinance (free)
    - Calculates squeeze potential score (0-100)
    - Adjusts signal conviction based on short interest levels
    - Caches data for 7 days to minimize API calls
    """

    def __init__(self, cache_dir: str = "data/short_interest_cache", cache_hours: int = 168):
        """
        Initialize the Short Interest Analyzer.

        Args:
            cache_dir: Directory to store cached short interest data
            cache_hours: Cache validity duration in hours (default: 168 = 7 days)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_hours = cache_hours

        # Short interest level thresholds
        self.HIGH_SHORT_INTEREST = 0.20  # 20%
        self.VERY_HIGH_SHORT_INTEREST = 0.30  # 30%
        self.LOW_SHORT_INTEREST = 0.10  # 10%
        self.HIGH_DAYS_TO_COVER = 7  # days

        logger.info(f"📊 Short Interest Analyzer initialized (cache: {cache_dir})")

    def _get_cache_path(self, ticker: str) -> Path:
        """Get the cache file path for a ticker."""
        return self.cache_dir / f"{ticker}_short_interest.json"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file is still valid."""
        if not cache_path.exists():
            return False

        cache_age_seconds = time.time() - cache_path.stat().st_mtime
        cache_duration_seconds = self.cache_hours * 60 * 60
        return cache_age_seconds < cache_duration_seconds

    def _read_cache(self, ticker: str) -> Optional[Dict]:
        """Read short interest data from cache if valid."""
        cache_path = self._get_cache_path(ticker)
        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                logger.info(f"📦 Using cached short interest data for {ticker}")
                return data
            except Exception as e:
                logger.warning(f"Failed to read cache for {ticker}: {e}")
                return None
        return None

    def _write_cache(self, ticker: str, data: Dict):
        """Write short interest data to cache."""
        cache_path = self._get_cache_path(ticker)
        try:
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"💾 Cached short interest data for {ticker}")
        except Exception as e:
            logger.warning(f"Failed to write cache for {ticker}: {e}")

    def get_short_interest_data(self, ticker: str) -> Dict:
        """
        Fetch short interest data for a ticker from yfinance.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict containing:
                - short_percent_float: Short % of float (0.0 - 1.0)
                - days_to_cover: Short ratio (days to cover)
                - shares_short: Number of shares short
                - short_level: Classification (high/moderate/low/unknown)
                - data_available: Boolean indicating if real data was fetched
        """
        # Check cache first
        cached_data = self._read_cache(ticker)
        if cached_data is not None:
            return cached_data

        # Fetch fresh data
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Extract short interest metrics
            short_percent_float = info.get('shortPercentOfFloat', None)
            shares_short = info.get('sharesShort', None)
            shares_outstanding = info.get('sharesOutstanding', None)
            avg_volume = info.get('averageVolume', None)

            # Calculate days to cover if we have the data
            days_to_cover = None
            if shares_short is not None and avg_volume is not None and avg_volume > 0:
                days_to_cover = shares_short / avg_volume

            # If we don't have short % of float but have shares short and outstanding
            if short_percent_float is None and shares_short is not None and shares_outstanding is not None:
                if shares_outstanding > 0:
                    short_percent_float = shares_short / shares_outstanding

            # Determine short interest level
            short_level = "unknown"
            if short_percent_float is not None:
                if short_percent_float >= self.VERY_HIGH_SHORT_INTEREST:
                    short_level = "very_high"
                elif short_percent_float >= self.HIGH_SHORT_INTEREST:
                    short_level = "high"
                elif short_percent_float >= self.LOW_SHORT_INTEREST:
                    short_level = "moderate"
                else:
                    short_level = "low"

            data = {
                'ticker': ticker,
                'short_percent_float': short_percent_float,
                'days_to_cover': days_to_cover,
                'shares_short': shares_short,
                'short_level': short_level,
                'data_available': short_percent_float is not None,
                'fetched_at': datetime.now().isoformat()
            }

            # Cache the data
            self._write_cache(ticker, data)

            if data['data_available']:
                logger.info(f"✅ Fetched short interest for {ticker}: {short_percent_float:.1%} float, "
                          f"{days_to_cover:.1f} days to cover" if days_to_cover else "N/A days to cover")
            else:
                logger.warning(f"⚠️  No short interest data available for {ticker}")

            return data

        except Exception as e:
            logger.error(f"❌ Failed to fetch short interest for {ticker}: {e}")
            # Return neutral data on failure
            return {
                'ticker': ticker,
                'short_percent_float': None,
                'days_to_cover': None,
                'shares_short': None,
                'short_level': 'unknown',
                'data_available': False,
                'error': str(e)
            }

    def calculate_squeeze_score(
        self,
        short_percent_float: Optional[float],
        days_to_cover: Optional[float],
        insider_value: float,
        market_cap: Optional[float]
    ) -> Tuple[float, bool]:
        """
        Calculate squeeze potential score (0-100) based on multiple factors.

        Scoring methodology:
        - Short % of float: 0-40 points (higher is better)
        - Days to cover: 0-30 points (higher is better)
        - Insider purchase impact: 0-30 points (larger relative to short position is better)

        Args:
            short_percent_float: Short % of float (0.0 - 1.0)
            days_to_cover: Days to cover short position
            insider_value: Total value of insider purchases
            market_cap: Market capitalization

        Returns:
            Tuple of (squeeze_score, squeeze_potential_flag)
            - squeeze_score: 0-100 score
            - squeeze_potential_flag: True if score > 70
        """
        if short_percent_float is None:
            return 0.0, False

        score = 0.0

        # Component 1: Short % of float (0-40 points)
        # Linear scaling: 0% = 0 points, 50%+ = 40 points
        short_pct_points = min(40, (short_percent_float / 0.50) * 40)
        score += short_pct_points

        # Component 2: Days to cover (0-30 points)
        # Linear scaling: 0 days = 0 points, 10+ days = 30 points
        days_to_cover_points = 0.0
        if days_to_cover is not None:
            days_to_cover_points = min(30, (days_to_cover / 10.0) * 30)
            score += days_to_cover_points

        # Component 3: Insider purchase impact vs short position (0-30 points)
        # Compare insider buying to the short position size
        impact_points = 0.0
        if market_cap is not None and market_cap > 0:
            # Estimate short position value
            short_position_value = market_cap * short_percent_float

            if short_position_value > 0:
                # Ratio of insider buying to short position
                impact_ratio = insider_value / short_position_value
                # Scale: 0% = 0 points, 5%+ of short position = 30 points
                impact_points = min(30, (impact_ratio / 0.05) * 30)
                score += impact_points

        # Flag high squeeze potential
        squeeze_potential = score >= 70

        logger.debug(f"Squeeze score calculation: {score:.1f} (short_pct: {short_pct_points:.1f}, "
                    f"days_to_cover: {days_to_cover_points:.1f}, "
                    f"impact: {impact_points:.1f})")

        return round(score, 1), squeeze_potential

    def adjust_conviction(
        self,
        base_conviction: float,
        short_percent_float: Optional[float],
        days_to_cover: Optional[float]
    ) -> Tuple[float, str]:
        """
        Adjust signal conviction based on short interest levels.

        Rules:
        - High short interest (20%+) + insider buying = UPGRADE by 1 level
        - Very high short interest (30%+) + high days to cover (7+) = Flag as squeeze potential
        - Low short interest (<10%) = No change

        Args:
            base_conviction: Original conviction score
            short_percent_float: Short % of float (0.0 - 1.0)
            days_to_cover: Days to cover short position

        Returns:
            Tuple of (adjusted_conviction, adjustment_reason)
        """
        if short_percent_float is None:
            return base_conviction, "No short interest data available"

        adjusted_conviction = base_conviction
        reason = "No adjustment"

        # High short interest boost
        if short_percent_float >= self.HIGH_SHORT_INTEREST:
            # Upgrade by 1 level (approximately +1.0 to conviction)
            boost = 1.0
            adjusted_conviction += boost
            reason = f"High short interest ({short_percent_float:.1%}) - conviction boosted"

            # Additional boost for very high short interest + high days to cover
            if (short_percent_float >= self.VERY_HIGH_SHORT_INTEREST and
                days_to_cover is not None and days_to_cover >= self.HIGH_DAYS_TO_COVER):
                extra_boost = 0.5
                adjusted_conviction += extra_boost
                reason = (f"Very high short interest ({short_percent_float:.1%}) + "
                         f"high days to cover ({days_to_cover:.1f}) - potential squeeze setup")

        elif short_percent_float < self.LOW_SHORT_INTEREST:
            reason = f"Low short interest ({short_percent_float:.1%}) - no change"

        else:
            reason = f"Moderate short interest ({short_percent_float:.1%}) - no change"

        logger.info(f"📈 Conviction adjustment: {base_conviction:.2f} → {adjusted_conviction:.2f} ({reason})")

        return adjusted_conviction, reason

    def analyze_signal(self, row: pd.Series) -> Dict:
        """
        Analyze a signal row and add short interest metrics.

        Args:
            row: Signal data (pandas Series) with at minimum: ticker, total_value, marketCap

        Returns:
            Dict with short interest analysis results to merge into signal
        """
        ticker = row['ticker']

        # Fetch short interest data
        si_data = self.get_short_interest_data(ticker)

        # Calculate squeeze score
        squeeze_score, squeeze_potential = self.calculate_squeeze_score(
            short_percent_float=si_data['short_percent_float'],
            days_to_cover=si_data['days_to_cover'],
            insider_value=row.get('total_value', 0),
            market_cap=row.get('marketCap', None)
        )

        # Adjust conviction if available
        adjusted_conviction = row.get('avg_conviction', 0)
        conviction_reason = ""

        if 'avg_conviction' in row:
            adjusted_conviction, conviction_reason = self.adjust_conviction(
                base_conviction=row['avg_conviction'],
                short_percent_float=si_data['short_percent_float'],
                days_to_cover=si_data['days_to_cover']
            )

        # Prepare result
        result = {
            'short_percent_float': si_data['short_percent_float'],
            'short_percent_float_display': f"{si_data['short_percent_float']:.1%}" if si_data['short_percent_float'] is not None else "N/A",
            'days_to_cover': si_data['days_to_cover'],
            'days_to_cover_display': f"{si_data['days_to_cover']:.1f}" if si_data['days_to_cover'] is not None else "N/A",
            'shares_short': si_data['shares_short'],
            'short_level': si_data['short_level'],
            'squeeze_score': squeeze_score,
            'squeeze_potential': squeeze_potential,
            'short_interest_available': si_data['data_available'],
            'conviction_adjusted': adjusted_conviction,
            'conviction_adjustment_reason': conviction_reason
        }

        return result

    def analyze_signals(self, signals_df: pd.DataFrame) -> pd.DataFrame:
        """
        Analyze short interest for all signals in a DataFrame.

        Args:
            signals_df: DataFrame of signals with ticker, total_value, marketCap columns

        Returns:
            DataFrame with short interest columns added
        """
        if signals_df.empty:
            logger.info("No signals to analyze for short interest")
            return signals_df

        logger.info(f"🔍 Analyzing short interest for {len(signals_df)} signals...")

        # Analyze each signal
        results = []
        for idx, row in signals_df.iterrows():
            try:
                analysis = self.analyze_signal(row)
                results.append(analysis)
            except Exception as e:
                logger.error(f"Failed to analyze {row['ticker']}: {e}")
                # Add neutral data
                results.append({
                    'short_percent_float': None,
                    'short_percent_float_display': "N/A",
                    'days_to_cover': None,
                    'days_to_cover_display': "N/A",
                    'shares_short': None,
                    'short_level': 'unknown',
                    'squeeze_score': 0.0,
                    'squeeze_potential': False,
                    'short_interest_available': False,
                    'conviction_adjusted': row.get('avg_conviction', 0),
                    'conviction_adjustment_reason': f"Error: {str(e)}"
                })

        # Merge results into DataFrame
        results_df = pd.DataFrame(results)
        # Fix for pandas FutureWarning: check for empty DataFrames before concat
        if not signals_df.empty and not results_df.empty:
            enhanced_df = pd.concat([signals_df.reset_index(drop=True), results_df], axis=1)
        elif not signals_df.empty:
            enhanced_df = signals_df.reset_index(drop=True)
        else:
            enhanced_df = results_df

        # Update avg_conviction with adjusted values
        if 'conviction_adjusted' in enhanced_df.columns:
            enhanced_df['avg_conviction'] = enhanced_df['conviction_adjusted']

        # Log summary
        high_squeeze_count = enhanced_df['squeeze_potential'].sum()
        if high_squeeze_count > 0:
            logger.info(f"🚀 Found {high_squeeze_count} signal(s) with high squeeze potential!")

        available_count = enhanced_df['short_interest_available'].sum()
        logger.info(f"✅ Short interest data available for {available_count}/{len(enhanced_df)} signals")

        return enhanced_df


def test_short_interest_analyzer():
    """Test function to validate the analyzer."""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Test tickers (known to have various short interest levels)
    test_tickers = ['GME', 'AAPL', 'TSLA', 'AMC', 'SPY']

    analyzer = ShortInterestAnalyzer()

    print("\n" + "="*80)
    print("SHORT INTEREST ANALYZER TEST")
    print("="*80 + "\n")

    for ticker in test_tickers:
        print(f"\n--- Testing {ticker} ---")

        # Fetch data
        data = analyzer.get_short_interest_data(ticker)

        # Display results
        print(f"Short % of Float: {data['short_percent_float_display'] if 'short_percent_float_display' in data else 'N/A'}")
        print(f"Days to Cover: {data.get('days_to_cover', 'N/A')}")
        print(f"Shares Short: {data.get('shares_short', 'N/A'):,}" if data.get('shares_short') else "Shares Short: N/A")
        print(f"Short Level: {data['short_level']}")
        print(f"Data Available: {data['data_available']}")

        # Test squeeze score calculation
        if data['data_available']:
            score, potential = analyzer.calculate_squeeze_score(
                short_percent_float=data['short_percent_float'],
                days_to_cover=data['days_to_cover'],
                insider_value=1000000,  # $1M insider buy
                market_cap=1000000000   # $1B market cap
            )
            print(f"Squeeze Score: {score}/100")
            print(f"Squeeze Potential: {'YES' if potential else 'NO'}")

        time.sleep(1)  # Be nice to the API

    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80 + "\n")


if __name__ == "__main__":
    test_short_interest_analyzer()
