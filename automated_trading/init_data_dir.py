#!/usr/bin/env python3
"""
Data Directory Initialization Script

Initializes the automated_trading/data directory with required files.
Run this before first execution of the trading system.
"""

import os
import json
from datetime import datetime

# Get script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, 'data')


def initialize_data_directory():
    """Create data directory and initialize all required files."""

    print(f"Initializing data directory: {DATA_DIR}")

    # Create directory if it doesn't exist
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"✓ Created directory: {DATA_DIR}")

    # Initialize JSON files with empty state
    files_to_create = {
        'live_positions.json': {
            'positions': {},
            'last_updated': datetime.now().isoformat()
        },
        'pending_orders.json': {
            'orders': {},
            'last_updated': datetime.now().isoformat()
        },
        'queued_signals.json': {
            'signals': {},
            'daily_redeployments': 0,
            'last_reset_date': datetime.now().strftime('%Y-%m-%d'),
            'last_updated': datetime.now().isoformat()
        },
        'daily_state.json': {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'daily_pnl': 0.0,
            'consecutive_losses': 0,
            'is_halted': False,
            'halt_reason': None,
            'trades_today': [],
            'last_updated': datetime.now().isoformat()
        }
    }

    for filename, initial_data in files_to_create.items():
        filepath = os.path.join(DATA_DIR, filename)

        # Only create if doesn't exist
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                json.dump(initial_data, f, indent=2)
            print(f"✓ Created: {filename}")
        else:
            print(f"  Exists: {filename} (skipped)")

    # Create empty audit log (JSONL format)
    audit_log = os.path.join(DATA_DIR, 'audit_log.jsonl')
    if not os.path.exists(audit_log):
        # Create empty file
        open(audit_log, 'a').close()
        print(f"✓ Created: audit_log.jsonl")
    else:
        print(f"  Exists: audit_log.jsonl (skipped)")

    # Create .gitkeep to track directory in git
    gitkeep = os.path.join(DATA_DIR, '.gitkeep')
    if not os.path.exists(gitkeep):
        open(gitkeep, 'a').close()
        print(f"✓ Created: .gitkeep")
    else:
        print(f"  Exists: .gitkeep (skipped)")

    print(f"\n✅ Data directory initialized successfully!")
    print(f"\nNext steps:")
    print(f"1. Set environment variables (ALPACA_PAPER_API_KEY, etc.)")
    print(f"2. Run: python -m automated_trading.execute_trades status")
    print(f"3. Test connection to Alpaca")


if __name__ == '__main__':
    initialize_data_directory()
