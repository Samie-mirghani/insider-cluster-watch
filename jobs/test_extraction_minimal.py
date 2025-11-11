#!/usr/bin/env python3
"""
Test Capitol Trades parser with minimal HTML sample
Tests the extraction methods directly
"""

import logging
from bs4 import BeautifulSoup
from capitol_trades_scraper import CapitolTradesScraper

# Enable DEBUG logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s:%(name)s:%(message)s'
)

print("="*60)
print("Testing Capitol Trades Extraction Methods")
print("="*60)

# Minimal HTML sample matching Capitol Trades structure
html_sample = """
<table class="q-table">
<tbody>
<tr>
  <td>
    <div class="pl-1 pr-4">
      <div class="q-cell cell--politician has-avatar">
        <h2 class="politician-name overflow-hidden">
          <a class="text-txt-interactive" href="/politicians/J000309">Jonathan Jackson</a>
        </h2>
      </div>
    </div>
  </td>
  <td>
    <div class="q-cell">
      <h3 class="q-fieldset issuer-name">
        <a href="/issuers/433283">McKesson Corp</a>
      </h3>
      <span class="q-field issuer-ticker">MCK:US</span>
    </div>
  </td>
  <td>
    <div class="tx-type-tooltip-wrapper">
      <span class="q-field tx-type tx-type--sell has-asterisk">sell</span>
    </div>
  </td>
  <td>
    <div class="text-center">
      <div class="text-size-3 font-medium">09:05</div>
      <div class="text-size-2 text-txt-dimmer">Today</div>
    </div>
  </td>
  <td>11/08/2025</td>
  <td>$1,001 - $15,000</td>
</tr>
<tr>
  <td>
    <div class="pl-1 pr-4">
      <div class="q-cell cell--politician has-avatar">
        <h2 class="politician-name overflow-hidden">
          <a class="text-txt-interactive" href="/politicians/P000197">Nancy Pelosi</a>
        </h2>
      </div>
    </div>
  </td>
  <td>
    <div class="q-cell">
      <h3 class="q-fieldset issuer-name">
        <a href="/issuers/123456">Apple Inc</a>
      </h3>
      <span class="q-field issuer-ticker">AAPL:US</span>
    </div>
  </td>
  <td>
    <div class="tx-type-tooltip-wrapper">
      <span class="q-field tx-type tx-type--buy has-asterisk">buy</span>
    </div>
  </td>
  <td>
    <div class="text-center">
      <div class="text-size-3 font-medium">14:30</div>
      <div class="text-size-2 text-txt-dimmer">Yesterday</div>
    </div>
  </td>
  <td>11/09/2025</td>
  <td>$15,001 - $50,000</td>
</tr>
</tbody>
</table>
"""

# Parse with BeautifulSoup
soup = BeautifulSoup(html_sample, 'html.parser')

# Create scraper instance (without Selenium)
scraper = CapitolTradesScraper(use_selenium=False)

# Parse the trades
print("\nParsing sample HTML...")
trades = scraper._parse_trades_page(soup)

print("\n" + "="*60)
print("RESULTS")
print("="*60)
print(f"Total trades parsed: {len(trades)}")

if trades:
    print("\nTrades found:")
    for i, trade in enumerate(trades, 1):
        print(f"\n{i}. {trade['politician']}")
        print(f"   Ticker: {trade['ticker']}")
        print(f"   Type: {trade['transaction_type']}")
        print(f"   Date: {trade['trade_date']}")
        print(f"   Amount: {trade['amount_range']}")

    print("\n✓ Extraction methods working correctly!")
else:
    print("\n⚠️  No trades parsed!")
    print("\nDebugging info:")

    # Test individual extraction methods
    table = soup.find('table', class_='q-table')
    if table:
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
            print(f"Found {len(rows)} rows")

            if rows:
                cells = rows[0].find_all('td')
                print(f"First row has {len(cells)} cells")

                print("\nTesting extraction methods on first row:")
                print(f"  Politician: {scraper._extract_politician_name(cells[0])}")
                print(f"  Ticker: {scraper._extract_ticker(cells[1])}")
                print(f"  Transaction: {scraper._extract_transaction_type(cells[2])}")

print("\n" + "="*60)
