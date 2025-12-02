#!/usr/bin/env python3
"""
backfill_60d_outcomes.py - BACKFILL 60D DATA FOR EXISTING TRADES

This script recalculates missing outcome_60d and return_60d values for
trades that were tracked before the bug fixes.

Purpose:
- Fixes trades that only have 30d/90d/180d outcomes
- Adds missing 60d data to complete the schema
- Essential after the schema bugfix to ensure data consistency

Usage:
    python backfill_60d_outcomes.py              # Backfill all missing 60d data
    python backfill_60d_outcomes.py --dry-run    # Preview what would be updated
    python backfill_60d_outcomes.py --limit 50   # Process only 50 trades (for testing)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

import argparse
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import yfinance as yf
import time

# Paths
DATA_DIR = Path('data')
TRADES_FILE = DATA_DIR / 'insider_trades_history.csv'


def check_missing_60d_data():
    """
    Check how many trades are missing 60d data.

    Returns:
        Dict with statistics
    """
    if not TRADES_FILE.exists():
        return {'total': 0, 'missing_60d': 0, 'message': 'No trades file found'}

    try:
        df = pd.read_csv(TRADES_FILE, parse_dates=['trade_date'])

        # Check for missing 60d data
        # A trade is missing 60d if outcome_60d or return_60d is null/NaN
        # but it has 30d and 90d data (meaning it's old enough)
        missing_60d = df[
            (df['outcome_60d'].isna()) &
            (df['outcome_30d'].notna()) &  # Has 30d data
            (df['outcome_90d'].notna())     # Has 90d data
        ]

        return {
            'total': len(df),
            'missing_60d': len(missing_60d),
            'percent': (len(missing_60d) / len(df) * 100) if len(df) > 0 else 0,
            'df': missing_60d
        }

    except Exception as e:
        return {'total': 0, 'missing_60d': 0, 'message': f'Error: {e}'}


def calculate_60d_outcome(ticker: str, trade_date: pd.Timestamp, entry_price: float,
                          max_retries: int = 3) -> dict:
    """
    Calculate 60-day outcome for a single trade with retry logic.

    Args:
        ticker: Stock ticker
        trade_date: Trade date
        entry_price: Entry price
        max_retries: Max retry attempts

    Returns:
        Dict with outcome_60d and return_60d, or None if failed
    """
    delay = 1.0

    for attempt in range(max_retries):
        try:
            # Calculate target date
            target_date = trade_date + timedelta(days=60)

            # Fetch historical data
            start_date = trade_date - timedelta(days=5)
            end_date = target_date + timedelta(days=10)  # Buffer

            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date)

            if hist.empty:
                return None

            # Remove timezone
            hist = hist.reset_index()
            hist['Date'] = pd.to_datetime(hist['Date']).dt.tz_localize(None)

            # Normalize trade_date
            trade_date_normalized = pd.to_datetime(trade_date)
            if trade_date_normalized.tz is not None:
                trade_date_normalized = trade_date_normalized.tz_localize(None)

            # Find price on or after 60-day mark
            target_date_normalized = trade_date_normalized + timedelta(days=60)
            future_data = hist[hist['Date'] >= target_date_normalized]

            if not future_data.empty:
                outcome_price = future_data.iloc[0]['Close']
                return_pct = ((outcome_price - entry_price) / entry_price) * 100

                return {
                    'outcome_60d': float(outcome_price),
                    'return_60d': float(return_pct)
                }
            else:
                return None

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            else:
                return None

    return None


def backfill_60d_outcomes(dry_run: bool = False, limit: int = None, rate_limit_delay: float = 0.5):
    """
    Backfill missing 60d outcomes for existing trades.

    Args:
        dry_run: If True, don't save changes (preview only)
        limit: Max number of trades to process (None = all)
        rate_limit_delay: Delay between API calls
    """
    print("\n" + "="*70)
    print("BACKFILL 60D OUTCOMES - FIXING HISTORICAL DATA")
    print("="*70)

    # Check what needs to be backfilled
    stats = check_missing_60d_data()

    if stats.get('message'):
        print(f"\n{stats['message']}")
        return

    print(f"\nDatabase Statistics:")
    print(f"  Total trades: {stats['total']:,}")
    print(f"  Missing 60d data: {stats['missing_60d']:,} ({stats['percent']:.1f}%)")

    if stats['missing_60d'] == 0:
        print("\n✅ All trades already have 60d data!")
        print("   No backfill needed.")
        return

    if dry_run:
        print(f"\n🧪 DRY RUN MODE - Changes will NOT be saved")

    # Get trades to backfill
    missing_df = stats['df']

    if limit:
        missing_df = missing_df.head(limit)
        print(f"\n⚠️  Limiting to {limit} trades (--limit flag)")

    print(f"\nProcessing {len(missing_df)} trade(s)...")
    print(f"Estimated time: {len(missing_df) * rate_limit_delay / 60:.1f} minutes")
    print()

    # Load full dataframe for updating
    df = pd.read_csv(TRADES_FILE, parse_dates=['trade_date'])

    # Process each trade
    updated_count = 0
    failed_count = 0

    for idx, row in missing_df.iterrows():
        ticker = row['ticker']
        trade_date = row['trade_date']
        entry_price = row['entry_price']
        insider = row['insider_name'][:30]

        print(f"[{updated_count + failed_count + 1}/{len(missing_df)}] {ticker} - {insider}")
        print(f"  Trade date: {str(trade_date)[:10]}, Entry: ${entry_price:.2f}")

        # Calculate 60d outcome
        outcome = calculate_60d_outcome(ticker, trade_date, entry_price)

        if outcome:
            print(f"  ✅ 60d: ${outcome['outcome_60d']:.2f} ({outcome['return_60d']:+.1f}%)")

            if not dry_run:
                # Update the dataframe
                df.loc[idx, 'outcome_60d'] = outcome['outcome_60d']
                df.loc[idx, 'return_60d'] = outcome['return_60d']
                df.loc[idx, 'last_updated'] = datetime.now().isoformat()

            updated_count += 1
        else:
            print(f"  ⚠️  Failed to fetch 60d data (too recent or no data available)")
            failed_count += 1

        # Rate limiting
        time.sleep(rate_limit_delay)

    # Save updated dataframe
    if not dry_run:
        print(f"\n💾 Saving updated data to {TRADES_FILE}...")
        df.to_csv(TRADES_FILE, index=False)
        print("   ✅ Saved successfully")
    else:
        print(f"\n🧪 DRY RUN - No changes saved")

    # Summary
    print(f"\n{'='*70}")
    print("BACKFILL COMPLETE")
    print(f"{'='*70}")
    print(f"  Successfully updated: {updated_count}")
    print(f"  Failed: {failed_count}")
    if dry_run:
        print(f"  Status: DRY RUN (no changes saved)")
    else:
        print(f"  Status: SAVED TO DISK")
    print(f"{'='*70}\n")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Backfill missing 60d outcomes for existing insider trades',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what would be updated (dry run)
  python backfill_60d_outcomes.py --dry-run

  # Backfill all missing 60d data
  python backfill_60d_outcomes.py

  # Test with first 10 trades
  python backfill_60d_outcomes.py --limit 10

  # Fast backfill (shorter rate limit)
  python backfill_60d_outcomes.py --rate-limit 0.3
        """
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview changes without saving (dry run)')
    parser.add_argument('--limit', type=int, default=None,
                       help='Maximum number of trades to process')
    parser.add_argument('--rate-limit', type=float, default=0.5,
                       help='Delay between API calls in seconds (default: 0.5)')

    args = parser.parse_args()

    # Run backfill
    backfill_60d_outcomes(
        dry_run=args.dry_run,
        limit=args.limit,
        rate_limit_delay=args.rate_limit
    )


if __name__ == '__main__':
    main()
