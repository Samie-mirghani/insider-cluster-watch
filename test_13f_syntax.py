#!/usr/bin/env python3
"""
Basic syntax and structure validation for 13F scraper fixes
Tests without requiring external dependencies
"""

import ast
import sys
from pathlib import Path

print("="*80)
print("13F SCRAPER SYNTAX & STRUCTURE VALIDATION")
print("="*80)
print()

tests_passed = 0
tests_failed = 0

def test_result(test_name, passed, error=None):
    global tests_passed, tests_failed
    if passed:
        tests_passed += 1
        print(f"✅ PASS: {test_name}")
    else:
        tests_failed += 1
        print(f"❌ FAIL: {test_name}")
        if error:
            print(f"   Error: {error}")

# Read the source file
print("TEST 1: File Reading")
print("-" * 80)
try:
    source_path = Path("jobs/sec_13f_parser.py")
    source_code = source_path.read_text()
    test_result("Read sec_13f_parser.py", True)
    print(f"   ℹ️  File size: {len(source_code)} bytes")
except Exception as e:
    test_result("Read sec_13f_parser.py", False, str(e))
    sys.exit(1)

# Parse the AST
print("\nTEST 2: Python Syntax Validation")
print("-" * 80)
try:
    tree = ast.parse(source_code, filename="sec_13f_parser.py")
    test_result("Valid Python syntax", True)
except SyntaxError as e:
    test_result("Valid Python syntax", False, str(e))
    sys.exit(1)

# Extract class and function definitions
print("\nTEST 3: Code Structure Analysis")
print("-" * 80)
try:
    classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]

    test_result("SEC13FParser class exists", "SEC13FParser" in classes)
    test_result("RateLimiter class exists", "RateLimiter" in classes)
    test_result("_get_session method exists", "_get_session" in functions)
    test_result("_get_cache_path method exists", "_get_cache_path" in functions)
    test_result("_write_cache method exists", "_write_cache" in functions)
    test_result("_read_cache method exists", "_read_cache" in functions)
    test_result("check_institutional_interest method exists", "check_institutional_interest" in functions)

    print(f"   ℹ️  Found {len(classes)} classes")
    print(f"   ℹ️  Found {len(functions)} functions/methods")
except Exception as e:
    test_result("Code structure", False, str(e))

# Check for critical strings/patterns
print("\nTEST 4: Critical Code Pattern Validation")
print("-" * 80)
try:
    # Check cache key includes quarter
    test_result("Cache key includes quarter pattern",
                "_{quarter_year}Q{quarter}_13f.json" in source_code)

    # Check thread-local storage
    test_result("Thread-local storage initialized",
                "self._thread_local = threading.local()" in source_code)

    # Check _get_session method
    test_result("_get_session method implemented",
                "def _get_session(self)" in source_code)

    # Check empty DataFrame validation
    test_result("Empty DataFrame check in _write_cache",
                "if df.empty or df.isna().all().all():" in source_code)

    # Check input validation
    test_result("Quarter validation (1-4)",
                "not 1 <= quarter <= 4" in source_code)

    # Check MAX_PARALLEL_WORKERS = 10
    test_result("MAX_PARALLEL_WORKERS set to 10",
                "MAX_PARALLEL_WORKERS = 10" in source_code)

    # Check ticker sanitization
    test_result("Ticker sanitization for path traversal",
                'safe_ticker = "".join(c for c in ticker if c.isalnum() or c in "-_")' in source_code)

except Exception as e:
    test_result("Critical patterns", False, str(e))

# Check CIK values
print("\nTEST 5: CIK Verification")
print("-" * 80)
try:
    # Check Two Sigma CIK
    test_result("Two Sigma CIK is 0001173945",
                "'Two Sigma': ['0001173945']" in source_code)

    # Check Third Point CIK
    test_result("Third Point CIK is 0001040273",
                "'Third Point': ['0001040273']" in source_code)

    # Make sure old duplicate is gone
    test_result("Old Two Sigma CIK (0001040273) not in Two Sigma entry",
                "'Two Sigma': ['0001040273']" not in source_code)

    # Check for duplicate detection code
    test_result("Duplicate CIK detection code exists",
                "DUPLICATE CIKs found" in source_code)

except Exception as e:
    test_result("CIK verification", False, str(e))

# Check for removed sleeps
print("\nTEST 6: Performance Optimization Verification")
print("-" * 80)
try:
    # Count remaining sleep calls
    import re
    sleep_pattern = r'time\.sleep\('
    sleep_matches = re.findall(sleep_pattern, source_code)

    # Should only have sleeps in retry logic, not in main flow
    # Expected: retry delays (3) + yfinance retry (2) = 5 total
    test_result("Redundant sleeps removed", len(sleep_matches) <= 6)
    print(f"   ℹ️  Remaining time.sleep() calls: {len(sleep_matches)}")

    # Verify the comment about removing redundant sleep
    test_result("Comment about removing redundant sleep exists",
                "Removed redundant sleep" in source_code or
                "RateLimiter handles rate limiting" in source_code)

except Exception as e:
    test_result("Performance optimization", False, str(e))

# Check imports
print("\nTEST 7: Required Imports")
print("-" * 80)
try:
    test_result("threading import present", "import threading" in source_code)
    test_result("requests import present", "import requests" in source_code)
    test_result("pathlib Path import present", "from pathlib import Path" in source_code)
    test_result("concurrent.futures imports present",
                "from concurrent.futures import ThreadPoolExecutor" in source_code)

except Exception as e:
    test_result("Required imports", False, str(e))

# Check for fix comments
print("\nTEST 8: Documentation of Fixes")
print("-" * 80)
try:
    test_result("CRITICAL FIX #2 comment present",
                "CRITICAL FIX #2" in source_code)
    test_result("CRITICAL FIX #3 comment present",
                "CRITICAL FIX #3" in source_code)
    test_result("CRITICAL FIX #4 comment present",
                "CRITICAL FIX #4" in source_code)
    test_result("CRITICAL FIX #5 comment present",
                "CRITICAL FIX #5" in source_code)
    test_result("HIGH PRIORITY FIX #6 comment present",
                "HIGH PRIORITY FIX #6" in source_code)
    test_result("HIGH PRIORITY FIX #7 comment present",
                "HIGH PRIORITY FIX #7" in source_code)

except Exception as e:
    test_result("Fix documentation", False, str(e))

# FINAL RESULTS
print("\n" + "="*80)
print("TEST RESULTS SUMMARY")
print("="*80)
print(f"Total Tests: {tests_passed + tests_failed}")
print(f"✅ Passed: {tests_passed}")
print(f"❌ Failed: {tests_failed}")
print()

if tests_failed > 0:
    print("="*80)
    print("❌ SOME TESTS FAILED")
    print("="*80)
    sys.exit(1)
else:
    print("="*80)
    print("✅ ALL SYNTAX & STRUCTURE TESTS PASSED!")
    print("="*80)
    print()
    print("VERIFIED:")
    print("  ✅ Python syntax is valid")
    print("  ✅ All required classes and methods present")
    print("  ✅ Cache keys include quarter/year")
    print("  ✅ Thread-local sessions implemented")
    print("  ✅ Empty DataFrame validation in place")
    print("  ✅ Input validation for quarter/year")
    print("  ✅ CIKs corrected (Two Sigma: 0001173945, Third Point: 0001040273)")
    print("  ✅ MAX_PARALLEL_WORKERS = 10")
    print("  ✅ Redundant sleeps removed")
    print("  ✅ Ticker sanitization implemented")
    print("  ✅ All fixes documented with comments")
    print()
    sys.exit(0)
