#!/usr/bin/env python3
"""
Migrate paper_trades.csv from old format to new format

Old format:
- date, action, ticker, price, shares, cost, reason, signal_score, cash_remaining, portfolio_value
- For SELL: adds profit, profit_pct, days_held

New format (expected by generate_public_performance.py):
- entry_date, exit_date, action, ticker, entry_price, exit_price, shares, proceeds,
  exit_reason, profit, pnl_pct, hold_days, signal_score, cash_remaining, portfolio_value
"""

import pandas as pd
import os
from datetime import datetime, timedelta
from pathlib import Path
import shutil

# Paths
DATA_DIR = Path(__file__).parent.parent / 'data'
OLD_CSV = DATA_DIR / 'paper_trades.csv'
BACKUP_CSV = DATA_DIR / 'paper_trades_backup.csv'
NEW_CSV = DATA_DIR / 'paper_trades_new.csv'


def migrate_trades():
    """Migrate trades from old format to new format"""

    if not OLD_CSV.exists():
        print("❌ No paper_trades.csv found - nothing to migrate")
        return False

    # Backup original file
    print(f"📦 Backing up original CSV to {BACKUP_CSV}")
    shutil.copy2(OLD_CSV, BACKUP_CSV)

    # Read old CSV
    print(f"📖 Reading {OLD_CSV}")
    try:
        df = pd.read_csv(OLD_CSV, parse_dates=['date'])
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return False

    print(f"   Found {len(df)} records")

    # Check if already in new format
    if 'entry_date' in df.columns and 'exit_date' in df.columns and 'pnl_pct' in df.columns:
        print("✅ CSV is already in new format - no migration needed")
        return True

    # Build a mapping of BUY actions for each ticker
    buys = {}  # ticker -> list of BUY records
    for _, row in df[df['action'] == 'BUY'].iterrows():
        ticker = row['ticker']
        if ticker not in buys:
            buys[ticker] = []
        buys[ticker].append(row)

    print(f"   Found {len(buys)} tickers with BUY records")

    # Convert SELL records to new format
    new_records = []
    sells = df[df['action'] == 'SELL']

    print(f"   Processing {len(sells)} SELL records...")

    for _, sell_row in sells.iterrows():
        ticker = sell_row['ticker']

        # Find corresponding BUY (use the first one for this ticker)
        if ticker not in buys or len(buys[ticker]) == 0:
            print(f"   ⚠️  No BUY found for {ticker} SELL - calculating entry date from days_held")
            # Fallback: calculate entry_date from exit_date - days_held
            exit_date = sell_row['date']
            days_held = sell_row.get('days_held', 0)
            entry_date = exit_date - timedelta(days=int(days_held))

            # Calculate entry_price from profit
            exit_price = sell_row['price']
            shares = sell_row['shares']
            profit = sell_row.get('profit', 0)
            proceeds = sell_row.get('proceeds', exit_price * shares)
            cost_basis = proceeds - profit
            entry_price = cost_basis / shares if shares > 0 else exit_price
        else:
            # Use the first BUY record for this ticker
            buy_row = buys[ticker][0]
            entry_date = buy_row['date']
            entry_price = buy_row['price']
            exit_date = sell_row['date']
            exit_price = sell_row['price']

            # Remove the used BUY from the list
            buys[ticker].pop(0)

        # Build new record
        new_record = {
            'entry_date': entry_date,
            'exit_date': sell_row['date'],
            'action': 'SELL',
            'ticker': ticker,
            'entry_price': entry_price,
            'exit_price': sell_row['price'],
            'shares': sell_row['shares'],
            'proceeds': sell_row.get('proceeds', sell_row['price'] * sell_row['shares']),
            'exit_reason': sell_row.get('reason', 'Unknown'),
            'profit': sell_row.get('profit', 0),
            'pnl_pct': sell_row.get('profit_pct', 0),  # Old name -> new name
            'hold_days': sell_row.get('days_held', 0),  # Old name -> new name
            'signal_score': sell_row.get('signal_score', 0),
            'cash_remaining': sell_row.get('cash_remaining', 0),
            'portfolio_value': sell_row.get('portfolio_value', 0)
        }

        new_records.append(new_record)
        print(f"   ✓ Migrated {ticker}: {entry_date.date()} -> {sell_row['date'].date()} "
              f"({new_record['pnl_pct']:+.2f}%)")

    if not new_records:
        print("⚠️  No SELL records found to migrate")
        return True

    # Create new DataFrame
    new_df = pd.DataFrame(new_records)

    # Write to new CSV
    print(f"\n💾 Writing {len(new_df)} migrated records to {NEW_CSV}")
    new_df.to_csv(NEW_CSV, index=False)

    # Show preview
    print("\n📊 Preview of migrated data:")
    print(new_df[['ticker', 'entry_date', 'exit_date', 'pnl_pct', 'hold_days']].head(10))

    # Ask for confirmation to replace
    print("\n" + "="*70)
    print("Migration complete!")
    print(f"✅ Original backed up to: {BACKUP_CSV}")
    print(f"✅ New format written to: {NEW_CSV}")
    print("\nTo apply the migration:")
    print(f"  mv {NEW_CSV} {OLD_CSV}")
    print("\nOr run this script with --apply to auto-apply")
    print("="*70)

    return True


def apply_migration():
    """Apply the migration by replacing the old CSV with the new one"""
    if not NEW_CSV.exists():
        print("❌ No migration file found - run migration first")
        return False

    print(f"🔄 Applying migration...")
    print(f"   Moving {NEW_CSV} -> {OLD_CSV}")

    shutil.move(NEW_CSV, OLD_CSV)

    print("✅ Migration applied successfully!")
    print(f"   Backup remains at: {BACKUP_CSV}")

    return True


if __name__ == '__main__':
    import sys

    if '--apply' in sys.argv:
        apply_migration()
    else:
        success = migrate_trades()
        if success and NEW_CSV.exists():
            print("\nRun with --apply to replace the old CSV with the migrated version")
