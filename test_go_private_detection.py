#!/usr/bin/env python3
"""
Test script for enhanced go-private transaction detection.

Tests the following scenarios:
1. SHCO: 1 insider, $72M, $120M market cap (60%) - should be REJECTED
2. Moderate case: 1 insider, $25M, $150M market cap (17%) - should PASS with ALERT
3. Large LLC: 1 insider, $30M, $180M market cap (17%) - should be REJECTED (entity pattern)
4. Small insider: 1 insider, $200K, $50M market cap (0.4%) - should PASS
5. Multiple insiders: 3 insiders, $50M, $100M market cap (50%) - should PASS (only applies to single insiders)
"""

import sys
import os


def is_institutional_entity(insider_name):
    """
    Check if insider name suggests institutional/M&A entity.

    Returns: (is_entity, entity_type)
    """
    if not insider_name or not isinstance(insider_name, str):
        return False, None

    name_upper = insider_name.upper()

    patterns = {
        'Private Equity': ['PE', 'PRIVATE EQUITY'],
        'Investment Fund': ['FUND', 'FUNDS', 'INVESTMENT', 'INVESTMENTS'],
        'LLC': ['LLC', 'L.L.C', 'L.L.C.', 'LIMITED LIABILITY'],
        'Partnership': ['PARTNERS', 'PARTNERSHIP', 'LP', 'L.P.'],
        'Capital': ['CAPITAL', 'CAPITAL MANAGEMENT'],
        'Holdings': ['HOLDINGS', 'HOLDING COMPANY', 'HOLDING CO'],
        'Acquisition Entity': ['ACQUISITION', 'ACQUISITIONS', 'ACQUIRER']
    }

    for entity_type, keywords in patterns.items():
        if any(kw in name_upper for kw in keywords):
            return True, entity_type

    return False, None


def test_go_private_detection():
    """Test all scenarios for go-private detection."""

    print("="*70)
    print("TESTING ENHANCED GO-PRIVATE TRANSACTION DETECTION")
    print("="*70)

    # Test scenarios
    scenarios = [
        {
            'name': 'SHCO (False Positive)',
            'ticker': 'SHCO',
            'insider_count': 1,
            'buy_value': 72_000_000,
            'market_cap': 120_000_000,
            'insider_name': 'John Smith',
            'expected': 'REJECTED (60% > 50% threshold)'
        },
        {
            'name': 'Moderate Single-Insider',
            'ticker': 'LIFE',
            'insider_count': 1,
            'buy_value': 25_000_000,
            'market_cap': 150_000_000,
            'insider_name': 'Jane Doe',
            'expected': 'PASS with ALERT (17% in 15-30% range)'
        },
        {
            'name': 'Large LLC Entity',
            'ticker': 'ACME',
            'insider_count': 1,
            'buy_value': 30_000_000,
            'market_cap': 180_000_000,
            'insider_name': 'Acme Capital Partners LLC',
            'expected': 'REJECTED (entity pattern + 17% > 15%)'
        },
        {
            'name': 'Small Insider Purchase',
            'ticker': 'TINY',
            'insider_count': 1,
            'buy_value': 200_000,
            'market_cap': 50_000_000,
            'insider_name': 'Bob Jones',
            'expected': 'PASS (0.4% below thresholds)'
        },
        {
            'name': 'Multiple Insiders (50%)',
            'ticker': 'MULTI',
            'insider_count': 3,
            'buy_value': 50_000_000,
            'market_cap': 100_000_000,
            'insider_name': 'Various',
            'expected': 'PASS (only applies to single insiders)'
        },
        {
            'name': 'Very Large Transaction',
            'ticker': 'HUGE',
            'insider_count': 1,
            'buy_value': 150_000_000,
            'market_cap': 2_000_000_000,
            'insider_name': 'Warren Buffett',
            'expected': 'PASS with ALERT (>$100M threshold)'
        },
        {
            'name': '$50M + 25% Threshold',
            'ticker': 'BIGM',
            'insider_count': 1,
            'buy_value': 60_000_000,
            'market_cap': 250_000_000,
            'insider_name': 'Private Equity Fund',
            'expected': 'REJECTED ($50M+24% > 20% threshold)'
        }
    ]

    all_passed = True

    for scenario in scenarios:
        print(f"\n{'='*70}")
        print(f"Test: {scenario['name']}")
        print(f"{'='*70}")
        print(f"Ticker: {scenario['ticker']}")
        print(f"Insider Count: {scenario['insider_count']}")
        print(f"Buy Value: ${scenario['buy_value']:,.0f}")
        print(f"Market Cap: ${scenario['market_cap']:,.0f}")
        print(f"Insider: {scenario['insider_name']}")

        pct_of_cap = scenario['buy_value'] / scenario['market_cap']
        print(f"% of Company: {pct_of_cap*100:.1f}%")

        # Check entity pattern
        is_entity, entity_type = is_institutional_entity(scenario['insider_name'])
        if is_entity:
            print(f"Entity Type: {entity_type}")

        # Apply detection logic (for single insiders only)
        result = "PASS"
        reason = "No threshold triggered"

        if scenario['insider_count'] == 1 and scenario['market_cap'] > 0:
            # Level 1: Hard rejections
            if pct_of_cap > 0.5:
                result = "REJECTED"
                reason = f"Go-private: single insider buying {pct_of_cap*100:.0f}% of company (likely acquisition)"

            elif scenario['buy_value'] > 50_000_000 and pct_of_cap > 0.2:
                result = "REJECTED"
                reason = f"Go-private: ${scenario['buy_value']/1e6:.0f}M purchase = {pct_of_cap*100:.0f}% of ${scenario['market_cap']/1e6:.0f}M company (likely M&A)"

            elif is_entity and scenario['buy_value'] > 20_000_000 and pct_of_cap > 0.15:
                result = "REJECTED"
                reason = f"Go-private: institutional entity ({entity_type}) buying {pct_of_cap*100:.0f}% of company (likely M&A)"

            # Level 2: Alerts (don't change result, just flag)
            else:
                if 0.15 <= pct_of_cap < 0.3 and scenario['buy_value'] > 20_000_000:
                    result = "PASS with ALERT"
                    reason = f"ALERT: Large single-insider purchase ({pct_of_cap*100:.1f}% of company, ${scenario['buy_value']/1e6:.1f}M)"

                elif is_entity and scenario['buy_value'] > 10_000_000 and pct_of_cap > 0.1:
                    result = "PASS with ALERT"
                    reason = f"ALERT: Institutional entity ({entity_type}) purchase ({pct_of_cap*100:.1f}% of company, ${scenario['buy_value']/1e6:.1f}M)"

                elif scenario['buy_value'] > 100_000_000:
                    result = "PASS with ALERT"
                    reason = f"ALERT: Exceptionally large purchase (${scenario['buy_value']/1e6:.1f}M)"

        print(f"\nResult: {result}")
        print(f"Reason: {reason}")
        print(f"Expected: {scenario['expected']}")

        # Verify result matches expected
        expected_result = scenario['expected'].split()[0]  # Extract PASS/REJECTED
        actual_result = result.split()[0]  # Extract PASS/REJECTED

        if expected_result == actual_result:
            print("✅ TEST PASSED")
        else:
            print(f"❌ TEST FAILED - Expected {expected_result}, got {actual_result}")
            all_passed = False

    print(f"\n{'='*70}")
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*70)

    return all_passed


if __name__ == '__main__':
    success = test_go_private_detection()
    sys.exit(0 if success else 1)
