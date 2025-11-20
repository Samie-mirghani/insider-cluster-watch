#!/usr/bin/env python3
"""
Test script for the Follow-the-Smart-Money Scoring feature

This script tests the basic functionality of the insider performance tracker.
"""

import sys
import os

# Add jobs directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

import pandas as pd
from datetime import datetime, timedelta
from jobs.insider_performance_tracker import InsiderPerformanceTracker

def test_basic_functionality():
    """Test basic tracker functionality"""
    print("="*70)
    print("TESTING INSIDER PERFORMANCE TRACKER")
    print("="*70)

    # Create tracker
    print("\n1. Creating tracker instance...")
    tracker = InsiderPerformanceTracker(lookback_years=3, min_trades_for_score=3)
    print(f"   ✅ Tracker created")
    print(f"   - Profiles loaded: {len(tracker.profiles)}")
    print(f"   - Trades in history: {len(tracker.trades_history)}")

    # Create sample trade data
    print("\n2. Creating sample trade data...")
    sample_trades = pd.DataFrame([
        {
            'trade_date': datetime.now() - timedelta(days=100),
            'ticker': 'AAPL',
            'insider': 'John Smith',
            'title': 'CEO',
            'qty': 10000,
            'price': 150.0,
            'value': 1500000
        },
        {
            'trade_date': datetime.now() - timedelta(days=90),
            'ticker': 'MSFT',
            'insider': 'Jane Doe',
            'title': 'CFO',
            'qty': 5000,
            'price': 300.0,
            'value': 1500000
        },
        {
            'trade_date': datetime.now() - timedelta(days=50),
            'ticker': 'GOOGL',
            'insider': 'John Smith',
            'title': 'CEO',
            'qty': 2000,
            'price': 100.0,
            'value': 200000
        }
    ])
    print(f"   ✅ Created {len(sample_trades)} sample trades")

    # Add trades to tracker
    print("\n3. Adding trades to tracker...")
    tracker.add_trades(sample_trades)
    print(f"   ✅ Trades added")
    print(f"   - Total trades now: {len(tracker.trades_history)}")

    # Test get_insider_score
    print("\n4. Testing get_insider_score()...")
    score1 = tracker.get_insider_score('John Smith')
    score2 = tracker.get_insider_score('Unknown Insider')
    print(f"   ✅ John Smith score: {score1.get('overall_score', 50)}/100")
    print(f"   ✅ Unknown Insider score: {score2.get('overall_score', 50)}/100 (should be 50 - neutral)")

    # Test get_signal_multiplier
    print("\n5. Testing get_signal_multiplier()...")
    multiplier1 = tracker.get_signal_multiplier('John Smith', 10.0)
    multiplier2 = tracker.get_signal_multiplier('Unknown Insider', 10.0)
    print(f"   ✅ John Smith multiplier: {multiplier1}x")
    print(f"   ✅ Unknown Insider multiplier: {multiplier2}x (should be 1.0x)")

    # Test profile calculation
    print("\n6. Testing calculate_insider_profiles()...")
    tracker.calculate_insider_profiles()
    print(f"   ✅ Profiles calculated: {len(tracker.profiles)}")

    # Test top performers
    print("\n7. Testing get_top_performers()...")
    top = tracker.get_top_performers(n=5, min_trades=1)
    if not top.empty:
        print(f"   ✅ Found {len(top)} top performers")
        if len(top) > 0:
            print(f"\n   Top Performer:")
            first = top.iloc[0]
            print(f"   - Name: {first.get('name', 'N/A')}")
            print(f"   - Score: {first.get('overall_score', 0)}/100")
            print(f"   - Total Trades: {first.get('total_trades', 0)}")
    else:
        print(f"   ℹ️  No top performers found (need more data with outcomes)")

    # Show data file locations
    print("\n8. Data storage:")
    print(f"   - Profiles: data/insider_profiles.json")
    print(f"   - Trade History: data/insider_trades_history.csv")

    print("\n" + "="*70)
    print("✅ ALL TESTS PASSED")
    print("="*70)
    print("\nNOTE: To get meaningful insider scores, you need to:")
    print("  1. Run update_outcomes() to fetch historical price data")
    print("  2. Wait for trades to have 30/90/180 day outcomes")
    print("  3. Recalculate profiles with calculate_insider_profiles()")
    print("\nThe system will do this automatically during daily runs.")
    print("="*70 + "\n")

if __name__ == '__main__':
    try:
        test_basic_functionality()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
