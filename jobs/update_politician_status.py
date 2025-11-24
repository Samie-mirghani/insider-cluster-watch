#!/usr/bin/env python3
"""
Politician Status Update Script (Option B: Semi-Automated)

This script helps maintain the politician registry by updating statuses when
politicians retire, announce retirement, or return to office.

Usage:
    python update_politician_status.py

Recommended Schedule:
    - After each election cycle (every 2 years)
    - When retirements are announced (as they happen)
    - Quarterly review (January, April, July, October)

How to Use:
    1. Check news/congress.gov for politician changes
    2. Update the UPDATES dictionary below
    3. Run this script
    4. Review the changes
    5. Commit the updated politician_registry.json
"""

from politician_tracker import PoliticianTracker
from datetime import datetime
import sys
from typing import Dict, List


# ============================================================================
# CONFIGURATION: Update this section with politician status changes
# ============================================================================

UPDATES = {
    # Example 1: Politician retiring (announced but not yet left)
    # Uncomment and modify when someone announces retirement:
    # 'Brian Higgins': {
    #     'action': 'set_retiring',
    #     'term_ended': '2025-02-01',
    #     'retirement_announced': '2024-11-08',
    #     'reason': 'Announced early retirement February 2025'
    # },

    # Example 2: Politician has left office (retirement effective)
    # 'Nancy Pelosi': {
    #     'action': 'set_retired',
    #     'term_ended': '2023-01-03',
    #     'retirement_announced': '2022-11-17',
    #     'reason': 'Left leadership position, no longer Speaker'
    # },

    # Example 3: Add new politician to tracking
    # 'Alexandria Ocasio-Cortez': {
    #     'action': 'add_new',
    #     'party': 'D',
    #     'office': 'House',
    #     'state': 'NY',
    #     'district': '14',
    #     'base_weight': 1.2,
    #     'reason': 'High-volume trader, notable trading activity'
    # },

    # Example 4: Return to active status (if politician returns)
    # 'Some Politician': {
    #     'action': 'set_active',
    #     'term_started': '2025-01-03',
    #     'reason': 'Re-elected to office'
    # },
}

# ============================================================================
# Add any notes about this update cycle
# ============================================================================

UPDATE_NOTES = """
Quarterly Update - Q4 2024
--------------------------
Reviewed congress.gov and news sources for:
- Retirements announced in November 2024 election cycle
- Politicians who left office
- New high-volume traders to track

Sources checked:
- congress.gov member directory
- Capitol Trades recent activity
- Major news outlets for retirement announcements
"""


# ============================================================================
# Script Implementation (No need to modify below this line)
# ============================================================================

class PoliticianStatusUpdater:
    """Helper class for updating politician statuses"""

    def __init__(self):
        self.tracker = PoliticianTracker()
        self.changes_made = []

    def process_updates(self, updates: Dict) -> bool:
        """Process all updates and return success status"""
        if not updates:
            print("📋 No updates configured in UPDATES dictionary")
            print("💡 Edit this script and add politician updates to the UPDATES section")
            return False

        print(f"\n{'='*70}")
        print(f"POLITICIAN STATUS UPDATE SCRIPT")
        print(f"{'='*70}")
        print(f"\nDate: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total updates to process: {len(updates)}")

        # Show current registry stats
        stats = self.tracker.get_summary_stats()
        print(f"\nCurrent Registry Stats:")
        print(f"  Total politicians: {stats['total_politicians']}")
        print(f"  Active: {stats['active']}")
        print(f"  Retiring: {stats['retiring']}")
        print(f"  Retired: {stats['retired']}")

        print(f"\n{'-'*70}")
        print("PROCESSING UPDATES")
        print(f"{'-'*70}\n")

        # Process each update
        success_count = 0
        error_count = 0

        for politician_name, update_info in updates.items():
            try:
                action = update_info.get('action')
                reason = update_info.get('reason', 'No reason provided')

                print(f"📝 {politician_name}")
                print(f"   Action: {action}")
                print(f"   Reason: {reason}")

                if action == 'set_retiring':
                    self._set_retiring(politician_name, update_info)
                elif action == 'set_retired':
                    self._set_retired(politician_name, update_info)
                elif action == 'set_active':
                    self._set_active(politician_name, update_info)
                elif action == 'add_new':
                    self._add_new_politician(politician_name, update_info)
                else:
                    print(f"   ❌ Unknown action: {action}")
                    error_count += 1
                    continue

                print(f"   ✅ Success")
                success_count += 1
                self.changes_made.append({
                    'politician': politician_name,
                    'action': action,
                    'reason': reason
                })

            except Exception as e:
                print(f"   ❌ Error: {e}")
                error_count += 1

            print()

        # Save changes
        if success_count > 0:
            self.tracker._save_registry()
            print(f"{'='*70}")
            print(f"✅ UPDATES COMPLETE")
            print(f"{'='*70}")
            print(f"  Successful: {success_count}")
            print(f"  Errors: {error_count}")
            print(f"  Registry saved to: data/politician_registry.json")

            # Show updated stats
            stats = self.tracker.get_summary_stats()
            print(f"\nUpdated Registry Stats:")
            print(f"  Total politicians: {stats['total_politicians']}")
            print(f"  Active: {stats['active']}")
            print(f"  Retiring: {stats['retiring']}")
            print(f"  Retired: {stats['retired']}")

            self._show_weight_changes()

            return True
        else:
            print(f"{'='*70}")
            print(f"⚠️  NO CHANGES MADE")
            print(f"{'='*70}")
            print(f"  Errors: {error_count}")
            return False

    def _set_retiring(self, name: str, info: Dict):
        """Mark politician as retiring"""
        self.tracker.update_politician_status(
            name,
            status='retiring',
            term_ended=info.get('term_ended'),
            retirement_announced=info.get('retirement_announced')
        )

    def _set_retired(self, name: str, info: Dict):
        """Mark politician as retired"""
        self.tracker.update_politician_status(
            name,
            status='retired',
            term_ended=info.get('term_ended'),
            retirement_announced=info.get('retirement_announced')
        )

    def _set_active(self, name: str, info: Dict):
        """Mark politician as active (e.g., returned to office)"""
        politician = self.tracker.get_politician_info(name)
        if politician:
            politician['current_status'] = 'active'
            politician['term_started'] = info.get('term_started')
            politician['term_ended'] = None
            politician['retirement_announced'] = None
        else:
            raise ValueError(f"Politician '{name}' not found in registry")

    def _add_new_politician(self, name: str, info: Dict):
        """Add new politician to registry"""
        self.tracker.add_politician(
            full_name=name,
            party=info.get('party', 'Unknown'),
            office=info.get('office', 'House'),
            state=info.get('state', ''),
            base_weight=info.get('base_weight', 1.0),
            status='active',
            district=info.get('district'),
            notes=info.get('reason', '')
        )

    def _show_weight_changes(self):
        """Show how weights changed for affected politicians"""
        if not self.changes_made:
            return

        print(f"\n{'-'*70}")
        print("WEIGHT CHANGES")
        print(f"{'-'*70}")

        for change in self.changes_made:
            name = change['politician']
            info = self.tracker.get_politician_info(name)
            if info:
                base_weight = info.get('base_weight', 1.0)
                current_weight = self.tracker.calculate_time_decay_weight(name)

                status = info.get('current_status', 'unknown')
                multiplier = current_weight / base_weight if base_weight > 0 else 0

                print(f"\n{name}")
                print(f"  Status: {status}")
                print(f"  Base weight: {base_weight:.2f}x")
                print(f"  Current weight: {current_weight:.2f}x ({multiplier:.1f}x multiplier)")

                if status == 'retiring':
                    print(f"  💡 Boosted for lame duck urgency!")
                elif status == 'retired':
                    term_ended = info.get('term_ended')
                    if term_ended:
                        end_date = datetime.fromisoformat(term_ended)
                        days = (datetime.now() - end_date).days
                        print(f"  📉 Time-decay active ({days} days since retirement)")


def print_usage_guide():
    """Print helpful usage guide"""
    print(f"\n{'='*70}")
    print("USAGE GUIDE")
    print(f"{'='*70}")
    print("""
This script helps you maintain politician statuses. Here's how to use it:

1. GATHER INFORMATION
   - Check congress.gov for current members
   - Review news for retirement announcements
   - Check Capitol Trades for new notable traders

2. EDIT THIS SCRIPT
   - Scroll to the UPDATES dictionary at the top
   - Uncomment and modify examples
   - Or add new entries following the examples

3. RUN THE SCRIPT
   python update_politician_status.py

4. REVIEW CHANGES
   - Script shows before/after stats
   - Review weight changes
   - Verify everything looks correct

5. COMMIT CHANGES
   git add data/politician_registry.json
   git commit -m "Update politician statuses - Q4 2024"
   git push

COMMON ACTIONS:

├── Set Retiring (announced but not yet left):
│   'Name': {
│       'action': 'set_retiring',
│       'term_ended': '2025-01-03',
│       'retirement_announced': '2024-11-15',
│       'reason': 'Announced retirement'
│   }
│
├── Set Retired (has left office):
│   'Name': {
│       'action': 'set_retired',
│       'term_ended': '2025-01-03',
│       'reason': 'Left office'
│   }
│
├── Add New Politician:
│   'Name': {
│       'action': 'add_new',
│       'party': 'D',
│       'office': 'House',
│       'state': 'CA',
│       'base_weight': 1.2,
│       'reason': 'High-volume trader'
│   }
│
└── Set Active (returned to office):
    'Name': {
        'action': 'set_active',
        'term_started': '2025-01-03',
        'reason': 'Re-elected'
    }

RECOMMENDED SCHEDULE:
- After each election (every 2 years)
- When retirements announced (as they happen)
- Quarterly review (Jan, Apr, Jul, Oct)
""")


def main():
    """Main execution"""
    print_usage_guide()

    if UPDATE_NOTES.strip():
        print(f"\n{'='*70}")
        print("UPDATE NOTES")
        print(f"{'='*70}")
        print(UPDATE_NOTES)

    # Confirm before proceeding
    if UPDATES:
        print(f"\n⚠️  This will modify data/politician_registry.json")
        response = input("Continue? (y/n): ").lower().strip()
        if response != 'y':
            print("❌ Cancelled")
            return 1

    # Process updates
    updater = PoliticianStatusUpdater()
    success = updater.process_updates(UPDATES)

    if success:
        print(f"\n{'='*70}")
        print("NEXT STEPS")
        print(f"{'='*70}")
        print("""
1. Review the changes above
2. Commit the updated registry:

   git add data/politician_registry.json
   git commit -m "Update politician statuses - $(date +%Y-%m-%d)"
   git push

3. The time-decay system will automatically apply updated weights
   in the next pipeline run!
""")
        return 0
    else:
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
