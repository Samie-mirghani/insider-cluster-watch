#!/usr/bin/env python3
"""
check_tracking_status.py - TRACKING STATUS DASHBOARD

Quick dashboard to check the health and status of the continuous
insider performance tracking system.

Usage:
    python check_tracking_status.py
    python check_tracking_status.py --detailed  # Show more details
    python check_tracking_status.py --top 20    # Show top 20 performers
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import argparse
from datetime import datetime, timedelta
from typing import Dict, List
import pandas as pd

from jobs.insider_performance_auto_tracker import AutoInsiderTracker
from jobs.insider_performance_tracker import InsiderPerformanceTracker


def format_age(days: float) -> str:
    """Format age in days to human-readable string"""
    if days < 1:
        return f"{int(days * 24)} hours"
    elif days < 7:
        return f"{int(days)} days"
    elif days < 30:
        return f"{int(days / 7)} weeks"
    else:
        return f"{int(days / 30)} months"


def print_header(title: str):
    """Print section header"""
    print("\n" + "="*70)
    print(title.center(70))
    print("="*70)


def print_tracking_stats(auto_tracker: AutoInsiderTracker):
    """Print tracking queue statistics"""
    stats = auto_tracker.get_tracking_stats()

    print_header("TRACKING QUEUE STATUS")

    print(f"\n📊 Overall Stats:")
    print(f"   Total tracked trades: {stats['total_tracks']:,}")
    print(f"   Currently tracking: {stats['active']:,}")
    print(f"   Matured (complete): {stats['matured']:,}")

    print(f"\n📅 Outcomes by Time Horizon:")
    print(f"   30-day outcomes:  {stats['outcomes']['30d']:,} / {stats['total_tracks']:,}")
    print(f"   60-day outcomes:  {stats['outcomes']['60d']:,} / {stats['total_tracks']:,}")
    print(f"   90-day outcomes:  {stats['outcomes']['90d']:,} / {stats['total_tracks']:,}")
    print(f"   180-day outcomes: {stats['outcomes']['180d']:,} / {stats['total_tracks']:,}")

    # Calculate completion rates
    if stats['total_tracks'] > 0:
        completion_30d = (stats['outcomes']['30d'] / stats['total_tracks']) * 100
        completion_90d = (stats['outcomes']['90d'] / stats['total_tracks']) * 100

        print(f"\n📈 Completion Rates:")
        print(f"   30-day:  {completion_30d:.1f}%")
        print(f"   90-day:  {completion_90d:.1f}%")


def print_active_tracks(auto_tracker: AutoInsiderTracker, limit: int = 10):
    """Print currently active tracks"""
    active_tracks = auto_tracker._get_active_tracks()

    if not active_tracks:
        print("\nℹ️  No active tracks")
        return

    print_header(f"ACTIVE TRACKS (showing {min(limit, len(active_tracks))} of {len(active_tracks)})")

    # Sort by days elapsed (oldest first)
    today = datetime.now()
    active_tracks_sorted = sorted(
        active_tracks,
        key=lambda t: (today - pd.to_datetime(t['trade_date'])).days,
        reverse=True
    )

    print(f"\n{'Ticker':<8} {'Insider':<25} {'Date':<12} {'Age':<12} {'30d':<8} {'90d':<8} {'180d':<8}")
    print("-" * 90)

    for track in active_tracks_sorted[:limit]:
        ticker = track['ticker'][:7]
        insider = track['insider_name'][:24]
        trade_date = str(track['trade_date'])[:10]
        age = (today - pd.to_datetime(track['trade_date'])).days
        age_str = f"{age}d"

        # Outcome status
        outcome_30d = "✓" if track['outcomes'].get('30d') else "..."
        outcome_90d = "✓" if track['outcomes'].get('90d') else "..."
        outcome_180d = "✓" if track['outcomes'].get('180d') else "..."

        print(f"{ticker:<8} {insider:<25} {trade_date:<12} {age_str:<12} {outcome_30d:<8} {outcome_90d:<8} {outcome_180d:<8}")


def print_recent_matured(auto_tracker: AutoInsiderTracker, limit: int = 10):
    """Print recently matured trades"""
    matured_tracks = auto_tracker._get_matured_tracks()

    if not matured_tracks:
        print("\nℹ️  No matured trades yet")
        return

    print_header(f"RECENTLY MATURED TRADES (showing {min(limit, len(matured_tracks))} of {len(matured_tracks)})")

    # Sort by last updated (most recent first)
    matured_sorted = sorted(
        matured_tracks,
        key=lambda t: pd.to_datetime(t.get('last_updated', '1970-01-01')),
        reverse=True
    )

    print(f"\n{'Ticker':<8} {'Insider':<25} {'Trade Date':<12} {'90d Return':<12}")
    print("-" * 60)

    for track in matured_sorted[:limit]:
        ticker = track['ticker'][:7]
        insider = track['insider_name'][:24]
        trade_date = str(track['trade_date'])[:10]

        outcome_90d = track['outcomes'].get('90d')
        if outcome_90d:
            return_pct = outcome_90d.get('return', 0)
            return_str = f"{return_pct:+.1f}%"
        else:
            return_str = "N/A"

        print(f"{ticker:<8} {insider:<25} {trade_date:<12} {return_str:<12}")


def print_insider_performance(tracker: InsiderPerformanceTracker, top_n: int = 10):
    """Print top and bottom performers"""
    if not tracker.profiles:
        print("\nℹ️  No insider profiles available")
        return

    print_header(f"TOP {top_n} PERFORMING INSIDERS")

    top_performers = tracker.get_top_performers(n=top_n, min_trades=3)

    if top_performers.empty:
        print("ℹ️  No profiles with ≥3 trades")
        return

    print(f"\n{'Rank':<6} {'Name':<35} {'Score':<8} {'Win Rate':<10} {'Avg Ret':<10} {'Trades':<8}")
    print("-" * 80)

    for idx, (_, row) in enumerate(top_performers.iterrows(), 1):
        name = row['name'][:34]
        score = row.get('overall_score', 0)
        win_rate = row.get('win_rate_90d', 0)
        avg_return = row.get('avg_return_90d', 0)
        trades = row.get('total_trades', 0)

        print(f"{idx:<6} {name:<35} {score:>5.1f}    {win_rate:>5.1f}%     {avg_return:>+6.1f}%    {trades:>5}")

    # Bottom performers
    print_header(f"BOTTOM {top_n} PERFORMING INSIDERS")

    worst_performers = tracker.get_worst_performers(n=top_n, min_trades=3)

    if worst_performers.empty:
        print("ℹ️  No profiles with ≥3 trades")
        return

    print(f"\n{'Rank':<6} {'Name':<35} {'Score':<8} {'Win Rate':<10} {'Avg Ret':<10} {'Trades':<8}")
    print("-" * 80)

    for idx, (_, row) in enumerate(worst_performers.iterrows(), 1):
        name = row['name'][:34]
        score = row.get('overall_score', 0)
        win_rate = row.get('win_rate_90d', 0)
        avg_return = row.get('avg_return_90d', 0)
        trades = row.get('total_trades', 0)

        print(f"{idx:<6} {name:<35} {score:>5.1f}    {win_rate:>5.1f}%     {avg_return:>+6.1f}%    {trades:>5}")


def print_system_health():
    """Print overall system health summary"""
    print_header("CONTINUOUS TRACKING SYSTEM HEALTH")

    try:
        auto_tracker = AutoInsiderTracker()
        stats = auto_tracker.get_tracking_stats()

        # Check 1: Data exists
        data_exists = stats['historical_trades'] > 0
        print(f"\n✓ Historical data:  {'✅ YES' if data_exists else '❌ NO'}")

        if not data_exists:
            print("   → Run bootstrap: python bootstrap_insider_history.py --quick-test")

        # Check 2: Tracking active
        has_active_tracks = stats['active'] > 0 or stats['matured'] > 0
        print(f"✓ Active tracking:  {'✅ YES' if has_active_tracks else '⚠️  NONE'}")

        if not has_active_tracks:
            print("   → New signals will be tracked automatically on next daily run")

        # Check 3: Recent updates
        if stats['matured'] > 0:
            print(f"✓ Matured trades:   ✅ {stats['matured']}")
        else:
            print(f"✓ Matured trades:   ℹ️  None yet (trades need 90+ days to mature)")

        # Check 4: Completion rate
        if stats['total_tracks'] > 0:
            completion_rate = (stats['outcomes']['90d'] / stats['total_tracks']) * 100
            status = "✅" if completion_rate > 50 else "⚠️ "
            print(f"✓ 90d completion:   {status} {completion_rate:.1f}%")

        # Overall status
        if data_exists and (has_active_tracks or stats['matured'] > 0):
            print(f"\n{'🎉 SYSTEM STATUS: OPERATIONAL ✅'.center(70)}")
        elif data_exists:
            print(f"\n{'⚠️  SYSTEM STATUS: INITIALIZED (waiting for signals)'.center(70)}")
        else:
            print(f"\n{'❌ SYSTEM STATUS: NOT INITIALIZED'.center(70)}")

    except Exception as e:
        print(f"\n❌ Error checking system health: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main dashboard function"""
    parser = argparse.ArgumentParser(
        description='Check insider performance tracking system status',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--detailed', action='store_true',
                       help='Show detailed information')
    parser.add_argument('--top', type=int, default=10,
                       help='Number of top/bottom performers to show (default: 10)')

    args = parser.parse_args()

    # Header
    print("\n" + "="*70)
    print("INSIDER PERFORMANCE TRACKING - STATUS DASHBOARD".center(70))
    print("="*70)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Initialize trackers
        auto_tracker = AutoInsiderTracker()
        insider_tracker = InsiderPerformanceTracker()

        # System health check
        print_system_health()

        # Tracking stats
        print_tracking_stats(auto_tracker)

        # Top/bottom performers
        print_insider_performance(insider_tracker, top_n=args.top)

        if args.detailed:
            # Active tracks
            print_active_tracks(auto_tracker, limit=20)

            # Recent matured
            print_recent_matured(auto_tracker, limit=20)

        # Footer
        print("\n" + "="*70)
        print("For detailed tracking queue, check: data/insider_tracking_queue.json")
        print("For historical trades, check: data/insider_trades_history.csv")
        print("For profiles, check: data/insider_profiles.json")
        print("="*70 + "\n")

    except Exception as e:
        print(f"\n❌ Error generating dashboard: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
