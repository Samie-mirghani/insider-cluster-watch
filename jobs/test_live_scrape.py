#!/usr/bin/env python3
"""Quick test to see Capitol Trades cell structure"""

import logging
from capitol_trades_scraper import CapitolTradesScraper

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

print("Testing Capitol Trades scraper to see cell structure...")
scraper = CapitolTradesScraper(use_selenium=True)
trades = scraper.scrape_recent_trades(days_back=30, max_pages=1, debug=True)

print(f"\nTotal trades extracted: {len(trades)}")
if trades:
    print("\nFirst few trades:")
    for _, trade in trades.head(3).iterrows():
        print(f"  {trade['politician']} - {trade['ticker']} - {trade['transaction_type']}")
