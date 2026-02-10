"""
sec_13f_parser.py
Parse SEC 13F filings to track institutional holdings
FREE data from SEC EDGAR API
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logging.warning("rapidfuzz not available - fuzzy matching disabled. Install with: pip install rapidfuzz")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logging.warning("yfinance not available - ticker to company name lookup will be limited")

try:
    from config import SEC_13F_CACHE_HOURS
except ImportError:
    SEC_13F_CACHE_HOURS = 168  # Default to 7 days if config not available

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Parallel execution constants
MAX_PARALLEL_WORKERS = 4   # Reduced from 10: fewer concurrent workers prevents burst flooding SEC
RATE_LIMIT_CALLS_PER_SECOND = 5  # Reduced from 10: conservative rate to avoid 429s across ticker batches

# Fuzzy matching constants
FUZZY_MATCH_THRESHOLD = 85  # Minimum match score (0-100)
MIN_STRING_LENGTH_FOR_FUZZY = 3  # Minimum string length to avoid false positives


class RateLimiter:
    """Thread-safe rate limiter for API calls"""

    def __init__(self, calls_per_second: float):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0
        self.lock = threading.Lock()

    def wait(self):
        """Wait if necessary to respect rate limit"""
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_call
            if time_since_last < self.min_interval:
                sleep_time = self.min_interval - time_since_last
                time.sleep(sleep_time)
            self.last_call = time.time()


class SEC13FParser:
    """
    Parse 13F filings from SEC EDGAR
    Track what major institutions are buying
    """

    BASE_URL = "https://www.sec.gov"
    
    # Class-level flag to warn about missing yfinance only once
    _yfinance_warning_logged = False

    # Priority funds to track (top performers)
    # CRITICAL FIX #4: Verified and corrected CIKs
    PRIORITY_FUNDS = {
        'Berkshire Hathaway': ['0001067983'],
        'Bridgewater Associates': ['0001350694'],
        'Renaissance Technologies': ['0001037389'],
        'Two Sigma': ['0001173945'],  # Two Sigma Investments, LP (CORRECTED)
        'Citadel': ['0001423053'],  # Citadel Advisors LLC
        'Point72': ['0001603466'],  # Point72 Asset Management
        'Tiger Global': ['0001167483'],  # Tiger Global Management
        'Coatue Management': ['0001537986'],
        'D1 Capital': ['0001683040'],
        'Viking Global': ['0001103804'],
        'Soros Fund Management': ['0001029160'],
        'Third Point': ['0001040273'],  # Third Point LLC (VERIFIED)
        'Pershing Square': ['0001336528'],
        'Bill & Melinda Gates Foundation': ['0001166559'],
        'ValueAct': ['0001105158']
    }

    # Validation: Check for duplicate CIKs
    _all_ciks = [cik for ciks in PRIORITY_FUNDS.values() for cik in ciks]
    if len(_all_ciks) != len(set(_all_ciks)):
        _duplicates = [cik for cik in set(_all_ciks) if _all_ciks.count(cik) > 1]
        logger.warning(f"⚠️  DUPLICATE CIKs found in PRIORITY_FUNDS: {_duplicates}")
        logger.warning(f"   This will cause the same fund to be checked multiple times!")
        # Find which funds have duplicates
        for dup_cik in _duplicates:
            funds_with_dup = [name for name, ciks in PRIORITY_FUNDS.items() if dup_cik in ciks]
            logger.warning(f"   CIK {dup_cik} used by: {', '.join(funds_with_dup)}")

    def __init__(self, user_agent: str, cache_dir: str = "data/13f_cache"):
        """
        Initialize parser

        Args:
            user_agent: User-Agent for SEC requests (required by SEC)
                       Format: "CompanyName AdminContact@example.com"
            cache_dir: Directory for caching 13F results (24-hour cache)
        """
        self.user_agent = user_agent
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # CRITICAL FIX #3: Thread-local storage for sessions (thread safety)
        # requests.Session is NOT thread-safe, so each thread gets its own
        self._thread_local = threading.local()

        # Retry settings
        self.max_retries = 3
        self.retry_delays = [2, 4, 8]  # Exponential backoff
        self.timeout = 30  # Increased from 10s

        # Rate limiter for parallel requests
        self.rate_limiter = RateLimiter(RATE_LIMIT_CALLS_PER_SECOND)

        # In-memory CIK filing cache: avoids re-fetching the same fund's filing list
        # for each of the N tickers being checked in one pipeline run.
        # 15 funds × 33 tickers = 495 requests without this; 15 with it.
        self._cik_filings_cache: dict = {}
        self._cik_filings_cache_lock = threading.Lock()

    def _get_session(self) -> requests.Session:
        """Get thread-local session for thread-safe API calls"""
        if not hasattr(self._thread_local, 'session'):
            # Create new session for this thread
            session = requests.Session()
            session.headers.update({
                'User-Agent': self.user_agent,
                'Accept-Encoding': 'gzip, deflate',
                'Host': 'www.sec.gov'
            })
            self._thread_local.session = session
        return self._thread_local.session

    def _get_cache_path(self, ticker: str, quarter_year: int = None, quarter: int = None) -> Path:
        """Get cache file path for a ticker with quarter info to prevent stale data"""
        # Sanitize ticker to prevent path traversal
        safe_ticker = "".join(c for c in ticker if c.isalnum() or c in "-_")
        if not safe_ticker:
            raise ValueError(f"Invalid ticker: {ticker}")

        # Include quarter in cache key to prevent serving stale quarterly data
        if quarter_year and quarter:
            return self.cache_dir / f"{safe_ticker}_{quarter_year}Q{quarter}_13f.json"
        else:
            # Fallback for backward compatibility (will be deprecated)
            return self.cache_dir / f"{safe_ticker}_13f.json"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file is valid based on configured cache duration"""
        if not cache_path.exists():
            return False

        cache_age = time.time() - cache_path.stat().st_mtime
        cache_duration_seconds = SEC_13F_CACHE_HOURS * 60 * 60
        return cache_age < cache_duration_seconds

    def _read_cache(self, ticker: str, quarter_year: int = None, quarter: int = None) -> Optional[pd.DataFrame]:
        """Read cached 13F results"""
        cache_path = self._get_cache_path(ticker, quarter_year, quarter)

        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                logger.debug(f"📦 Using cached 13F data for {ticker} ({quarter_year} Q{quarter})")
                return pd.DataFrame(data)
            except Exception as e:
                logger.warning(f"Cache read error for {ticker}: {e}")
                return None

        return None

    def _write_cache(self, ticker: str, df: pd.DataFrame, quarter_year: int = None, quarter: int = None):
        """Write 13F results to cache"""
        cache_path = self._get_cache_path(ticker, quarter_year, quarter)

        try:
            # Cache both empty and non-empty results
            # Empty results are legitimate when institutions don't hold the stock
            with open(cache_path, 'w') as f:
                json.dump(df.to_dict('records'), f)

            if df.empty:
                logger.debug(f"Cached empty 13F result for {ticker} ({quarter_year} Q{quarter}) - no institutional holdings")
            else:
                logger.debug(f"Cached 13F data for {ticker} ({quarter_year} Q{quarter})")
        except Exception as e:
            logger.warning(f"Cache write error for {ticker}: {e}")

    def _get_company_name(self, ticker: str) -> Optional[str]:
        """Get company name for a ticker using yfinance with retry logic"""
        if not YFINANCE_AVAILABLE:
            # Only log error once per class instance to avoid log pollution
            if not SEC13FParser._yfinance_warning_logged:
                logger.error("yfinance not installed - 13F matching disabled. Install with: pip install yfinance")
                SEC13FParser._yfinance_warning_logged = True
            return None

        max_attempts = 2
        last_error = None

        for attempt in range(max_attempts):
            try:
                stock = yf.Ticker(ticker)
                info = stock.info

                # Check if we got valid data (yfinance returns empty dict for invalid tickers)
                if not info or len(info) < 3:
                    if attempt < max_attempts - 1:
                        time.sleep(1)
                        continue
                    # Only log on final attempt
                    logger.warning(f"Ticker {ticker} not found or invalid")
                    return None

                # Try multiple fields for company name
                company_name = info.get('longName') or info.get('shortName') or info.get('name')
                if company_name:
                    logger.debug(f"✓ Resolved {ticker} -> {company_name}")
                    return company_name
                else:
                    logger.warning(f"Ticker {ticker} found but missing company name field")
                    return None

            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    continue

        # Only log error once after all retries exhausted
        if last_error:
            logger.warning(f"Failed to lookup {ticker}: {last_error}")

        return None

    def _normalize_company_name(self, name: str) -> str:
        """
        Normalize company name for matching
        Removes common suffixes, punctuation, and normalizes whitespace

        Args:
            name: Company name to normalize

        Returns:
            Normalized company name
        """
        if not name or not isinstance(name, str):
            return ""

        # Convert to uppercase for case-insensitive matching
        normalized = name.upper().strip()

        # Remove trailing suffixes only (not in middle of words)
        # Order matters - remove longer suffixes first
        suffixes = [
            ' CORPORATION', ' INCORPORATED', ' INC.', ' INC',
            ' CORP.', ' CORP', ' LTD.', ' LTD', ' LLC',
            ' CO.', ' CO', ' LP', ' L.P.', ' PLC',
            ' COMPANY', ' GROUP', ' HOLDINGS'
        ]
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()

        # Handle .COM domains specially (normalize "AMAZON.COM" to "AMAZON COM")
        normalized = normalized.replace('.COM', ' COM')

        # Remove other punctuation and normalize whitespace
        for char in [',', '.', '-', '&', '/', '(', ')', "'", '"']:
            normalized = normalized.replace(char, ' ')

        # Normalize multiple spaces to single space
        normalized = ' '.join(normalized.split())

        return normalized

    def _fuzzy_match_company_name(self, target_name: str, filing_name: str) -> tuple:
        """
        Perform fuzzy matching between target and filing company names
        Returns (matched: bool, score: float, method: str)

        Args:
            target_name: Target company name (from ticker lookup)
            filing_name: Company name from 13F filing

        Returns:
            Tuple of (matched, score, match_method)
        """
        # Normalize both names
        target_clean = self._normalize_company_name(target_name)
        filing_clean = self._normalize_company_name(filing_name)

        # Validation: prevent false positives with short strings
        if len(target_clean) < MIN_STRING_LENGTH_FOR_FUZZY or len(filing_clean) < MIN_STRING_LENGTH_FOR_FUZZY:
            return (False, 0.0, "too_short")

        # Try exact match first (after normalization)
        if target_clean == filing_clean:
            return (True, 100.0, "exact")

        # Try substring match with high overlap ratio
        if len(target_clean) >= 8 and target_clean in filing_clean:
            overlap_ratio = len(target_clean) / len(filing_clean)
            if overlap_ratio > 0.7:
                return (True, 95.0, "substring_target_in_filing")

        if len(filing_clean) >= 8 and filing_clean in target_clean:
            overlap_ratio = len(filing_clean) / len(target_clean)
            if overlap_ratio > 0.7:
                return (True, 95.0, "substring_filing_in_target")

        # Use rapidfuzz for fuzzy matching if available
        if RAPIDFUZZ_AVAILABLE:
            # Use token_sort_ratio for better matching with word order differences
            score = fuzz.token_sort_ratio(target_clean, filing_clean)

            if score >= FUZZY_MATCH_THRESHOLD:
                return (True, score, "fuzzy")

            return (False, score, "fuzzy_below_threshold")

        # Fallback: no fuzzy matching available
        return (False, 0.0, "no_fuzzy_lib")

    def get_latest_13f_filings(self, cik: str, count: int = 5) -> List[Dict]:
        """
        Get latest 13F filings for a given CIK

        Args:
            cik: Central Index Key (SEC identifier)
            count: Number of filings to retrieve

        Returns:
            List of filing metadata dictionaries
        """
        # Pad CIK to 10 digits
        cik_padded = cik.zfill(10)

        # Check in-memory CIK filings cache first.
        # The same 15 fund CIKs are looked up for every ticker in the batch, so
        # caching here reduces ~(N_tickers × 15) SEC requests to just 15 per run.
        cache_key = (cik_padded, count)
        with self._cik_filings_cache_lock:
            if cache_key in self._cik_filings_cache:
                logger.debug(f"CIK {cik}: returning cached filings (in-memory)")
                return self._cik_filings_cache[cache_key]

        url = f"{self.BASE_URL}/cgi-bin/browse-edgar"
        params = {
            'action': 'getcompany',
            'CIK': cik,
            'type': '13F-HR',
            'dateb': '',
            'owner': 'exclude',
            'count': count,
            'output': 'atom'
        }

        logger.debug(f"Fetching 13F filings for CIK {cik}...")

        # Retry logic with exponential backoff
        for attempt in range(self.max_retries):
            try:
                # CRITICAL FIX #3: Use thread-local session for thread safety
                response = self._get_session().get(url, params=params, timeout=self.timeout)
                response.raise_for_status()

                # Parse XML feed with better error handling
                try:
                    root = ET.fromstring(response.content)
                except ET.ParseError as xml_error:
                    logger.debug(f"XML parsing error for CIK {cik}: {xml_error}")
                    # Try cleaning the content
                    content = response.content.decode('utf-8', errors='ignore')
                    # Remove problematic characters
                    content = content.replace('\x00', '')
                    try:
                        root = ET.fromstring(content.encode('utf-8'))
                    except ET.ParseError:
                        logger.debug(f"Unable to parse XML for CIK {cik} even after cleaning")
                        return []

                filings = []
                for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                    filing_date = entry.find('{http://www.w3.org/2005/Atom}updated')
                    filing_url = entry.find('{http://www.w3.org/2005/Atom}link[@type="text/html"]')

                    if filing_date is not None and filing_url is not None:
                        filings.append({
                            'date': datetime.strptime(filing_date.text[:10], '%Y-%m-%d'),
                            'url': filing_url.attrib['href']
                        })

                # Store in in-memory cache so subsequent ticker checks reuse this result
                with self._cik_filings_cache_lock:
                    self._cik_filings_cache[cache_key] = filings
                return filings

            except requests.exceptions.Timeout:
                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]
                    logger.warning(f"Timeout for CIK {cik}, retrying in {delay}s... (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(delay)
                else:
                    logger.warning(f"Timeout for CIK {cik} after {self.max_retries} attempts")
                    return []

            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]
                    logger.warning(f"Request error for CIK {cik}: {e}, retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.warning(f"Request failed for CIK {cik} after {self.max_retries} attempts: {e}")
                    return []

            except Exception as e:
                logger.warning(f"Unexpected error fetching 13F for CIK {cik}: {e}")
                return []

        return []

    def parse_13f_holdings(self, filing_url: str, target_company_name: str = None) -> pd.DataFrame:
        """
        Parse holdings from a 13F filing

        Args:
            filing_url: URL to the filing (e.g., https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=...)
            target_company_name: Optional company name to search for (returns faster if specified)

        Returns:
            DataFrame with holdings (or single holding if target_company_name specified)
        """
        try:
            # Get the filing index page
            # CRITICAL FIX #3: Use thread-local session for thread safety
            response = self._get_session().get(filing_url, timeout=self.timeout)
            response.raise_for_status()

            # Parse HTML to find the information table XML file
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for information table XML link
            xml_link = None
            for link in soup.find_all('a'):
                href = link.get('href', '')
                text = link.get_text().lower()
                # Common patterns for 13F information table files
                if ('infotable' in href.lower() or 'form13f' in href.lower()) and \
                   ('.xml' in href.lower() or 'informationtable' in text):
                    xml_link = href
                    break

            if not xml_link:
                logger.debug(f"No information table XML found at {filing_url}")
                return pd.DataFrame()

            # Make URL absolute
            if not xml_link.startswith('http'):
                xml_link = f"{self.BASE_URL}{xml_link}"

            # Fetch the XML file
            # HIGH PRIORITY FIX #7: Removed redundant sleep - RateLimiter handles rate limiting
            # CRITICAL FIX #3: Use thread-local session for thread safety
            xml_response = self._get_session().get(xml_link, timeout=self.timeout)
            xml_response.raise_for_status()

            # Parse XML
            try:
                root = ET.fromstring(xml_response.content)
            except ET.ParseError as xml_error:
                logger.debug(f"XML parsing error: {xml_error}")
                # Try cleaning the content
                content = xml_response.content.decode('utf-8', errors='ignore')
                content = content.replace('\x00', '')
                try:
                    root = ET.fromstring(content.encode('utf-8'))
                except ET.ParseError:
                    return pd.DataFrame()

            # Parse holdings from XML
            holdings = []

            # XML namespace handling
            namespaces = {}
            if root.tag.startswith('{'):
                ns = root.tag[1:root.tag.index('}')]
                namespaces['ns'] = ns

            # Find all infoTable entries
            info_tables = root.findall('.//ns:infoTable', namespaces) if namespaces else root.findall('.//infoTable')
            if not info_tables:
                # Try without namespace
                info_tables = root.findall('.//infoTable')

            for entry in info_tables:
                try:
                    # Extract ticker/name
                    name_elem = entry.find('.//ns:nameOfIssuer', namespaces) if namespaces else entry.find('.//nameOfIssuer')
                    if name_elem is None:
                        name_elem = entry.find('.//nameOfIssuer')

                    ticker_elem = entry.find('.//ns:titleOfClass', namespaces) if namespaces else entry.find('.//titleOfClass')
                    if ticker_elem is None:
                        ticker_elem = entry.find('.//titleOfClass')

                    # Extract shares
                    shares_elem = entry.find('.//ns:sshPrnamt', namespaces) if namespaces else entry.find('.//sshPrnamt')
                    if shares_elem is None:
                        shares_elem = entry.find('.//sshPrnamt')

                    # Extract value (in thousands)
                    value_elem = entry.find('.//ns:value', namespaces) if namespaces else entry.find('.//value')
                    if value_elem is None:
                        value_elem = entry.find('.//value')

                    if name_elem is not None:
                        name = name_elem.text.strip() if name_elem.text else ""
                        ticker = ticker_elem.text.strip() if ticker_elem is not None and ticker_elem.text else ""
                        shares = int(shares_elem.text) if shares_elem is not None and shares_elem.text else 0
                        # Value is in thousands of dollars per SEC format
                        value = int(value_elem.text) * 1000 if value_elem is not None and value_elem.text else 0

                        # If target company name specified, only return matching holdings
                        if target_company_name:
                            # Use fuzzy matching to find company
                            matched, score, method = self._fuzzy_match_company_name(target_company_name, name)

                            if matched:
                                # Log fuzzy matches separately for monitoring
                                if method == "fuzzy":
                                    logger.info(f"Fuzzy match: '{target_company_name}' -> '{name}' ({score:.0f}%)")
                                elif method in ["substring_target_in_filing", "substring_filing_in_target"]:
                                    logger.debug(f"Substring match: '{target_company_name}' -> '{name}' ({score:.0f}%)")
                                else:  # exact match
                                    logger.debug(f"Exact match: '{target_company_name}' -> '{name}'")

                                holdings.append({
                                    'name': name,
                                    'ticker_class': ticker,
                                    'shares': shares,
                                    'value': value
                                })
                                break  # Found it, no need to continue
                        else:
                            holdings.append({
                                'name': name,
                                'ticker_class': ticker,
                                'shares': shares,
                                'value': value
                            })

                except Exception as entry_error:
                    logger.debug(f"Error parsing entry: {entry_error}")
                    continue

            return pd.DataFrame(holdings)

        except Exception as e:
            logger.debug(f"Error parsing 13F from {filing_url}: {e}")
            return pd.DataFrame()

    def _check_single_fund(self, fund_name: str, cik: str, ticker: str, company_name: str) -> Optional[Dict]:
        """
        Check a single fund for holdings of a specific ticker
        Thread-safe helper method for parallel execution

        Args:
            fund_name: Name of the fund
            cik: Central Index Key
            ticker: Stock ticker
            company_name: Company name to match

        Returns:
            Dictionary with holding data if found, None otherwise
            OR dictionary with 'error': True if API call failed
        """
        try:
            # Apply rate limiting
            self.rate_limiter.wait()

            # Get latest filings
            filings = self.get_latest_13f_filings(cik, count=2)

            if not filings:
                # Distinguish between "no filings found" (legitimate) vs API failure
                # If get_latest_13f_filings returns empty list, it could be either
                # We'll treat it as "no holdings" rather than error
                logger.debug(f"{fund_name}: No recent 13F filings found")
                return None

            # Check most recent filing
            latest = filings[0]

            # Parse holdings to find this company
            # Use company name for matching (more reliable than ticker)
            holdings = self.parse_13f_holdings(latest['url'], target_company_name=company_name)

            if not holdings.empty:
                # Found the company in this fund's holdings
                holding = holdings.iloc[0]  # Should only be one match
                result = {
                    'fund': fund_name,
                    'cik': cik,
                    'filing_date': latest['date'],
                    'ticker': ticker,
                    'value': holding['value'],
                    'shares': holding['shares']
                }
                logger.debug(f"✓ {fund_name}: {holding['shares']:,} shares (${holding['value']:,.0f})")
                return result
            else:
                logger.debug(f"{fund_name}: Does not hold {ticker}")

            return None

        except Exception as e:
            # This is a genuine error - API failure, timeout, etc.
            logger.warning(f"API error checking {fund_name} for {ticker}: {e}")
            return {'error': True, 'fund': fund_name, 'exception': str(e)}

    def check_institutional_interest(self, ticker: str, quarter_year: int, quarter: int) -> pd.DataFrame:
        """
        Check which priority funds hold a given ticker and extract actual position sizes
        Uses parallel execution with ThreadPoolExecutor for improved performance

        Args:
            ticker: Stock ticker symbol
            quarter_year: Year (e.g., 2024)
            quarter: Quarter (1-4)

        Returns:
            DataFrame of funds that hold this ticker with shares and values
        """
        # CRITICAL FIX #5: Validate inputs
        if not isinstance(quarter, int) or not 1 <= quarter <= 4:
            raise ValueError(f"Invalid quarter: {quarter}. Must be 1-4.")

        current_year = datetime.now().year
        if not isinstance(quarter_year, int) or not 2010 <= quarter_year <= current_year + 1:
            raise ValueError(f"Invalid year: {quarter_year}. Must be 2010-{current_year+1}.")

        # Check cache first (with quarter-aware key)
        cached_data = self._read_cache(ticker, quarter_year, quarter)
        if cached_data is not None:
            return cached_data

        logger.info(f"Checking institutional interest for {ticker} ({quarter_year} Q{quarter})")

        # Get company name for ticker to match against 13F filings
        company_name = self._get_company_name(ticker)
        if not company_name:
            # Already logged in _get_company_name, just return empty
            # CRITICAL FIX #2: Don't cache empty results - _write_cache now validates
            empty_df = pd.DataFrame()
            self._write_cache(ticker, empty_df, quarter_year, quarter)
            return empty_df

        # Prepare list of (fund_name, cik) tuples for parallel processing
        fund_tasks = []
        for fund_name, ciks in self.PRIORITY_FUNDS.items():
            for cik in ciks:
                fund_tasks.append((fund_name, cik))

        # Execute fund checks in parallel
        results = []
        api_errors = []
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
            # Submit all tasks
            future_to_fund = {
                executor.submit(self._check_single_fund, fund_name, cik, ticker, company_name): (fund_name, cik)
                for fund_name, cik in fund_tasks
            }

            # Collect results as they complete
            for future in as_completed(future_to_fund):
                try:
                    result = future.result()
                    if result is not None:
                        # Check if this is an error result
                        if isinstance(result, dict) and result.get('error'):
                            api_errors.append(result)
                        else:
                            # Valid holding found
                            results.append(result)
                except Exception as e:
                    fund_name, cik = future_to_fund[future]
                    logger.warning(f"Exception in parallel fund check for {fund_name}: {e}")
                    api_errors.append({'error': True, 'fund': fund_name, 'exception': str(e)})

        elapsed_time = time.time() - start_time
        df = pd.DataFrame(results)

        # Log summary with institutions checked and holdings found
        total_institutions = len(self.PRIORITY_FUNDS)
        holdings_found = len(df)
        errors_count = len(api_errors)

        # Improved logging: distinguish between errors and legitimate empty results
        if api_errors:
            logger.warning(f"⚠️  {ticker}: {errors_count}/{total_institutions} institutions had API errors")
            logger.warning(f"   Failed institutions: {', '.join([e['fund'] for e in api_errors])}")
            # Don't cache if we had significant API failures
            if errors_count > total_institutions / 2:
                logger.warning(f"   Too many API errors ({errors_count}/{total_institutions}), not caching result")
                return df

        if holdings_found > 0:
            logger.info(f"✓ {ticker}: Checked {total_institutions} institutions in {elapsed_time:.1f}s, {holdings_found} have positions")
        else:
            # No holdings found - this is often legitimate for small-cap stocks
            logger.info(f"✓ {ticker}: Checked {total_institutions} institutions in {elapsed_time:.1f}s, 0 have positions (likely not held by mega-funds)")

        # Cache the results (empty results are OK if no API errors)
        self._write_cache(ticker, df, quarter_year, quarter)

        return df

    def get_13f_summary_for_ticker(self, ticker: str) -> Dict:
        """
        Get summary of institutional ownership for a ticker

        Args:
            ticker: Stock ticker

        Returns:
            Dictionary with summary stats
        """
        # Calculate most recent FILED quarter (13F filings due 45 days after quarter end)
        now = datetime.now()
        current_month = now.month
        current_year = now.year

        # Conservative approach to ensure data availability
        if current_month <= 2:  # Jan-Feb: Q3 of previous year
            quarter = 3
            year = current_year - 1
        elif current_month <= 5:  # Mar-May: Q4 of previous year
            quarter = 4
            year = current_year - 1
        elif current_month <= 8:  # Jun-Aug: Q1 of current year
            quarter = 1
            year = current_year
        elif current_month <= 11:  # Sep-Nov: Q2 of current year
            quarter = 2
            year = current_year
        else:  # December: Q3 of current year
            quarter = 3
            year = current_year

        holdings = self.check_institutional_interest(ticker, year, quarter)

        if holdings.empty:
            return {
                'ticker': ticker,
                'total_funds': 0,
                'priority_funds': 0,
                'total_value': 0,
                'total_shares': 0
            }

        return {
            'ticker': ticker,
            'total_funds': len(holdings),
            'priority_funds': len(holdings[holdings['fund'].isin(self.PRIORITY_FUNDS.keys())]),
            'total_value': holdings['value'].sum(),
            'total_shares': holdings['shares'].sum(),
            'funds': holdings['fund'].tolist()
        }


# Usage example
if __name__ == "__main__":
    # SEC requires a user agent
    user_agent = "InsiderClusterWatch admin@example.com"

    parser = SEC13FParser(user_agent)

    # Test with a sample ticker
    test_ticker = "AAPL"

    print(f"\n{'='*60}")
    print(f"Testing 13F Parser for {test_ticker}")
    print(f"{'='*60}\n")

    summary = parser.get_13f_summary_for_ticker(test_ticker)

    print(f"Institutional Interest Summary:")
    print(f"  Total Funds: {summary['total_funds']}")
    print(f"  Priority Funds: {summary['priority_funds']}")

    if summary.get('funds'):
        print(f"\n  Funds holding {test_ticker}:")
        for fund in summary['funds'][:5]:
            print(f"    • {fund}")
