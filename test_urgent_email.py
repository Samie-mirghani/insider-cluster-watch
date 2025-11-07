#!/usr/bin/env python3
"""
Test script to verify urgent email template fixes:
1. Dynamic signal count (not hardcoded to "1")
2. Dynamic insider count (not hardcoded to "3")
3. Proper layout with multiple signals (no duplicate footers)
4. Date displays correctly
"""

import pandas as pd
import sys
import os
from datetime import datetime

# Add jobs directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

from generate_report import render_urgent_html
from send_email import send_email

def test_single_signal():
    """Test with 1 signal - should say '1 cluster' (singular)"""
    print("=" * 60)
    print("TEST 1: Single Urgent Signal")
    print("=" * 60)

    fake_data = pd.DataFrame([{
        'ticker': 'AAPL',
        'last_trade_date': pd.Timestamp.now(),
        'cluster_count': 5,
        'total_value': 1500000,
        'avg_conviction': 18.5,
        'insiders': 'CEO John Smith, CFO Jane Doe, Director Bob Johnson, VP Sarah Lee, CTO Mike Chen',
        'currentPrice': 175.50,
        'pct_from_52wk_low': 8.5,
        'rank_score': 22.3,
        'suggested_action': 'URGENT: Consider small entry at open / immediate review',
        'rationale': 'Strong C-suite cluster with 5 insiders buying $1.5M total. Stock near 52-week lows.',
        'sector': 'Technology',
        'quality_score': 9.2,
        'pattern_detected': 'CEO Cluster',
        'news_sentiment': 'positive'
    }])

    html, text = render_urgent_html(fake_data)

    # Verify count in HTML
    if '1 high-conviction insider buying cluster detected' in html:
        print("✅ PASS: Shows '1 cluster' (singular)")
    elif '{{ urgent_trades|length }}' in html:
        print("❌ FAIL: Template variable not rendered")
    else:
        print("⚠️  WARNING: Check signal count manually")

    # Verify insider count
    if '(5 TOTAL)' in html:
        print("✅ PASS: Shows '(5 TOTAL)' insiders")
    elif '(3 TOTAL)' in html:
        print("❌ FAIL: Still hardcoded to '(3 TOTAL)'")
    else:
        print("⚠️  WARNING: Check insider count manually")

    # Check for duplicate footer issue
    footer_count = html.count('Insider Cluster Watch - Urgent Alert System')
    if footer_count == 1:
        print(f"✅ PASS: Footer appears once (found {footer_count})")
    else:
        print(f"❌ FAIL: Footer appears {footer_count} times (should be 1)")

    return html, text

def test_multiple_signals():
    """Test with 3 signals - should say '3 clusters' (plural)"""
    print("\n" + "=" * 60)
    print("TEST 2: Multiple Urgent Signals (3)")
    print("=" * 60)

    fake_data = pd.DataFrame([
        {
            'ticker': 'MTDR',
            'last_trade_date': pd.Timestamp.now(),
            'cluster_count': 13,
            'total_value': 1408102,
            'avg_conviction': 15.2,
            'insiders': 'CEO, CFO, Director A, Director B, VP Operations, and 8 others',
            'currentPrice': 37.94,
            'pct_from_52wk_low': 12.3,
            'rank_score': 30.97,
            'suggested_action': 'URGENT: Consider small entry at open / immediate review',
            'rationale': 'Massive insider cluster - 13 executives buying $1.4M. Stock trading 12% above 52-week lows.',
            'sector': 'Energy',
            'quality_score': 9.5,
            'pattern_detected': 'CEO Cluster',
            'news_sentiment': 'positive'
        },
        {
            'ticker': 'RLMD',
            'last_trade_date': pd.Timestamp.now(),
            'cluster_count': 4,
            'total_value': 2196700,
            'avg_conviction': 12.8,
            'insiders': 'CEO Mark Johnson, CFO Lisa Wang, Director Tom Brown, Director Sarah Miller',
            'currentPrice': 2.61,
            'pct_from_52wk_low': 5.2,
            'rank_score': 13.24,
            'suggested_action': 'URGENT: Consider small entry at open / immediate review',
            'rationale': 'Four C-suite insiders buying $2.2M near 52-week lows. Strong conviction signal.',
            'sector': 'Healthcare',
            'quality_score': 8.9,
            'pattern_detected': 'CFO Buying',
            'news_sentiment': 'neutral'
        },
        {
            'ticker': 'AMRZ',
            'last_trade_date': pd.Timestamp.now(),
            'cluster_count': 3,
            'total_value': 6213440,
            'avg_conviction': 14.1,
            'insiders': 'CEO David Chen, CFO Emily Rodriguez, Director Michael Park',
            'currentPrice': 45.20,
            'pct_from_52wk_low': 9.8,
            'rank_score': 10.03,
            'suggested_action': 'URGENT: Consider small entry at open / immediate review',
            'rationale': 'Top executives buying $6.2M - largest cluster value this week. Stock discounted.',
            'sector': 'Basic Materials',
            'quality_score': 8.7,
            'pattern_detected': 'CEO Cluster',
            'news_sentiment': 'positive'
        }
    ])

    html, text = render_urgent_html(fake_data)

    # Verify count in HTML
    if '3 high-conviction insider buying clusters detected' in html:
        print("✅ PASS: Shows '3 clusters' (plural)")
    elif '1 high-conviction insider buying cluster detected' in html:
        print("❌ FAIL: Still shows '1' instead of actual count")
    else:
        print("⚠️  WARNING: Check signal count manually")

    # Verify each signal has correct insider count
    if '(13 TOTAL)' in html and '(4 TOTAL)' in html and '(3 TOTAL)' in html:
        print("✅ PASS: All signals show correct insider counts")
    elif html.count('(3 TOTAL)') == 3:
        print("❌ FAIL: All signals hardcoded to '(3 TOTAL)'")
    else:
        print("⚠️  WARNING: Check insider counts manually")

    # Check for duplicate footer issue
    footer_count = html.count('Insider Cluster Watch - Urgent Alert System')
    if footer_count == 1:
        print(f"✅ PASS: Footer appears once (found {footer_count})")
    else:
        print(f"❌ FAIL: Footer appears {footer_count} times (should be 1)")

    # Check for proper spacing between signals
    spacer_count = html.count('<!-- Spacer between signals -->')
    if spacer_count == 2:  # 3 signals = 2 spacers
        print(f"✅ PASS: Proper spacing between signals ({spacer_count} spacers for 3 signals)")
    else:
        print(f"⚠️  INFO: Found {spacer_count} spacers (expected 2 for 3 signals)")

    return html, text

def test_deduplication():
    """Test that deduplication logic works"""
    print("\n" + "=" * 60)
    print("TEST 3: Transaction Deduplication")
    print("=" * 60)

    # Create duplicate transactions
    from process_signals import cluster_and_score

    transactions = pd.DataFrame([
        # Original transaction
        {'ticker': 'TEST', 'insider': 'CEO John', 'trade_date': '2025-11-07',
         'trade_type': 'P - Purchase', 'qty': 10000, 'price': 50.0, 'value': 500000,
         'title': 'CEO', 'filing_date': '2025-11-07'},
        # Duplicate (amended Form 4)
        {'ticker': 'TEST', 'insider': 'CEO John', 'trade_date': '2025-11-07',
         'trade_type': 'P - Purchase', 'qty': 10000, 'price': 50.0, 'value': 500000,
         'title': 'CEO', 'filing_date': '2025-11-07'},
        # Different insider - should NOT be removed
        {'ticker': 'TEST', 'insider': 'CFO Jane', 'trade_date': '2025-11-07',
         'trade_type': 'P - Purchase', 'qty': 5000, 'price': 50.0, 'value': 250000,
         'title': 'CFO', 'filing_date': '2025-11-07'},
    ])

    transactions['trade_date'] = pd.to_datetime(transactions['trade_date'])
    transactions['filing_date'] = pd.to_datetime(transactions['filing_date'])

    print("   Input: 3 transactions (1 duplicate)")
    print("   - CEO John: 10,000 shares @ $50 (original)")
    print("   - CEO John: 10,000 shares @ $50 (duplicate)")
    print("   - CFO Jane: 5,000 shares @ $50 (unique)")

    result = cluster_and_score(transactions)

    if not result.empty:
        cluster_count = result.iloc[0]['cluster_count']
        total_value = result.iloc[0]['total_value']

        # Should be 2 insiders and $750k total
        if cluster_count == 2:
            print(f"✅ PASS: Cluster count is 2 (duplicate removed)")
        else:
            print(f"❌ FAIL: Cluster count is {cluster_count} (expected 2)")

        if abs(total_value - 750000) < 1:
            print(f"✅ PASS: Total value is $750k (duplicate removed)")
        else:
            print(f"❌ FAIL: Total value is ${total_value:,.0f} (expected $750,000)")
    else:
        print("❌ FAIL: No results returned from cluster_and_score")

def main():
    print("\n🧪 URGENT EMAIL TEMPLATE TESTING SUITE")
    print("=" * 60)
    print("This will test all the fixes:\n")
    print("1. Dynamic signal count (not hardcoded to '1')")
    print("2. Dynamic insider count (not hardcoded to '3')")
    print("3. Proper layout with multiple signals")
    print("4. Transaction deduplication\n")

    # Run tests
    html1, text1 = test_single_signal()
    html2, text2 = test_multiple_signals()
    test_deduplication()

    print("\n" + "=" * 60)
    print("OPTIONAL: Send Test Emails")
    print("=" * 60)

    response = input("\nDo you want to send test emails to verify rendering? (yes/no): ").strip().lower()

    if response in ['yes', 'y']:
        print("\n📧 Sending test emails...")
        try:
            send_email("TEST 1: Single Urgent Signal", html1, text1)
            print("✅ Sent: TEST 1 - Single Signal")

            send_email("TEST 2: Multiple Urgent Signals (3)", html2, text2)
            print("✅ Sent: TEST 2 - Multiple Signals")

            print("\n✅ Test emails sent! Check your inbox.")
        except Exception as e:
            print(f"\n❌ Error sending emails: {e}")
            print("   Make sure you have GMAIL_USER, GMAIL_APP_PASSWORD, and RECIPIENT_EMAIL set in .env")
    else:
        print("\n✅ Tests complete. No emails sent.")
        print("\nTo manually review the HTML, you can save it to files:")
        print("  - Check the HTML output above for pass/fail results")

    print("\n" + "=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print("If all tests passed, you can:")
    print("1. Merge this branch to your main repo")
    print("2. Deploy to production")
    print("\nIf any tests failed:")
    print("1. Review the HTML output above")
    print("2. Check the template file: templates/urgent_alert.html")
    print("3. Check the deduplication code: jobs/process_signals.py")

if __name__ == "__main__":
    main()
