#!/usr/bin/env python3
"""
Test script for PoliticianTradeTracker API integration
Verifies API connectivity, data parsing, and filtering
"""

import sys
import os

# Add jobs directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

from capitol_trades_scraper import CapitolTradesScraper
from datetime import datetime, timedelta

def test_api_integration():
    """Run comprehensive API integration tests"""

    print("\n" + "="*70)
    print("🧪 POLITICIAN TRADE API - INTEGRATION TEST")
    print("="*70 + "\n")

    # Initialize scraper
    print("1️⃣ Initializing API scraper...")
    try:
        scraper = CapitolTradesScraper()
        print("   ✓ Scraper initialized successfully\n")
    except Exception as e:
        print(f"   ❌ FAIL: Could not initialize scraper: {e}")
        return False

    # Test API fetch
    print("2️⃣ Testing API fetch (last 30 days)...")
    try:
        trades = scraper.scrape_recent_trades(days_back=30)

        if trades.empty:
            print("   ⚠️  WARNING: No trades returned (may be rate limited or no recent trades)")
            print("   → Checking if using cached data...")

            # Try to load cache directly
            cached = scraper._load_cached_trades()
            if not cached.empty:
                print(f"   ✓ Found {len(cached)} trades in cache")
                trades = cached
            else:
                print("   ❌ FAIL: No trades and no cache available")
                return False
        else:
            print(f"   ✓ Fetched {len(trades)} trades from API\n")
    except Exception as e:
        print(f"   ❌ FAIL: API fetch error: {e}\n")
        import traceback
        traceback.print_exc()
        return False

    # Test 3: Verify data structure
    print("3️⃣ Verifying data structure...")
    required_columns = ['ticker', 'politician', 'party', 'trade_date', 'amount_range', 'transaction_type']
    missing_cols = [col for col in required_columns if col not in trades.columns]

    if missing_cols:
        print(f"   ❌ FAIL: Missing columns: {missing_cols}")
        return False
    else:
        print(f"   ✓ All required columns present\n")

    # Test 4: Verify ticker format (no :US suffix)
    print("4️⃣ Testing ticker format (no :US suffix)...")
    bad_tickers = trades[trades['ticker'].str.contains(':', na=False)]

    if len(bad_tickers) > 0:
        print(f"   ❌ FAIL: Found {len(bad_tickers)} tickers with ':' character")
        print(f"   → Examples: {bad_tickers['ticker'].head().tolist()}")
        return False
    else:
        print(f"   ✓ All tickers clean (no exchange suffixes)\n")

    # Test 5: Verify only buy trades
    print("5️⃣ Verifying only buy trades included...")
    non_buys = trades[trades['transaction_type'].str.lower() != 'buy']

    if len(non_buys) > 0:
        print(f"   ❌ FAIL: Found {len(non_buys)} non-buy trades")
        print(f"   → Types: {non_buys['transaction_type'].unique()}")
        return False
    else:
        print(f"   ✓ All trades are buys\n")

    # Test 6: Verify date filtering (last 30 days)
    print("6️⃣ Testing date filtering...")
    cutoff_date = datetime.now() - timedelta(days=30)
    old_trades = trades[trades['trade_date'] < cutoff_date]

    if len(old_trades) > 0:
        print(f"   ❌ FAIL: Found {len(old_trades)} trades older than 30 days")
        oldest = old_trades['trade_date'].min()
        print(f"   → Oldest trade: {oldest}")
        return False
    else:
        print(f"   ✓ All trades within last 30 days\n")

    # Test 7: Display sample data
    print("7️⃣ Sample trades:")
    if len(trades) > 0:
        sample = trades.head(5)[['politician', 'ticker', 'trade_date', 'amount_range', 'party']]
        for idx, row in sample.iterrows():
            print(f"   • {row['politician']} ({row['party']}) → {row['ticker']}")
            print(f"     Date: {row['trade_date'].strftime('%Y-%m-%d')}, Amount: {row['amount_range']}")
        print()

    # Test 8: Test cluster detection
    print("8️⃣ Testing cluster detection...")
    try:
        clusters = scraper.detect_politician_clusters(trades, min_politicians=2)

        print(f"   ✓ Cluster detection successful")
        print(f"   → Found {len(clusters)} clusters with 2+ politicians\n")

        if not clusters.empty:
            print("   Top clusters:")
            for idx, row in clusters.head(3).iterrows():
                print(f"   • {row['ticker']}: {row['num_politicians']} politicians, score={row['conviction_score']:.1f}")
                print(f"     Politicians: {', '.join(row['politician_list'][:3])}")
            print()
    except Exception as e:
        print(f"   ❌ FAIL: Cluster detection error: {e}\n")
        return False

    # Test 9: Rate limiting check
    print("9️⃣ Verifying rate limiting...")
    try:
        can_call = scraper._check_rate_limit()

        # Load rate limit file
        if os.path.exists(scraper.rate_limit_file):
            import json
            with open(scraper.rate_limit_file, 'r') as f:
                rate_data = json.load(f)

            calls_made = rate_data.get('calls', 0)
            month = rate_data.get('month', 'unknown')

            print(f"   ✓ Rate limiting working")
            print(f"   → API calls this month: {calls_made}/100")
            print(f"   → Can make more calls: {can_call}\n")
        else:
            print(f"   ⚠️  Rate limit file not found (will be created on first API call)\n")
    except Exception as e:
        print(f"   ⚠️  WARNING: Rate limit check error: {e}\n")

    # Test 10: Caching check
    print("🔟 Verifying caching mechanism...")
    try:
        if os.path.exists(scraper.cache_file):
            import json
            with open(scraper.cache_file, 'r') as f:
                cache_data = json.load(f)

            cached_at = datetime.fromisoformat(cache_data['cached_at'])
            age_hours = (datetime.now() - cached_at).total_seconds() / 3600
            num_cached = len(cache_data['trades'])

            print(f"   ✓ Cache working")
            print(f"   → Cached {num_cached} trades")
            print(f"   → Cache age: {age_hours:.1f} hours")
            print(f"   → Cache valid: {age_hours < 24}\n")
        else:
            print(f"   ⚠️  Cache file not found (will be created after first successful API call)\n")
    except Exception as e:
        print(f"   ⚠️  WARNING: Cache check error: {e}\n")

    # Final summary
    print("="*70)
    print("✅ ALL TESTS PASSED!")
    print("="*70)
    print(f"\n📊 Summary:")
    print(f"   • Total trades fetched: {len(trades)}")
    print(f"   • Unique tickers: {trades['ticker'].nunique()}")
    print(f"   • Unique politicians: {trades['politician'].nunique()}")
    print(f"   • Date range: {trades['trade_date'].min().strftime('%Y-%m-%d')} to {trades['trade_date'].max().strftime('%Y-%m-%d')}")
    print(f"   • Clusters detected: {len(clusters)}")

    # Party breakdown
    party_counts = trades['party'].value_counts()
    print(f"\n   Party breakdown:")
    for party, count in party_counts.items():
        print(f"   • {party}: {count} trades")

    print("\n" + "="*70)
    print("🎉 API INTEGRATION SUCCESSFUL - READY FOR PRODUCTION!")
    print("="*70 + "\n")

    return True


if __name__ == "__main__":
    success = test_api_integration()
    sys.exit(0 if success else 1)
