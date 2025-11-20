"""
capitol_trades_scraper.py
Robust web scraper for Capitol Trades (FREE politician trading data)
Handles errors, retries, and rate limiting
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from typing import List, Dict, Optional
import json
from urllib.parse import urlencode

# Setup logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not installed. Capitol Trades scraping will be limited.")


class CapitolTradesScraper:
    """
    Scrape politician trading data from Capitol Trades
    FREE alternative to paid APIs
    """

    BASE_URL = "https://www.capitoltrades.com"

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

    def __init__(self, max_retries: int = 3, delay: float = 2.0, use_selenium: bool = True):
        """
        Initialize scraper

        Args:
            max_retries: Maximum retry attempts
            delay: Delay between requests (seconds)
            use_selenium: Use Selenium for JavaScript rendering (required for Capitol Trades)
        """
        self.max_retries = max_retries
        self.delay = delay
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE
        self.driver = None

        # Always create session as fallback
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

        if self.use_selenium:
            logger.info("Using Selenium for JavaScript rendering")
            self._setup_selenium()
        else:
            logger.info("Using basic HTTP requests (may not work with Capitol Trades)")

    def _setup_selenium(self):
        """Setup Selenium WebDriver with Chrome headless"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("✓ Selenium WebDriver initialized")
        except WebDriverException as e:
            logger.error(f"Failed to initialize Selenium: {e}")
            logger.error("Falling back to basic HTTP requests")
            self.use_selenium = False
            self.driver = None

    def __del__(self):
        """Cleanup Selenium driver on deletion"""
        if self.driver:
            try:
                self.driver.quit()
                logger.debug("Selenium driver closed")
            except:
                pass

    def _make_request(self, url: str) -> Optional[BeautifulSoup]:
        """
        Make HTTP request with retries and error handling

        Args:
            url: URL to request

        Returns:
            BeautifulSoup object or None on failure
        """
        if self.use_selenium and self.driver:
            return self._make_selenium_request(url)
        else:
            return self._make_http_request(url)

    def _make_selenium_request(self, url: str) -> Optional[BeautifulSoup]:
        """Make request using Selenium to handle JavaScript"""
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Requesting with Selenium: {url} (attempt {attempt + 1}/{self.max_retries})")

                self.driver.get(url)

                # Wait for the table to load (Capitol Trades uses JavaScript)
                try:
                    # Wait for table element to be present
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "table.q-table"))
                    )
                    logger.info("✓ Table loaded successfully")
                except TimeoutException:
                    # Try alternative selector
                    try:
                        WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.TAG_NAME, "table"))
                        )
                        logger.info("✓ Table loaded (alternative selector)")
                    except TimeoutException:
                        logger.warning("Timeout waiting for table to load")
                        if attempt < self.max_retries - 1:
                            time.sleep((attempt + 1) * 3)
                            continue
                        return None

                # Get page source and parse with BeautifulSoup
                html = self.driver.page_source
                soup = BeautifulSoup(html, 'html.parser')

                # Rate limiting
                time.sleep(self.delay)

                return soup

            except WebDriverException as e:
                logger.warning(f"Selenium request failed (attempt {attempt + 1}): {e}")

                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    logger.info(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All Selenium retry attempts failed for {url}")
                    return None

        return None

    def _make_http_request(self, url: str) -> Optional[BeautifulSoup]:
        """Make basic HTTP request (fallback method)"""
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Requesting: {url} (attempt {attempt + 1}/{self.max_retries})")

                response = self.session.get(url, timeout=30)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, 'html.parser')

                # Rate limiting
                time.sleep(self.delay)

                return soup

            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")

                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    logger.info(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All retry attempts failed for {url}")
                    return None

        return None

    def save_debug_html(self, html_content: str, page_num: int = 1):
        """Save HTML for debugging purposes"""
        import os
        os.makedirs('data/debug', exist_ok=True)
        filepath = f'data/debug/capitol_trades_page{page_num}.html'
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"💾 Saved debug HTML to {filepath}")

    def scrape_recent_trades(self, days_back: int = 30, max_pages: int = 5, debug: bool = False) -> pd.DataFrame:
        """
        Scrape recent politician trades

        Args:
            days_back: Days to look back
            max_pages: Maximum pages to scrape

        Returns:
            DataFrame with trades
        """
        logger.info(f"Scraping politician trades from last {days_back} days")
        logger.info(f"Max pages: {max_pages}")

        all_trades = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        for page in range(1, max_pages + 1):
            url = f"{self.BASE_URL}/trades?page={page}"

            soup = self._make_request(url)
            if not soup:
                break

            # Save HTML for debugging if requested
            if debug:
                self.save_debug_html(str(soup), page)

            # Find trade table
            trades = self._parse_trades_page(soup, debug=debug)

            if not trades:
                logger.info(f"No trades found on page {page}, stopping")
                break

            # Filter by date
            recent_trades = [
                t for t in trades
                if t.get('trade_date') and t['trade_date'] >= cutoff_date
            ]

            all_trades.extend(recent_trades)
            logger.info(f"Page {page}: Found {len(recent_trades)} recent trades")

            # Stop if we've gone past our date range
            if len(recent_trades) < len(trades):
                logger.info("Reached trades outside date range, stopping")
                break

        if not all_trades:
            logger.warning("No trades scraped")
            return pd.DataFrame()

        df = pd.DataFrame(all_trades)

        # Clean and enrich data
        df = self._clean_trades_data(df)

        logger.info(f"✓ Scraped {len(df)} trades total")
        return df

    def _parse_trades_page(self, soup: BeautifulSoup, debug: bool = False) -> List[Dict]:
        """
        Parse trades from a Capitol Trades page

        Args:
            soup: BeautifulSoup object
            debug: Enable verbose debug logging

        Returns:
            List of trade dictionaries
        """
        trades = []

        # Find the trades table - structure may vary
        # This is a robust approach that tries multiple methods

        # Method 1: Look for table with class
        table = soup.find('table', class_='q-table')

        if not table:
            # Method 2: Look for any table with trade data
            table = soup.find('table')

        if not table:
            logger.warning("Could not find trades table on page")
            return trades

        # Parse table rows - try both tbody and direct tr
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
            logger.debug(f"Found {len(rows)} rows in tbody")
        else:
            rows = table.find_all('tr')[1:]  # Skip header if no tbody
            logger.debug(f"Found {len(rows)} rows in table (no tbody)")

        if not rows:
            logger.warning("No table rows found")
            return trades

        logger.info(f"Parsing {len(rows)} table rows...")

        for idx, row in enumerate(rows):
            try:
                cells = row.find_all('td')

                if len(cells) < 4:
                    logger.debug(f"Row {idx}: Skipping - only {len(cells)} cells")
                    continue

                # Log first few rows for debugging
                if debug and idx < 3:
                    logger.info(f"Row {idx}: {len(cells)} cells")
                    for i, cell in enumerate(cells):
                        logger.info(f"  Cell {i}: {self._extract_text(cell)[:50]}")

                # Capitol Trades structure (based on actual HTML):
                # Cell 0: Politician name (h2.politician-name > a)
                # Cell 1: Ticker/Asset (span.issuer-ticker format "MCK:US")
                # Cell 2: Transaction type (span.tx-type.tx-type--buy or tx-type--sell)
                # Cell 3: Trade date (nested divs)
                # Cell 4: Disclosure date (nested divs)
                # Cell 5: Amount range

                # Extract politician name using Capitol Trades-specific method
                politician = self._extract_politician_name(cells[0]) if len(cells) > 0 else ""

                # Try to extract ticker - it might be in different cells
                ticker = None
                for i in range(min(4, len(cells))):
                    ticker = self._extract_ticker(cells[i])
                    if ticker:
                        break

                # Extract transaction type using Capitol Trades-specific method
                transaction_type = ""
                for i in range(len(cells)):  # Check all cells
                    transaction_type = self._extract_transaction_type(cells[i])
                    if transaction_type:
                        break

                # Fallback: Search entire row HTML for transaction indicators
                if not transaction_type:
                    row_html = str(row).lower()
                    if 'tx-type--buy' in row_html or 'purchase' in row_html:
                        transaction_type = 'buy'
                    elif 'tx-type--sell' in row_html or 'sale' in row_html:
                        transaction_type = 'sell'
                    elif 'tx-type--exchange' in row_html:
                        transaction_type = 'exchange'

                trade = {
                    'politician': politician,
                    'ticker': ticker or "",
                    'asset_name': self._extract_text(cells[1]) if len(cells) > 1 else "",
                    'transaction_type': transaction_type,
                    'trade_date': self._parse_date(self._extract_text(cells[3])) if len(cells) > 3 else None,
                    'disclosure_date': self._parse_date(self._extract_text(cells[4])) if len(cells) > 4 else None,
                    'amount_range': self._extract_text(cells[5]) if len(cells) > 5 else "",
                    'chamber': self._detect_chamber(cells[0]) if len(cells) > 0 else "",
                    'party': self._detect_party(cells[0]) if len(cells) > 0 else ""
                }

                # Only add if we have minimum required fields and it's a purchase
                if trade['politician'] and trade['ticker']:
                    if 'purchase' in trade['transaction_type'].lower() or 'buy' in trade['transaction_type'].lower():
                        trades.append(trade)
                        if debug:
                            logger.info(f"✓ Added trade: {trade['politician']} - {trade['ticker']}")
                    elif debug:
                        logger.info(f"✗ Skipped (not purchase/buy): {trade['politician']} - {trade['ticker']} ({trade['transaction_type']})")
                elif debug:
                    logger.info(f"✗ Skipped (missing fields): politician={trade['politician']}, ticker={trade['ticker']}")

            except Exception as e:
                logger.debug(f"Error parsing row {idx}: {e}")
                continue

        logger.info(f"Successfully parsed {len(trades)} trades from {len(rows)} rows")
        return trades

    def _extract_text(self, cell) -> str:
        """Extract clean text from cell"""
        if not cell:
            return ""
        return cell.get_text(strip=True)

    def _extract_politician_name(self, cell) -> str:
        """Extract politician name from Capitol Trades cell structure"""
        if not cell:
            return ""

        # Capitol Trades uses: h2.politician-name > a
        politician_elem = cell.find('h2', class_='politician-name')
        if politician_elem:
            link = politician_elem.find('a')
            if link:
                return link.get_text(strip=True)

        # Fallback to generic text extraction
        return self._extract_text(cell)

    def _extract_ticker(self, cell) -> str:
        """Extract ticker symbol from Capitol Trades cell structure"""
        if not cell:
            return ""

        # Capitol Trades uses: span.issuer-ticker with format "MCK:US"
        ticker_elem = cell.find('span', class_='issuer-ticker')
        if ticker_elem:
            ticker_text = ticker_elem.get_text(strip=True)
            # Parse format like "MCK:US" to get just "MCK"
            if ':' in ticker_text:
                return ticker_text.split(':')[0].strip()
            return ticker_text

        # Fallback: Look for ticker in parentheses or brackets
        import re
        text = self._extract_text(cell)
        match = re.search(r'[\(\[]([A-Z]{1,5})[\)\]]', text)
        if match:
            return match.group(1)

        # Fallback: Sometimes ticker is in a span or link
        ticker_elem = cell.find('span', class_='ticker') or cell.find('a', class_='ticker')
        if ticker_elem:
            return ticker_elem.get_text(strip=True)

        return ""

    def _extract_transaction_type(self, cell) -> str:
        """Extract transaction type from Capitol Trades cell structure"""
        if not cell:
            return ""

        # Method 1: Capitol Trades uses: span.tx-type.tx-type--buy or span.tx-type.tx-type--sell
        import re
        tx_elem = cell.find('span', class_=re.compile(r'tx-type'))
        if tx_elem:
            return tx_elem.get_text(strip=True)

        # Method 2: Look for div with tx-type class
        tx_elem = cell.find('div', class_=re.compile(r'tx-type'))
        if tx_elem:
            return tx_elem.get_text(strip=True)

        # Method 3: Search for common transaction keywords in text
        text = self._extract_text(cell).lower()
        if text in ['buy', 'purchase', 'sell', 'sale', 'exchange']:
            return text

        # Don't fallback beyond this - only return if we found transaction indicators
        return ""

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime"""
        if not date_str:
            return None

        date_str = date_str.strip().lower()

        # Handle relative dates (Capitol Trades format)
        if 'today' in date_str:
            return datetime.now()
        elif 'yesterday' in date_str:
            return datetime.now() - timedelta(days=1)

        # Try multiple date formats
        formats = [
            '%Y-%m-%d',
            '%m/%d/%Y',
            '%m/%d/%y',
            '%B %d, %Y',
            '%b %d, %Y',
            '%m-%d-%Y',
            '%m-%d-%y'
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        logger.debug(f"Could not parse date: {date_str}")
        return None

    def _detect_chamber(self, cell) -> str:
        """Detect if Senate or House"""
        text = self._extract_text(cell).lower()

        if 'senator' in text or 'sen.' in text:
            return 'Senate'
        elif 'representative' in text or 'rep.' in text:
            return 'House'

        return 'Unknown'

    def _detect_party(self, cell) -> str:
        """Detect political party"""
        text = self._extract_text(cell).lower()

        if '(d)' in text or 'democrat' in text:
            return 'Democrat'
        elif '(r)' in text or 'republican' in text:
            return 'Republican'
        elif '(i)' in text or 'independent' in text:
            return 'Independent'

        return 'Unknown'

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

        # Apply politician weights
        df['politician_weight'] = df['politician'].apply(
            lambda p: self.POLITICIAN_WEIGHTS.get(p, self.POLITICIAN_WEIGHTS['Default'])
        )

        # Calculate weighted amount
        df['weighted_amount'] = df['amount_mid'] * df['politician_weight']

        # Add disclosure lag
        df['disclosure_lag_days'] = (
            df['disclosure_date'] - df['trade_date']
        ).dt.days

        # Remove invalid tickers
        df = df[df['ticker'].str.len() > 0]
        df = df[df['ticker'].str.len() <= 5]  # Valid tickers are 1-5 chars

        return df

    def _parse_amount_min(self, amount_str: str) -> float:
        """Parse minimum amount from range string"""
        if not amount_str or amount_str == '':
            return 1000  # Default minimum

        # Extract first number
        import re
        numbers = re.findall(r'\$?([\d,]+)', str(amount_str))

        if numbers:
            return float(numbers[0].replace(',', ''))

        return 1000

    def _parse_amount_max(self, amount_str: str) -> float:
        """Parse maximum amount from range string"""
        if not amount_str or amount_str == '':
            return 15000  # Default maximum

        # Extract all numbers
        import re
        numbers = re.findall(r'\$?([\d,]+)', str(amount_str))

        if len(numbers) >= 2:
            return float(numbers[1].replace(',', ''))
        elif len(numbers) == 1:
            return float(numbers[0].replace(',', ''))

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
            'politician': ['count', lambda x: list(x)],
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
        # Scrape recent trades
        all_trades = self.scrape_recent_trades(days_back, max_pages=10)

        if all_trades.empty:
            return pd.DataFrame()

        # Filter to ticker
        ticker_trades = all_trades[
            all_trades['ticker'].str.upper() == ticker.upper()
        ]

        return ticker_trades.sort_values('trade_date', ascending=False)


# Usage example and test
if __name__ == "__main__":
    scraper = CapitolTradesScraper()

    # Test scraping
    trades = scraper.scrape_recent_trades(days_back=30, max_pages=3)

    if not trades.empty:
        print(f"\n{'='*60}")
        print(f"Scraped {len(trades)} politician trades")
        print(f"{'='*60}\n")
        print(trades[['politician', 'ticker', 'trade_date', 'amount_mid']].head(10))

        # Detect clusters
        clusters = scraper.detect_politician_clusters(trades)

        if not clusters.empty:
            print(f"\n{'='*60}")
            print(f"Found {len(clusters)} politician clusters")
            print(f"{'='*60}\n")
            print(clusters[['ticker', 'num_politicians', 'conviction_score']].head())
