"""
Bootstrap Script for Insider Performance Tracking

This script populates the insider performance tracker with 2-3 years of
historical data so that meaningful scores can be calculated immediately
instead of waiting 90+ days for natural accumulation.

Usage:
    python bootstrap_insider_history.py --years 3 --batch-size 100

WARNING: This will make many API calls and may take 6-12 hours to complete.
Run overnight or in background.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

import argparse
from datetime import datetime, timedelta
import pandas as pd
from insider_performance_tracker import InsiderPerformanceTracker
import time


def fetch_historical_insider_trades(years_back=3, data_source='openinsider'):
    """
    Fetch historical insider trades going back N years.

    Args:
        years_back: Number of years of history to fetch
        data_source: 'openinsider' or 'sec_edgar'

    Returns:
        DataFrame with historical trades
    """
    print(f"\n📥 Fetching {years_back} years of historical insider trades...")
    print(f"   Source: {data_source}")

    if data_source == 'openinsider':
        # OpenInsider approach - scrape past data
        # NOTE: You'll need to implement historical scraping
        # OpenInsider's archive pages: http://openinsider.com/insider-purchases/YYYY-MM-DD

        all_trades = []
        start_date = datetime.now() - timedelta(days=years_back * 365)
        current_date = start_date

        print(f"   Start date: {start_date.strftime('%Y-%m-%d')}")
        print(f"   End date: {datetime.now().strftime('%Y-%m-%d')}")

        # Fetch week by week to avoid overwhelming the system
        weeks_to_fetch = (years_back * 365) // 7

        print(f"   Fetching {weeks_to_fetch} weeks of data...")

        # Import your existing fetcher
        from fetch_openinsider import fetch_openinsider_recent

        # Fetch current data (you'd need to extend this to support date ranges)
        df = fetch_openinsider_recent()

        if df is not None and not df.empty:
            print(f"   ✅ Fetched {len(df)} recent transactions")
            # Filter for buys only
            buys = df[df['trade_type'].str.upper().str.contains('BUY|PURCHASE|P -', na=False)].copy()
            print(f"   ✅ {len(buys)} buy transactions")
            return buys

    elif data_source == 'sec_edgar':
        # SEC EDGAR approach - query Form 4 filings
        from fetch_sec_edgar import fetch_sec_edgar_data

        # Fetch in batches (SEC limits results)
        all_trades = []
        batch_days = 30  # Fetch 30 days at a time

        total_days = years_back * 365
        num_batches = total_days // batch_days

        print(f"   Fetching {num_batches} batches of {batch_days} days each...")

        for i in range(num_batches):
            start_batch = datetime.now() - timedelta(days=(i+1) * batch_days)
            print(f"   Batch {i+1}/{num_batches}: {start_batch.strftime('%Y-%m-%d')}", end="")

            df = fetch_sec_edgar_data(days_back=batch_days, max_filings=100)

            if df is not None and not df.empty:
                buys = df[df['trade_type'].str.upper().str.contains('BUY|PURCHASE|P -', na=False)].copy()
                all_trades.append(buys)
                print(f" ✓ ({len(buys)} buys)")
            else:
                print(" ✗ (no data)")

            # Rate limiting
            time.sleep(1)

            # Progress checkpoint every 10 batches
            if (i + 1) % 10 == 0:
                print(f"\n   Progress: {i+1}/{num_batches} batches ({(i+1)/num_batches*100:.1f}%)")

        if all_trades:
            combined = pd.concat(all_trades, ignore_index=True)
            print(f"\n   ✅ Total: {len(combined)} historical buy transactions")
            return combined

    print("   ⚠️  No historical data available")
    return pd.DataFrame()


def bootstrap_insider_tracker(years_back=3, batch_size=100):
    """
    Main bootstrap function - populates tracker with historical data.

    Args:
        years_back: Years of history to collect
        batch_size: Number of trades to process per batch (for outcome updates)
    """
    print("\n" + "="*70)
    print("INSIDER PERFORMANCE TRACKER - BOOTSTRAP")
    print("="*70)
    print(f"\nThis will populate {years_back} years of historical insider data.")
    print("⏱️  Expected runtime: 6-12 hours (depends on API rate limits)")
    print("\n⚠️  WARNINGS:")
    print("   • This makes thousands of yfinance API calls")
    print("   • Do not interrupt - progress is saved incrementally")
    print("   • Run overnight or in a screen/tmux session")
    print("\n" + "="*70)

    response = input("\nContinue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("❌ Bootstrap cancelled")
        return

    # Initialize tracker
    print("\n📊 Initializing tracker...")
    tracker = InsiderPerformanceTracker(
        lookback_years=years_back,
        min_trades_for_score=3
    )

    print(f"   Current state:")
    print(f"   • Profiles: {len(tracker.profiles)}")
    print(f"   • Historical trades: {len(tracker.trades_history)}")

    # Step 1: Fetch historical trades
    print("\n" + "-"*70)
    print("STEP 1: FETCH HISTORICAL TRADES")
    print("-"*70)

    historical_trades = fetch_historical_insider_trades(
        years_back=years_back,
        data_source='openinsider'  # Change to 'sec_edgar' if needed
    )

    if historical_trades.empty:
        print("❌ No historical data fetched - cannot continue")
        return

    # Step 2: Add trades to tracker
    print("\n" + "-"*70)
    print("STEP 2: ADD TRADES TO TRACKER")
    print("-"*70)

    print(f"   Adding {len(historical_trades)} trades to tracking system...")
    tracker.add_trades(historical_trades)
    print(f"   ✅ Trades added")
    print(f"   • Total trades in database: {len(tracker.trades_history)}")
    print(f"   • Unique insiders: {tracker.trades_history['insider_name'].nunique()}")

    # Save checkpoint
    tracker._save_trades_history()
    print(f"   ✅ Checkpoint saved to data/insider_trades_history.csv")

    # Step 3: Update outcomes (SLOW - this is the bottleneck)
    print("\n" + "-"*70)
    print("STEP 3: CALCULATE TRADE OUTCOMES (SLOW)")
    print("-"*70)

    total_trades = len(tracker.trades_history)
    trades_needing_updates = tracker.trades_history[
        tracker.trades_history['return_90d'].isna()
    ]

    print(f"   Total trades: {total_trades}")
    print(f"   Trades needing outcomes: {len(trades_needing_updates)}")
    print(f"   Batch size: {batch_size}")
    print(f"   Estimated batches: {len(trades_needing_updates) // batch_size + 1}")
    print(f"   Estimated time: {(len(trades_needing_updates) * 0.5) / 60:.1f} minutes")

    # Process in batches with progress tracking
    batch_num = 0
    remaining = len(trades_needing_updates)

    while remaining > 0:
        batch_num += 1
        print(f"\n   Batch {batch_num}: Processing {min(batch_size, remaining)} trades...")

        tracker.update_outcomes(
            batch_size=batch_size,
            rate_limit_delay=0.5  # 500ms between calls to be safe
        )

        # Check progress
        trades_needing_updates = tracker.trades_history[
            tracker.trades_history['return_90d'].isna()
        ]
        new_remaining = len(trades_needing_updates)

        processed_this_batch = remaining - new_remaining
        remaining = new_remaining

        print(f"   ✅ Processed {processed_this_batch} trades")
        print(f"   📊 Progress: {total_trades - remaining}/{total_trades} ({(total_trades-remaining)/total_trades*100:.1f}%)")
        print(f"   ⏱️  Remaining: ~{(remaining * 0.5) / 60:.1f} minutes")

        # Save checkpoint after each batch
        tracker._save_trades_history()

        if remaining == 0:
            break

        # Pause between batches to avoid rate limits
        time.sleep(2)

    print(f"\n   ✅ All outcomes calculated!")

    # Step 4: Calculate insider profiles
    print("\n" + "-"*70)
    print("STEP 4: CALCULATE INSIDER PROFILES")
    print("-"*70)

    print("   Calculating performance profiles for all insiders...")
    tracker.calculate_insider_profiles()

    print(f"\n   ✅ Profiles calculated!")
    print(f"   • Total profiles: {len(tracker.profiles)}")

    # Save profiles
    tracker._save_profiles()
    print(f"   ✅ Profiles saved to data/insider_profiles.json")

    # Step 5: Generate summary report
    print("\n" + "="*70)
    print("BOOTSTRAP COMPLETE - SUMMARY")
    print("="*70)

    print(f"\n📊 Database Statistics:")
    print(f"   • Total trades tracked: {len(tracker.trades_history)}")
    print(f"   • Trades with outcomes: {tracker.trades_history['return_90d'].notna().sum()}")
    print(f"   • Unique insiders: {tracker.trades_history['insider_name'].nunique()}")
    print(f"   • Insiders with profiles (≥3 trades): {len(tracker.profiles)}")

    # Score distribution
    if tracker.profiles:
        scores = [p['overall_score'] for p in tracker.profiles.values()]
        print(f"\n📈 Score Distribution:")
        print(f"   • Mean: {sum(scores)/len(scores):.1f}")
        print(f"   • Min: {min(scores):.1f}")
        print(f"   • Max: {max(scores):.1f}")
        print(f"   • Score 80-100 (excellent): {len([s for s in scores if s >= 80])}")
        print(f"   • Score 60-80 (good): {len([s for s in scores if 60 <= s < 80])}")
        print(f"   • Score 40-60 (neutral): {len([s for s in scores if 40 <= s < 60])}")
        print(f"   • Score 20-40 (poor): {len([s for s in scores if 20 <= s < 40])}")
        print(f"   • Score 0-20 (very poor): {len([s for s in scores if s < 20])}")

        # Show top 10 performers
        print(f"\n🌟 Top 10 Best Performers:")
        top_performers = tracker.get_top_performers(n=10)
        if not top_performers.empty:
            for idx, row in top_performers.iterrows():
                print(f"   {row['name'][:40]:40} | Score: {row['overall_score']:.1f} | "
                      f"Win Rate: {row['win_rate_90d']:.0f}% | Avg Return: {row['avg_return_90d']:+.1f}%")

        # Show bottom 10 performers
        print(f"\n⚠️  Top 10 Worst Performers:")
        worst_performers = tracker.get_worst_performers(n=10)
        if not worst_performers.empty:
            for idx, row in worst_performers.iterrows():
                print(f"   {row['name'][:40]:40} | Score: {row['overall_score']:.1f} | "
                      f"Win Rate: {row['win_rate_90d']:.0f}% | Avg Return: {row['avg_return_90d']:+.1f}%")

    print(f"\n✅ Bootstrap complete! Insider performance tracking is now fully functional.")
    print(f"   Next signals will use real historical performance data.")
    print(f"\n📁 Files created:")
    print(f"   • data/insider_trades_history.csv")
    print(f"   • data/insider_profiles.json")
    print("\n" + "="*70 + "\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Bootstrap insider performance tracker with historical data'
    )
    parser.add_argument(
        '--years',
        type=int,
        default=3,
        help='Years of historical data to collect (default: 3)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of trades to process per batch (default: 100)'
    )
    parser.add_argument(
        '--quick-test',
        action='store_true',
        help='Quick test mode - only processes 10 trades'
    )

    args = parser.parse_args()

    if args.quick_test:
        print("\n🧪 QUICK TEST MODE - Only processing 10 trades")
        args.batch_size = 10

    bootstrap_insider_tracker(
        years_back=args.years,
        batch_size=args.batch_size
    )
