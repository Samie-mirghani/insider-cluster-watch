#!/usr/bin/env python3
"""
Test Capitol Trades parser directly with saved HTML
No network requests needed
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
print("Testing Capitol Trades Parser with Saved HTML")
print("="*60)

# Read the saved HTML file
html_file = 'data/debug/capitol_trades_page1.html'
print(f"\nReading HTML from: {html_file}")

with open(html_file, 'r', encoding='utf-8') as f:
    html_content = f.read()

# Parse with BeautifulSoup
soup = BeautifulSoup(html_content, 'html.parser')

# Create scraper instance (without Selenium)
scraper = CapitolTradesScraper(use_selenium=False)

# Parse the trades
trades = scraper._parse_trades_page(soup)

print("\n" + "="*60)
print("RESULTS")
print("="*60)
print(f"Total trades parsed: {len(trades)}")

if trades:
    print("\nTrades found:")
    for i, trade in enumerate(trades[:5], 1):
        print(f"\n{i}. {trade['politician']}")
        print(f"   Ticker: {trade['ticker']}")
        print(f"   Type: {trade['transaction_type']}")
        print(f"   Date: {trade['trade_date']}")
else:
    print("\n⚠️  No trades parsed!")
    print("\nThis means the extraction methods still need adjustment.")

print("\n" + "="*60)
