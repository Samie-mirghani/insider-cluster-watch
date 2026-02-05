"""
capitol_trades_scraper.py
API-based politician trading data fetcher using PoliticianTradeTracker API
Replaces broken Selenium scraper with reliable API integration
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from typing import List, Dict, Optional
import json
import os

# Setup logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import politician tracker for time-decay weighting
try:
    from politician_tracker import PoliticianTracker
    POLITICIAN_TRACKER_AVAILABLE = True
except ImportError:
    POLITICIAN_TRACKER_AVAILABLE = False
    logger.warning("PoliticianTracker not available. Using static weights.")


class CapitolTradesScraper:
    """
    Fetch politician trading data via PoliticianTradeTracker API
    FREE tier: 100 calls/month (~3 per day)
    """

    API_BASE_URL = "https://politician-trade-tracker1.p.rapidapi.com"

    # Track politician performance (update based on your research)
    POLITICIAN_WEIGHTS = {
        'Nancy Pelosi': 2.0,          # Legendary performance
        'Paul Pelosi': 2.0,           # Nancy's husband
        'Josh Gottheimer': 1.8,
        'Mark Green': 1.6,
        'Dan Crenshaw': 1.5,
        'Marjorie Taylor Greene': 1.4,
        'Tommy Tuberville': 1.4,
        'Austin Scott': 1.3,
        'Michael McCaul': 1.3,
        'Brian Higgins': 1.3,
        'Ro Khanna': 1.2,
        'Default': 1.0
    }

    def __init__(self, max_retries: int = 3, delay: float = 2.0, use_selenium: bool = False,
                 politician_tracker: Optional['PoliticianTracker'] = None):
        """
        Initialize API-based scraper

        Args:
            max_retries: Maximum retry attempts for API calls
            delay: Delay between requests (seconds) - not critical for API
            use_selenium: DEPRECATED - kept for compatibility, ignored
            politician_tracker: Optional PoliticianTracker instance for time-decay weighting
        """
        self.max_retries = max_retries
        self.delay = delay
        self.politician_tracker = politician_tracker

        # API configuration
        self.api_key = os.getenv('RAPIDAPI_KEY')
        if not self.api_key:
            logger.warning("⚠️  RAPIDAPI_KEY environment variable not set")
            logger.warning("    Politician trade fetching will fail")
            logger.warning("    Please set RAPIDAPI_KEY in GitHub Secrets or environment")

        self.headers = {
            'x-rapidapi-host': 'politician-trade-tracker1.p.rapidapi.com',
            'x-rapidapi-key': self.api_key
        }

        # Rate limiting
        self.rate_limit_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'data', 'api_rate_limit.json'
        )
        self.cache_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'data', 'politician_trades_cache.json'
        )

        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.rate_limit_file), exist_ok=True)

        # Log configuration
        if self.politician_tracker:
            logger.info("✓ Using PoliticianTracker for dynamic time-decay weights")
        else:
            logger.info("✓ Using static POLITICIAN_WEIGHTS (no time-decay)")

        logger.info("✓ API-based politician trade fetcher initialized")

    def _check_rate_limit(self) -> bool:
        """
        Ensure we don't exceed 100 calls/month (free tier)

        Returns:
            True if we can make a call, False if limit reached
        """
        try:
            # Load rate limit data
            if os.path.exists(self.rate_limit_file):
                with open(self.rate_limit_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {'month': datetime.now().month, 'year': datetime.now().year, 'calls': 0}

            current_month = datetime.now().month
            current_year = datetime.now().year

            # Reset counter if new month
            if data['month'] != current_month or data['year'] != current_year:
                data = {'month': current_month, 'year': current_year, 'calls': 0}
                logger.info(f"📅 New month detected - rate limit counter reset")
                # Save the reset data immediately
                with open(self.rate_limit_file, 'w') as f:
                    json.dump(data, f, indent=2)

            # Check limit (100 calls/month)
            if data['calls'] >= 100:
                logger.warning(f"⚠️ API rate limit reached ({data['calls']}/100 calls this month)")
                return False

            # We're good to make a call
            logger.debug(f"API calls this month: {data['calls']}/100")
            return True

        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # If we can't check, be conservative and allow the call
            return True

    def _increment_rate_limit(self):
        """Increment the API call counter"""
        try:
            # Load current data
            if os.path.exists(self.rate_limit_file):
                with open(self.rate_limit_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {'month': datetime.now().month, 'year': datetime.now().year, 'calls': 0}

            # Increment
            data['calls'] += 1

            # Save
            with open(self.rate_limit_file, 'w') as f:
                json.dump(data, f, indent=2)

            logger.info(f"📊 API usage: {data['calls']}/100 calls this month")

        except Exception as e:
            logger.error(f"Error incrementing rate limit: {e}")

    def _load_cached_trades(self) -> pd.DataFrame:
        """
        Load cached politician trades

        Returns:
            DataFrame with cached trades, or empty DataFrame
        """
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)

                # Check cache age
                cache_time = datetime.fromisoformat(cache_data['cached_at'])
                age_hours = (datetime.now() - cache_time).total_seconds() / 3600

                if age_hours < 24:
                    logger.info(f"✓ Using cached data (age: {age_hours:.1f} hours)")
                    df = pd.DataFrame(cache_data['trades'])

                    # Convert date strings back to datetime
                    if not df.empty and 'trade_date' in df.columns:
                        df['trade_date'] = pd.to_datetime(df['trade_date'])

                    return df
                else:
                    logger.info(f"Cache expired (age: {age_hours:.1f} hours)")

            return pd.DataFrame()

        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            return pd.DataFrame()

    def _save_to_cache(self, df: pd.DataFrame):
        """Save trades to cache"""
        try:
            # Convert DataFrame to dict for JSON serialization
            trades_dict = df.to_dict('records')

            # Convert datetime objects to strings
            for trade in trades_dict:
                if 'trade_date' in trade and isinstance(trade['trade_date'], (pd.Timestamp, datetime)):
                    trade['trade_date'] = trade['trade_date'].strftime('%Y-%m-%d')

            cache_data = {
                'cached_at': datetime.now().isoformat(),
                'trades': trades_dict
            }

            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

            logger.info(f"✓ Cached {len(df)} trades for future use")

        except Exception as e:
            logger.error(f"Error saving cache: {e}")

    def _fetch_trades_from_api(self, days_back: int = 30) -> List[Dict]:
        """
        Fetch trades from PoliticianTradeTracker API

        Args:
            days_back: Only return trades from last N days

        Returns:
            List of trade dictionaries
        """
        try:
            # Check if API key is set
            if not self.api_key:
                logger.error("Cannot fetch trades: RAPIDAPI_KEY not set")
                return []

            logger.info(f"📡 Fetching politician trades via API (last {days_back} days)")

            # Make API request
            url = f"{self.API_BASE_URL}/get_latest_trades"

            for attempt in range(self.max_retries):
                try:
                    response = requests.get(
                        url,
                        headers=self.headers,
                        timeout=30
                    )

                    response.raise_for_status()
                    trades_data = response.json()

                    logger.info(f"✓ API returned {len(trades_data)} total trades")

                    # Increment rate limit counter
                    self._increment_rate_limit()

                    return trades_data

                except requests.exceptions.RequestException as e:
                    logger.warning(f"API request failed (attempt {attempt + 1}/{self.max_retries}): {e}")

                    if attempt < self.max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        logger.info(f"Waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All API retry attempts failed")
                        raise

            return []

        except Exception as e:
            logger.error(f"Error fetching from API: {e}")
            return []

    def _parse_and_filter_trades(self, trades_data: List[Dict], days_back: int = 30) -> List[Dict]:
        """
        Parse API response and filter to recent buy trades

        Args:
            trades_data: Raw API response
            days_back: Only keep trades from last N days

        Returns:
            List of clean trade dictionaries
        """
        cutoff_date = datetime.now() - timedelta(days=days_back)
        recent_trades = []

        for trade in trades_data:
            try:
                # Skip if not a buy
                trade_type = trade.get('trade_type', '').lower()
                if trade_type != 'buy' and trade_type != 'purchase':
                    continue

                # Skip if no valid ticker
                ticker_raw = trade.get('ticker', '')
                if ticker_raw == 'N/A' or not ticker_raw or ticker_raw == '':
                    continue

                # Clean ticker (remove :US suffix and other exchange indicators)
                ticker = ticker_raw.split(':')[0].strip()

                # Skip if ticker is invalid
                if len(ticker) == 0 or len(ticker) > 5:
                    continue

                # Parse date
                date_str = trade.get('trade_date', '')
                if not date_str:
                    continue

                try:
                    # API returns format: "November 18, 2025"
                    trade_date = datetime.strptime(date_str, '%B %d, %Y')
                except ValueError:
                    # Try alternative formats
                    try:
                        trade_date = datetime.strptime(date_str, '%b %d, %Y')
                    except ValueError:
                        logger.warning(f"Could not parse date: {date_str}")
                        continue

                # Check if recent
                if trade_date < cutoff_date:
                    continue

                # Build clean trade object
                clean_trade = {
                    'ticker': ticker,
                    'politician': trade.get('name', ''),
                    'party': trade.get('party', ''),
                    'trade_date': trade_date,
                    'amount_range': trade.get('trade_amount', ''),
                    'asset_name': trade.get('company', ''),
                    'chamber': trade.get('chamber', ''),
                    'transaction_type': 'buy',  # We filtered for buys only
                    'disclosure_date': None,  # Not provided by API
                }

                # Add state if available
                if 'state_abbreviation' in trade:
                    clean_trade['state'] = trade['state_abbreviation']

                recent_trades.append(clean_trade)

            except Exception as e:
                logger.debug(f"Error parsing trade: {e}")
                continue

        logger.info(f"✓ Filtered to {len(recent_trades)} recent buy trades")
        return recent_trades

    def scrape_recent_trades(self, days_back: int = 30, max_pages: int = 5, debug: bool = False) -> pd.DataFrame:
        """
        Fetch recent politician trades via API

        NOTE: max_pages parameter is kept for compatibility but ignored (API returns all trades)

        Args:
            days_back: Days to look back
            max_pages: IGNORED - kept for compatibility
            debug: Enable debug logging

        Returns:
            DataFrame with trades
        """
        logger.info(f"Fetching politician trades from last {days_back} days")

        # Check rate limit first
        if not self._check_rate_limit():
            logger.warning("⚠️ API rate limit reached - using cached data")
            cached_df = self._load_cached_trades()

            if not cached_df.empty:
                # Filter cached data to requested time range
                cutoff_date = datetime.now() - timedelta(days=days_back)
                cached_df = cached_df[cached_df['trade_date'] >= cutoff_date]
                logger.info(f"✓ Returning {len(cached_df)} cached trades")
                return cached_df
            else:
                logger.error("❌ No cached data available and rate limit reached")
                return pd.DataFrame()

        # Fetch from API
        trades_data = self._fetch_trades_from_api(days_back)

        if not trades_data:
            logger.warning("No trades returned from API - checking cache")
            cached_df = self._load_cached_trades()

            if not cached_df.empty:
                cutoff_date = datetime.now() - timedelta(days=days_back)
                cached_df = cached_df[cached_df['trade_date'] >= cutoff_date]
                logger.info(f"✓ Returning {len(cached_df)} cached trades (API failed)")
                return cached_df
            else:
                logger.warning("No cached data available")
                return pd.DataFrame()

        # Parse and filter
        clean_trades = self._parse_and_filter_trades(trades_data, days_back)

        if not clean_trades:
            logger.warning("No trades after filtering")
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(clean_trades)

        # Clean and enrich data
        df = self._clean_trades_data(df)

        # Save to cache
        self._save_to_cache(df)

        logger.info(f"✓ Fetched {len(df)} politician trades")
        return df

    def _clean_trades_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and enrich trades data

        Args:
            df: Raw trades DataFrame

        Returns:
            Cleaned DataFrame
        """
        if df.empty:
            return df

        # Parse amount ranges
        df['amount_min'] = df['amount_range'].apply(self._parse_amount_min)
        df['amount_max'] = df['amount_range'].apply(self._parse_amount_max)
        df['amount_mid'] = (df['amount_min'] + df['amount_max']) / 2

        # Apply politician weights (time-decay if tracker available, otherwise static)
        if self.politician_tracker:
            # Get current weights from tracker (includes time-decay for retiring/retired politicians)
            current_weights = self.politician_tracker.get_all_weights()
            df['politician_weight'] = df['politician'].apply(
                lambda p: current_weights.get(p, self.politician_tracker.default_weight)
            )
            logger.info("✓ Applied time-decay weights from PoliticianTracker")
        else:
            # Fall back to static weights
            df['politician_weight'] = df['politician'].apply(
                lambda p: self.POLITICIAN_WEIGHTS.get(p, self.POLITICIAN_WEIGHTS['Default'])
            )
            logger.debug("✓ Applied static weights (no time-decay)")

        # Calculate weighted amount
        df['weighted_amount'] = df['amount_mid'] * df['politician_weight']

        # Add disclosure lag (if disclosure_date is available)
        if 'disclosure_date' in df.columns:
            try:
                df['disclosure_lag_days'] = (
                    pd.to_datetime(df['disclosure_date']) - pd.to_datetime(df['trade_date'])
                ).dt.days
            except (TypeError, AttributeError):
                df['disclosure_lag_days'] = pd.NA

        # Remove invalid tickers
        df = df[df['ticker'].str.len() > 0]
        df = df[df['ticker'].str.len() <= 5]  # Valid tickers are 1-5 chars

        return df

    def _parse_amount_min(self, amount_str: str) -> float:
        """Parse minimum amount from range string like '1K-15K' or '$1,000-$15,000'"""
        if not amount_str or amount_str == '' or amount_str == 'N/A':
            return 1000  # Default minimum

        import re

        # Handle formats like "1K-15K" or "$1K-$15K"
        # Extract first number with K/M multiplier
        match = re.search(r'\$?([\d,]+\.?\d*)\s*([KMB])?', str(amount_str), re.IGNORECASE)

        if match:
            num_str = match.group(1).replace(',', '')
            multiplier = match.group(2)

            try:
                value = float(num_str)

                if multiplier:
                    multiplier = multiplier.upper()
                    if multiplier == 'K':
                        value *= 1000
                    elif multiplier == 'M':
                        value *= 1000000
                    elif multiplier == 'B':
                        value *= 1000000000

                return value
            except ValueError:
                pass

        return 1000

    def _parse_amount_max(self, amount_str: str) -> float:
        """Parse maximum amount from range string"""
        if not amount_str or amount_str == '' or amount_str == 'N/A':
            return 15000  # Default maximum

        import re

        # Find all numbers with K/M multipliers
        matches = re.findall(r'\$?([\d,]+\.?\d*)\s*([KMB])?', str(amount_str), re.IGNORECASE)

        if len(matches) >= 2:
            # Take the second number (max of range)
            num_str = matches[1][0].replace(',', '')
            multiplier = matches[1][1]

            try:
                value = float(num_str)

                if multiplier:
                    multiplier = multiplier.upper()
                    if multiplier == 'K':
                        value *= 1000
                    elif multiplier == 'M':
                        value *= 1000000
                    elif multiplier == 'B':
                        value *= 1000000000

                return value
            except ValueError:
                pass
        elif len(matches) == 1:
            # Only one number - use it as max
            return self._parse_amount_min(amount_str)

        return 15000

    def detect_politician_clusters(self, df: pd.DataFrame,
                                   min_politicians: int = 2,
                                   max_days_span: int = 30) -> pd.DataFrame:
        """
        Detect stocks with clustered politician purchases

        Args:
            df: Trades DataFrame
            min_politicians: Minimum politicians for cluster
            max_days_span: Maximum days between trades

        Returns:
            DataFrame with clusters
        """
        if df.empty:
            logger.warning("No trades to analyze")
            return pd.DataFrame()

        # Group by ticker
        clusters = df.groupby('ticker').agg({
            'politician': ['nunique', lambda x: list(x)],  # Fixed: nunique counts unique politicians, not all rows
            'trade_date': ['min', 'max'],
            'amount_mid': ['sum', lambda x: list(x)],
            'weighted_amount': 'sum',
            'asset_name': 'first',
            'chamber': lambda x: list(x),
            'party': lambda x: list(x),
            'transaction_type': lambda x: list(x)
        }).reset_index()

        # Flatten column names
        clusters.columns = [
            'ticker', 'num_politicians', 'politician_list',
            'first_trade', 'last_trade', 'total_amount', 'amount_list',
            'weighted_total', 'company', 'chambers', 'parties', 'transaction_types'
        ]

        # Calculate time span
        clusters['days_span'] = (
            clusters['last_trade'] - clusters['first_trade']
        ).dt.days

        # Detect bipartisan
        clusters['is_bipartisan'] = clusters['parties'].apply(
            lambda p: len(set(p)) >= 2
        )

        # Filter clusters
        clusters = clusters[
            (clusters['num_politicians'] >= min_politicians) &
            (clusters['days_span'] <= max_days_span)
        ]

        if clusters.empty:
            logger.info(f"No clusters with {min_politicians}+ politicians found")
            return clusters

        # Create detailed trades list for each cluster (for email display)
        def create_trades_list(row):
            trades = []
            for pol, amt, tx_type in zip(row['politician_list'], row['amount_list'], row['transaction_types']):
                trades.append({
                    'politician': pol,
                    'amount': amt,
                    'transaction_type': tx_type
                })
            return trades

        clusters['trades'] = clusters.apply(create_trades_list, axis=1)

        # Calculate conviction score
        clusters['conviction_score'] = (
            clusters['num_politicians'] * 2.0 +
            clusters['weighted_total'] / 100000 * 1.5 +
            (max_days_span - clusters['days_span']) / max_days_span * 1.0 +
            clusters['is_bipartisan'] * 2.0  # Bonus for bipartisan
        )

        # Sort by conviction
        clusters = clusters.sort_values('conviction_score', ascending=False)

        logger.info(f"✓ Detected {len(clusters)} politician clusters")

        return clusters

    def get_trades_for_ticker(self, ticker: str, days_back: int = 90) -> pd.DataFrame:
        """
        Get all politician trades for a specific ticker

        Args:
            ticker: Stock ticker
            days_back: Days to look back

        Returns:
            DataFrame with trades for this ticker
        """
        # Fetch recent trades
        all_trades = self.scrape_recent_trades(days_back, max_pages=10)

        if all_trades.empty:
            return pd.DataFrame()

        # Filter to ticker
        ticker_trades = all_trades[
            all_trades['ticker'].str.upper() == ticker.upper()
        ]

        return ticker_trades.sort_values('trade_date', ascending=False)


# Backward compatibility: Keep old method names
class PoliticianTradeAPI(CapitolTradesScraper):
    """
    Alias for CapitolTradesScraper
    Maintains backward compatibility
    """
    pass


# Usage example and test
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🏛️ POLITICIAN TRADE API TEST")
    print("="*60 + "\n")

    scraper = CapitolTradesScraper()

    # Test API fetch
    print("Testing API fetch...")
    trades = scraper.scrape_recent_trades(days_back=30)

    if not trades.empty:
        print(f"\n{'='*60}")
        print(f"✓ Fetched {len(trades)} politician trades")
        print(f"{'='*60}\n")
        print("Sample trades:")
        print(trades[['politician', 'ticker', 'trade_date', 'amount_mid', 'party']].head(10))

        # Detect clusters
        print(f"\n{'='*60}")
        print("Testing cluster detection...")
        print(f"{'='*60}\n")

        clusters = scraper.detect_politician_clusters(trades)

        if not clusters.empty:
            print(f"✓ Found {len(clusters)} politician clusters\n")
            print("Top clusters:")
            print(clusters[['ticker', 'num_politicians', 'conviction_score', 'company']].head())
        else:
            print("No clusters detected (need 2+ politicians)")
    else:
        print("❌ No trades fetched - check API key and rate limit")

    print("\n" + "="*60)
    print("Test complete!")
    print("="*60 + "\n")
