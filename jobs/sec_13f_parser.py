"""
sec_13f_parser.py
Fetch 13F institutional holdings via Financial Modeling Prep API
Replaces broken SEC EDGAR XML parser with working API
"""

import requests
import os
from datetime import datetime
from typing import List, Dict
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class InstitutionalHoldingsAPI:
    """Fetch 13F institutional holdings via FMP API."""

    def __init__(self):
        self.api_key = os.getenv('FMP_API_KEY', 'T3OOAKzBEr80o1fKyYC0BQWNS1pUeR1r')
        self.base_url = "https://financialmodelingprep.com/stable/institutional-ownership/extract-analytics/holder"
        self.calls_file = 'data/fmp_api_calls.json'

        # Ensure data directory exists
        Path('data').mkdir(parents=True, exist_ok=True)

        # Target major institutions to check for
        self.target_institutions = [
            'VANGUARD',
            'BLACKROCK',
            'STATE STREET',
            'FIDELITY',
            'CAPITAL RESEARCH',
            'JPMORGAN',
            'INVESCO',
            'GEODE CAPITAL',
            'NORTHERN TRUST',
            'BANK OF AMERICA',
            'MORGAN STANLEY',
            'WELLS FARGO',
            'DIMENSIONAL FUND',
            'CHARLES SCHWAB',
            'T. ROWE PRICE'
        ]

    def _get_current_quarter(self):
        """Determine current year and quarter."""
        now = datetime.now()
        quarter = (now.month - 1) // 3 + 1
        year = now.year

        # 13F filings have 45-day lag, so use previous quarter
        quarter -= 1
        if quarter < 1:
            quarter = 4
            year -= 1

        return year, quarter

    def _check_rate_limit(self):
        """Ensure we don't exceed 250 calls/day."""
        if not os.path.exists(self.calls_file):
            data = {'date': datetime.now().date().isoformat(), 'calls': 0}
        else:
            try:
                with open(self.calls_file) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Rate limit file corrupted, resetting: {e}")
                data = {'date': datetime.now().date().isoformat(), 'calls': 0}

        today = datetime.now().date().isoformat()

        # Reset if new day
        if data['date'] != today:
            data = {'date': today, 'calls': 0}

        # Check limit
        if data['calls'] >= 250:
            logger.warning("⚠️ FMP API rate limit reached (250/day)")
            return False

        # Increment
        data['calls'] += 1
        try:
            with open(self.calls_file, 'w') as f:
                json.dump(data, f)
        except IOError as e:
            logger.warning(f"Failed to update rate limit file: {e}")

        logger.debug(f"FMP API calls today: {data['calls']}/250")
        return True

    def get_institutional_holders(self, ticker: str) -> List[Dict]:
        """
        Get institutional holders for a ticker.

        Args:
            ticker: Stock symbol

        Returns:
            List of institutional holder dicts
        """
        # Check rate limit
        if not self._check_rate_limit():
            logger.warning(f"Rate limit reached, skipping {ticker}")
            return []

        try:
            year, quarter = self._get_current_quarter()

            logger.debug(f"Fetching 13F data for {ticker} ({year} Q{quarter})")

            # Call API
            params = {
                'symbol': ticker,
                'year': str(year),
                'quarter': str(quarter),
                'page': 0,
                'limit': 100,  # Get top 100 institutions
                'apikey': self.api_key
            }

            response = requests.get(
                self.base_url,
                params=params,
                timeout=30
            )

            response.raise_for_status()
            holders = response.json()

            # Ensure we got a list, not an error dict
            if not isinstance(holders, list):
                logger.warning(f"Unexpected response format for {ticker}: {type(holders)}")
                return []

            if not holders:
                logger.debug(f"No institutional holders found for {ticker}")
                return []

            logger.debug(f"✓ {ticker}: Found {len(holders)} institutional holders")
            return holders

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for {ticker}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error processing {ticker}: {e}")
            return []

    def check_institutional_interest(self, ticker: str) -> Dict:
        """
        Check if target institutions hold this stock.

        Args:
            ticker: Stock symbol

        Returns:
            Dict with institutional overlap data
        """
        holders = self.get_institutional_holders(ticker)

        if not holders:
            return {
                'has_institutional_interest': False,
                'institutions': [],
                'total_institutions': 0,
                'target_matches': 0
            }

        # Find overlaps with target institutions
        overlaps = []
        for holder in holders:
            investor_name = holder.get('investorName', '').upper()

            # Check if any target institution name matches
            for target in self.target_institutions:
                if target in investor_name:
                    overlaps.append({
                        'name': holder['investorName'],
                        'shares': holder.get('sharesNumber', 0),
                        'market_value': holder.get('marketValue', 0),
                        'weight': holder.get('weight', 0),
                        'date': holder.get('date', '')
                    })
                    break

        result = {
            'has_institutional_interest': len(overlaps) > 0,
            'institutions': overlaps,
            'total_institutions': len(holders),
            'target_matches': len(overlaps)
        }

        if overlaps:
            logger.info(f"✓ {ticker}: {len(overlaps)} target institutions found")
        else:
            logger.debug(f"{ticker}: No target institution matches")

        return result


# Legacy compatibility wrappers for existing code
class SEC13FParser:
    """Legacy wrapper for backward compatibility."""

    PRIORITY_FUNDS = {
        'Vanguard Group': [],
        'BlackRock': [],
        'State Street': [],
        'Fidelity': [],
        'Capital Research': [],
        'JPMorgan': [],
        'Invesco': [],
        'Geode Capital': [],
        'Northern Trust': [],
        'Bank of America': [],
        'Morgan Stanley': [],
        'Wells Fargo': [],
        'Dimensional Fund': [],
        'Charles Schwab': [],
        'T. Rowe Price': []
    }

    def __init__(self, user_agent: str = None, cache_dir: str = "data/13f_cache"):
        """Initialize with legacy interface."""
        self.api = InstitutionalHoldingsAPI()
        logger.info("SEC13FParser initialized with FMP API backend")

    def check_institutional_interest(self, ticker: str, quarter_year: int = None, quarter: int = None):
        """
        Legacy method - converts old return format to new.

        Returns:
            DataFrame-like dict for backward compatibility
        """
        result = self.api.check_institutional_interest(ticker)

        # Convert to format expected by old code
        if result['has_institutional_interest']:
            # Return as list of dicts (simulating DataFrame)
            import pandas as pd
            return pd.DataFrame([
                {
                    'fund': inst['name'],
                    'shares': inst['shares'],
                    'value': inst['market_value'],
                    'ticker': ticker,
                    'filing_date': inst['date']
                }
                for inst in result['institutions']
            ])
        else:
            import pandas as pd
            return pd.DataFrame()


def check_institutional_interest(ticker: str, year: int = None, quarter: int = None) -> Dict:
    """
    Legacy function for backward compatibility.

    Args:
        ticker: Stock symbol
        year: Ignored (API determines current quarter)
        quarter: Ignored (API determines current quarter)

    Returns:
        Dict with institutional data
    """
    api = InstitutionalHoldingsAPI()
    return api.check_institutional_interest(ticker)


# Usage example
if __name__ == "__main__":
    print("="*60)
    print("TESTING FMP API - 13F INSTITUTIONAL HOLDINGS")
    print("="*60)

    api = InstitutionalHoldingsAPI()

    # Test with major stock
    test_ticker = "AAPL"
    print(f"\nTest: {test_ticker}")
    result = api.check_institutional_interest(test_ticker)

    print(f"  Total institutions: {result['total_institutions']}")
    print(f"  Target matches: {result['target_matches']}")
    print(f"  Has interest: {result['has_institutional_interest']}")

    if result['institutions']:
        print(f"\n  Top 5 institutions:")
        for inst in result['institutions'][:5]:
            shares_m = inst['shares'] / 1_000_000
            value_b = inst['market_value'] / 1_000_000_000
            print(f"    • {inst['name']}: {shares_m:.1f}M shares (${value_b:.2f}B)")

    print("\n" + "="*60)
    print("✓ TEST COMPLETE")
    print("="*60)
