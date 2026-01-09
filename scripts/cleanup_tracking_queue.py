#!/usr/bin/env python3
"""
Cleanup Tracking Queue - Archive Failed Entries

This script:
1. Loads the insider_tracking_queue.json
2. Separates FAILED entries from active entries
3. Archives failed entries to a backup file
4. Saves the cleaned queue back to the original file
5. Reports statistics

Run this once to clean up the 2,340 FAILED entries that are currently
cluttering the tracking queue and causing performance issues.
"""

import json
import os
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / 'data'
QUEUE_FILE = DATA_DIR / 'insider_tracking_queue.json'
ARCHIVE_FILE = DATA_DIR / 'insider_tracking_queue_failed_archive.json'
BACKUP_FILE = DATA_DIR / f'insider_tracking_queue_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'

def main():
    print("="*70)
    print("INSIDER TRACKING QUEUE CLEANUP")
    print("="*70)
    print()

    # Load the queue
    print(f"📂 Loading queue from: {QUEUE_FILE}")

    if not QUEUE_FILE.exists():
        print(f"❌ Error: Queue file not found at {QUEUE_FILE}")
        return

    with open(QUEUE_FILE, 'r') as f:
        queue = json.load(f)

    initial_count = len(queue)
    print(f"   Total entries: {initial_count:,}")
    print()

    # Analyze the queue
    print("📊 Analyzing queue...")

    status_counts = {}
    for entry in queue:
        status = entry.get('status', 'UNKNOWN')
        status_counts[status] = status_counts.get(status, 0) + 1

    print("   Status breakdown:")
    for status, count in sorted(status_counts.items()):
        pct = (count / initial_count * 100) if initial_count > 0 else 0
        print(f"      {status:20} {count:6,} ({pct:5.1f}%)")
    print()

    # Separate failed entries
    print("🔄 Separating failed entries...")

    active_entries = []
    failed_entries = []

    for entry in queue:
        if entry.get('status') == 'FAILED':
            failed_entries.append(entry)
        else:
            active_entries.append(entry)

    print(f"   Active entries: {len(active_entries):,}")
    print(f"   Failed entries: {len(failed_entries):,}")
    print()

    if not failed_entries:
        print("✅ No failed entries to archive. Queue is clean!")
        return

    # Create backup
    print(f"💾 Creating backup: {BACKUP_FILE.name}")
    with open(BACKUP_FILE, 'w') as f:
        json.dump(queue, f, indent=2)
    print(f"   ✅ Backup created successfully")
    print()

    # Archive failed entries
    print(f"📦 Archiving {len(failed_entries):,} failed entries...")

    # Load existing archive if it exists
    existing_archive = []
    if ARCHIVE_FILE.exists():
        print(f"   Found existing archive with {len(existing_archive):,} entries")
        with open(ARCHIVE_FILE, 'r') as f:
            existing_archive = json.load(f)

    # Combine and deduplicate
    all_failed = existing_archive + failed_entries

    # Deduplicate by trade_id
    seen_ids = set()
    unique_failed = []
    for entry in all_failed:
        trade_id = entry.get('trade_id')
        if trade_id and trade_id not in seen_ids:
            seen_ids.add(trade_id)
            unique_failed.append(entry)

    # Save archive
    with open(ARCHIVE_FILE, 'w') as f:
        json.dump(unique_failed, f, indent=2)

    print(f"   ✅ Archived to: {ARCHIVE_FILE.name}")
    print(f"   Archive now contains: {len(unique_failed):,} unique failed entries")
    print()

    # Save cleaned queue
    print(f"💾 Saving cleaned queue...")
    with open(QUEUE_FILE, 'w') as f:
        json.dump(active_entries, f, indent=2)

    print(f"   ✅ Queue saved successfully")
    print()

    # Summary
    print("="*70)
    print("CLEANUP SUMMARY")
    print("="*70)
    print(f"   Original queue size:     {initial_count:6,} entries")
    print(f"   Failed entries archived: {len(failed_entries):6,} entries")
    print(f"   New queue size:          {len(active_entries):6,} entries")
    print(f"   Reduction:               {initial_count - len(active_entries):6,} entries ({(initial_count - len(active_entries))/initial_count*100:.1f}%)")
    print()
    print(f"   Backup saved to:  {BACKUP_FILE}")
    print(f"   Archive saved to: {ARCHIVE_FILE}")
    print("="*70)
    print()

    # Recommendations
    print("📋 RECOMMENDATIONS:")
    print()
    print("   1. The failed entries have been archived and can be analyzed separately")
    print("   2. The cleaned queue should now run much faster")
    print("   3. The backup file can be deleted after verifying everything works")
    print("   4. Failed tickers will be prevented from re-entering via the blacklist")
    print()
    print("✅ Cleanup complete!")
    print()


if __name__ == "__main__":
    main()
