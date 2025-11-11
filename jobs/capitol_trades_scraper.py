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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

    def __init__(self, max_retries: int = 3, delay: float = 2.0):
        """
        Initialize scraper

        Args:
            max_retries: Maximum retry attempts
            delay: Delay between requests (seconds)
        """
        self.max_retries = max_retries
        self.delay = delay
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

    def _make_request(self, url: str) -> Optional[BeautifulSoup]:
        """
        Make HTTP request with retries and error handling

        Args:
            url: URL to request

        Returns:
            BeautifulSoup object or None on failure
        """
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

    def scrape_recent_trades(self, days_back: int = 30, max_pages: int = 5) -> pd.DataFrame:
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

            # Find trade table
            trades = self._parse_trades_page(soup)

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

    def _parse_trades_page(self, soup: BeautifulSoup) -> List[Dict]:
        """
        Parse trades from a Capitol Trades page

        Args:
            soup: BeautifulSoup object

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

        # Parse table rows
        rows = table.find_all('tr')[1:]  # Skip header

        for row in rows:
            try:
                cells = row.find_all('td')

                if len(cells) < 6:
                    continue

                # Extract data (adjust indices based on actual table structure)
                trade = {
                    'politician': self._extract_text(cells[0]),
                    'ticker': self._extract_ticker(cells[1]),
                    'asset_name': self._extract_text(cells[1]),
                    'transaction_type': self._extract_text(cells[2]),
                    'trade_date': self._parse_date(self._extract_text(cells[3])),
                    'disclosure_date': self._parse_date(self._extract_text(cells[4])),
                    'amount_range': self._extract_text(cells[5]),
                    'chamber': self._detect_chamber(cells[0]),
                    'party': self._detect_party(cells[0])
                }

                # Only add if it's a purchase
                if 'purchase' in trade['transaction_type'].lower():
                    trades.append(trade)

            except Exception as e:
                logger.debug(f"Error parsing row: {e}")
                continue

        return trades

    def _extract_text(self, cell) -> str:
        """Extract clean text from cell"""
        if not cell:
            return ""
        return cell.get_text(strip=True)

    def _extract_ticker(self, cell) -> str:
        """Extract ticker symbol from cell"""
        text = self._extract_text(cell)

        # Look for ticker in parentheses or brackets
        import re
        match = re.search(r'[\(\[]([A-Z]{1,5})[\)\]]', text)
        if match:
            return match.group(1)

        # Sometimes ticker is in a span or link
        ticker_elem = cell.find('span', class_='ticker') or cell.find('a', class_='ticker')
        if ticker_elem:
            return ticker_elem.get_text(strip=True)

        return ""

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime"""
        if not date_str:
            return None

        # Try multiple date formats
        formats = [
            '%Y-%m-%d',
            '%m/%d/%Y',
            '%m/%d/%y',
            '%B %d, %Y',
            '%b %d, %Y'
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
            'amount_mid': 'sum',
            'weighted_amount': 'sum',
            'asset_name': 'first',
            'chamber': lambda x: list(x),
            'party': lambda x: list(x)
        }).reset_index()

        # Flatten column names
        clusters.columns = [
            'ticker', 'num_politicians', 'politician_list',
            'first_trade', 'last_trade', 'total_amount',
            'weighted_total', 'company', 'chambers', 'parties'
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
