"""
Ticker Validation and Normalization Module

Provides centralized ticker validation, normalization, and failed ticker caching
to prevent wasted API calls and improve data quality.

Features:
- Ticker normalization (remove .Q, .G, .M and other suffixes)
- Ticker validation (mutual funds, invalid formats, etc.)
- Failed ticker cache (blacklist known-bad tickers)
- Smart retry logic (distinguish permanent vs temporary failures)
"""

import os
import json
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Set

logger = logging.getLogger(__name__)

# File paths
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
FAILED_TICKERS_CACHE_FILE = os.path.join(DATA_DIR, 'failed_tickers_cache.json')

# Ticker validation patterns
MUTUAL_FUND_SUFFIXES = ['X', 'Y', 'Z']  # Common mutual fund share class indicators
STOCK_CLASS_SUFFIXES = ['Q', 'G', 'M', 'A', 'B', 'C', 'D', 'E', 'K', 'P', 'R', 'U', 'V', 'W']
VALID_TICKER_PATTERN = re.compile(r'^[A-Z]{1,5}$')  # 1-5 uppercase letters after normalization

# Known problematic patterns
OTC_INDICATORS = ['OTC', 'OTCQB', 'OTCQX', 'PINK']

# Cache settings
CACHE_EXPIRY_DAYS = 30  # How long to cache failed tickers
MAX_RETRY_ATTEMPTS = 3  # How many failures before permanent blacklist


class FailedTickerCache:
    """
    Manages cache of failed tickers to prevent repeated API calls.

    Tracks:
    - Ticker symbol
    - Failure count
    - Last failure date
    - Failure reason (404, timeout, delisted, etc.)
    - Failure type (permanent vs temporary)
    """

    def __init__(self, cache_file: str = FAILED_TICKERS_CACHE_FILE):
        self.cache_file = cache_file
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict:
        """Load failed tickers cache from disk"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache = json.load(f)
                logger.info(f"Loaded {len(cache)} failed tickers from cache")
                return cache
            else:
                logger.info("No failed ticker cache found. Starting fresh.")
                return {}
        except Exception as e:
            logger.error(f"Error loading failed ticker cache: {e}")
            return {}

    def _save_cache(self) -> None:
        """Save failed tickers cache to disk"""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
            logger.debug(f"Saved {len(self.cache)} failed tickers to cache")
        except Exception as e:
            logger.error(f"Error saving failed ticker cache: {e}")

    def is_blacklisted(self, ticker: str) -> Tuple[bool, Optional[str]]:
        """
        Check if ticker is blacklisted

        Returns:
            (is_blacklisted, reason)
        """
        ticker = ticker.upper().strip()

        if ticker not in self.cache:
            return False, None

        entry = self.cache[ticker]

        # Check if permanent failure
        if entry.get('failure_type') == 'PERMANENT':
            return True, entry.get('reason', 'Permanently blacklisted')

        # Check if exceeded retry attempts
        if entry.get('failure_count', 0) >= MAX_RETRY_ATTEMPTS:
            return True, f"Exceeded max retry attempts ({entry.get('failure_count')})"

        # Check if cache is expired (allow retry after expiry)
        if 'last_failure' in entry:
            try:
                last_failure = datetime.fromisoformat(entry['last_failure'])
                age_days = (datetime.now() - last_failure).days

                if age_days > CACHE_EXPIRY_DAYS:
                    logger.debug(f"{ticker}: Cache expired ({age_days} days old), allowing retry")
                    return False, None
            except Exception:
                pass

        # Temporary failure - check retry count
        if entry.get('failure_count', 0) < MAX_RETRY_ATTEMPTS:
            return False, None

        return True, entry.get('reason', 'Unknown failure')

    def record_failure(self, ticker: str, reason: str,
                      failure_type: str = 'TEMPORARY',
                      error_code: Optional[int] = None) -> None:
        """
        Record a ticker failure

        Args:
            ticker: Stock ticker
            reason: Failure reason (e.g., "404 Not Found", "Delisted", etc.)
            failure_type: 'PERMANENT' or 'TEMPORARY'
            error_code: HTTP error code if applicable
        """
        ticker = ticker.upper().strip()

        if ticker not in self.cache:
            self.cache[ticker] = {
                'failure_count': 0,
                'first_failure': datetime.now().isoformat(),
                'failure_history': []
            }

        entry = self.cache[ticker]
        entry['failure_count'] += 1
        entry['last_failure'] = datetime.now().isoformat()
        entry['reason'] = reason
        entry['failure_type'] = failure_type

        if error_code:
            entry['error_code'] = error_code

        # Track failure history (last 5)
        entry['failure_history'].append({
            'date': datetime.now().isoformat(),
            'reason': reason,
            'type': failure_type
        })
        if len(entry['failure_history']) > 5:
            entry['failure_history'] = entry['failure_history'][-5:]

        # Auto-promote to PERMANENT after max retries
        if entry['failure_count'] >= MAX_RETRY_ATTEMPTS and failure_type == 'TEMPORARY':
            entry['failure_type'] = 'PERMANENT'
            logger.info(f"{ticker}: Promoted to PERMANENT blacklist after {entry['failure_count']} failures")

        self._save_cache()

        logger.debug(f"Recorded failure for {ticker}: {reason} (count: {entry['failure_count']}, type: {failure_type})")

    def record_success(self, ticker: str) -> None:
        """
        Record a successful ticker fetch (removes from cache)

        Args:
            ticker: Stock ticker
        """
        ticker = ticker.upper().strip()

        if ticker in self.cache:
            del self.cache[ticker]
            self._save_cache()
            logger.info(f"{ticker}: Removed from failed ticker cache (successful fetch)")

    def get_stats(self) -> Dict:
        """Get cache statistics"""
        permanent = sum(1 for e in self.cache.values() if e.get('failure_type') == 'PERMANENT')
        temporary = len(self.cache) - permanent

        return {
            'total_failed_tickers': len(self.cache),
            'permanent_failures': permanent,
            'temporary_failures': temporary,
            'cache_file': self.cache_file
        }

    def cleanup_expired(self) -> int:
        """Remove expired entries from cache"""
        expired = []

        for ticker, entry in self.cache.items():
            # Don't remove permanent failures
            if entry.get('failure_type') == 'PERMANENT':
                continue

            # Check if expired
            if 'last_failure' in entry:
                try:
                    last_failure = datetime.fromisoformat(entry['last_failure'])
                    age_days = (datetime.now() - last_failure).days

                    if age_days > CACHE_EXPIRY_DAYS:
                        expired.append(ticker)
                except Exception:
                    pass

        for ticker in expired:
            del self.cache[ticker]

        if expired:
            self._save_cache()
            logger.info(f"Cleaned up {len(expired)} expired failed ticker entries")

        return len(expired)


# Global singleton
_failed_ticker_cache = None


def get_failed_ticker_cache() -> FailedTickerCache:
    """Get or create global failed ticker cache"""
    global _failed_ticker_cache
    if _failed_ticker_cache is None:
        _failed_ticker_cache = FailedTickerCache()
    return _failed_ticker_cache


def normalize_ticker(ticker: str) -> str:
    """
    Normalize ticker symbol by removing problematic suffixes

    Removes:
    - Stock class suffixes: .Q, .G, .M, .A, .B, etc.
    - Whitespace and special characters
    - Converts to uppercase

    Examples:
        GAB.Q -> GAB
        GRX.G -> GRX
        GDV.M -> GDV
        brk.b -> BRK
        AAPL  -> AAPL

    Args:
        ticker: Raw ticker symbol

    Returns:
        Normalized ticker symbol
    """
    if not ticker:
        return ""

    # Convert to uppercase and strip whitespace
    ticker = str(ticker).upper().strip()

    # Remove stock class suffixes (e.g., .Q, .G, .M, .A, .B)
    # Pattern: dot followed by 1-2 uppercase letters at end of string
    # Apply repeatedly to handle cases like GAB.Q.X
    while re.search(r'\.[A-Z]{1,2}$', ticker):
        ticker = re.sub(r'\.[A-Z]{1,2}$', '', ticker)

    # Remove any remaining special characters except hyphens
    # (Some tickers legitimately have hyphens like BRK-B)
    ticker = re.sub(r'[^A-Z0-9\-]', '', ticker)

    # Replace hyphens with dots for Berkshire-style tickers
    # BRK-B is sometimes written as BRK.B
    # We'll keep the hyphen for now as it's more standard

    return ticker


def is_mutual_fund(ticker: str) -> bool:
    """
    Detect if ticker is likely a mutual fund

    Mutual funds typically:
    - End with X, Y, or Z (share class indicators)
    - Are 5 characters long
    - Have specific patterns (e.g., VFIAX, XIVYX)

    Args:
        ticker: Ticker symbol

    Returns:
        True if likely a mutual fund
    """
    if not ticker:
        return False

    ticker = ticker.upper().strip()

    # Check for mutual fund suffixes
    if len(ticker) == 5 and ticker[-1] in MUTUAL_FUND_SUFFIXES:
        return True

    # Check for known mutual fund patterns
    # Many funds end in X (institutional), Y (advisor), Z (investor)
    if len(ticker) >= 5 and ticker[-1] in MUTUAL_FUND_SUFFIXES:
        # Additional check: second-to-last char is often also a letter
        if len(ticker) >= 2 and ticker[-2].isalpha():
            return True

    return False


def is_valid_ticker(ticker: str) -> Tuple[bool, Optional[str]]:
    """
    Validate ticker symbol format

    Checks:
    - Length (1-5 characters after normalization)
    - Valid characters (A-Z, 0-9, hyphen)
    - Not a mutual fund
    - Not in blacklist

    Args:
        ticker: Ticker symbol (should be normalized first)

    Returns:
        (is_valid, reason_if_invalid)
    """
    if not ticker:
        return False, "Empty ticker"

    ticker = ticker.upper().strip()

    # Check length
    if len(ticker) < 1:
        return False, "Too short"
    if len(ticker) > 6:  # Allow up to 6 for some tickers
        return False, f"Too long ({len(ticker)} chars)"

    # Check for mutual fund
    if is_mutual_fund(ticker):
        return False, "Mutual fund ticker"

    # Check for invalid characters
    # Valid: A-Z, 0-9, hyphen, dot (for special cases like BRK.B)
    if not re.match(r'^[A-Z0-9\-\.]+$', ticker):
        return False, "Invalid characters"

    # Check if starts with number (unusual but some exist)
    if ticker[0].isdigit():
        return False, "Starts with number"

    # Check blacklist
    cache = get_failed_ticker_cache()
    is_blacklisted, reason = cache.is_blacklisted(ticker)
    if is_blacklisted:
        return False, f"Blacklisted: {reason}"

    return True, None


def validate_and_normalize_ticker(raw_ticker: str) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Complete ticker validation and normalization pipeline

    Steps:
    1. Normalize ticker (remove suffixes, clean format)
    2. Validate ticker (check format, mutual funds, blacklist)
    3. Return normalized ticker if valid

    Args:
        raw_ticker: Raw ticker from data source

    Returns:
        (normalized_ticker, error_reason, should_retry)
        - normalized_ticker: Clean ticker if valid, None if invalid
        - error_reason: Reason for invalidity, None if valid
        - should_retry: Whether this is a temporary failure worth retrying
    """
    if not raw_ticker:
        return None, "Empty ticker", False

    # Step 1: Normalize
    normalized = normalize_ticker(raw_ticker)

    if not normalized:
        return None, "Normalization failed", False

    # Step 2: Validate
    is_valid, reason = is_valid_ticker(normalized)

    if not is_valid:
        # Determine if this is retryable
        should_retry = False
        if reason and ('Blacklisted' not in reason and 'Mutual fund' not in reason):
            should_retry = True

        return None, reason, should_retry

    # All good!
    return normalized, None, True


def bulk_normalize_tickers(tickers: list) -> Dict[str, str]:
    """
    Normalize a list of tickers

    Args:
        tickers: List of raw ticker symbols

    Returns:
        Dict mapping raw_ticker -> normalized_ticker
    """
    mapping = {}

    for raw_ticker in tickers:
        if not raw_ticker:
            continue

        normalized, error, _ = validate_and_normalize_ticker(raw_ticker)

        if normalized:
            mapping[raw_ticker] = normalized
        else:
            logger.debug(f"Skipping invalid ticker '{raw_ticker}': {error}")

    return mapping


def get_validation_stats() -> Dict:
    """
    Get ticker validation statistics

    Returns:
        Dict with cache stats and metrics
    """
    cache = get_failed_ticker_cache()
    return cache.get_stats()


def cleanup_failed_ticker_cache() -> int:
    """
    Clean up expired entries from failed ticker cache

    Returns:
        Number of entries removed
    """
    cache = get_failed_ticker_cache()
    return cache.cleanup_expired()


if __name__ == "__main__":
    # Test the module
    import logging
    logging.basicConfig(level=logging.INFO)

    print("Testing Ticker Validation Module\n")

    # Test cases
    test_tickers = [
        "GAB.Q",      # Stock class suffix
        "GRX.G",      # Stock class suffix
        "GDV.M",      # Stock class suffix
        "EMBY",       # Normal ticker
        "XIVYX",      # Mutual fund
        "AAPL",       # Normal ticker
        "BRK.B",      # Berkshire class B
        "MSFT",       # Normal ticker
        "",           # Empty
        "TOOLONG123", # Too long
        "12AB",       # Starts with number
        "ABC@DEF",    # Invalid chars
    ]

    print("1. Testing normalization and validation:\n")
    for ticker in test_tickers:
        normalized, error, should_retry = validate_and_normalize_ticker(ticker)
        status = "✅ VALID" if normalized else f"❌ INVALID ({error})"
        print(f"  {ticker:15} -> {normalized or 'N/A':10} | {status}")

    print("\n2. Testing failed ticker cache:\n")
    cache = get_failed_ticker_cache()

    # Record some failures
    cache.record_failure("BADTICKER1", "404 Not Found", "PERMANENT", 404)
    cache.record_failure("BADTICKER2", "Timeout", "TEMPORARY")
    cache.record_failure("BADTICKER2", "Timeout", "TEMPORARY")
    cache.record_failure("BADTICKER2", "Timeout", "TEMPORARY")  # Should promote to PERMANENT

    print("  Recorded 3 failures")
    print(f"  Stats: {cache.get_stats()}")

    # Test blacklist check
    is_bl, reason = cache.is_blacklisted("BADTICKER1")
    print(f"  BADTICKER1 blacklisted: {is_bl} ({reason})")

    is_bl, reason = cache.is_blacklisted("GOODTICKER")
    print(f"  GOODTICKER blacklisted: {is_bl} ({reason})")

    print("\n✅ Test complete!")
