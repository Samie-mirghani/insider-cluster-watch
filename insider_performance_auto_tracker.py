"""
insider_performance_auto_tracker.py - CONTINUOUS TRACKING SYSTEM

This module provides real-time, automatic tracking of insider performance.

Key Features:
• Track new insider purchases as signals are detected (zero manual intervention)
• Daily background job to update maturing trades (30/60/90 day outcomes)
• Incremental profile updates (no need to re-process entire history)
• Self-maintaining system after initial bootstrap
• Intelligent failure handling with categorization and retry logic

Failure Handling:
• DELISTED: Stock no longer trades (marked as FAILED, no retry)
• INVALID_TICKER: Bad ticker format or non-stock (marked as FAILED, no retry)
• RATE_LIMIT: API rate limiting (retries tomorrow)
• NETWORK_ERROR: Temporary network issues (retries tomorrow)

Impact on Profiles:
• Failed trades do NOT affect insider performance profiles
• Profiles are calculated ONLY from trades with successful outcomes
• Insiders need minimum 3 successful trades for profile calculation
• This ensures profile quality is not degraded by data availability issues
• Failed trades are excluded entirely (conservative approach)

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
import logging

# Suppress yfinance error spam for delisted stocks
# yfinance logs ERROR for every delisted ticker, which clutters logs
# These are expected failures and don't break the pipeline
logging.getLogger('yfinance').setLevel(logging.WARNING)

from insider_performance_tracker import InsiderPerformanceTracker


class AutoInsiderTracker:
    """
    Continuous tracking system for insider performance.

    Automatically tracks new insider purchases and updates maturing trades
    without manual intervention.
    """

    def __init__(self, data_dir: str = "data", verbose: bool = False):
        """
        Initialize the auto-tracker.

        Args:
            data_dir: Directory for data storage
            verbose: Enable verbose logging (default: False)
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose

        # Tracking database file
        self.tracking_db_file = self.data_dir / "insider_tracking_queue.json"

        # Initialize the main performance tracker
        self.tracker = InsiderPerformanceTracker()

        # Load tracking queue
        self.tracking_queue = self._load_tracking_queue()

        if self.verbose:
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
        """Get all actively tracked trades (excluding failed)"""
        return [t for t in self.tracking_queue if t.get('status') == 'TRACKING']

    def _get_matured_tracks(self) -> List[Dict]:
        """Get all matured trades"""
        return [t for t in self.tracking_queue if t.get('status') == 'MATURED']

    def _get_failed_tracks(self) -> List[Dict]:
        """Get all permanently failed trades"""
        return [t for t in self.tracking_queue if t.get('status') == 'FAILED']

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
                if self.verbose:
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
                'outcome_60d': None,  # BUG FIX: Added missing 60d field
                'outcome_90d': None,
                'outcome_180d': None,
                'return_30d': None,
                'return_60d': None,   # BUG FIX: Added missing 60d field
                'return_90d': None,
                'return_180d': None,
                'last_updated': datetime.now().isoformat()
            }])

            self.tracker.add_trades(trade_df)

            if self.verbose:
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
            return {'updated': 0, 'matured': 0, 'failed': 0, 'permanently_failed': 0}

        today = datetime.now()
        updated_count = 0
        matured_count = 0
        failed_count = 0
        permanently_failed_count = 0
        failure_details = []  # Collect failure info for summary logging

        for track in active_tracks:
            trade_date = pd.to_datetime(track['trade_date'])
            days_elapsed = (today - trade_date).days

            # Skip permanently failed trades (no point retrying)
            if track.get('failure_type') in ['DELISTED', 'INVALID_TICKER']:
                continue

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

            if self.verbose:
                print(f"\n📊 {ticker} - {days_elapsed} days elapsed")
                print(f"   Checking horizons: {[h[0] for h in horizons_to_check]}")

            # Fetch price data with retry
            result = self._fetch_outcomes_with_retry(
                ticker, trade_date, entry_price, horizons_to_check, max_retries
            )

            if result and result.get('outcomes'):
                outcomes = result['outcomes']
                # Update tracking record
                for horizon, _ in horizons_to_check:
                    if outcomes.get(horizon):
                        track['outcomes'][horizon] = outcomes[horizon]
                        if self.verbose:
                            print(f"   ✅ {horizon}: ${outcomes[horizon]['price']:.2f} ({outcomes[horizon]['return']:+.1f}%)")

                track['last_updated'] = datetime.now().isoformat()
                # Clear any previous failure info on success
                track.pop('failure_type', None)
                track.pop('failure_reason', None)
                track.pop('failure_count', None)
                updated_count += 1

                # Update main tracker's database
                self._update_tracker_outcomes(track)

                # Check if all outcomes complete (matured)
                if all(track['outcomes'][h] is not None for h in ['30d', '90d', '180d']):
                    track['status'] = 'MATURED'
                    matured_count += 1
                    if self.verbose:
                        print(f"   🎯 Trade MATURED - all outcomes complete")

            else:
                # Handle failure - categorize and track
                failure_type = result.get('failure_type', 'UNKNOWN') if result else 'UNKNOWN'
                failure_reason = result.get('failure_reason', 'Unknown error') if result else 'Unknown error'

                # Track failure count
                failure_count = track.get('failure_count', 0) + 1
                track['failure_count'] = failure_count

                # Categorize permanent vs temporary failures
                if failure_type in ['DELISTED', 'INVALID_TICKER']:
                    track['status'] = 'FAILED'
                    track['failure_type'] = failure_type
                    track['failure_reason'] = failure_reason
                    track['last_updated'] = datetime.now().isoformat()
                    permanently_failed_count += 1

                    failure_details.append({
                        'ticker': ticker,
                        'type': failure_type,
                        'reason': failure_reason,
                        'permanent': True
                    })
                elif failure_type == 'RATE_LIMIT':
                    # Temporary - will retry tomorrow
                    track['failure_type'] = failure_type
                    track['failure_reason'] = failure_reason
                    track['last_updated'] = datetime.now().isoformat()

                    failure_details.append({
                        'ticker': ticker,
                        'type': failure_type,
                        'reason': failure_reason,
                        'permanent': False
                    })
                else:
                    # Network or unknown error - will retry tomorrow
                    track['failure_type'] = 'NETWORK_ERROR'
                    track['failure_reason'] = failure_reason
                    track['last_updated'] = datetime.now().isoformat()

                    failure_details.append({
                        'ticker': ticker,
                        'type': 'NETWORK_ERROR',
                        'reason': failure_reason,
                        'permanent': False
                    })

                failed_count += 1

            # Rate limiting
            time.sleep(0.5)

        # Save updated queue
        self._save_tracking_queue()

        # Summary logging - reduced noise
        print(f"\n{'='*70}")
        print(f"UPDATE COMPLETE")
        print(f"{'='*70}")
        print(f"  Updated: {updated_count}")
        print(f"  Matured: {matured_count}")

        if failed_count > 0:
            print(f"  Failed: {failed_count}")

            # Group by failure type
            from collections import Counter
            permanent_failures = [f for f in failure_details if f['permanent']]
            temporary_failures = [f for f in failure_details if not f['permanent']]

            if permanent_failures:
                print(f"\n  ⚠️  Permanent failures (will not retry): {len(permanent_failures)}")
                type_counts = Counter(f['type'] for f in permanent_failures)
                for ftype, count in type_counts.items():
                    print(f"     • {ftype}: {count}")
                    # Show first few examples
                    examples = [f['ticker'] for f in permanent_failures if f['type'] == ftype][:3]
                    print(f"       Examples: {', '.join(examples)}")

            if temporary_failures:
                print(f"\n  ⚠️  Temporary failures (will retry tomorrow): {len(temporary_failures)}")
                type_counts = Counter(f['type'] for f in temporary_failures)
                for ftype, count in type_counts.items():
                    print(f"     • {ftype}: {count}")
        else:
            print(f"  Failed: 0")

        print(f"{'='*70}\n")

        return {
            'updated': updated_count,
            'matured': matured_count,
            'failed': failed_count,
            'permanently_failed': permanently_failed_count
        }

    def _fetch_outcomes_with_retry(self, ticker: str, trade_date: datetime,
                                   entry_price: float, horizons: List[tuple],
                                   max_retries: int = 3) -> Optional[Dict]:
        """
        Fetch price outcomes with retry logic and failure categorization.

        Args:
            ticker: Stock ticker
            trade_date: Trade date
            entry_price: Entry price
            horizons: List of (horizon_name, days) tuples to check
            max_retries: Max retry attempts

        Returns:
            Dict with 'outcomes' key on success, or 'failure_type'/'failure_reason' on failure
        """
        delay = 1.0
        last_error = None

        for attempt in range(max_retries):
            try:
                # Fetch historical data
                start_date = trade_date - timedelta(days=5)
                end_date = datetime.now()

                stock = yf.Ticker(ticker)
                hist = stock.history(start=start_date, end=end_date)

                if hist.empty:
                    # Try to get more context from ticker info
                    try:
                        info = stock.info
                        # Check for invalid ticker patterns
                        if not info or len(info) < 5:
                            # Likely invalid ticker
                            if self._is_invalid_ticker_format(ticker):
                                return {
                                    'failure_type': 'INVALID_TICKER',
                                    'failure_reason': f'Invalid ticker format: {ticker}'
                                }
                            # Empty history could mean delisted
                            return {
                                'failure_type': 'DELISTED',
                                'failure_reason': 'No trading history available (possibly delisted)'
                            }
                        # Check quote type - mutual funds/ETFs may have different data availability
                        quote_type = info.get('quoteType', '').upper()
                        if quote_type in ['MUTUALFUND', 'INDEX']:
                            return {
                                'failure_type': 'INVALID_TICKER',
                                'failure_reason': f'Ticker is {quote_type}, not a stock'
                            }
                    except:
                        pass  # Continue to retry logic below

                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay *= 2
                        continue

                    # After all retries, classify as delisted
                    return {
                        'failure_type': 'DELISTED',
                        'failure_reason': 'No trading history after multiple retries (possibly delisted)'
                    }

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

                if outcomes:
                    return {'outcomes': outcomes}
                else:
                    # No data for the required horizons (trade too recent)
                    return {
                        'failure_type': 'DELISTED',
                        'failure_reason': 'No trading data for required time horizon'
                    }

            except Exception as e:
                last_error = str(e)

                # Check for rate limiting
                if 'rate limit' in last_error.lower() or '429' in last_error:
                    if attempt < max_retries - 1:
                        if self.verbose:
                            print(f"   Rate limit hit, retry {attempt + 1}/{max_retries}")
                        time.sleep(delay * 2)  # Longer delay for rate limits
                        delay *= 2
                        continue
                    return {
                        'failure_type': 'RATE_LIMIT',
                        'failure_reason': f'Rate limited: {last_error}'
                    }

                # Check for network errors
                if any(err in last_error.lower() for err in ['timeout', 'connection', 'network']):
                    if attempt < max_retries - 1:
                        if self.verbose:
                            print(f"   Network error, retry {attempt + 1}/{max_retries}: {last_error}")
                        time.sleep(delay)
                        delay *= 2
                        continue
                    return {
                        'failure_type': 'NETWORK_ERROR',
                        'failure_reason': f'Network error: {last_error}'
                    }

                # Other exceptions
                if attempt < max_retries - 1:
                    if self.verbose:
                        print(f"   Retry {attempt + 1}/{max_retries}: {last_error}")
                    time.sleep(delay)
                    delay *= 2
                    continue
                else:
                    if self.verbose:
                        print(f"   Error after {max_retries} attempts: {last_error}")
                    return {
                        'failure_type': 'NETWORK_ERROR',
                        'failure_reason': f'Failed after {max_retries} attempts: {last_error}'
                    }

        return {
            'failure_type': 'UNKNOWN',
            'failure_reason': f'Unknown failure: {last_error}'
        }

    def _is_invalid_ticker_format(self, ticker: str) -> bool:
        """
        Check if ticker has obviously invalid format.

        Returns:
            True if ticker format is invalid
        """
        if not ticker or len(ticker) > 10:
            return True
        # Check for common invalid patterns
        invalid_patterns = [
            'N.A.', 'N/A', 'NA', 'NONE', 'NULL',  # Placeholder values
            '.',  # Just a period
        ]
        if ticker.upper() in invalid_patterns:
            return True
        # Check for trailing periods (bad format)
        if ticker.endswith('.') and len(ticker) > 1:
            return True
        # Check for spaces
        if ' ' in ticker:
            return True
        return False

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
        failed = self._get_failed_tracks()

        # Count by time horizon
        with_30d = len([t for t in self.tracking_queue if t['outcomes'].get('30d') is not None])
        with_60d = len([t for t in self.tracking_queue if t['outcomes'].get('60d') is not None])
        with_90d = len([t for t in self.tracking_queue if t['outcomes'].get('90d') is not None])
        with_180d = len([t for t in self.tracking_queue if t['outcomes'].get('180d') is not None])

        # Count failure types
        from collections import Counter
        failure_types = Counter(t.get('failure_type', 'UNKNOWN') for t in failed)

        return {
            'total_tracks': len(self.tracking_queue),
            'active': len(active),
            'matured': len(matured),
            'failed': len(failed),
            'failure_types': dict(failure_types),
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

    def cleanup_old_failed_trades(self, days_old: int = 90):
        """
        Archive permanently failed trades older than specified days.

        Args:
            days_old: Archive failed trades this many days old
        """
        cutoff_date = datetime.now() - timedelta(days=days_old)
        before_count = len(self.tracking_queue)

        # Filter out old failed trades
        self.tracking_queue = [
            t for t in self.tracking_queue
            if not (
                t.get('status') == 'FAILED' and
                pd.to_datetime(t.get('last_updated', datetime.now())) < cutoff_date
            )
        ]

        after_count = len(self.tracking_queue)
        archived = before_count - after_count

        if archived > 0:
            self._save_tracking_queue()
            print(f"🧹 Archived {archived} old failed trades (>{days_old} days old)")

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
    print(f"   Failed trades: {stats_before.get('failed', 0)}")
    if stats_before.get('failure_types'):
        print(f"   Failure types: {stats_before['failure_types']}")
    print(f"   Insider profiles: {stats_before['insider_profiles']}")

    # Update maturing trades
    update_results = auto_tracker.update_maturing_trades()

    # Update profiles if any trades were updated
    if update_results['updated'] > 0:
        auto_tracker.update_insider_profiles()

    # Cleanup old matured trades (keep last year only)
    auto_tracker.cleanup_old_matured_trades(days_old=365)

    # Cleanup old failed trades (keep last 90 days for analysis)
    auto_tracker.cleanup_old_failed_trades(days_old=90)

    # Final stats
    stats_after = auto_tracker.get_tracking_stats()

    print(f"\n📊 Final Stats:")
    print(f"   Active tracks: {stats_after['active']}")
    print(f"   Matured trades: {stats_after['matured']}")
    print(f"   Failed trades: {stats_after.get('failed', 0)}")
    if stats_after.get('failure_types'):
        print(f"   Failure types: {stats_after['failure_types']}")
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
