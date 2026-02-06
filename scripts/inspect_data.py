#!/usr/bin/env python3
"""
Inspect actual data structures to help debug issues.
"""

import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent


def inspect_live_positions():
    """Show actual structure of live_positions.json."""
    print("=" * 60)
    print("LIVE POSITIONS STRUCTURE")
    print("=" * 60)

    file_path = BASE_DIR / 'automated_trading' / 'data' / 'live_positions.json'

    if not file_path.exists():
        print("File does not exist")
        return

    with open(file_path, 'r') as f:
        data = json.load(f)

    print(f"\nTop-level keys: {list(data.keys())}")

    if 'positions' in data:
        positions = data['positions']
        print(f"Number of positions: {len(positions)}")

        if positions:
            first_ticker = list(positions.keys())[0]
            first_position = positions[first_ticker]

            print(f"\nExample position ({first_ticker}):")
            print(f"  Keys: {list(first_position.keys())}")
            print(f"  Sector: {first_position.get('sector', 'NOT FOUND')}")
            print(f"  Has signal_data: {'signal_data' in first_position}")

            print(f"\nAll sectors:")
            for ticker, pos in positions.items():
                sector = pos.get('sector', 'MISSING')
                print(f"  {ticker}: {sector}")


def inspect_exits_today():
    """Show actual structure of exits_today.json."""
    print("\n" + "=" * 60)
    print("EXITS TODAY STRUCTURE")
    print("=" * 60)

    file_path = BASE_DIR / 'automated_trading' / 'data' / 'exits_today.json'

    if not file_path.exists():
        print("File does not exist")
        return

    with open(file_path, 'r') as f:
        data = json.load(f)

    print(f"\nKeys: {list(data.keys())}")
    print(f"Date: {data.get('date', 'NOT FOUND')}")
    print(f"Today: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"Exits count: {len(data.get('exits', []))}")

    if data.get('exits'):
        print("\nExit details:")
        for exit in data['exits']:
            print(f"  {exit}")


def inspect_audit_log_today():
    """Count today's events in audit log."""
    print("\n" + "=" * 60)
    print("AUDIT LOG TODAY")
    print("=" * 60)

    file_path = BASE_DIR / 'automated_trading' / 'data' / 'audit_log.jsonl'

    if not file_path.exists():
        print("File does not exist")
        return

    today = datetime.now().strftime('%Y-%m-%d')

    events_today = {}
    exits_today = []

    with open(file_path, 'r') as f:
        for line in f:
            try:
                event = json.loads(line)

                if event.get('timestamp', '').startswith(today):
                    event_type = event.get('event_type', 'UNKNOWN')
                    events_today[event_type] = events_today.get(event_type, 0) + 1

                    if event_type == 'POSITION_CLOSED':
                        exits_today.append(event.get('details', {}))
            except Exception:
                continue

    print(f"\nToday's date: {today}")
    print(f"Event counts:")
    for event_type, count in sorted(events_today.items()):
        print(f"  {event_type}: {count}")

    if exits_today:
        print(f"\nExits found in audit log ({len(exits_today)}):")
        for exit in exits_today:
            ticker = exit.get('ticker', 'UNKNOWN')
            pnl = exit.get('pnl', 0)
            reason = exit.get('reason', 'UNKNOWN')
            print(f"  {ticker}: ${pnl:+,.2f} ({reason})")


if __name__ == '__main__':
    inspect_live_positions()
    inspect_exits_today()
    inspect_audit_log_today()
