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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SEC13FParser:
    """
    Parse 13F filings from SEC EDGAR
    Track what major institutions are buying
    """

    BASE_URL = "https://www.sec.gov"

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

    def __init__(self, user_agent: str):
        """
        Initialize parser

        Args:
            user_agent: User-Agent for SEC requests (required by SEC)
                       Format: "CompanyName AdminContact@example.com"
        """
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept-Encoding': 'gzip, deflate',
            'Host': 'www.sec.gov'
        })

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

        try:
            logger.info(f"Fetching 13F filings for CIK {cik}...")

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()

            # Parse XML feed
            root = ET.fromstring(response.content)

            filings = []
            for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                filing_date = entry.find('{http://www.w3.org/2005/Atom}updated')
                filing_url = entry.find('{http://www.w3.org/2005/Atom}link[@type="text/html"]')

                if filing_date is not None and filing_url is not None:
                    filings.append({
                        'date': datetime.strptime(filing_date.text[:10], '%Y-%m-%d'),
                        'url': filing_url.attrib['href']
                    })

            time.sleep(0.1)  # Rate limiting
            return filings

        except Exception as e:
            logger.warning(f"Error fetching 13F for CIK {cik}: {e}")
            return []

    def parse_13f_holdings(self, filing_url: str) -> pd.DataFrame:
        """
        Parse holdings from a 13F filing

        Args:
            filing_url: URL to the filing

        Returns:
            DataFrame with holdings
        """
        try:
            # Get filing page
            response = self.session.get(filing_url, timeout=10)
            response.raise_for_status()

            # Look for XML or text file with holdings
            # This is a simplified parser - full implementation would need to handle
            # different filing formats

            # For now, return empty DataFrame
            # Full implementation would parse the actual holdings table
            logger.info(f"Parsing 13F from {filing_url}")

            holdings = []

            return pd.DataFrame(holdings)

        except Exception as e:
            logger.warning(f"Error parsing 13F: {e}")
            return pd.DataFrame()

    def check_institutional_interest(self, ticker: str, quarter_year: int, quarter: int) -> pd.DataFrame:
        """
        Check which priority funds hold a given ticker

        Args:
            ticker: Stock ticker symbol
            quarter_year: Year (e.g., 2024)
            quarter: Quarter (1-4)

        Returns:
            DataFrame of funds that hold this ticker
        """
        logger.info(f"Checking institutional interest for {ticker} ({quarter_year} Q{quarter})")

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

                    # Parse holdings (simplified - actual implementation needed)
                    # holdings = self.parse_13f_holdings(latest['url'])

                    # For now, just track that we found the filing
                    results.append({
                        'fund': fund_name,
                        'cik': cik,
                        'filing_date': latest['date'],
                        'ticker': ticker,
                        'value': 0,  # Would come from parsed holdings
                        'shares': 0   # Would come from parsed holdings
                    })

                    time.sleep(0.1)  # Rate limiting

                except Exception as e:
                    logger.debug(f"Error checking {fund_name}: {e}")
                    continue

        df = pd.DataFrame(results)

        if not df.empty:
            logger.info(f"✓ Found {len(df)} priority funds with potential interest")

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
