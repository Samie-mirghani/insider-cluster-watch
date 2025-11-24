#!/usr/bin/env python3
"""
View Politician Status - Quick Reference Tool

Quick utility to view current politician statuses and weights.
Useful for quarterly reviews and verification.

Usage:
    python view_politician_status.py [--status STATUS] [--sort weight]

Examples:
    # View all politicians
    python view_politician_status.py

    # View only retiring politicians
    python view_politician_status.py --status retiring

    # Sort by weight (highest first)
    python view_politician_status.py --sort weight
"""

import argparse
from politician_tracker import PoliticianTracker
from datetime import datetime
import sys


def format_date(date_str):
    """Format ISO date for display"""
    if not date_str:
        return "N/A"
    try:
        date = datetime.fromisoformat(date_str)
        return date.strftime("%Y-%m-%d")
    except:
        return date_str


def days_since(date_str):
    """Calculate days since a date"""
    if not date_str:
        return None
    try:
        date = datetime.fromisoformat(date_str)
        return (datetime.now() - date).days
    except:
        return None


def print_politician_table(politicians, tracker, sort_by='name'):
    """Print formatted table of politicians"""

    # Prepare data
    rows = []
    for name, info in politicians.items():
        weight = tracker.calculate_time_decay_weight(name)
        base_weight = info.get('base_weight', 1.0)
        status = info.get('current_status', 'unknown')
        party = info.get('party', '')
        office = info.get('office', '')

        # Calculate multiplier
        multiplier = weight / base_weight if base_weight > 0 else 0

        # Days info
        term_ended = info.get('term_ended')
        days_retired = days_since(term_ended) if term_ended else None

        rows.append({
            'name': name,
            'status': status,
            'party': party,
            'office': office,
            'base_weight': base_weight,
            'current_weight': weight,
            'multiplier': multiplier,
            'term_ended': format_date(term_ended),
            'days_retired': days_retired
        })

    # Sort
    if sort_by == 'weight':
        rows.sort(key=lambda x: x['current_weight'], reverse=True)
    elif sort_by == 'status':
        # Sort by status priority: retiring > active > retired
        status_order = {'retiring': 0, 'active': 1, 'retired': 2}
        rows.sort(key=lambda x: status_order.get(x['status'], 999))
    else:  # name
        rows.sort(key=lambda x: x['name'])

    # Print header
    print(f"\n{'='*100}")
    print(f"{'Name':<25} {'Status':<10} {'Party':<6} {'Office':<8} {'Base':<8} {'Current':<10} {'Note':<20}")
    print(f"{'='*100}")

    # Print rows
    for row in rows:
        name = row['name'][:24]
        status = row['status']
        party = row['party']
        office = row['office'][:7]
        base = f"{row['base_weight']:.2f}x"
        current = f"{row['current_weight']:.2f}x"

        # Add contextual note
        note = ""
        if status == 'retiring':
            note = f"🔥 BOOSTED {row['multiplier']:.1f}x"
        elif status == 'retired' and row['days_retired']:
            note = f"📉 {row['days_retired']}d ago"
        elif status == 'active':
            note = "✅ Active"

        print(f"{name:<25} {status:<10} {party:<6} {office:<8} {base:<8} {current:<10} {note:<20}")

    print(f"{'='*100}\n")


def main():
    parser = argparse.ArgumentParser(
        description='View politician statuses and weights',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                        # View all politicians
  %(prog)s --status retiring      # View only retiring politicians
  %(prog)s --sort weight          # Sort by current weight
  %(prog)s --status retired --sort weight  # Retired politicians by weight
        """
    )

    parser.add_argument(
        '--status',
        choices=['active', 'retiring', 'retired'],
        help='Filter by status'
    )

    parser.add_argument(
        '--sort',
        choices=['name', 'weight', 'status'],
        default='name',
        help='Sort by field (default: name)'
    )

    parser.add_argument(
        '--details',
        action='store_true',
        help='Show detailed information'
    )

    args = parser.parse_args()

    try:
        # Initialize tracker
        tracker = PoliticianTracker()

        # Get statistics
        stats = tracker.get_summary_stats()

        print(f"\n{'='*100}")
        print(f"POLITICIAN STATUS OVERVIEW")
        print(f"{'='*100}")
        print(f"\nRegistry Statistics:")
        print(f"  Total Politicians: {stats['total_politicians']}")
        print(f"  Active: {stats['active']}")
        print(f"  Retiring: {stats['retiring']}")
        print(f"  Retired: {stats['retired']}")

        # Filter politicians
        politicians = tracker.registry.get('politicians', {})
        if args.status:
            politicians = {
                name: info for name, info in politicians.items()
                if info.get('current_status') == args.status
            }

            if not politicians:
                print(f"\n⚠️  No politicians with status '{args.status}' found")
                return 0

        # Print table
        print_politician_table(politicians, tracker, args.sort)

        # Show detailed info if requested
        if args.details:
            print(f"\n{'='*100}")
            print("DETAILED INFORMATION")
            print(f"{'='*100}\n")

            for name, info in sorted(politicians.items()):
                print(f"{name}")
                print(f"  Status: {info.get('current_status', 'unknown')}")
                print(f"  Party: {info.get('party', 'N/A')}")
                print(f"  Office: {info.get('office', 'N/A')}")

                if info.get('state'):
                    district = f"-{info['district']}" if info.get('district') else ""
                    print(f"  Location: {info['state']}{district}")

                if info.get('term_started'):
                    print(f"  Term Started: {format_date(info['term_started'])}")

                if info.get('term_ended'):
                    print(f"  Term Ended: {format_date(info['term_ended'])}")
                    days = days_since(info['term_ended'])
                    if days and days > 0:
                        print(f"  Days Since Retirement: {days}")

                if info.get('retirement_announced'):
                    print(f"  Retirement Announced: {format_date(info['retirement_announced'])}")

                print(f"  Base Weight: {info.get('base_weight', 1.0):.2f}x")
                current_weight = tracker.calculate_time_decay_weight(name)
                print(f"  Current Weight: {current_weight:.2f}x")

                if info.get('performance_score'):
                    print(f"  Performance Score: {info['performance_score']:.1f}/100")

                if info.get('total_trades_tracked'):
                    print(f"  Total Trades Tracked: {info['total_trades_tracked']}")

                if info.get('notes'):
                    print(f"  Notes: {info['notes']}")

                print()

        # Show weight legend
        print(f"{'='*100}")
        print("WEIGHT LEGEND")
        print(f"{'='*100}")
        print("""
Status Effects:
  ✅ Active:   Full base weight (e.g., 2.0x stays 2.0x)
  🔥 Retiring: Boosted by 1.5x (e.g., 1.3x becomes 1.95x) - "Lame duck" urgency!
  📉 Retired:  Exponential decay over time
               - Day 0-90:  100% → 50% (half-life)
               - Day 90-180: 50% → 25%
               - Day 180+:   25% → 20% (floor)

Weight never drops below 20% to preserve historical value!
""")

        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(1)
