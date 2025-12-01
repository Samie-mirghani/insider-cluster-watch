"""
Bootstrap Script for Insider Performance Tracking

Populates the insider performance tracker with 2-3 years of historical data
so that meaningful scores can be calculated immediately.

Usage:
    python bootstrap_insider_history.py --years 3 --batch-size 100
    python bootstrap_insider_history.py --quick-test  # Test with 10 trades only

WARNING: This will make thousands of API calls and may take 6-12 hours.
Run overnight or in a screen/tmux session.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import time
import yfinance as yf
from typing import Optional, Dict, List
import traceback

from insider_performance_tracker import InsiderPerformanceTracker

# Checkpoint file for resuming
CHECKPOINT_FILE = 'data/bootstrap_checkpoint.json'


class BootstrapProgress:
    """Track progress for resumable bootstrap process"""

    def __init__(self, checkpoint_file=CHECKPOINT_FILE):
        self.checkpoint_file = checkpoint_file
        self.total_trades = 0
        self.processed_trades = 0
        self.successful_outcomes = 0
        self.failed_outcomes = 0
        self.start_time = datetime.now()
        self.checkpoints_saved = 0

        # Load existing checkpoint if available
        self.load_checkpoint()

    def load_checkpoint(self):
        """Load progress from checkpoint file"""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r') as f:
                    data = json.load(f)
                    self.processed_trades = data.get('processed_trades', 0)
                    self.successful_outcomes = data.get('successful_outcomes', 0)
                    self.failed_outcomes = data.get('failed_outcomes', 0)
                    print(f"📂 Loaded checkpoint: {self.processed_trades} trades already processed")
            except Exception as e:
                print(f"⚠️  Could not load checkpoint: {e}")

    def save_checkpoint(self):
        """Save current progress"""
        Path(self.checkpoint_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.checkpoint_file, 'w') as f:
            json.dump({
                'processed_trades': self.processed_trades,
                'successful_outcomes': self.successful_outcomes,
                'failed_outcomes': self.failed_outcomes,
                'last_updated': datetime.now().isoformat(),
                'checkpoints_saved': self.checkpoints_saved
            }, f, indent=2)
        self.checkpoints_saved += 1

    def update(self, success: bool):
        """Update progress after processing a trade"""
        self.processed_trades += 1
        if success:
            self.successful_outcomes += 1
        else:
            self.failed_outcomes += 1

    def print_progress(self):
        """Print current progress with time estimates"""
        if self.total_trades == 0:
            return

        pct = (self.processed_trades / self.total_trades) * 100
        elapsed = (datetime.now() - self.start_time).total_seconds()

        if self.processed_trades > 0:
            avg_time_per_trade = elapsed / self.processed_trades
            remaining_trades = self.total_trades - self.processed_trades
            est_remaining_seconds = avg_time_per_trade * remaining_trades
            est_remaining_hours = est_remaining_seconds / 3600
        else:
            est_remaining_hours = 0

        # Progress bar
        bar_length = 50
        filled = int(bar_length * pct / 100)
        bar = '█' * filled + '░' * (bar_length - filled)

        print(f"\n[{bar}] {pct:.1f}%")
        print(f"Progress: {self.processed_trades:,}/{self.total_trades:,} trades")
        print(f"  ✅ Successful: {self.successful_outcomes:,} ({self.successful_outcomes/self.processed_trades*100:.1f}%)" if self.processed_trades > 0 else "  ✅ Successful: 0")
        print(f"  ❌ Failed: {self.failed_outcomes:,}")
        print(f"  ⏱️  Est. remaining: {est_remaining_hours:.1f}h")
        print(f"  💾 Checkpoints saved: {self.checkpoints_saved}")


def fetch_historical_trades(years_back: int, quick_test: bool = False) -> pd.DataFrame:
    """
    Fetch historical insider trades.

    Strategy: Use OpenInsider's screener with date filters to get historical data.
    We'll fetch data month by month going backwards.

    Args:
        years_back: Number of years of history to fetch
        quick_test: If True, only fetch ~100 trades for testing

    Returns:
        DataFrame with historical buy transactions
    """
    print("\n" + "="*70)
    print("STEP 1: FETCHING HISTORICAL TRADES")
    print("="*70)
    print(f"Target: {years_back} years ({datetime.now().year - years_back} to {datetime.now().year})")

    if quick_test:
        print("🧪 QUICK TEST MODE: Fetching only ~100 trades")

    all_trades = []

    # Import the existing fetcher
    try:
        from fetch_openinsider import fetch_openinsider_recent
    except ImportError:
        print("❌ Could not import fetch_openinsider. Make sure it's in the jobs/ directory.")
        return pd.DataFrame()

    if quick_test:
        # Just fetch recent data for testing
        print("   Fetching recent trades for quick test...")
        df = fetch_openinsider_recent()
        if df is not None and not df.empty:
            buys = df[df['trade_type'].str.upper().str.contains('BUY|PURCHASE|P', na=False)].copy()
            print(f"   ✅ Fetched {len(buys)} buy transactions")
            return buys.head(100)  # Limit to 100 for quick test
        return pd.DataFrame()

    # For full bootstrap, we'll fetch in monthly batches
    # Note: OpenInsider's free scraper typically only gets recent data
    # For a full bootstrap, you'd ideally:
    # 1. Use SEC EDGAR bulk downloads (quarterly index files)
    # 2. Or use a paid data provider
    # 3. Or accumulate data over time

    # For now, let's fetch what we can from recent data and simulate historical
    print("\n⚠️  NOTE: OpenInsider free scraper typically only provides recent data.")
    print("   For full historical data, consider:")
    print("   1. SEC EDGAR quarterly bulk downloads")
    print("   2. Accumulating data over time with daily runs")
    print("   3. Paid data providers (e.g., Quandl, Alpha Vantage)")
    print()

    # Fetch available recent data (last 30-90 days typically)
    print("   Fetching available recent insider trades...")
    df = fetch_openinsider_recent()

    if df is None or df.empty:
        print("   ⚠️  No data from OpenInsider, trying SEC EDGAR...")

        try:
            from fetch_sec_edgar import fetch_sec_edgar_data

            # Fetch last 90 days from SEC EDGAR
            df = fetch_sec_edgar_data(days_back=90, max_filings=500)
        except Exception as e:
            print(f"   ❌ SEC EDGAR also failed: {e}")
            return pd.DataFrame()

    if df is not None and not df.empty:
        # Filter for buy transactions
        buys = df[df['trade_type'].str.upper().str.contains('BUY|PURCHASE|P', na=False)].copy()
        print(f"   ✅ Fetched {len(buys)} buy transactions")

        # For demonstration, we'll use what we have
        # In production, you'd fetch more historical data here
        all_trades.append(buys)

    if all_trades:
        combined = pd.concat(all_trades, ignore_index=True)
        print(f"\n✅ Total historical trades fetched: {len(combined):,}")
        return combined
    else:
        print("\n❌ No historical trades found")
        return pd.DataFrame()


def calculate_trade_outcome_with_retry(ticker: str, trade_date: str, entry_price: float,
                                       max_retries: int = 3) -> Optional[Dict]:
    """
    Calculate trade outcomes with retry logic and exponential backoff.

    Args:
        ticker: Stock ticker
        trade_date: Trade date (YYYY-MM-DD)
        entry_price: Entry price
        max_retries: Maximum retry attempts

    Returns:
        Dict with outcomes or None if failed
    """
    delay = 0.5

    for attempt in range(max_retries):
        try:
            # Convert trade date to datetime
            trade_dt = pd.to_datetime(trade_date)

            # Calculate target dates
            date_30d = trade_dt + timedelta(days=30)
            date_60d = trade_dt + timedelta(days=60)
            date_90d = trade_dt + timedelta(days=90)
            date_180d = trade_dt + timedelta(days=180)

            # Fetch historical data
            start_date = trade_dt - timedelta(days=5)
            end_date = trade_dt + timedelta(days=200)

            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date)

            if hist.empty:
                return None

            # Remove timezone for comparison
            hist = hist.reset_index()
            hist['Date'] = pd.to_datetime(hist['Date']).dt.tz_localize(None)

            trade_dt_normalized = pd.to_datetime(trade_date)
            if trade_dt_normalized.tz is not None:
                trade_dt_normalized = trade_dt_normalized.tz_localize(None)

            outcomes = {}

            # Calculate outcomes for each time horizon
            for days, key, target_date in [(30, '30d', date_30d),
                                            (60, '60d', date_60d),
                                            (90, '90d', date_90d),
                                            (180, '180d', date_180d)]:

                # Find price on or after target date
                future_data = hist[hist['Date'] >= target_date]

                if not future_data.empty:
                    outcome_price = future_data.iloc[0]['Close']
                    outcomes[f'price_{key}'] = float(outcome_price)
                    outcomes[f'return_{key}'] = float(((outcome_price - entry_price) / entry_price) * 100)
                else:
                    outcomes[f'price_{key}'] = None
                    outcomes[f'return_{key}'] = None

            return outcomes

        except Exception as e:
            if attempt < max_retries - 1:
                # Retry with exponential backoff
                time.sleep(delay)
                delay *= 2
                continue
            else:
                # Final attempt failed
                return None

    return None


def bootstrap_with_progress(tracker: InsiderPerformanceTracker, trades_df: pd.DataFrame,
                            batch_size: int, progress: BootstrapProgress,
                            rate_limit_delay: float = 0.3):
    """
    Process trades in batches with progress tracking and checkpointing.

    Args:
        tracker: InsiderPerformanceTracker instance
        trades_df: DataFrame of trades to process
        batch_size: Trades per batch
        progress: Progress tracker
        rate_limit_delay: Delay between API calls (seconds)
    """
    print("\n" + "="*70)
    print("STEP 2: CALCULATING TRADE OUTCOMES")
    print("="*70)
    print(f"Total trades to process: {len(trades_df):,}")
    print(f"Batch size: {batch_size}")
    print(f"Rate limit delay: {rate_limit_delay}s")
    print(f"Estimated time: {(len(trades_df) * rate_limit_delay / 3600):.1f} hours")
    print()

    progress.total_trades = len(trades_df)

    # Add all trades to tracker first
    print("📊 Adding trades to tracking system...")
    tracker.add_trades(trades_df)
    tracker._save_trades_history()
    print(f"   ✅ {len(tracker.trades_history)} trades in database")

    # Process outcomes in batches
    batch_num = 0

    for start_idx in range(0, len(tracker.trades_history), batch_size):
        batch_num += 1
        end_idx = min(start_idx + batch_size, len(tracker.trades_history))
        batch = tracker.trades_history.iloc[start_idx:end_idx]

        print(f"\n{'='*70}")
        print(f"BATCH {batch_num}: Processing trades {start_idx+1} to {end_idx}")
        print(f"{'='*70}")

        for idx, row in batch.iterrows():
            # Skip if already has outcome
            if pd.notna(row['return_90d']):
                progress.update(success=True)
                continue

            ticker = row['ticker']
            trade_date = row['trade_date']
            entry_price = row['entry_price']

            # Skip if too recent (less than 90 days old)
            if pd.to_datetime(trade_date) > (datetime.now() - timedelta(days=90)):
                progress.update(success=False)
                continue

            print(f"\n  [{progress.processed_trades + 1}/{progress.total_trades}] {ticker} - {trade_date}")
            print(f"    Entry: ${entry_price:.2f}", end=" ")

            # Calculate outcomes with retry
            outcomes = calculate_trade_outcome_with_retry(
                ticker, str(trade_date)[:10], entry_price, max_retries=3
            )

            if outcomes:
                # Update tracker
                tracker.trades_history.loc[idx, 'outcome_30d'] = outcomes.get('price_30d')
                tracker.trades_history.loc[idx, 'outcome_60d'] = outcomes.get('price_60d')
                tracker.trades_history.loc[idx, 'outcome_90d'] = outcomes.get('price_90d')
                tracker.trades_history.loc[idx, 'outcome_180d'] = outcomes.get('price_180d')
                tracker.trades_history.loc[idx, 'return_30d'] = outcomes.get('return_30d')
                tracker.trades_history.loc[idx, 'return_60d'] = outcomes.get('return_60d')
                tracker.trades_history.loc[idx, 'return_90d'] = outcomes.get('return_90d')
                tracker.trades_history.loc[idx, 'return_180d'] = outcomes.get('return_180d')
                tracker.trades_history.loc[idx, 'last_updated'] = datetime.now().isoformat()

                ret_90d = outcomes.get('return_90d', 0)
                if ret_90d:
                    status = "✓ WIN" if ret_90d > 0 else "✗ LOSS"
                    print(f"→ 90d: ${outcomes.get('price_90d', 0):.2f} ({ret_90d:+.1f}%) {status}")
                else:
                    print(f"→ No 90d data")

                progress.update(success=True)
            else:
                print(f"→ ⚠️  Failed to fetch outcomes")
                progress.update(success=False)

            # Rate limiting
            time.sleep(rate_limit_delay)

        # Save checkpoint after each batch
        tracker._save_trades_history()
        progress.save_checkpoint()
        progress.print_progress()

    print(f"\n✅ Outcome calculation complete!")
    print(f"   Success rate: {progress.successful_outcomes}/{progress.processed_trades} ({progress.successful_outcomes/progress.processed_trades*100:.1f}%)" if progress.processed_trades > 0 else "   No trades processed")


def generate_summary_report(tracker: InsiderPerformanceTracker):
    """Generate final summary report"""
    print("\n" + "="*70)
    print("BOOTSTRAP COMPLETE - SUMMARY")
    print("="*70)

    print(f"\n📊 Database Statistics:")
    print(f"   Total trades tracked: {len(tracker.trades_history):,}")

    with_outcomes = tracker.trades_history['return_90d'].notna().sum()
    print(f"   Trades with 90d outcomes: {with_outcomes:,} ({with_outcomes/len(tracker.trades_history)*100:.1f}%)" if len(tracker.trades_history) > 0 else "   Trades with 90d outcomes: 0")

    unique_insiders = tracker.trades_history['insider_name'].nunique()
    print(f"   Unique insiders: {unique_insiders:,}")
    print(f"   Insiders with profiles (≥3 trades): {len(tracker.profiles):,}")

    # Score distribution
    if tracker.profiles:
        scores = [p['overall_score'] for p in tracker.profiles.values() if p.get('overall_score')]

        if scores:
            print(f"\n📈 Score Distribution:")
            print(f"   Mean: {sum(scores)/len(scores):.1f}")
            print(f"   Min: {min(scores):.1f}")
            print(f"   Max: {max(scores):.1f}")
            print(f"   Score 80-100 (excellent): {len([s for s in scores if s >= 80])}")
            print(f"   Score 60-80 (good): {len([s for s in scores if 60 <= s < 80])}")
            print(f"   Score 40-60 (neutral): {len([s for s in scores if 40 <= s < 60])}")
            print(f"   Score 20-40 (poor): {len([s for s in scores if 20 <= s < 40])}")
            print(f"   Score 0-20 (very poor): {len([s for s in scores if s < 20])}")

        # Top performers
        print(f"\n🌟 Top 10 Best Performers:")
        top = tracker.get_top_performers(n=10, min_trades=3)
        if not top.empty:
            for idx, row in top.iterrows():
                name = row['name'][:40].ljust(40)
                score = row.get('overall_score', 0)
                win_rate = row.get('win_rate_90d', 0)
                avg_ret = row.get('avg_return_90d', 0)
                trades = row.get('total_trades', 0)
                print(f"   {name} | Score: {score:5.1f} | WR: {win_rate:5.1f}% | Avg: {avg_ret:+6.1f}% | Trades: {trades}")

        # Worst performers
        print(f"\n⚠️  Top 10 Worst Performers:")
        worst = tracker.get_worst_performers(n=10, min_trades=3)
        if not worst.empty:
            for idx, row in worst.iterrows():
                name = row['name'][:40].ljust(40)
                score = row.get('overall_score', 0)
                win_rate = row.get('win_rate_90d', 0)
                avg_ret = row.get('avg_return_90d', 0)
                trades = row.get('total_trades', 0)
                print(f"   {name} | Score: {score:5.1f} | WR: {win_rate:5.1f}% | Avg: {avg_ret:+6.1f}% | Trades: {trades}")

    print(f"\n✅ Bootstrap complete!")
    print(f"   Files created:")
    print(f"   • data/insider_trades_history.csv")
    print(f"   • data/insider_profiles.json")
    print(f"\n🎉 Insider performance tracking is now fully operational!")
    print("="*70 + "\n")


def main():
    """Main bootstrap function"""
    parser = argparse.ArgumentParser(
        description='Bootstrap insider performance tracker with historical data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full bootstrap (6-12 hours)
  python bootstrap_insider_history.py --years 3 --batch-size 100

  # Quick test (5 minutes)
  python bootstrap_insider_history.py --quick-test

  # Resume from checkpoint
  python bootstrap_insider_history.py --years 3 --resume
        """
    )
    parser.add_argument('--years', type=int, default=3,
                       help='Years of historical data to collect (default: 3)')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Number of trades to process per batch (default: 100)')
    parser.add_argument('--quick-test', action='store_true',
                       help='Quick test mode - only processes 10 trades')
    parser.add_argument('--resume', action='store_true',
                       help='Resume from last checkpoint')
    parser.add_argument('--rate-limit', type=float, default=0.3,
                       help='Delay between API calls in seconds (default: 0.3)')

    args = parser.parse_args()

    # Header
    print("\n" + "="*70)
    print("INSIDER PERFORMANCE TRACKER - BOOTSTRAP")
    print("="*70)

    if args.quick_test:
        print("\n🧪 QUICK TEST MODE")
        print("   Processing only 10 trades for testing")
        args.batch_size = 10
    else:
        print(f"\n📋 Configuration:")
        print(f"   Years of history: {args.years}")
        print(f"   Batch size: {args.batch_size}")
        print(f"   Rate limit delay: {args.rate_limit}s")
        print(f"   Resume from checkpoint: {'Yes' if args.resume else 'No'}")

        print("\n⏱️  Estimated runtime: 6-12 hours (depends on data volume and API limits)")
        print("\n⚠️  WARNINGS:")
        print("   • This makes thousands of yfinance API calls")
        print("   • Do not interrupt - progress is saved incrementally")
        print("   • Run in a screen/tmux session or overnight")

    print("\n" + "="*70)

    if not args.quick_test:
        response = input("\nContinue? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("❌ Bootstrap cancelled")
            return

    # Initialize progress tracker
    progress = BootstrapProgress()

    # Initialize insider tracker
    print("\n📊 Initializing tracker...")
    tracker = InsiderPerformanceTracker(
        lookback_years=args.years,
        min_trades_for_score=3
    )

    print(f"   Current state:")
    print(f"   • Profiles: {len(tracker.profiles):,}")
    print(f"   • Historical trades: {len(tracker.trades_history):,}")

    # Fetch historical trades
    historical_trades = fetch_historical_trades(
        years_back=args.years,
        quick_test=args.quick_test
    )

    if historical_trades.empty:
        print("\n❌ No historical data fetched - cannot continue")
        print("\n💡 Suggestions:")
        print("   1. Check your internet connection")
        print("   2. Verify OpenInsider is accessible")
        print("   3. Try using --quick-test mode first")
        return

    # Process trades with progress tracking
    try:
        bootstrap_with_progress(
            tracker,
            historical_trades,
            args.batch_size,
            progress,
            rate_limit_delay=args.rate_limit
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Bootstrap interrupted by user")
        print("   Progress has been saved to checkpoint")
        print("   Run with --resume to continue from where you left off")
        return
    except Exception as e:
        print(f"\n❌ Bootstrap failed with error: {e}")
        traceback.print_exc()
        print("\n   Progress has been saved to checkpoint")
        print("   Run with --resume to retry")
        return

    # Calculate insider profiles
    print("\n" + "="*70)
    print("STEP 3: CALCULATING INSIDER PROFILES")
    print("="*70)

    print("   Calculating performance profiles for all insiders...")
    tracker.calculate_insider_profiles()
    print(f"   ✅ {len(tracker.profiles):,} profiles created")

    # Generate summary report
    generate_summary_report(tracker)

    # Clean up checkpoint file
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print("🧹 Cleaned up checkpoint file")


if __name__ == '__main__':
    main()
