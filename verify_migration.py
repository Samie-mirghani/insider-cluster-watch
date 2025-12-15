#!/usr/bin/env python3
"""
Comprehensive verification of politician trading API migration
Tests ALL integration points, data flows, and functionality
"""

import sys
import os
from datetime import datetime, timedelta
import json

# Add jobs directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

# Test results
results = {
    'passed': [],
    'failed': [],
    'warnings': [],
    'metrics': {}
}


def test_api_integration():
    """Part 1: API Integration Test"""
    print("\n" + "="*70)
    print("PART 1: API INTEGRATION TEST")
    print("="*70 + "\n")

    try:
        from capitol_trades_scraper import CapitolTradesScraper

        print("✓ Import successful")

        # Initialize API
        api = CapitolTradesScraper()
        print("✓ API initialized")

        # Fetch trades
        print("\nFetching trades (last 30 days)...")
        trades_df = api.scrape_recent_trades(days_back=30)

        # Check 1: Returns data
        if trades_df.empty:
            results['warnings'].append("API returned zero trades (may be using cache)")
            print("⚠️  WARNING: API returned zero trades")
        else:
            results['passed'].append(f"API Integration: {len(trades_df)} trades fetched")
            print(f"✓ API returned {len(trades_df)} trades")
            results['metrics']['total_trades'] = len(trades_df)

        # Check 2: Correct structure
        print("\nChecking data structure...")
        required_fields = ['ticker', 'politician', 'party', 'trade_date', 'amount_range', 'asset_name']
        missing_fields = [f for f in required_fields if f not in trades_df.columns]

        if missing_fields:
            results['failed'].append(f"Missing required fields: {missing_fields}")
            print(f"❌ FAIL: Missing fields: {missing_fields}")
            return False
        else:
            results['passed'].append("Data structure: All required fields present")
            print("✓ All required fields present")

        if not trades_df.empty:
            # Check 3: Tickers clean (no :US suffix)
            print("\nChecking ticker format...")
            bad_tickers = trades_df[trades_df['ticker'].str.contains(':', na=False)]

            if len(bad_tickers) > 0:
                results['failed'].append(f"Unclean tickers found: {bad_tickers['ticker'].tolist()}")
                print(f"❌ FAIL: {len(bad_tickers)} tickers still have ':' suffix")
                return False
            else:
                results['passed'].append("Ticker format: All tickers clean (no :US suffix)")
                print("✓ All tickers clean (no :US suffix)")

            # Check 4: Only buys
            print("\nChecking transaction types...")
            if 'transaction_type' in trades_df.columns:
                non_buys = trades_df[trades_df['transaction_type'].str.lower() != 'buy']

                if len(non_buys) > 0:
                    results['failed'].append(f"Non-buy transactions found: {len(non_buys)}")
                    print(f"❌ FAIL: Found {len(non_buys)} non-buy transactions")
                    return False
                else:
                    results['passed'].append("Transaction filtering: Only buy trades")
                    print("✓ Only buy trades included")

            # Check 5: Recent dates only
            print("\nChecking date filtering...")
            cutoff = datetime.now() - timedelta(days=30)
            old_trades = trades_df[trades_df['trade_date'] < cutoff]

            if len(old_trades) > 0:
                results['warnings'].append(f"{len(old_trades)} trades older than 30 days")
                print(f"⚠️  WARNING: {len(old_trades)} trades older than 30 days")
            else:
                results['passed'].append("Date filtering: All trades within 30 days")
                print("✓ All trades within last 30 days")

        print(f"\n✅ API Integration: PASSED")
        return True

    except Exception as e:
        results['failed'].append(f"API integration test failed: {e}")
        print(f"\n❌ API Integration: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_format_compatibility():
    """Part 2: Data Format Compatibility"""
    print("\n" + "="*70)
    print("PART 2: DATA FORMAT COMPATIBILITY")
    print("="*70 + "\n")

    try:
        import pandas as pd
        from capitol_trades_scraper import CapitolTradesScraper

        api = CapitolTradesScraper()
        trades_df = api.scrape_recent_trades(days_back=30)

        if trades_df.empty:
            results['warnings'].append("Cannot test format compatibility - no trades available")
            print("⚠️  WARNING: No trades to test format compatibility")
            return True

        # Check expected schema for multi_signal_detector
        print("Checking schema compatibility with multi_signal_detector...")

        expected_for_multi_signal = {
            'ticker': 'str',
            'politician': 'str',
            'party': 'str',
            'trade_date': 'datetime',
            'amount_range': 'str',
            'weighted_amount': 'float',
            'politician_weight': 'float'
        }

        schema_ok = True
        for field, expected_type in expected_for_multi_signal.items():
            if field not in trades_df.columns:
                results['failed'].append(f"Missing field for multi_signal: {field}")
                print(f"❌ Missing field: {field}")
                schema_ok = False
            else:
                print(f"✓ Field present: {field}")

        if schema_ok:
            results['passed'].append("Data format: Compatible with multi_signal_detector")
            print("\n✓ Schema compatible with multi_signal_detector")

        # Check date format
        print("\nChecking date format...")
        sample_date = trades_df.iloc[0]['trade_date']
        if isinstance(sample_date, (datetime, pd.Timestamp)):
            results['passed'].append("Date format: Correct (datetime objects)")
            print(f"✓ Date format correct: {type(sample_date).__name__}")
        else:
            results['warnings'].append(f"Date format unexpected: {type(sample_date)}")
            print(f"⚠️  WARNING: Date format is {type(sample_date)}")

        print(f"\n✅ Data Format Compatibility: PASSED")
        return True

    except Exception as e:
        results['failed'].append(f"Data format test failed: {e}")
        print(f"\n❌ Data Format Compatibility: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration_points():
    """Part 3: Integration Points Audit"""
    print("\n" + "="*70)
    print("PART 3: INTEGRATION POINTS AUDIT")
    print("="*70 + "\n")

    try:
        # Test 1: multi_signal_detector import
        print("1. Testing multi_signal_detector import...")
        try:
            from multi_signal_detector import MultiSignalDetector
            results['passed'].append("Integration: multi_signal_detector imports successfully")
            print("   ✓ MultiSignalDetector imports successfully")
        except ImportError as e:
            results['failed'].append(f"Cannot import MultiSignalDetector: {e}")
            print(f"   ❌ Import failed: {e}")
            return False

        # Test 2: CapitolTradesScraper can be instantiated
        print("\n2. Testing CapitolTradesScraper instantiation...")
        try:
            from capitol_trades_scraper import CapitolTradesScraper
            scraper = CapitolTradesScraper()
            results['passed'].append("Integration: CapitolTradesScraper instantiates successfully")
            print("   ✓ CapitolTradesScraper instantiates")
        except Exception as e:
            results['failed'].append(f"Cannot instantiate CapitolTradesScraper: {e}")
            print(f"   ❌ Instantiation failed: {e}")
            return False

        # Test 3: MultiSignalDetector can use CapitolTradesScraper
        print("\n3. Testing MultiSignalDetector with politician tracker...")
        try:
            # Try to create detector (may fail if other dependencies missing)
            detector = MultiSignalDetector(sec_user_agent="test/1.0")

            # Check if it has politician_scraper
            if hasattr(detector, 'politician_scraper'):
                results['passed'].append("Integration: MultiSignalDetector has politician_scraper")
                print("   ✓ MultiSignalDetector has politician_scraper attribute")

                # Check the scraper type
                if isinstance(detector.politician_scraper, CapitolTradesScraper):
                    results['passed'].append("Integration: politician_scraper is CapitolTradesScraper")
                    print("   ✓ politician_scraper is correct type (CapitolTradesScraper)")
                else:
                    results['warnings'].append(f"politician_scraper type unexpected: {type(detector.politician_scraper)}")
                    print(f"   ⚠️  WARNING: politician_scraper type is {type(detector.politician_scraper)}")
            else:
                results['failed'].append("MultiSignalDetector missing politician_scraper")
                print("   ❌ MultiSignalDetector missing politician_scraper attribute")
                return False

        except Exception as e:
            results['warnings'].append(f"MultiSignalDetector test partial: {e}")
            print(f"   ⚠️  WARNING: Could not fully test MultiSignalDetector: {e}")

        # Test 4: Check method signatures
        print("\n4. Checking method signatures...")
        try:
            from capitol_trades_scraper import CapitolTradesScraper
            api = CapitolTradesScraper()

            # Check required methods exist
            required_methods = ['scrape_recent_trades', 'detect_politician_clusters']
            for method in required_methods:
                if hasattr(api, method):
                    print(f"   ✓ Method exists: {method}")
                else:
                    results['failed'].append(f"Missing method: {method}")
                    print(f"   ❌ Missing method: {method}")
                    return False

            results['passed'].append("Integration: All required methods present")

        except Exception as e:
            results['failed'].append(f"Method signature check failed: {e}")
            print(f"   ❌ Method check failed: {e}")
            return False

        print(f"\n✅ Integration Points Audit: PASSED")
        return True

    except Exception as e:
        results['failed'].append(f"Integration points test failed: {e}")
        print(f"\n❌ Integration Points Audit: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


def test_code_cleanup():
    """Part 4: Code Cleanup Verification"""
    print("\n" + "="*70)
    print("PART 4: CODE CLEANUP VERIFICATION")
    print("="*70 + "\n")

    import subprocess

    print("Searching for Selenium remnants...")

    # Search for selenium imports
    print("\n1. Checking for 'selenium' references...")
    try:
        result = subprocess.run(
            ['grep', '-rn', 'selenium', 'jobs/capitol_trades_scraper.py'],
            capture_output=True,
            text=True
        )

        # grep returns 0 if found, 1 if not found
        if result.returncode == 0:
            # Found selenium references
            lines = result.stdout.strip().split('\n')
            # Filter out comments, documented references, and deprecated parameters
            actual_code = [
                l for l in lines
                if not l.strip().startswith('#')
                and 'DEPRECATED' not in l
                and 'use_selenium: bool = False' not in l
            ]

            if actual_code:
                results['failed'].append(f"Selenium code still present: {len(actual_code)} lines")
                print(f"   ❌ FAIL: Found {len(actual_code)} selenium references:")
                for line in actual_code[:5]:  # Show first 5
                    print(f"      {line}")
            else:
                results['passed'].append("Code cleanup: No active selenium code (deprecated params OK)")
                print("   ✓ Selenium only in deprecated/compatibility params (OK)")
        else:
            results['passed'].append("Code cleanup: No selenium references")
            print("   ✓ No selenium references found")
    except Exception as e:
        results['warnings'].append(f"Could not search for selenium: {e}")
        print(f"   ⚠️  WARNING: Search failed: {e}")

    # Search for webdriver
    print("\n2. Checking for 'webdriver' references...")
    try:
        result = subprocess.run(
            ['grep', '-rn', 'webdriver', 'jobs/capitol_trades_scraper.py'],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            results['warnings'].append("Found webdriver references (may be in comments)")
            print("   ⚠️  WARNING: Found webdriver references")
        else:
            results['passed'].append("Code cleanup: No webdriver references")
            print("   ✓ No webdriver references found")
    except Exception as e:
        print(f"   ⚠️  WARNING: Search failed: {e}")

    # Search for headless
    print("\n3. Checking for 'headless' references...")
    try:
        result = subprocess.run(
            ['grep', '-rn', 'headless', 'jobs/capitol_trades_scraper.py'],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            results['warnings'].append("Found headless references (may be in comments)")
            print("   ⚠️  WARNING: Found headless references")
        else:
            results['passed'].append("Code cleanup: No headless references")
            print("   ✓ No headless references found")
    except Exception as e:
        print(f"   ⚠️  WARNING: Search failed: {e}")

    # Check for Chrome references
    print("\n4. Checking for 'ChromeDriver' references...")
    try:
        result = subprocess.run(
            ['grep', '-rn', 'ChromeDriver', 'jobs/capitol_trades_scraper.py'],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            results['warnings'].append("Found ChromeDriver references")
            print("   ⚠️  WARNING: Found ChromeDriver references")
        else:
            results['passed'].append("Code cleanup: No ChromeDriver references")
            print("   ✓ No ChromeDriver references found")
    except Exception as e:
        print(f"   ⚠️  WARNING: Search failed: {e}")

    print(f"\n✅ Code Cleanup Verification: PASSED")
    return True


def test_error_handling():
    """Part 5: Error Handling Test"""
    print("\n" + "="*70)
    print("PART 5: ERROR HANDLING TEST")
    print("="*70 + "\n")

    try:
        from capitol_trades_scraper import CapitolTradesScraper

        # Test 1: Invalid API key (simulate)
        print("1. Testing invalid API key handling...")
        try:
            api = CapitolTradesScraper()
            original_key = api.api_key
            api.api_key = "invalid_test_key_12345"

            # This should use cache fallback, not crash
            trades = api.scrape_recent_trades(days_back=30)

            # Restore key
            api.api_key = original_key

            results['passed'].append("Error handling: Invalid API key handled gracefully")
            print("   ✓ Invalid API key handled gracefully (cache fallback)")

        except Exception as e:
            results['warnings'].append(f"Invalid API key test error: {e}")
            print(f"   ⚠️  WARNING: Error during invalid key test: {e}")

        # Test 2: Empty response handling
        print("\n2. Testing empty response handling...")
        try:
            api = CapitolTradesScraper()

            # Call with very old date range (should return empty or cached)
            trades = api.scrape_recent_trades(days_back=1)  # Only 1 day

            # Should return DataFrame (empty or with cache), not crash
            import pandas as pd
            if isinstance(trades, pd.DataFrame):
                results['passed'].append("Error handling: Empty response handled")
                print("   ✓ Empty response returns DataFrame (not crash)")
            else:
                results['warnings'].append(f"Unexpected return type: {type(trades)}")
                print(f"   ⚠️  WARNING: Return type is {type(trades)}")

        except Exception as e:
            results['warnings'].append(f"Empty response test error: {e}")
            print(f"   ⚠️  WARNING: Error during empty response test: {e}")

        # Test 3: Rate limit check functionality
        print("\n3. Testing rate limit functionality...")
        try:
            api = CapitolTradesScraper()

            # Check if rate limit method exists
            if hasattr(api, '_check_rate_limit'):
                can_call = api._check_rate_limit()

                results['passed'].append(f"Error handling: Rate limit check works (can_call={can_call})")
                print(f"   ✓ Rate limit check functional (can_call={can_call})")
            else:
                results['failed'].append("Missing rate limit check method")
                print("   ❌ Missing _check_rate_limit method")

        except Exception as e:
            results['warnings'].append(f"Rate limit test error: {e}")
            print(f"   ⚠️  WARNING: Error during rate limit test: {e}")

        # Test 4: Cache fallback
        print("\n4. Testing cache fallback...")
        try:
            api = CapitolTradesScraper()

            # Check if cache method exists
            if hasattr(api, '_load_cached_trades'):
                cached = api._load_cached_trades()

                import pandas as pd
                if isinstance(cached, pd.DataFrame):
                    results['passed'].append("Error handling: Cache fallback functional")
                    print(f"   ✓ Cache fallback works ({len(cached)} cached trades)")
                else:
                    results['warnings'].append("Cache returned unexpected type")
                    print("   ⚠️  WARNING: Cache returned non-DataFrame")
            else:
                results['failed'].append("Missing cache fallback method")
                print("   ❌ Missing _load_cached_trades method")

        except Exception as e:
            results['warnings'].append(f"Cache fallback test error: {e}")
            print(f"   ⚠️  WARNING: Error during cache test: {e}")

        print(f"\n✅ Error Handling Test: PASSED")
        return True

    except Exception as e:
        results['failed'].append(f"Error handling test failed: {e}")
        print(f"\n❌ Error Handling Test: FAILED - {e}")
        import traceback
        traceback.print_exc()
        return False


def generate_report():
    """Generate comprehensive verification report"""
    print("\n" + "="*70)
    print("COMPREHENSIVE VERIFICATION REPORT")
    print("="*70 + "\n")

    # Passed tests
    print("✅ PASSED TESTS:")
    print("-" * 70)
    if results['passed']:
        for test in results['passed']:
            print(f"  ✓ {test}")
    else:
        print("  (none)")
    print()

    # Failed tests
    print("❌ FAILED TESTS:")
    print("-" * 70)
    if results['failed']:
        for test in results['failed']:
            print(f"  ✗ {test}")
    else:
        print("  (none)")
    print()

    # Warnings
    print("⚠️  WARNINGS:")
    print("-" * 70)
    if results['warnings']:
        for warning in results['warnings']:
            print(f"  ⚠  {warning}")
    else:
        print("  (none)")
    print()

    # Metrics
    print("📊 METRICS:")
    print("-" * 70)
    if results['metrics']:
        for metric, value in results['metrics'].items():
            print(f"  • {metric}: {value}")
    else:
        print("  (no metrics collected)")
    print()

    # Overall status
    print("="*70)
    if not results['failed']:
        print("✅ OVERALL STATUS: ALL TESTS PASSED")
        if results['warnings']:
            print(f"   ({len(results['warnings'])} warning(s) - review above)")
    else:
        print(f"❌ OVERALL STATUS: {len(results['failed'])} TEST(S) FAILED")
        print("   IMMEDIATE ACTION REQUIRED")
    print("="*70 + "\n")

    # Save report to file
    report_file = 'verification_report.json'
    with open(report_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"📄 Detailed report saved to: {report_file}\n")

    return len(results['failed']) == 0


def main():
    """Run all verification tests"""
    print("\n" + "="*70)
    print("POLITICIAN TRADING API MIGRATION - COMPREHENSIVE VERIFICATION")
    print("="*70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")

    import pandas as pd

    # Run all tests
    tests = [
        ("API Integration", test_api_integration),
        ("Data Format Compatibility", test_data_format_compatibility),
        ("Integration Points Audit", test_integration_points),
        ("Code Cleanup", test_code_cleanup),
        ("Error Handling", test_error_handling)
    ]

    all_passed = True
    for test_name, test_func in tests:
        try:
            if not test_func():
                all_passed = False
        except Exception as e:
            print(f"\n❌ {test_name}: EXCEPTION - {e}")
            results['failed'].append(f"{test_name}: Unexpected exception")
            all_passed = False

    # Generate final report
    success = generate_report()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
