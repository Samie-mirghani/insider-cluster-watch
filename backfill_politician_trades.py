#!/usr/bin/env python3
"""
One-time backfill script to recover politician trading data from Oct 1, 2025 to today
Uses PoliticianTradeTracker API to fill the 2-month gap from when the Selenium scraper was broken
"""

import sys
import os
from datetime import datetime
import json

# Add jobs directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

from capitol_trades_scraper import CapitolTradesScraper


def backfill_politician_trades():
    """One-time backfill from Oct 1 to today."""

    print("\n" + "="*70)
    print("🏛️ POLITICIAN TRADE DATA BACKFILL")
    print("   Recovering missing data from Oct 1, 2025 to today")
    print("="*70 + "\n")

    # Initialize API client
    print("1️⃣ Initializing PoliticianTradeTracker API...")
    api = CapitolTradesScraper()
    print("   ✓ API client initialized\n")

    # Fetch all available trades (API returns recent trades)
    print("2️⃣ Fetching politician trades from API...")
    print("   Note: API returns recent trades, we'll filter to Oct 1+ locally\n")

    # Try to get as much data as possible (API typically returns ~90 days)
    trades_df = api.scrape_recent_trades(days_back=90)

    if trades_df.empty:
        print("   ❌ No trades returned from API")
        print("   → Check rate limit or API connectivity\n")
        return

    print(f"   ✓ API returned {len(trades_df)} total trades\n")

    # Filter to Oct 1 onwards
    print("3️⃣ Filtering to trades since October 1, 2025...")
    cutoff = datetime(2025, 10, 1)

    oct_trades = trades_df[trades_df['trade_date'] >= cutoff].copy()

    print(f"   Total from API: {len(trades_df)}")
    print(f"   Since Oct 1: {len(oct_trades)}")
    print(f"   Recovered period: {(datetime.now() - cutoff).days} days\n")

    if oct_trades.empty:
        print("   ⚠️  No trades found since Oct 1")
        print("   → API may only have more recent data\n")
        return

    # Convert to JSON-serializable format
    print("4️⃣ Converting to JSON format...")
    trades_list = oct_trades.to_dict('records')

    # Convert datetime objects to strings
    for trade in trades_list:
        if 'trade_date' in trade and isinstance(trade['trade_date'], datetime):
            trade['trade_date'] = trade['trade_date'].strftime('%Y-%m-%d')

    # Save to file
    output_file = 'data/politician_trades_backfill.json'
    os.makedirs('data', exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump({
            'backfilled_at': datetime.now().isoformat(),
            'period_start': '2025-10-01',
            'period_end': datetime.now().strftime('%Y-%m-%d'),
            'total_trades': len(trades_list),
            'trades': trades_list
        }, f, indent=2)

    print(f"   ✓ Saved to {output_file}\n")

    # Show summary statistics
    print("="*70)
    print("📊 BACKFILL SUMMARY")
    print("="*70)

    # Date range
    min_date = oct_trades['trade_date'].min()
    max_date = oct_trades['trade_date'].max()
    print(f"\n📅 Date Range:")
    print(f"   Earliest trade: {min_date.strftime('%Y-%m-%d')}")
    print(f"   Latest trade: {max_date.strftime('%Y-%m-%d')}")
    print(f"   Days covered: {(max_date - min_date).days + 1}")

    # Ticker breakdown
    print(f"\n📈 Ticker Breakdown:")
    top_tickers = oct_trades['ticker'].value_counts().head(5)
    for ticker, count in top_tickers.items():
        print(f"   {ticker}: {count} trades")

    # Politician breakdown
    print(f"\n🏛️ Politician Breakdown:")
    top_politicians = oct_trades['politician'].value_counts().head(5)
    for politician, count in top_politicians.items():
        print(f"   {politician}: {count} trades")

    # Party breakdown
    print(f"\n🎯 Party Breakdown:")
    party_counts = oct_trades['party'].value_counts()
    for party, count in party_counts.items():
        print(f"   {party}: {count} trades")

    # Show sample trades
    print(f"\n💼 Sample Trades:")
    sample_size = min(10, len(oct_trades))
    for idx, row in oct_trades.head(sample_size).iterrows():
        date_str = row['trade_date'].strftime('%Y-%m-%d')
        amount = row.get('amount_range', 'N/A')
        print(f"   • {date_str} - {row['politician']} ({row['party']})")
        print(f"     → {row['ticker']} ({amount})")

    if len(oct_trades) > sample_size:
        print(f"   ... and {len(oct_trades) - sample_size} more trades")

    print("\n" + "="*70)
    print("✅ BACKFILL COMPLETE!")
    print("="*70)
    print(f"\n💾 Data saved to: {output_file}")
    print(f"📊 Total trades recovered: {len(oct_trades)}")
    print(f"📅 Period: Oct 1, 2025 to {datetime.now().strftime('%Y-%m-%d')}")
    print("\n🎉 You've recovered {0} days of missing politician trade data!\n".format(
        (datetime.now() - cutoff).days
    ))


if __name__ == "__main__":
    try:
        backfill_politician_trades()
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
