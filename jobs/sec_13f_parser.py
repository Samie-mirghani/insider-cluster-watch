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


class SEC13FParser:
    """
    Parse 13F filings from SEC EDGAR
    Track what major institutions are buying
    """

    BASE_URL = "https://www.sec.gov"
    
    # Class-level flag to warn about missing yfinance only once
    _yfinance_warning_logged = False

    # Priority funds to track (top performers)
    PRIORITY_FUNDS = {
        'Berkshire Hathaway': ['0001067983'],
        'Bridgewater Associates': ['0001350694'],
        'Renaissance Technologies': ['0001037389'],
        'Two Sigma': ['0001040273'],
        'Citadel': ['0001423053'],
        'Point72': ['0001603466'],
        'Tiger Global': ['0001167483'],
        'Coatue Management': ['0001537986'],
        'D1 Capital': ['0001683040'],
        'Viking Global': ['0001103804'],
        'Soros Fund Management': ['0001029160'],
        'Third Point': ['0001040273'],
        'Pershing Square': ['0001336528'],
        'Bill & Melinda Gates Foundation': ['0001166559'],
        'ValueAct': ['0001105158']
    }

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

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept-Encoding': 'gzip, deflate',
            'Host': 'www.sec.gov'
        })

        # Retry settings
        self.max_retries = 3
        self.retry_delays = [2, 4, 8]  # Exponential backoff
        self.timeout = 30  # Increased from 10s

    def _get_cache_path(self, ticker: str) -> Path:
        """Get cache file path for a ticker"""
        return self.cache_dir / f"{ticker}_13f.json"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache file is valid based on configured cache duration"""
        if not cache_path.exists():
            return False

        cache_age = time.time() - cache_path.stat().st_mtime
        cache_duration_seconds = SEC_13F_CACHE_HOURS * 60 * 60
        return cache_age < cache_duration_seconds

    def _read_cache(self, ticker: str) -> Optional[pd.DataFrame]:
        """Read cached 13F results"""
        cache_path = self._get_cache_path(ticker)

        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                logger.info(f"📦 Using cached 13F data for {ticker}")
                return pd.DataFrame(data)
            except Exception as e:
                logger.debug(f"Cache read error: {e}")
                return None

        return None

    def _write_cache(self, ticker: str, df: pd.DataFrame):
        """Write 13F results to cache"""
        cache_path = self._get_cache_path(ticker)

        try:
            with open(cache_path, 'w') as f:
                json.dump(df.to_dict('records'), f)
            logger.debug(f"Cached 13F data for {ticker}")
        except Exception as e:
            logger.debug(f"Cache write error: {e}")

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
                response = self.session.get(url, params=params, timeout=self.timeout)
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

                time.sleep(0.5)  # Increased rate limiting from 0.1s to 0.5s
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
            response = self.session.get(filing_url, timeout=self.timeout)
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
            time.sleep(0.5)  # Rate limiting
            xml_response = self.session.get(xml_link, timeout=self.timeout)
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
                            # Fuzzy match: check if key parts of company name are in the 13F name
                            # Remove common suffixes/punctuation for better matching
                            target_clean = target_company_name.upper().strip()
                            name_clean = name.upper().strip()

                            # Remove trailing suffixes only (not in middle of words)
                            # Order matters - remove longer suffixes first
                            for suffix in [' CORPORATION', ' INCORPORATED', ' INC.', ' INC',
                                          ' CORP.', ' CORP', ' LTD.', ' LTD', ' LLC',
                                          ' CO.', ' CO']:
                                if target_clean.endswith(suffix):
                                    target_clean = target_clean[:-len(suffix)].strip()
                                if name_clean.endswith(suffix):
                                    name_clean = name_clean[:-len(suffix)].strip()

                            # Handle .COM domains specially (normalize "AMAZON.COM" to "AMAZON COM")
                            target_clean = target_clean.replace('.COM', ' COM')
                            name_clean = name_clean.replace('.COM', ' COM')

                            # Remove other punctuation and normalize whitespace
                            for char in [',', '.', '-', '&']:
                                target_clean = target_clean.replace(char, ' ')
                                name_clean = name_clean.replace(char, ' ')

                            # Normalize multiple spaces to single space
                            target_clean = ' '.join(target_clean.split())
                            name_clean = ' '.join(name_clean.split())

                            # Match logic: require exact match or high similarity to avoid false positives
                            matched = False
                            if target_clean == name_clean:
                                # Exact match after cleaning
                                matched = True
                            elif len(target_clean) >= 8 and target_clean in name_clean and \
                                 len(target_clean) / len(name_clean) > 0.7:
                                # Target is substantial substring with high overlap ratio
                                matched = True
                            elif len(name_clean) >= 8 and name_clean in target_clean and \
                                 len(name_clean) / len(target_clean) > 0.7:
                                # 13F name is substantial substring with high overlap ratio
                                matched = True

                            if matched:
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

    def check_institutional_interest(self, ticker: str, quarter_year: int, quarter: int) -> pd.DataFrame:
        """
        Check which priority funds hold a given ticker and extract actual position sizes

        Args:
            ticker: Stock ticker symbol
            quarter_year: Year (e.g., 2024)
            quarter: Quarter (1-4)

        Returns:
            DataFrame of funds that hold this ticker with shares and values
        """
        # Check cache first
        cached_data = self._read_cache(ticker)
        if cached_data is not None:
            return cached_data

        logger.info(f"Checking institutional interest for {ticker} ({quarter_year} Q{quarter})")

        # Get company name for ticker to match against 13F filings
        company_name = self._get_company_name(ticker)
        if not company_name:
            # Already logged in _get_company_name, just return empty
            # Cache empty result to avoid repeated failed lookups
            empty_df = pd.DataFrame()
            self._write_cache(ticker, empty_df)
            return empty_df

        results = []

        for fund_name, ciks in self.PRIORITY_FUNDS.items():
            for cik in ciks:
                try:
                    # Get latest filings
                    filings = self.get_latest_13f_filings(cik, count=2)

                    if not filings:
                        continue

                    # Check most recent filing
                    latest = filings[0]

                    # Parse holdings to find this company
                    # Use company name for matching (more reliable than ticker)
                    holdings = self.parse_13f_holdings(latest['url'], target_company_name=company_name)

                    if not holdings.empty:
                        # Found the company in this fund's holdings
                        holding = holdings.iloc[0]  # Should only be one match
                        results.append({
                            'fund': fund_name,
                            'cik': cik,
                            'filing_date': latest['date'],
                            'ticker': ticker,
                            'value': holding['value'],
                            'shares': holding['shares']
                        })
                        logger.debug(f"✓ {fund_name}: {holding['shares']:,} shares (${holding['value']:,.0f})")

                except Exception as e:
                    logger.debug(f"Error checking {fund_name}: {e}")
                    continue

        df = pd.DataFrame(results)

        # Log summary with institutions checked and holdings found
        total_institutions = len(self.PRIORITY_FUNDS)
        holdings_found = len(df)

        if not df.empty:
            logger.info(f"✓ {ticker}: Checked {total_institutions} institutions, {holdings_found} have positions")
            # Cache the results
            self._write_cache(ticker, df)
        else:
            logger.info(f"✓ {ticker}: Checked {total_institutions} institutions, {holdings_found} have positions")
            # Cache empty result too (avoid repeated failed lookups)
            self._write_cache(ticker, df)

        return df

    def get_13f_summary_for_ticker(self, ticker: str) -> Dict:
        """
        Get summary of institutional ownership for a ticker

        Args:
            ticker: Stock ticker

        Returns:
            Dictionary with summary stats
        """
        # Get current quarter
        now = datetime.now()
        quarter = (now.month - 1) // 3 + 1
        year = now.year

        # Check last quarter (13F filings lag by 45 days)
        if quarter == 1:
            quarter = 4
            year -= 1
        else:
            quarter -= 1

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
