#!/usr/bin/env python3
"""
Debug script for Capitol Trades scraper
Enables detailed logging and saves HTML for inspection
"""

import logging
from capitol_trades_scraper import CapitolTradesScraper

# Enable DEBUG logging to see detailed output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s:%(name)s:%(message)s'
)

print("="*60)
print("Capitol Trades Scraper - Debug Mode")
print("="*60)

# Initialize scraper
scraper = CapitolTradesScraper()

# Scrape with debug mode enabled (saves HTML to data/debug/)
trades = scraper.scrape_recent_trades(
    days_back=30,  # Look back 30 days
    max_pages=2,   # Just 2 pages for testing
    debug=True     # Save HTML for inspection
)

print("\n" + "="*60)
print("RESULTS")
print("="*60)
print(f"Total trades found: {len(trades)}")

if not trades.empty:
    print("\nSample trades:")
    print(trades[['politician', 'ticker', 'transaction_type', 'trade_date']].head(10))
    print(f"\nUnique tickers: {trades['ticker'].nunique()}")
    print(f"Unique politicians: {trades['politician'].nunique()}")
else:
    print("\n⚠️  No trades found!")
    print("\nPossible reasons:")
    print("  1. No politician trades in last 30 days (could be genuine)")
    print("  2. HTML structure doesn't match parser expectations")
    print("  3. Capitol Trades changed their website")
    print("\nCheck saved HTML at: data/debug/capitol_trades_page1.html")
    print("You can open this file in a browser to see what we're scraping")

print("\n" + "="*60)
