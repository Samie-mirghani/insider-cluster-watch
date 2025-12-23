#!/usr/bin/env python3
"""
Simple standalone test for quarterly politician status check mechanism.
Tests the logic without importing the full main.py file.
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path

# Test configuration
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
TIMESTAMP_FILE = os.path.join(DATA_DIR, 'politician_status_last_checked.json')
POLITICIAN_STATUS_CHECK_INTERVAL_DAYS = 90

# Standalone implementations of the functions (copied from main.py logic)
def should_check_politician_status_standalone(force_check=False):
    """Standalone version of should_check_politician_status for testing."""
    if force_check:
        print("   🔧 FORCE_POLITICIAN_CHECK enabled - bypassing interval check")
        return True

    if not os.path.exists(TIMESTAMP_FILE):
        return True

    try:
        with open(TIMESTAMP_FILE, 'r') as f:
            data = json.load(f)
            last_checked_str = data.get('last_checked')

            if not last_checked_str:
                return True

            last_checked = datetime.strptime(last_checked_str, '%Y-%m-%d %H:%M:%S')
            days_since_check = (datetime.utcnow() - last_checked).days

            if days_since_check >= POLITICIAN_STATUS_CHECK_INTERVAL_DAYS:
                return True
            else:
                next_check_days = POLITICIAN_STATUS_CHECK_INTERVAL_DAYS - days_since_check
                print(f"   ℹ️  Politician status check skipped (last checked {days_since_check} days ago, next check in {next_check_days} days)")
                return False

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"   ⚠️  Corrupted timestamp file, running check: {e}")
        return True

def mark_politician_status_checked_standalone():
    """Standalone version of mark_politician_status_checked for testing."""
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp_data = {
        'last_checked': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        'next_check_due': (datetime.utcnow() + timedelta(days=POLITICIAN_STATUS_CHECK_INTERVAL_DAYS)).strftime('%Y-%m-%d'),
        'check_interval_days': POLITICIAN_STATUS_CHECK_INTERVAL_DAYS
    }

    with open(TIMESTAMP_FILE, 'w') as f:
        json.dump(timestamp_data, f, indent=2)

def cleanup_test_file():
    """Remove the timestamp file for testing."""
    if os.path.exists(TIMESTAMP_FILE):
        os.remove(TIMESTAMP_FILE)

# Test functions
def test_scenario_1():
    """Scenario 1: First run ever (no timestamp file) - should execute."""
    print("\n" + "="*70)
    print("SCENARIO 1: First Run (No Timestamp File)")
    print("="*70)
    cleanup_test_file()

    result = should_check_politician_status_standalone()
    print(f"Result: {result}")

    if result:
        print("✅ PASS: Correctly executes check on first run")
        return True
    else:
        print("❌ FAIL: Should execute check when no timestamp exists")
        return False

def test_scenario_2():
    """Scenario 2: Second run same day - should skip."""
    print("\n" + "="*70)
    print("SCENARIO 2: Same Day (Should Skip)")
    print("="*70)

    # Create timestamp for today
    mark_politician_status_checked_standalone()
    print("Created timestamp: checked today")

    result = should_check_politician_status_standalone()
    print(f"Result: {result}")

    if not result:
        print("✅ PASS: Correctly skips check on same day")
        return True
    else:
        print("❌ FAIL: Should skip check when run same day")
        return False

def test_scenario_3():
    """Scenario 3: 89 days later - should skip."""
    print("\n" + "="*70)
    print("SCENARIO 3: 89 Days Later (Should Skip)")
    print("="*70)

    # Create timestamp from 89 days ago
    last_checked = datetime.utcnow() - timedelta(days=89)
    timestamp_data = {
        'last_checked': last_checked.strftime('%Y-%m-%d %H:%M:%S'),
        'next_check_due': (last_checked + timedelta(days=90)).strftime('%Y-%m-%d'),
        'check_interval_days': 90
    }
    with open(TIMESTAMP_FILE, 'w') as f:
        json.dump(timestamp_data, f, indent=2)
    print("Created timestamp: checked 89 days ago")

    result = should_check_politician_status_standalone()
    print(f"Result: {result}")

    if not result:
        print("✅ PASS: Correctly skips check after 89 days")
        return True
    else:
        print("❌ FAIL: Should skip check when only 89 days have passed")
        return False

def test_scenario_4():
    """Scenario 4: 90 days later - should execute."""
    print("\n" + "="*70)
    print("SCENARIO 4: 90 Days Later (Should Execute)")
    print("="*70)

    # Create timestamp from 90 days ago
    last_checked = datetime.utcnow() - timedelta(days=90)
    timestamp_data = {
        'last_checked': last_checked.strftime('%Y-%m-%d %H:%M:%S'),
        'next_check_due': (last_checked + timedelta(days=90)).strftime('%Y-%m-%d'),
        'check_interval_days': 90
    }
    with open(TIMESTAMP_FILE, 'w') as f:
        json.dump(timestamp_data, f, indent=2)
    print("Created timestamp: checked 90 days ago")

    result = should_check_politician_status_standalone()
    print(f"Result: {result}")

    if result:
        print("✅ PASS: Correctly executes check after 90 days")
        return True
    else:
        print("❌ FAIL: Should execute check when 90 days have passed")
        return False

def test_scenario_5():
    """Scenario 5: Force check flag - should execute regardless."""
    print("\n" + "="*70)
    print("SCENARIO 5: Force Check Flag (Should Execute)")
    print("="*70)

    # Create recent timestamp (checked 1 day ago)
    last_checked = datetime.utcnow() - timedelta(days=1)
    timestamp_data = {
        'last_checked': last_checked.strftime('%Y-%m-%d %H:%M:%S'),
        'next_check_due': (last_checked + timedelta(days=90)).strftime('%Y-%m-%d'),
        'check_interval_days': 90
    }
    with open(TIMESTAMP_FILE, 'w') as f:
        json.dump(timestamp_data, f, indent=2)
    print("Created timestamp: checked 1 day ago")

    result = should_check_politician_status_standalone(force_check=True)
    print(f"Result: {result}")

    if result:
        print("✅ PASS: Force check correctly bypasses interval")
        return True
    else:
        print("❌ FAIL: Force check should execute regardless of interval")
        return False

def test_scenario_6():
    """Scenario 6: Corrupted timestamp file - should execute."""
    print("\n" + "="*70)
    print("SCENARIO 6: Corrupted File (Should Execute)")
    print("="*70)

    # Create corrupted JSON
    with open(TIMESTAMP_FILE, 'w') as f:
        f.write("{ invalid json }")
    print("Created corrupted timestamp file")

    result = should_check_politician_status_standalone()
    print(f"Result: {result}")

    if result:
        print("✅ PASS: Corrupted file correctly triggers check (safety fallback)")
        return True
    else:
        print("❌ FAIL: Corrupted file should trigger check for safety")
        return False

def test_scenario_7():
    """Scenario 7: Verify timestamp file creation."""
    print("\n" + "="*70)
    print("SCENARIO 7: Timestamp File Creation")
    print("="*70)

    cleanup_test_file()
    mark_politician_status_checked_standalone()
    print("Called mark_politician_status_checked()")

    if not os.path.exists(TIMESTAMP_FILE):
        print("❌ FAIL: Timestamp file was not created")
        return False

    with open(TIMESTAMP_FILE, 'r') as f:
        data = json.load(f)

    print(f"Timestamp file contents: {json.dumps(data, indent=2)}")

    # Validate required fields
    if 'last_checked' not in data:
        print("❌ FAIL: Missing 'last_checked' field")
        return False

    if 'next_check_due' not in data:
        print("❌ FAIL: Missing 'next_check_due' field")
        return False

    if data.get('check_interval_days') != 90:
        print(f"❌ FAIL: Incorrect interval (expected 90, got {data.get('check_interval_days')})")
        return False

    print("✅ PASS: Timestamp file created with correct structure")
    return True

def run_all_tests():
    """Run all test scenarios."""
    print("="*70)
    print("QUARTERLY POLITICIAN STATUS CHECK - TEST SUITE")
    print("="*70)

    tests = [
        test_scenario_1,
        test_scenario_2,
        test_scenario_3,
        test_scenario_4,
        test_scenario_5,
        test_scenario_6,
        test_scenario_7
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"\n❌ EXCEPTION in {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test.__name__, False))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\n{passed}/{total} tests passed ({passed/total*100:.1f}%)")

    # Cleanup
    cleanup_test_file()
    print(f"\n🧹 Cleaned up test file")

    return passed == total

if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
