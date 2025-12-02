"""
insider_performance_auto_tracker.py - CONTINUOUS TRACKING SYSTEM

This module provides real-time, automatic tracking of insider performance.

Key Features:
• Track new insider purchases as signals are detected (zero manual intervention)
• Daily background job to update maturing trades (30/60/90 day outcomes)
• Incremental profile updates (no need to re-process entire history)
• Self-maintaining system after initial bootstrap

Usage:
    from insider_performance_auto_tracker import AutoInsiderTracker

    # Initialize tracker
    auto_tracker = AutoInsiderTracker()

    # When new insider signal detected
    auto_tracker.track_new_purchase(signal)

    # Daily background job (run in daily pipeline)
    auto_tracker.update_maturing_trades()
    auto_tracker.update_insider_profiles()
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import yfinance as yf
import time

from insider_performance_tracker import InsiderPerformanceTracker


class AutoInsiderTracker:
    """
    Continuous tracking system for insider performance.

    Automatically tracks new insider purchases and updates maturing trades
    without manual intervention.
    """

    def __init__(self, data_dir: str = "data"):
        """
        Initialize the auto-tracker.

        Args:
            data_dir: Directory for data storage
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Tracking database file
        self.tracking_db_file = self.data_dir / "insider_tracking_queue.json"

        # Initialize the main performance tracker
        self.tracker = InsiderPerformanceTracker()

        # Load tracking queue
        self.tracking_queue = self._load_tracking_queue()

        print(f"🔄 Auto-Tracker initialized")
        print(f"   Currently tracking: {len(self._get_active_tracks())} trades")
        print(f"   Matured trades: {len(self._get_matured_tracks())}")

    def _load_tracking_queue(self) -> List[Dict]:
        """Load the tracking queue from disk"""
        if self.tracking_db_file.exists():
            try:
                with open(self.tracking_db_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️  Could not load tracking queue: {e}")
                return []
        return []

    def _save_tracking_queue(self):
        """Save the tracking queue to disk"""
        try:
            with open(self.tracking_db_file, 'w') as f:
                json.dump(self.tracking_queue, f, indent=2, default=str)
        except Exception as e:
            print(f"❌ Error saving tracking queue: {e}")

    def _get_active_tracks(self) -> List[Dict]:
        """Get all actively tracked trades"""
        return [t for t in self.tracking_queue if t.get('status') == 'TRACKING']

    def _get_matured_tracks(self) -> List[Dict]:
        """Get all matured trades"""
        return [t for t in self.tracking_queue if t.get('status') == 'MATURED']

    def track_new_purchase(self, signal: Dict, source: str = "signal_detection") -> bool:
        """
        Track a new insider purchase in real-time.

        Called automatically when new insider signal is detected.

        Args:
            signal: Signal dict with keys: ticker, insider_name, trade_date, price, etc.
            source: Source of the signal (for tracking)

        Returns:
            True if successfully added to tracking, False otherwise
        """
        try:
            # Extract signal details
            ticker = signal.get('ticker')
            insider_name = signal.get('insider_name')
            trade_date = signal.get('trade_date')
            entry_price = signal.get('price') or signal.get('entry_price')
            title = signal.get('title', '')
            qty = signal.get('qty', 0)
            value = signal.get('value', 0)

            # Validate required fields
            if not all([ticker, insider_name, trade_date, entry_price]):
                print(f"⚠️  Missing required fields for tracking: {signal}")
                return False

            # Check if already tracking this trade
            trade_id = f"{ticker}_{insider_name}_{trade_date}"
            existing = [t for t in self.tracking_queue if t.get('trade_id') == trade_id]
            if existing:
                print(f"   Already tracking {trade_id}")
                return True

            # Create tracking record
            track_record = {
                'trade_id': trade_id,
                'ticker': ticker,
                'insider_name': insider_name,
                'trade_date': str(trade_date)[:10],
                'entry_price': float(entry_price),
                'title': title,
                'qty': qty,
                'value': value,
                'status': 'TRACKING',
                'tracked_since': datetime.now().isoformat(),
                'source': source,
                'last_updated': datetime.now().isoformat(),
                'outcomes': {
                    '30d': None,
                    '60d': None,
                    '90d': None,
                    '180d': None
                }
            }

            # Add to tracking queue
            self.tracking_queue.append(track_record)
            self._save_tracking_queue()

            # Add to main tracker's historical database
            trade_df = pd.DataFrame([{
                'trade_date': trade_date,
                'ticker': ticker,
                'insider_name': insider_name,
                'title': title,
                'qty': qty,
                'price': entry_price,
                'value': value,
                'entry_price': entry_price,
                'outcome_30d': None,
                'outcome_90d': None,
                'outcome_180d': None,
                'return_30d': None,
                'return_90d': None,
                'return_180d': None,
                'last_updated': datetime.now().isoformat()
            }])

            self.tracker.add_trades(trade_df)

            print(f"✅ Now tracking: {ticker} - {insider_name} (${entry_price:.2f})")
            return True

        except Exception as e:
            print(f"❌ Error tracking purchase: {e}")
            return False

    def update_maturing_trades(self, max_retries: int = 3) -> Dict:
        """
        Update outcomes for trades that are maturing (reached 30/60/90/180 days).

        This should be run daily as a background job.

        Args:
            max_retries: Max retries for API failures

        Returns:
            Dict with summary stats
        """
        print("\n" + "="*70)
        print("UPDATING MATURING TRADES")
        print("="*70)

        active_tracks = self._get_active_tracks()
        print(f"Active tracks: {len(active_tracks)}")

        if not active_tracks:
            print("✅ No active tracks to update")
            return {'updated': 0, 'matured': 0, 'failed': 0}

        today = datetime.now()
        updated_count = 0
        matured_count = 0
        failed_count = 0

        for track in active_tracks:
            trade_date = pd.to_datetime(track['trade_date'])
            days_elapsed = (today - trade_date).days

            # Check which time horizons need updating
            horizons_to_check = []
            if days_elapsed >= 30 and track['outcomes']['30d'] is None:
                horizons_to_check.append(('30d', 30))
            if days_elapsed >= 60 and track['outcomes']['60d'] is None:
                horizons_to_check.append(('60d', 60))
            if days_elapsed >= 90 and track['outcomes']['90d'] is None:
                horizons_to_check.append(('90d', 90))
            if days_elapsed >= 180 and track['outcomes']['180d'] is None:
                horizons_to_check.append(('180d', 180))

            if not horizons_to_check:
                continue  # No updates needed for this trade yet

            ticker = track['ticker']
            entry_price = track['entry_price']

            print(f"\n📊 {ticker} - {days_elapsed} days elapsed")
            print(f"   Checking horizons: {[h[0] for h in horizons_to_check]}")

            # Fetch price data with retry
            outcomes = self._fetch_outcomes_with_retry(
                ticker, trade_date, entry_price, horizons_to_check, max_retries
            )

            if outcomes:
                # Update tracking record
                for horizon, _ in horizons_to_check:
                    if outcomes.get(horizon):
                        track['outcomes'][horizon] = outcomes[horizon]
                        print(f"   ✅ {horizon}: ${outcomes[horizon]['price']:.2f} ({outcomes[horizon]['return']:+.1f}%)")

                track['last_updated'] = datetime.now().isoformat()
                updated_count += 1

                # Update main tracker's database
                self._update_tracker_outcomes(track)

                # Check if all outcomes complete (matured)
                if all(track['outcomes'][h] is not None for h in ['30d', '90d', '180d']):
                    track['status'] = 'MATURED'
                    matured_count += 1
                    print(f"   🎯 Trade MATURED - all outcomes complete")

            else:
                print(f"   ⚠️  Failed to fetch outcomes after {max_retries} retries")
                failed_count += 1

            # Rate limiting
            time.sleep(0.5)

        # Save updated queue
        self._save_tracking_queue()

        print(f"\n{'='*70}")
        print(f"UPDATE COMPLETE")
        print(f"{'='*70}")
        print(f"  Updated: {updated_count}")
        print(f"  Matured: {matured_count}")
        print(f"  Failed: {failed_count}")
        print(f"{'='*70}\n")

        return {
            'updated': updated_count,
            'matured': matured_count,
            'failed': failed_count
        }

    def _fetch_outcomes_with_retry(self, ticker: str, trade_date: datetime,
                                   entry_price: float, horizons: List[tuple],
                                   max_retries: int = 3) -> Optional[Dict]:
        """
        Fetch price outcomes with retry logic.

        Args:
            ticker: Stock ticker
            trade_date: Trade date
            entry_price: Entry price
            horizons: List of (horizon_name, days) tuples to check
            max_retries: Max retry attempts

        Returns:
            Dict with outcomes or None if failed
        """
        delay = 1.0

        for attempt in range(max_retries):
            try:
                # Fetch historical data
                start_date = trade_date - timedelta(days=5)
                end_date = datetime.now()

                stock = yf.Ticker(ticker)
                hist = stock.history(start=start_date, end=end_date)

                if hist.empty:
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay *= 2
                        continue
                    return None

                # Remove timezone
                hist = hist.reset_index()
                hist['Date'] = pd.to_datetime(hist['Date']).dt.tz_localize(None)

                outcomes = {}

                # Calculate outcomes for each horizon
                for horizon_name, days in horizons:
                    target_date = trade_date + timedelta(days=days)
                    future_data = hist[hist['Date'] >= target_date]

                    if not future_data.empty:
                        outcome_price = future_data.iloc[0]['Close']
                        return_pct = ((outcome_price - entry_price) / entry_price) * 100

                        outcomes[horizon_name] = {
                            'price': float(outcome_price),
                            'return': float(return_pct),
                            'date': str(future_data.iloc[0]['Date'])[:10]
                        }

                return outcomes if outcomes else None

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"   Retry {attempt + 1}/{max_retries}: {e}")
                    time.sleep(delay)
                    delay *= 2
                    continue
                else:
                    print(f"   Error after {max_retries} attempts: {e}")
                    return None

        return None

    def _update_tracker_outcomes(self, track: Dict):
        """Update the main tracker's database with new outcomes"""
        try:
            # Find the trade in the tracker's database
            mask = (
                (self.tracker.trades_history['ticker'] == track['ticker']) &
                (self.tracker.trades_history['insider_name'] == track['insider_name']) &
                (self.tracker.trades_history['trade_date'] == track['trade_date'])
            )

            if mask.any():
                idx = self.tracker.trades_history[mask].index[0]

                # Update outcomes
                for horizon in ['30d', '60d', '90d', '180d']:
                    if track['outcomes'].get(horizon):
                        outcome = track['outcomes'][horizon]
                        self.tracker.trades_history.loc[idx, f'outcome_{horizon}'] = outcome['price']
                        self.tracker.trades_history.loc[idx, f'return_{horizon}'] = outcome['return']

                self.tracker.trades_history.loc[idx, 'last_updated'] = datetime.now().isoformat()

                # Save to disk
                self.tracker._save_trades_history()

        except Exception as e:
            print(f"⚠️  Error updating tracker outcomes: {e}")

    def update_insider_profiles(self):
        """
        Recalculate insider profiles based on updated trade outcomes.

        This should be run after update_maturing_trades() to incorporate
        new outcomes into performance scores.
        """
        print("\n" + "="*70)
        print("UPDATING INSIDER PROFILES")
        print("="*70)

        before_count = len(self.tracker.profiles)

        # Recalculate all profiles
        self.tracker.calculate_insider_profiles()

        after_count = len(self.tracker.profiles)
        new_profiles = after_count - before_count

        print(f"✅ Profile update complete")
        print(f"   Total profiles: {after_count}")
        if new_profiles > 0:
            print(f"   New profiles: {new_profiles}")
        print("="*70 + "\n")

    def get_tracking_stats(self) -> Dict:
        """
        Get current tracking statistics.

        Returns:
            Dict with tracking stats
        """
        active = self._get_active_tracks()
        matured = self._get_matured_tracks()

        # Count by time horizon
        with_30d = len([t for t in self.tracking_queue if t['outcomes'].get('30d') is not None])
        with_60d = len([t for t in self.tracking_queue if t['outcomes'].get('60d') is not None])
        with_90d = len([t for t in self.tracking_queue if t['outcomes'].get('90d') is not None])
        with_180d = len([t for t in self.tracking_queue if t['outcomes'].get('180d') is not None])

        return {
            'total_tracks': len(self.tracking_queue),
            'active': len(active),
            'matured': len(matured),
            'outcomes': {
                '30d': with_30d,
                '60d': with_60d,
                '90d': with_90d,
                '180d': with_180d
            },
            'insider_profiles': len(self.tracker.profiles),
            'historical_trades': len(self.tracker.trades_history)
        }

    def cleanup_old_matured_trades(self, days_old: int = 365):
        """
        Archive matured trades older than specified days.

        This prevents the tracking queue from growing indefinitely.

        Args:
            days_old: Archive trades matured this many days ago
        """
        cutoff_date = datetime.now() - timedelta(days=days_old)
        before_count = len(self.tracking_queue)

        # Filter out old matured trades
        self.tracking_queue = [
            t for t in self.tracking_queue
            if not (
                t.get('status') == 'MATURED' and
                pd.to_datetime(t.get('last_updated', datetime.now())) < cutoff_date
            )
        ]

        after_count = len(self.tracking_queue)
        archived = before_count - after_count

        if archived > 0:
            self._save_tracking_queue()
            print(f"🧹 Archived {archived} old matured trades (>{days_old} days old)")

        return archived


# Convenience function for daily pipeline
def run_daily_update():
    """
    Run the daily update job.

    This is the main entry point for the daily pipeline to call.
    Updates maturing trades and recalculates profiles.
    """
    print("\n" + "="*70)
    print("DAILY INSIDER PERFORMANCE UPDATE")
    print("="*70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Initialize auto-tracker
    auto_tracker = AutoInsiderTracker()

    # Get current stats
    stats_before = auto_tracker.get_tracking_stats()
    print(f"\n📊 Current Stats:")
    print(f"   Active tracks: {stats_before['active']}")
    print(f"   Matured trades: {stats_before['matured']}")
    print(f"   Insider profiles: {stats_before['insider_profiles']}")

    # Update maturing trades
    update_results = auto_tracker.update_maturing_trades()

    # Update profiles if any trades were updated
    if update_results['updated'] > 0:
        auto_tracker.update_insider_profiles()

    # Cleanup old matured trades (keep last year only)
    auto_tracker.cleanup_old_matured_trades(days_old=365)

    # Final stats
    stats_after = auto_tracker.get_tracking_stats()

    print(f"\n📊 Final Stats:")
    print(f"   Active tracks: {stats_after['active']}")
    print(f"   Matured trades: {stats_after['matured']}")
    print(f"   Insider profiles: {stats_after['insider_profiles']}")

    print(f"\n✅ Daily update complete!")
    print("="*70 + "\n")

    return {
        'stats_before': stats_before,
        'stats_after': stats_after,
        'update_results': update_results
    }


if __name__ == '__main__':
    # If run directly, execute daily update
    run_daily_update()
