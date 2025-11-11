#!/usr/bin/env python3
"""
Debug script to understand Capitol Trades cell structure
Shows HTML tags and classes for each cell
"""

import logging
from bs4 import BeautifulSoup
from capitol_trades_scraper import CapitolTradesScraper

logging.basicConfig(level=logging.WARNING)  # Suppress INFO logs

print("Fetching Capitol Trades page...")
scraper = CapitolTradesScraper(use_selenium=True)

# Make a request
soup = scraper._make_request("https://www.capitoltrades.com/trades?page=1")

if soup:
    table = soup.find('table', class_='q-table') or soup.find('table')

    if table:
        tbody = table.find('tbody')
        rows = tbody.find_all('tr') if tbody else table.find_all('tr')[1:]

        print(f"\nFound {len(rows)} rows\n")
        print("="*80)
        print("ANALYZING FIRST ROW STRUCTURE")
        print("="*80)

        if rows:
            first_row = rows[0]
            cells = first_row.find_all('td')

            print(f"\nTotal cells: {len(cells)}\n")

            for i, cell in enumerate(cells):
                print(f"\n{'─'*80}")
                print(f"CELL {i}:")
                print(f"{'─'*80}")
                print(f"Text content: {cell.get_text(strip=True)[:100]}")
                print(f"\nHTML structure:")

                # Show key elements
                spans = cell.find_all('span')
                divs = cell.find_all('div')
                links = cell.find_all('a')

                if spans:
                    print(f"  Spans ({len(spans)}):")
                    for span in spans[:3]:  # Show first 3
                        classes = span.get('class', [])
                        text = span.get_text(strip=True)[:50]
                        print(f"    - classes={classes}, text='{text}'")

                if divs:
                    print(f"  Divs ({len(divs)}):")
                    for div in divs[:3]:  # Show first 3
                        classes = div.get('class', [])
                        text = div.get_text(strip=True)[:50]
                        print(f"    - classes={classes}, text='{text}'")

                if links:
                    print(f"  Links ({len(links)}):")
                    for link in links[:2]:
                        href = link.get('href', '')
                        text = link.get_text(strip=True)[:50]
                        print(f"    - href='{href}', text='{text}'")

                # Look for transaction type indicators
                tx_span = cell.find('span', class_=lambda x: x and 'tx-type' in str(x))
                tx_div = cell.find('div', class_=lambda x: x and 'tx-type' in str(x))

                if tx_span or tx_div:
                    print(f"\n  *** TRANSACTION TYPE FOUND IN THIS CELL ***")
                    if tx_span:
                        print(f"      span.tx-type: '{tx_span.get_text(strip=True)}'")
                    if tx_div:
                        print(f"      div.tx-type: '{tx_div.get_text(strip=True)}'")

        print(f"\n{'='*80}\n")
    else:
        print("No table found!")
else:
    print("Failed to fetch page")
