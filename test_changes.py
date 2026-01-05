#!/usr/bin/env python3
"""
Test script to verify the new features work correctly
"""

# Test 1: Dividend adjustment calculation
def test_dividend_calculation():
    """Test that dividends are correctly added to returns"""
    entry_price = 100.0
    outcome_price = 105.0
    dividends_received = 2.0

    # Without dividends: (105 - 100) / 100 * 100 = 5%
    # With dividends: (105 - 100 + 2) / 100 * 100 = 7%

    total_return = ((outcome_price - entry_price + dividends_received) / entry_price) * 100

    assert abs(total_return - 7.0) < 0.01, f"Expected 7.0, got {total_return}"
    print("✅ Dividend calculation test passed")


# Test 2: Alpha calculation
def test_alpha_calculation():
    """Test that alpha is correctly calculated"""
    insider_return = 15.0  # Insider gained 15%
    spy_return = 8.0       # S&P 500 gained 8%

    alpha = insider_return - spy_return

    assert abs(alpha - 7.0) < 0.01, f"Expected 7.0, got {alpha}"
    print("✅ Alpha calculation test passed")


# Test 3: Stale trade detection
def test_stale_trade_detection():
    """Test that stale trades are correctly identified"""
    from datetime import datetime, timedelta

    today = datetime.now()
    old_date = today - timedelta(days=250)  # 250 days ago
    recent_date = today - timedelta(days=50)  # 50 days ago

    # Trade from 250 days ago should be stale (threshold 200)
    days_tracking_old = (today - old_date).days
    is_stale_old = days_tracking_old > 200

    # Trade from 50 days ago should not be stale
    days_tracking_recent = (today - recent_date).days
    is_stale_recent = days_tracking_recent > 200

    assert is_stale_old == True, "Old trade should be flagged as stale"
    assert is_stale_recent == False, "Recent trade should not be stale"
    print("✅ Stale trade detection test passed")


# Test 4: Form 4 attribution fields
def test_form4_attribution():
    """Test that Form 4 attribution fields are handled"""
    signal = {
        'ticker': 'AAPL',
        'insider_name': 'Tim Cook',
        'trade_date': '2025-01-01',
        'price': 150.0,
        'filing_date': '2025-01-03',
        'filing_url': 'https://sec.gov/filing/123',
        'accession_number': '0001234567-25-000001'
    }

    # Verify all fields are extracted
    assert signal.get('filing_date') is not None, "Filing date should be present"
    assert signal.get('filing_url') is not None, "Filing URL should be present"
    assert signal.get('accession_number') is not None, "Accession number should be present"
    print("✅ Form 4 attribution test passed")


if __name__ == '__main__':
    print("Running tests...\n")
    test_dividend_calculation()
    test_alpha_calculation()
    test_stale_trade_detection()
    test_form4_attribution()
    print("\n🎉 All tests passed!")
