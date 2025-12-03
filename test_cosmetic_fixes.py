#!/usr/bin/env python3
"""
Test script to verify cosmetic email fixes.

Tests:
1. Industry "nan" filtering
2. Title normalization (Ceo(1) -> CEO)
3. Entity grouping (LLC series deduplication)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

import pandas as pd
from process_signals import (
    _is_valid_field,
    _clean_title_artifacts,
    expand_title,
    normalize_title,
    _extract_entity_base_name,
    _should_group_entities,
    format_insiders_structured
)

def test_issue_1_industry_nan_filtering():
    """Test Issue 1: Industry 'nan' values are filtered out."""
    print("\n" + "="*60)
    print("TEST 1: Industry 'nan' Filtering")
    print("="*60)

    test_cases = [
        (None, False, "None value"),
        ("nan", False, "String 'nan'"),
        ("NaN", False, "String 'NaN'"),
        ("null", False, "String 'null'"),
        ("", False, "Empty string"),
        ("N/A", False, "String 'N/A'"),
        ("Technology", True, "Valid sector"),
        ("Healthcare", True, "Valid industry"),
        (float('nan'), False, "pandas NaN"),
    ]

    passed = 0
    failed = 0

    for value, expected, description in test_cases:
        try:
            result = _is_valid_field(value)
            if result == expected:
                print(f"✅ PASS: {description} - {repr(value)} -> {result}")
                passed += 1
            else:
                print(f"❌ FAIL: {description} - Expected {expected}, got {result}")
                failed += 1
        except Exception as e:
            print(f"❌ ERROR: {description} - {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0

def test_issue_2_title_normalization():
    """Test Issue 2: Title normalization removes (1) suffixes."""
    print("\n" + "="*60)
    print("TEST 2: Title Normalization")
    print("="*60)

    test_cases = [
        ("Ceo(1)", "CEO", "Ceo(1) -> CEO"),
        ("Cfo(2)", "CFO", "Cfo(2) -> CFO"),
        ("Director", "Director", "Director unchanged"),
        ("10%", "10% Owner", "10% -> 10% Owner"),
        ("Pres, CEO", "President, CEO", "Multiple titles"),
        ("SVP & CFO", "Senior Vice President, CFO", "SVP & CFO expansion"),
        ("Dir", "Director", "Dir -> Director"),
        ("Exec COB", "Executive Chairman of the Board", "Exec COB expansion"),
    ]

    passed = 0
    failed = 0

    for input_title, expected, description in test_cases:
        result = expand_title(input_title)
        if result == expected:
            print(f"✅ PASS: {description} - '{input_title}' -> '{result}'")
            passed += 1
        else:
            print(f"❌ FAIL: {description} - Expected '{expected}', got '{result}'")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0

def test_issue_3_entity_grouping():
    """Test Issue 3: Entity grouping for LLC series."""
    print("\n" + "="*60)
    print("TEST 3: Entity Grouping (LLC Series Deduplication)")
    print("="*60)

    # Test base name extraction
    print("\nTesting base name extraction:")
    test_cases = [
        ("LLC Series U of Um Partners", "Um Partners LLC", "U"),
        ("LLC Series R of Um Partners", "Um Partners LLC", "R"),
        ("Series A LP of ABC Fund", "ABC Fund LP", "A"),
        ("John Doe", "John Doe", None),
    ]

    passed = 0
    failed = 0

    for name, expected_base, expected_series in test_cases:
        base, series = _extract_entity_base_name(name)
        if base == expected_base and series == expected_series:
            print(f"✅ PASS: '{name}' -> base='{base}', series='{series}'")
            passed += 1
        else:
            print(f"❌ FAIL: '{name}' - Expected base='{expected_base}', series='{expected_series}', got base='{base}', series='{series}'")
            failed += 1

    # Test entity grouping
    print("\nTesting entity grouping:")
    group_test_cases = [
        ("LLC Series U of Um Partners", "LLC Series R of Um Partners", True, "Same base, different series"),
        ("LLC Series A of Fund X", "LLC Series B of Fund X", True, "Same fund, different series"),
        ("John Doe", "Jane Smith", False, "Different people"),
        ("ABC LLC", "XYZ LLC", False, "Different companies"),
    ]

    for name1, name2, expected, description in group_test_cases:
        result = _should_group_entities(name1, name2)
        if result == expected:
            print(f"✅ PASS: {description} - '{name1}' & '{name2}' -> {result}")
            passed += 1
        else:
            print(f"❌ FAIL: {description} - Expected {expected}, got {result}")
            failed += 1

    # Test format_insiders_structured with grouped entities
    print("\nTesting format_insiders_structured with grouped entities:")
    test_df = pd.DataFrame([
        {'insider': 'LLC Series U of Um Partners', 'title': '10%', 'value_calc': 815000},
        {'insider': 'LLC Series R of Um Partners', 'title': '10%', 'value_calc': 144000},
        {'insider': 'Dylan Lissette', 'title': 'Director', 'value_calc': 70000},
    ])

    _, insiders_data, insiders_plain = format_insiders_structured(test_df, limit=10)

    print(f"\nInsiders found: {len(insiders_data)}")
    for insider in insiders_data:
        print(f"  - {insider['name']}: {insider['title']} - ${insider['value']:,}")
        if insider.get('is_grouped') and insider.get('series'):
            for s in insider['series']:
                print(f"    ├─ Series {s['series']}: ${s['value']:,}")

    # Check if Um Partners LLC was grouped
    um_partners_found = False
    for insider in insiders_data:
        if 'Um Partners' in insider['name']:
            um_partners_found = True
            if insider.get('is_grouped') and len(insider.get('series', [])) == 2:
                print(f"✅ PASS: Um Partners LLC grouped correctly with 2 series")
                passed += 1
            else:
                print(f"❌ FAIL: Um Partners LLC not grouped correctly")
                failed += 1
            break

    if not um_partners_found:
        print(f"❌ FAIL: Um Partners LLC not found in results")
        failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("COSMETIC EMAIL FIXES - TEST SUITE")
    print("="*60)

    results = []

    # Run all tests
    results.append(("Issue 1: Industry 'nan' Filtering", test_issue_1_industry_nan_filtering()))
    results.append(("Issue 2: Title Normalization", test_issue_2_title_normalization()))
    results.append(("Issue 3: Entity Grouping", test_issue_3_entity_grouping()))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    all_passed = True
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False

    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("="*60)
        return 0
    else:
        print("⚠️  SOME TESTS FAILED")
        print("="*60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
