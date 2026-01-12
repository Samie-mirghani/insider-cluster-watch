#!/usr/bin/env python3
"""
Add current price data to signals_history.csv using FMP API
"""

import sys
import os
import pandas as pd
from datetime import datetime

# Add jobs directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

from fmp_api import get_enhanced_client

def add_prices_to_signals():
    """Add current prices to signals_history.csv"""

    signals_file = 'data/signals_history.csv'

    print(f"{'='*60}")
    print(f"📊 Adding Price Data to Signals History")
    print(f"{'='*60}\n")

    # Read signals
    print(f"Reading {signals_file}...")
    df = pd.read_csv(signals_file)
    print(f"✅ Loaded {len(df)} signals\n")

    # Get unique tickers
    tickers = df['ticker'].unique().tolist()
    print(f"Found {len(tickers)} unique tickers")

    # Initialize FMP client
    client = get_enhanced_client()

    # Fetch prices in batch
    print(f"Fetching prices from FMP API...")
    profiles = client.fetch_profiles_batch(tickers)
    print(f"✅ Fetched {len(profiles)} profiles\n")

    # Create price mapping
    price_map = {}
    for ticker, profile in profiles.items():
        if profile and 'price' in profile:
            price_map[ticker] = profile['price']

    print(f"Prices available for {len(price_map)} tickers")

    # Add currentPrice column
    df['currentPrice'] = df['ticker'].map(price_map)

    # Report statistics
    total_signals = len(df)
    signals_with_price = df['currentPrice'].notna().sum()
    signals_without_price = total_signals - signals_with_price

    print(f"\nPrice Data Statistics:")
    print(f"  Total signals: {total_signals}")
    print(f"  With price: {signals_with_price} ({signals_with_price/total_signals*100:.1f}%)")
    print(f"  Without price: {signals_without_price} ({signals_without_price/total_signals*100:.1f}%)")

    # Save backup
    backup_file = f"{signals_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\nCreating backup: {backup_file}")
    df_original = pd.read_csv(signals_file)
    df_original.to_csv(backup_file, index=False)

    # Save updated CSV
    print(f"Saving updated signals to {signals_file}...")
    df.to_csv(signals_file, index=False)
    print(f"✅ Saved successfully!\n")

    # Show sample
    print("Sample of updated data (last 5 signals):")
    print(df[['date', 'ticker', 'signal_score', 'currentPrice']].tail().to_string(index=False))

    # Save analytics
    client.save_analytics()
    summary = client.get_analytics_summary()
    print(f"\nFMP API Usage:")
    print(f"  Cache hit rate: {summary['cache_hit_rate_pct']}%")
    print(f"  API calls today: {summary['today_api_calls']}")
    print(f"  Cost saved: ${summary['estimated_cost_saved']}")

    print(f"\n{'='*60}")
    print(f"✅ Price data successfully added to signals_history.csv")
    print(f"{'='*60}")

if __name__ == "__main__":
    try:
        add_prices_to_signals()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
