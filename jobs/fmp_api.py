"""
Enhanced FMP API Integration with Multi-Field Caching & Analytics

NEW FEATURES:
- Multi-field caching: price, marketCap, volume, industry, sector, etc.
- Smart analytics: API usage tracking, cost analysis, cache efficiency
- Cache warming: Pre-populate S&P 500 tickers for 100% hit rate
- Eliminates yfinance dependency for most fields

Performance targets:
- >95% success rate
- <10 seconds for 100 tickers (first fetch)
- <1 second for 100 tickers (cached)
- 100% hit rate for S&P 500 stocks (with cache warming)
"""

import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configuration
FMP_API_KEY = os.getenv('FMP_API_KEY')
COMPANY_PROFILES_CACHE_FILE = "data/company_profiles_cache.json"
ANALYTICS_FILE = "data/fmp_analytics.json"
PROFILE_CACHE_TTL_DAYS = 30  # Industry/sector rarely change
PRICE_CACHE_TTL_HOURS = 24  # Price data expires daily
MAX_PARALLEL_WORKERS = 5
FMP_API_BASE_URL = "https://financialmodelingprep.com/stable"

# Cost tracking (FMP pricing)
FMP_FREE_TIER_LIMIT = 250  # requests per day
FMP_COST_PER_REQUEST = 0.00  # Free tier
FMP_PAID_COST_PER_REQUEST = 0.000028  # $14/month ÷ 500k requests

# Logging setup
logger = logging.getLogger(__name__)


class FMPAnalytics:
    """Track FMP API usage, cache performance, and costs"""

    def __init__(self, analytics_file: str = ANALYTICS_FILE):
        self.analytics_file = analytics_file
        self.data = self._load_analytics()

    def _load_analytics(self) -> Dict:
        """Load analytics from disk"""
        try:
            if os.path.exists(self.analytics_file):
                with open(self.analytics_file, 'r') as f:
                    return json.load(f)
            else:
                return self._create_empty_analytics()
        except Exception as e:
            logger.warning(f"Error loading analytics: {e}")
            return self._create_empty_analytics()

    def _create_empty_analytics(self) -> Dict:
        """Create empty analytics structure"""
        return {
            'total_api_calls': 0,
            'total_cache_hits': 0,
            'total_cache_misses': 0,
            'total_errors': 0,
            'daily_usage': {},
            'monthly_usage': {},
            'cache_efficiency_history': [],
            'cost_tracking': {
                'total_free_calls': 0,
                'total_paid_calls': 0,
                'estimated_cost_saved': 0.0
            },
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }

    def _save_analytics(self) -> None:
        """Save analytics to disk"""
        try:
            os.makedirs(os.path.dirname(self.analytics_file), exist_ok=True)
            self.data['last_updated'] = datetime.now().isoformat()

            with open(self.analytics_file, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving analytics: {e}")

    def record_api_call(self, success: bool = True) -> None:
        """Record an API call"""
        self.data['total_api_calls'] += 1

        if not success:
            self.data['total_errors'] += 1

        # Daily tracking
        today = datetime.now().strftime('%Y-%m-%d')
        if today not in self.data['daily_usage']:
            self.data['daily_usage'][today] = 0
        self.data['daily_usage'][today] += 1

        # Monthly tracking
        month = datetime.now().strftime('%Y-%m')
        if month not in self.data['monthly_usage']:
            self.data['monthly_usage'][month] = 0
        self.data['monthly_usage'][month] += 1

        # Cost tracking
        if self.data['daily_usage'][today] <= FMP_FREE_TIER_LIMIT:
            self.data['cost_tracking']['total_free_calls'] += 1
        else:
            self.data['cost_tracking']['total_paid_calls'] += 1

    def record_cache_hit(self) -> None:
        """Record a cache hit"""
        self.data['total_cache_hits'] += 1

        # Calculate cost saved (avoided API call)
        self.data['cost_tracking']['estimated_cost_saved'] += FMP_PAID_COST_PER_REQUEST

    def record_cache_miss(self) -> None:
        """Record a cache miss"""
        self.data['total_cache_misses'] += 1

    def snapshot_efficiency(self, cache_size: int) -> None:
        """Take a snapshot of current cache efficiency"""
        total = self.data['total_cache_hits'] + self.data['total_cache_misses']
        hit_rate = (self.data['total_cache_hits'] / total * 100) if total > 0 else 0

        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'cache_size': cache_size,
            'hit_rate_pct': round(hit_rate, 2),
            'total_hits': self.data['total_cache_hits'],
            'total_misses': self.data['total_cache_misses']
        }

        self.data['cache_efficiency_history'].append(snapshot)

        # Keep only last 30 snapshots
        if len(self.data['cache_efficiency_history']) > 30:
            self.data['cache_efficiency_history'] = self.data['cache_efficiency_history'][-30:]

    def save(self) -> None:
        """Save analytics to disk"""
        self._save_analytics()

    def get_summary(self) -> Dict:
        """Get analytics summary"""
        total_requests = self.data['total_cache_hits'] + self.data['total_cache_misses']
        hit_rate = (self.data['total_cache_hits'] / total_requests * 100) if total_requests > 0 else 0

        today = datetime.now().strftime('%Y-%m-%d')
        today_usage = self.data['daily_usage'].get(today, 0)

        month = datetime.now().strftime('%Y-%m')
        month_usage = self.data['monthly_usage'].get(month, 0)

        return {
            'total_api_calls': self.data['total_api_calls'],
            'total_cache_hits': self.data['total_cache_hits'],
            'total_cache_misses': self.data['total_cache_misses'],
            'cache_hit_rate_pct': round(hit_rate, 1),
            'total_errors': self.data['total_errors'],
            'today_api_calls': today_usage,
            'month_api_calls': month_usage,
            'free_tier_remaining_today': max(0, FMP_FREE_TIER_LIMIT - today_usage),
            'estimated_cost_saved': round(self.data['cost_tracking']['estimated_cost_saved'], 2)
        }


class EnhancedFMPAPIClient:
    """
    Enhanced FMP API client with multi-field caching and analytics

    Caches: industry, sector, price, marketCap, volume, shares, float, etc.
    Tracks: API usage, cache efficiency, costs
    """

    def __init__(self, api_key: Optional[str] = None,
                 cache_file: str = COMPANY_PROFILES_CACHE_FILE):
        """Initialize enhanced FMP API client"""
        self.api_key = api_key or FMP_API_KEY
        self.cache_file = cache_file
        self.cache = {}
        self.analytics = FMPAnalytics()

        if not self.api_key:
            logger.warning("FMP_API_KEY not set. API calls will fail.")

        # Load cache
        self._load_cache()

        # Create session with retry logic
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic"""
        session = requests.Session()

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def _load_cache(self) -> None:
        """Load cache from disk"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    self.cache = json.load(f)
                logger.info(f"Loaded {len(self.cache)} cached profiles")
            else:
                logger.info("No cache file found. Starting with empty cache.")
                self.cache = {}
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            self.cache = {}

    def _save_cache(self) -> None:
        """Save cache to disk"""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)

            logger.debug(f"Saved {len(self.cache)} profiles to cache")
        except Exception as e:
            logger.error(f"Error saving cache: {e}")

    def _is_cache_valid(self, ticker: str, field: str = 'profile') -> bool:
        """
        Check if cached data is valid

        Args:
            ticker: Stock ticker
            field: 'profile' (30 days) or 'price' (24 hours)

        Returns:
            True if valid, False otherwise
        """
        if ticker not in self.cache:
            return False

        cached_data = self.cache[ticker]
        if 'updated' not in cached_data:
            return False

        try:
            updated_date = datetime.fromisoformat(cached_data['updated'])
            age = datetime.now() - updated_date

            if field == 'profile':
                # Profile data (industry/sector): 30 days TTL
                return age.days < PROFILE_CACHE_TTL_DAYS
            elif field == 'price':
                # Price data: 24 hours TTL
                return age.total_seconds() < (PRICE_CACHE_TTL_HOURS * 3600)
            else:
                return False

        except Exception:
            return False

    def _fetch_profile(self, ticker: str) -> Optional[Dict]:
        """
        Fetch company profile from FMP API

        Returns dict with all available fields:
        - industry, sector (classification)
        - price, mktCap, volAvg (market data)
        - beta, lastDiv, range (additional metrics)
        - And many more...
        """
        if not self.api_key:
            logger.error("Cannot fetch: FMP_API_KEY not configured")
            return None

        try:
            url = f"{FMP_API_BASE_URL}/profile"
            params = {
                'symbol': ticker,
                'apikey': self.api_key
            }

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Record API call
            self.analytics.record_api_call(success=True)

            if not data or not isinstance(data, list) or len(data) == 0:
                logger.warning(f"Empty response for {ticker}")
                return None

            profile = data[0]

            # Extract and normalize fields
            result = {
                # Classification
                'industry': profile.get('industry'),
                'sector': profile.get('sector'),

                # Market data
                'price': profile.get('price'),
                'marketCap': profile.get('mktCap'),
                'volume': profile.get('volAvg'),

                # Company info
                'companyName': profile.get('companyName'),
                'exchange': profile.get('exchangeShortName'),
                'currency': profile.get('currency', 'USD'),

                # Share structure
                'sharesOutstanding': profile.get('mktCap') / profile.get('price') if (profile.get('mktCap') and profile.get('price') and profile.get('price') > 0) else None,

                # Additional metrics
                'beta': profile.get('beta'),
                'lastDiv': profile.get('lastDiv'),
                'range': profile.get('range'),
                'changes': profile.get('changes'),
                'ipoDate': profile.get('ipoDate'),
                'dcfDiff': profile.get('dcfDiff'),
                'dcf': profile.get('dcf'),

                # Metadata
                'updated': datetime.now().isoformat(),
                'source': 'fmp_api'
            }

            # Remove None values to keep cache clean
            result = {k: v for k, v in result.items() if v is not None}

            return result

        except requests.exceptions.HTTPError as e:
            self.analytics.record_api_call(success=False)
            if e.response.status_code == 404:
                logger.debug(f"Ticker {ticker} not found (404)")
            else:
                logger.error(f"HTTP error for {ticker}: {e}")
            return None
        except Exception as e:
            self.analytics.record_api_call(success=False)
            logger.error(f"Error fetching {ticker}: {e}")
            return None

    def get_profile(self, ticker: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        Get complete profile for a ticker (with caching)

        Args:
            ticker: Stock ticker
            force_refresh: Force API call even if cached

        Returns:
            Dict with all profile fields, or None
        """
        ticker = ticker.upper().strip()

        # Check cache
        if not force_refresh and self._is_cache_valid(ticker, 'profile'):
            self.analytics.record_cache_hit()
            return self.cache[ticker]

        # Fetch from API
        self.analytics.record_cache_miss()
        profile = self._fetch_profile(ticker)

        if profile:
            self.cache[ticker] = profile
            self._save_cache()
            return profile
        else:
            return None

    def get_field(self, ticker: str, field: str) -> Optional[any]:
        """
        Get a specific field from profile

        Args:
            ticker: Stock ticker
            field: Field name (e.g., 'industry', 'price', 'marketCap')

        Returns:
            Field value or None
        """
        profile = self.get_profile(ticker)
        return profile.get(field) if profile else None

    def fetch_profiles_batch(self, tickers: List[str],
                             force_refresh: bool = False) -> Dict[str, Dict]:
        """
        Batch fetch profiles with parallelization

        Args:
            tickers: List of tickers
            force_refresh: Force refresh even if cached

        Returns:
            Dict mapping ticker to profile dict
        """
        tickers = [t.upper().strip() for t in tickers if t]
        results = {}

        # Check cache
        missing_tickers = []
        for ticker in tickers:
            if not force_refresh and self._is_cache_valid(ticker, 'profile'):
                self.analytics.record_cache_hit()
                results[ticker] = self.cache[ticker]
            else:
                missing_tickers.append(ticker)

        if missing_tickers:
            logger.info(f"Batch fetch: {len(results)} cached, {len(missing_tickers)} to fetch")

            # Parallel fetch
            start_time = time.time()

            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
                future_to_ticker = {
                    executor.submit(self._fetch_profile, ticker): ticker
                    for ticker in missing_tickers
                }

                for future in as_completed(future_to_ticker):
                    ticker = future_to_ticker[future]
                    self.analytics.record_cache_miss()

                    try:
                        profile = future.result()
                        if profile:
                            self.cache[ticker] = profile
                            results[ticker] = profile
                    except Exception as e:
                        logger.error(f"Error processing {ticker}: {e}")

            # Save cache and analytics
            self._save_cache()

            elapsed = time.time() - start_time
            logger.info(f"Fetched {len(missing_tickers)} profiles in {elapsed:.2f}s")

        return results

    def warm_cache(self, tickers: List[str], force_refresh: bool = False) -> Tuple[int, int]:
        """
        Pre-populate cache with tickers (e.g., S&P 500)

        Args:
            tickers: List of tickers to warm
            force_refresh: Force refresh even if cached

        Returns:
            Tuple of (success_count, failed_count)
        """
        logger.info(f"Warming cache with {len(tickers)} tickers...")

        profiles = self.fetch_profiles_batch(tickers, force_refresh=force_refresh)

        success = len(profiles)
        failed = len(tickers) - success

        logger.info(f"Cache warming complete: {success} success, {failed} failed")

        return success, failed

    def get_analytics_summary(self) -> Dict:
        """Get analytics summary with cache size"""
        summary = self.analytics.get_summary()
        summary['cache_size'] = len(self.cache)

        return summary

    def save_analytics(self) -> None:
        """Save analytics to disk"""
        self.analytics.snapshot_efficiency(len(self.cache))
        self.analytics.save()


# Global singleton
_enhanced_client = None


def get_enhanced_client() -> EnhancedFMPAPIClient:
    """Get or create global enhanced FMP client"""
    global _enhanced_client
    if _enhanced_client is None:
        _enhanced_client = EnhancedFMPAPIClient()
    return _enhanced_client


# Convenience functions (backward compatible)
def get_company_industry(ticker: str) -> Optional[str]:
    """Get industry for a ticker"""
    client = get_enhanced_client()
    return client.get_field(ticker, 'industry')


def get_company_profile(ticker: str) -> Optional[Dict]:
    """Get complete profile for a ticker"""
    client = get_enhanced_client()
    return client.get_profile(ticker)


def fetch_profiles_batch(tickers: List[str]) -> Dict[str, Dict]:
    """Batch fetch profiles"""
    client = get_enhanced_client()
    return client.fetch_profiles_batch(tickers)


def warm_cache_sp500(force_refresh: bool = False) -> Tuple[int, int]:
    """
    Warm cache with S&P 500 tickers

    Returns:
        Tuple of (success_count, failed_count)
    """
    # S&P 500 tickers (top 100 most traded for quick warmup)
    # Full list can be fetched from: https://datahub.io/core/s-and-p-500-companies
    sp500_top100 = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B", "UNH", "JNJ",
        "V", "XOM", "WMT", "JPM", "LLY", "MA", "PG", "AVGO", "HD", "CVX",
        "MRK", "ABBV", "COST", "KO", "PEP", "ADBE", "MCD", "CRM", "CSCO", "TMO",
        "ACN", "ABT", "NFLX", "WFC", "DHR", "ORCL", "VZ", "AMD", "NKE", "TXN",
        "PM", "INTC", "DIS", "CMCSA", "UPS", "NEE", "RTX", "BMY", "COP", "QCOM",
        "HON", "UNP", "SPGI", "LOW", "MS", "AMGN", "BA", "CAT", "IBM", "GE",
        "INTU", "T", "LMT", "SBUX", "PLD", "AXP", "BLK", "ELV", "DE", "MDLZ",
        "GILD", "ADI", "BKNG", "ADP", "TJX", "MMC", "VRTX", "SYK", "CVS", "REGN",
        "AMT", "C", "ZTS", "CI", "PGR", "ISRG", "TMUS", "MO", "CB", "SO",
        "BDX", "SCHW", "DUK", "MMM", "EOG", "BSX", "ITW", "EQIX", "HCA", "NOC"
    ]

    client = get_enhanced_client()
    return client.warm_cache(sp500_top100, force_refresh=force_refresh)


def get_analytics_summary() -> Dict:
    """Get analytics summary"""
    client = get_enhanced_client()
    return client.get_analytics_summary()


def save_analytics() -> None:
    """Save analytics to disk"""
    client = get_enhanced_client()
    client.save_analytics()


if __name__ == "__main__":
    # Test the enhanced module
    logging.basicConfig(level=logging.INFO)

    print("Testing Enhanced FMP API module...")

    # Test 1: Single profile fetch
    print("\n1. Single profile fetch:")
    profile = get_company_profile("AAPL")
    if profile:
        print(f"  Industry: {profile.get('industry')}")
        print(f"  Price: ${profile.get('price')}")
        print(f"  Market Cap: ${profile.get('marketCap'):,}" if profile.get('marketCap') else "  Market Cap: N/A")
        print(f"  Volume: {profile.get('volume'):,}" if profile.get('volume') else "  Volume: N/A")

    # Test 2: Batch fetch
    print("\n2. Batch fetch:")
    tickers = ["MSFT", "GOOGL", "TSLA", "NVDA", "META"]
    profiles = fetch_profiles_batch(tickers)
    print(f"  Fetched {len(profiles)} profiles")

    # Test 3: Analytics
    print("\n3. Analytics:")
    stats = get_analytics_summary()
    print(f"  Total API calls: {stats['total_api_calls']}")
    print(f"  Cache hit rate: {stats['cache_hit_rate_pct']}%")
    print(f"  Cache size: {stats['cache_size']} tickers")
    print(f"  Cost saved: ${stats['estimated_cost_saved']}")

    save_analytics()
    print("\n✅ Test complete!")
