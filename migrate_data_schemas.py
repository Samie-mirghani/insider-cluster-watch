#!/usr/bin/env python3
"""
Data Schema Migration Script
Adds multi-signal fields to existing data files
"""

import pandas as pd
import json
import os
from datetime import datetime

DATA_DIR = 'data'
SIGNALS_HISTORY = os.path.join(DATA_DIR, 'signals_history.csv')
PAPER_PORTFOLIO = os.path.join(DATA_DIR, 'paper_portfolio.json')
BACKUP_SUFFIX = f'.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}'

def migrate_signals_history():
    """Add multi-signal columns to signals_history.csv"""
    if not os.path.exists(SIGNALS_HISTORY):
        print(f"⚠️  {SIGNALS_HISTORY} not found, skipping")
        return

    print(f"\n📊 Migrating {SIGNALS_HISTORY}...")

    # Backup original
    backup_path = SIGNALS_HISTORY + BACKUP_SUFFIX
    print(f"   📦 Creating backup: {backup_path}")
    with open(SIGNALS_HISTORY, 'r') as f:
        with open(backup_path, 'w') as b:
            b.write(f.read())

    # Load CSV
    df = pd.read_csv(SIGNALS_HISTORY)
    original_columns = df.columns.tolist()
    print(f"   Original columns: {', '.join(original_columns)}")

    # Add new columns if they don't exist
    if 'multi_signal_tier' not in df.columns:
        df['multi_signal_tier'] = 'none'
        print(f"   ✅ Added column: multi_signal_tier (default: 'none')")

    if 'has_politician_signal' not in df.columns:
        df['has_politician_signal'] = False
        print(f"   ✅ Added column: has_politician_signal (default: False)")

    # Save updated CSV
    df.to_csv(SIGNALS_HISTORY, index=False)
    print(f"   💾 Updated {SIGNALS_HISTORY}")
    print(f"   📊 Total signals: {len(df)}")

    # Show new schema
    print(f"\n   New columns: {', '.join(df.columns.tolist())}")

def migrate_paper_portfolio():
    """Add multi-signal fields to paper_portfolio.json positions"""
    if not os.path.exists(PAPER_PORTFOLIO):
        print(f"⚠️  {PAPER_PORTFOLIO} not found, skipping")
        return

    print(f"\n💼 Migrating {PAPER_PORTFOLIO}...")

    # Backup original
    backup_path = PAPER_PORTFOLIO + BACKUP_SUFFIX
    print(f"   📦 Creating backup: {backup_path}")
    with open(PAPER_PORTFOLIO, 'r') as f:
        with open(backup_path, 'w') as b:
            b.write(f.read())

    # Load portfolio
    with open(PAPER_PORTFOLIO, 'r') as f:
        portfolio = json.load(f)

    # Update positions
    positions_updated = 0
    for ticker, position in portfolio.get('positions', {}).items():
        if 'multi_signal_tier' not in position:
            position['multi_signal_tier'] = 'none'
            positions_updated += 1

        if 'has_politician_signal' not in position:
            position['has_politician_signal'] = False
            positions_updated += 1

    if positions_updated > 0:
        # Save updated portfolio
        with open(PAPER_PORTFOLIO, 'w') as f:
            json.dump(portfolio, f, indent=2)

        print(f"   ✅ Updated {len(portfolio.get('positions', {}))} position(s)")
        print(f"   💾 Saved updated portfolio")
    else:
        print(f"   ℹ️  Portfolio already up to date")

def verify_migration():
    """Verify migration was successful"""
    print(f"\n✅ VERIFICATION")
    print(f"="*60)

    # Check signals_history.csv
    if os.path.exists(SIGNALS_HISTORY):
        df = pd.read_csv(SIGNALS_HISTORY)
        print(f"\n📊 signals_history.csv:")
        print(f"   Columns: {', '.join(df.columns.tolist())}")
        print(f"   Rows: {len(df)}")

        if 'multi_signal_tier' in df.columns and 'has_politician_signal' in df.columns:
            print(f"   ✅ Schema updated successfully")
        else:
            print(f"   ❌ Missing columns!")

    # Check paper_portfolio.json
    if os.path.exists(PAPER_PORTFOLIO):
        with open(PAPER_PORTFOLIO, 'r') as f:
            portfolio = json.load(f)

        print(f"\n💼 paper_portfolio.json:")
        positions = portfolio.get('positions', {})
        print(f"   Positions: {len(positions)}")

        if positions:
            sample_ticker = list(positions.keys())[0]
            sample_pos = positions[sample_ticker]

            has_tier = 'multi_signal_tier' in sample_pos
            has_politician = 'has_politician_signal' in sample_pos

            print(f"   Sample position ({sample_ticker}):")
            print(f"     - multi_signal_tier: {has_tier}")
            print(f"     - has_politician_signal: {has_politician}")

            if has_tier and has_politician:
                print(f"   ✅ Schema updated successfully")
            else:
                print(f"   ❌ Missing fields!")

def main():
    print("="*60)
    print("📦 DATA SCHEMA MIGRATION")
    print("   Multi-Signal Detection Fields")
    print("="*60)

    print("\nThis script will:")
    print("  1. Add 'multi_signal_tier' column to signals_history.csv")
    print("  2. Add 'has_politician_signal' column to signals_history.csv")
    print("  3. Add 'multi_signal_tier' field to paper trading positions")
    print("  4. Add 'has_politician_signal' field to paper trading positions")
    print("\nBackups will be created with timestamp suffix.")

    response = input("\n⚠️  Proceed with migration? (yes/no): ")

    if response.lower() not in ['yes', 'y']:
        print("\n❌ Migration cancelled")
        return

    print("\n🚀 Starting migration...")

    # Run migrations
    migrate_signals_history()
    migrate_paper_portfolio()

    # Verify
    verify_migration()

    print("\n" + "="*60)
    print("✅ MIGRATION COMPLETE")
    print("="*60)
    print("\nBackup files created:")
    print(f"  • {SIGNALS_HISTORY + BACKUP_SUFFIX}")
    print(f"  • {PAPER_PORTFOLIO + BACKUP_SUFFIX}")
    print("\nIf anything goes wrong, restore from backups:")
    print(f"  cp {SIGNALS_HISTORY + BACKUP_SUFFIX} {SIGNALS_HISTORY}")
    print(f"  cp {PAPER_PORTFOLIO + BACKUP_SUFFIX} {PAPER_PORTFOLIO}")
    print("\n✅ Your pipeline is now ready for multi-signal features!")

if __name__ == "__main__":
    main()
