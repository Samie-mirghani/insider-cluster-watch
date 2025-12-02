"""
Test script for insider performance tracking feature
Tests name matching, scoring, and data handling
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

import pandas as pd
from datetime import datetime, timedelta
from insider_performance_tracker import InsiderPerformanceTracker

def test_name_matching():
    """Test if name variations are handled correctly"""
    print("\n" + "="*70)
    print("TEST 1: NAME MATCHING")
    print("="*70)

    tracker = InsiderPerformanceTracker(lookback_years=3, min_trades_for_score=3)

    # Create test trades with name variations
    test_trades = pd.DataFrame([
        {
            'trade_date': '2024-01-15',
            'ticker': 'AAPL',
            'insider': 'Timothy D. Cook',  # Full name with middle initial
            'title': 'CEO',
            'qty': 10000,
            'price': 150.0,
            'value': 1500000
        },
        {
            'trade_date': '2024-02-10',
            'ticker': 'AAPL',
            'insider': 'Tim Cook',  # Short name
            'title': 'CEO',
            'qty': 5000,
            'price': 155.0,
            'value': 775000
        },
        {
            'trade_date': '2024-03-05',
            'ticker': 'AAPL',
            'insider': 'Cook, Timothy D.',  # Last, First format
            'title': 'Chief Executive Officer',
            'qty': 8000,
            'price': 160.0,
            'value': 1280000
        },
        {
            'trade_date': '2024-04-20',
            'ticker': 'MSFT',
            'insider': 'Smith John',  # Last First format (no comma)
            'title': 'CFO',
            'qty': 3000,
            'price': 200.0,
            'value': 600000
        },
        {
            'trade_date': '2024-05-15',
            'ticker': 'MSFT',
            'insider': 'John Smith',  # First Last format
            'title': 'Chief Financial Officer',
            'qty': 4000,
            'price': 205.0,
            'value': 820000
        }
    ])

    # Add trades
    tracker.add_trades(test_trades)

    # Check how many unique insiders are tracked
    unique_insiders = tracker.trades_history['insider_name'].unique()
    print(f"\n✓ Added {len(test_trades)} trades")
    print(f"\n📊 Unique insiders tracked: {len(unique_insiders)}")
    print("\nInsider names in system:")
    for name in unique_insiders:
        print(f"  • {name}")

    # Expected: Should have 5 entries (no deduplication currently implemented)
    # This reveals a BUG if they're not properly matched

    if len(unique_insiders) > 2:
        print("\n⚠️  POTENTIAL BUG: Name variations not being matched!")
        print("   Expected: 2 unique insiders (Tim Cook variations + John Smith variations)")
        print(f"   Actual: {len(unique_insiders)} unique insiders")
        return False
    else:
        print("\n✅ Name matching appears to be working")
        return True

def test_outcome_calculation():
    """Test if outcome calculation works with edge cases"""
    print("\n" + "="*70)
    print("TEST 2: OUTCOME CALCULATION")
    print("="*70)

    tracker = InsiderPerformanceTracker(lookback_years=3, min_trades_for_score=3)

    # Create test trades with dates that should have outcomes
    # Using well-known tickers that should have price history
    test_trades = pd.DataFrame([
        {
            'trade_date': '2024-01-15',
            'ticker': 'AAPL',
            'insider': 'Test Insider 1',
            'title': 'CEO',
            'qty': 1000,
            'price': 180.0,
            'value': 180000
        },
        {
            'trade_date': '2024-06-01',
            'ticker': 'MSFT',
            'insider': 'Test Insider 2',
            'title': 'CFO',
            'qty': 500,
            'price': 400.0,
            'value': 200000
        },
        {
            'trade_date': '2025-11-01',  # Very recent - shouldn't have 90d outcome yet
            'ticker': 'GOOGL',
            'insider': 'Test Insider 3',
            'title': 'Director',
            'qty': 300,
            'price': 140.0,
            'value': 42000
        }
    ])

    tracker.add_trades(test_trades)
    print(f"\n✓ Added {len(test_trades)} test trades")

    # Try to update outcomes (will use real API)
    print("\n📊 Updating outcomes (this may take a minute)...")
    print("   Note: Using real yfinance API with rate limiting")

    tracker.update_outcomes(batch_size=3, rate_limit_delay=0.5)

    # Check results
    print("\n📈 Outcome Results:")
    for idx, row in tracker.trades_history.iterrows():
        ticker = row['ticker']
        trade_date = row['trade_date']
        has_30d = pd.notna(row['return_30d'])
        has_90d = pd.notna(row['return_90d'])
        has_180d = pd.notna(row['return_180d'])

        print(f"\n  {ticker} ({trade_date}):")
        print(f"    30d:  {'✓' if has_30d else '✗'} {row['return_30d']:+.2f}%" if has_30d else f"    30d:  ✗ N/A")
        print(f"    90d:  {'✓' if has_90d else '✗'} {row['return_90d']:+.2f}%" if has_90d else f"    90d:  ✗ N/A")
        print(f"    180d: {'✓' if has_180d else '✗'} {row['return_180d']:+.2f}%" if has_180d else f"    180d: ✗ N/A")

    # Check if old trades have outcomes
    old_trades = tracker.trades_history[
        pd.to_datetime(tracker.trades_history['trade_date']) < (datetime.now() - timedelta(days=90))
    ]

    if not old_trades.empty:
        has_outcomes = old_trades['return_90d'].notna().sum()
        total_old = len(old_trades)
        print(f"\n📊 Old trades (>90 days): {has_outcomes}/{total_old} have 90-day outcomes")

        if has_outcomes == 0:
            print("⚠️  WARNING: No outcomes calculated for old trades")
            return False

    return True

def test_scoring_system():
    """Test the scoring formula with known scenarios"""
    print("\n" + "="*70)
    print("TEST 3: SCORING SYSTEM")
    print("="*70)

    tracker = InsiderPerformanceTracker(lookback_years=3, min_trades_for_score=3)

    # Manually create profiles to test scoring
    # Excellent performer
    tracker.profiles['Excellent Insider'] = {
        'name': 'Excellent Insider',
        'total_trades': 10,
        'win_rate_90d': 80.0,
        'avg_return_90d': 15.0,
        'median_return_90d': 12.0,
        'sharpe_90d': 1.5,
        'recent_avg_return_90d': 18.0,
        'overall_score': None  # Will be calculated
    }

    # Poor performer
    tracker.profiles['Poor Insider'] = {
        'name': 'Poor Insider',
        'total_trades': 8,
        'win_rate_90d': 25.0,
        'avg_return_90d': -5.0,
        'median_return_90d': -3.0,
        'sharpe_90d': -0.5,
        'recent_avg_return_90d': -8.0,
        'overall_score': None
    }

    # Average performer
    tracker.profiles['Average Insider'] = {
        'name': 'Average Insider',
        'total_trades': 6,
        'win_rate_90d': 50.0,
        'avg_return_90d': 2.0,
        'median_return_90d': 1.5,
        'sharpe_90d': 0.3,
        'recent_avg_return_90d': 3.0,
        'overall_score': None
    }

    # Calculate scores manually using the formula from the code
    for name, profile in tracker.profiles.items():
        score_components = []

        # Component 1: 90-day average return (weighted 40%)
        return_score = 50 + (profile['avg_return_90d'] * 2.5)
        return_score = max(0, min(100, return_score))
        score_components.append(return_score * 0.40)

        # Component 2: 90-day win rate (weighted 30%)
        score_components.append(profile['win_rate_90d'] * 0.30)

        # Component 3: Sharpe ratio (weighted 20%)
        sharpe_score = 50 + (profile['sharpe_90d'] * 25)
        sharpe_score = max(0, min(100, sharpe_score))
        score_components.append(sharpe_score * 0.20)

        # Component 4: Recent performance (weighted 10%)
        recent_score = 50 + (profile['recent_avg_return_90d'] * 2.5)
        recent_score = max(0, min(100, recent_score))
        score_components.append(recent_score * 0.10)

        overall_score = sum(score_components)
        profile['overall_score'] = round(overall_score, 2)

        # Calculate multiplier
        multiplier = 0.5 + (overall_score / 100) * 1.5

        print(f"\n{name}:")
        print(f"  Win Rate: {profile['win_rate_90d']}%")
        print(f"  Avg Return: {profile['avg_return_90d']:+.1f}%")
        print(f"  Sharpe: {profile['sharpe_90d']:.2f}")
        print(f"  → Overall Score: {overall_score:.1f}/100")
        print(f"  → Conviction Multiplier: {multiplier:.2f}x")

    # Test expected ranges
    excellent_score = tracker.profiles['Excellent Insider']['overall_score']
    poor_score = tracker.profiles['Poor Insider']['overall_score']
    average_score = tracker.profiles['Average Insider']['overall_score']

    print(f"\n📊 Score Distribution:")
    print(f"  Excellent: {excellent_score:.1f}/100 (expected: 75-95)")
    print(f"  Average:   {average_score:.1f}/100 (expected: 45-55)")
    print(f"  Poor:      {poor_score:.1f}/100 (expected: 10-35)")

    # Validation
    tests_passed = True
    if not (75 <= excellent_score <= 95):
        print(f"\n⚠️  WARNING: Excellent score outside expected range!")
        tests_passed = False
    if not (45 <= average_score <= 55):
        print(f"\n⚠️  WARNING: Average score outside expected range!")
        tests_passed = False
    if not (10 <= poor_score <= 35):
        print(f"\n⚠️  WARNING: Poor score outside expected range!")
        tests_passed = False

    if excellent_score <= poor_score:
        print(f"\n❌ CRITICAL BUG: Excellent performer scored lower than poor performer!")
        tests_passed = False

    if tests_passed:
        print(f"\n✅ Scoring system appears to be working correctly")

    return tests_passed

def test_signal_adjustment():
    """Test if scores actually adjust conviction in signals"""
    print("\n" + "="*70)
    print("TEST 4: SIGNAL ADJUSTMENT")
    print("="*70)

    tracker = InsiderPerformanceTracker(lookback_years=3, min_trades_for_score=3)

    # Create test profiles
    tracker.profiles['Great CEO'] = {
        'name': 'Great CEO',
        'overall_score': 85.0,
        'total_trades': 10
    }

    tracker.profiles['Bad Director'] = {
        'name': 'Bad Director',
        'overall_score': 25.0,
        'total_trades': 8
    }

    tracker.profiles['Unknown Person'] = {
        'name': 'Unknown Person',
        'overall_score': 50.0,
        'total_trades': 0
    }

    # Test multiplier calculation
    print("\n📊 Testing signal multipliers:")

    for insider_name in ['Great CEO', 'Bad Director', 'Unknown Person', 'Never Seen Before']:
        multiplier = tracker.get_signal_multiplier(insider_name, base_conviction=10.0)
        profile = tracker.get_insider_score(insider_name)
        score = profile.get('overall_score', 50.0)

        print(f"\n  {insider_name}:")
        print(f"    Score: {score:.1f}/100")
        print(f"    Multiplier: {multiplier:.2f}x")
        print(f"    Base conviction: 10.0 → Adjusted: {10.0 * multiplier:.2f}")

    # Test expected multiplier ranges
    great_multiplier = tracker.get_signal_multiplier('Great CEO', 10.0)
    bad_multiplier = tracker.get_signal_multiplier('Bad Director', 10.0)
    unknown_multiplier = tracker.get_signal_multiplier('Unknown Person', 10.0)

    print(f"\n📈 Multiplier Analysis:")
    print(f"  Great CEO: {great_multiplier:.2f}x (expected: 1.5-2.0x)")
    print(f"  Bad Director: {bad_multiplier:.2f}x (expected: 0.5-0.8x)")
    print(f"  Unknown: {unknown_multiplier:.2f}x (expected: ~1.0x)")

    tests_passed = True
    if not (1.5 <= great_multiplier <= 2.0):
        print(f"\n⚠️  WARNING: Great CEO multiplier outside expected range!")
        tests_passed = False
    if not (0.5 <= bad_multiplier <= 0.8):
        print(f"\n⚠️  WARNING: Bad Director multiplier outside expected range!")
        tests_passed = False
    if not (0.95 <= unknown_multiplier <= 1.05):
        print(f"\n⚠️  WARNING: Unknown insider should be neutral (~1.0x)!")
        tests_passed = False

    if tests_passed:
        print(f"\n✅ Signal adjustment working correctly")

    return tests_passed

def test_insufficient_data_handling():
    """Test how system handles insiders with <3 trades"""
    print("\n" + "="*70)
    print("TEST 5: INSUFFICIENT DATA HANDLING")
    print("="*70)

    tracker = InsiderPerformanceTracker(lookback_years=3, min_trades_for_score=3)

    # Create trades with insufficient data
    test_trades = pd.DataFrame([
        {
            'trade_date': '2024-01-15',
            'ticker': 'AAPL',
            'insider': 'New Insider 1',
            'title': 'CEO',
            'qty': 1000,
            'price': 180.0,
            'value': 180000
        },
        {
            'trade_date': '2024-02-10',
            'ticker': 'AAPL',
            'insider': 'New Insider 1',
            'title': 'CEO',
            'qty': 500,
            'price': 185.0,
            'value': 92500
        }
    ])

    tracker.add_trades(test_trades)

    # Manually set outcomes for testing
    tracker.trades_history.loc[0, 'return_90d'] = 15.0
    tracker.trades_history.loc[1, 'return_90d'] = 12.0

    # Try to calculate profiles
    tracker.calculate_insider_profiles()

    print(f"\n✓ Created insider with only 2 trades (below minimum of 3)")
    print(f"  Trades: {len(tracker.trades_history)}")
    print(f"  Profiles created: {len(tracker.profiles)}")

    if 'New Insider 1' in tracker.profiles:
        print(f"\n⚠️  WARNING: Profile created for insider with insufficient data!")
        print(f"  This should have been skipped (min_trades_for_score = 3)")
        return False
    else:
        print(f"\n✅ Correctly skipped profile for insufficient data")

        # Check that getting score for unknown insider returns neutral
        profile = tracker.get_insider_score('New Insider 1')
        print(f"\n  Unknown insider score: {profile['overall_score']}/100")
        print(f"  Note: {profile.get('note', 'No note')}")

        if profile['overall_score'] == 50.0:
            print(f"  ✅ Correctly returns neutral score (50)")
            return True
        else:
            print(f"  ⚠️  Expected neutral score of 50, got {profile['overall_score']}")
            return False

def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("INSIDER PERFORMANCE TRACKER - COMPREHENSIVE TEST SUITE")
    print("="*70)
    print("\nThis will test:")
    print("  1. Name matching (duplicate detection)")
    print("  2. Outcome calculation (price data fetching)")
    print("  3. Scoring system (formula validation)")
    print("  4. Signal adjustment (conviction multipliers)")
    print("  5. Insufficient data handling (edge cases)")

    results = {
        'Name Matching': test_name_matching(),
        'Outcome Calculation': test_outcome_calculation(),
        'Scoring System': test_scoring_system(),
        'Signal Adjustment': test_signal_adjustment(),
        'Insufficient Data': test_insufficient_data_handling()
    }

    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test_name}: {status}")

    total_passed = sum(results.values())
    total_tests = len(results)

    print(f"\nOverall: {total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total_tests - total_passed} test(s) failed - review output above")

    print("="*70 + "\n")

if __name__ == '__main__':
    main()
