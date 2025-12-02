"""
Diagnostic script to understand why bootstrap had 0% success rate.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'jobs'))

import pandas as pd
from datetime import datetime, timedelta
import yfinance as yf
from pathlib import Path

def analyze_trades_data():
    """Analyze the trades in the database to understand the failure"""

    print("\n" + "="*80)
    print("BOOTSTRAP FAILURE DIAGNOSTICS")
    print("="*80)

    # Check if data files exist
    trades_file = 'data/insider_trades_history.csv'

    if not os.path.exists(trades_file):
        print(f"\n❌ ERROR: {trades_file} not found")
        print("   The bootstrap script may not have saved the fetched trades.")
        return

    # Load trades data
    print(f"\n📂 Loading trades from {trades_file}...")
    df = pd.read_csv(trades_file)
    print(f"   ✅ Loaded {len(df):,} trades")

    # Convert trade_date to datetime
    df['trade_date'] = pd.to_datetime(df['trade_date'])

    # Analyze dates
    print("\n" + "="*80)
    print("DATE ANALYSIS")
    print("="*80)

    today = datetime.now()
    print(f"Today's date: {today.strftime('%Y-%m-%d')}")
    print(f"\nTrade date range:")
    print(f"  Oldest trade:  {df['trade_date'].min().strftime('%Y-%m-%d')}")
    print(f"  Newest trade:  {df['trade_date'].max().strftime('%Y-%m-%d')}")

    # Calculate age of each trade
    df['days_old'] = (today - df['trade_date']).dt.days

    print(f"\nTrade age distribution:")
    print(f"  Mean age: {df['days_old'].mean():.1f} days")
    print(f"  Median age: {df['days_old'].median():.1f} days")
    print(f"  Min age: {df['days_old'].min()} days")
    print(f"  Max age: {df['days_old'].max()} days")

    # Count trades by age bucket
    print("\n" + "="*80)
    print("AGE BUCKETS")
    print("="*80)

    buckets = {
        '< 30 days old (too recent for any outcome)': (df['days_old'] < 30).sum(),
        '30-59 days old (only 30d outcome available)': ((df['days_old'] >= 30) & (df['days_old'] < 60)).sum(),
        '60-89 days old (30d and 60d outcomes available)': ((df['days_old'] >= 60) & (df['days_old'] < 90)).sum(),
        '90-179 days old (90d outcome available)': ((df['days_old'] >= 90) & (df['days_old'] < 180)).sum(),
        '>= 180 days old (all outcomes available)': (df['days_old'] >= 180).sum(),
    }

    for label, count in buckets.items():
        pct = (count / len(df) * 100) if len(df) > 0 else 0
        print(f"  {label}: {count:,} ({pct:.1f}%)")

    # Key insight
    processable = (df['days_old'] >= 90).sum()
    too_recent = (df['days_old'] < 90).sum()

    print("\n" + "="*80)
    print("KEY FINDINGS")
    print("="*80)

    print(f"\n✅ Trades >= 90 days old (processable): {processable:,} ({processable/len(df)*100:.1f}%)")
    print(f"❌ Trades < 90 days old (too recent):   {too_recent:,} ({too_recent/len(df)*100:.1f}%)")

    if processable == 0:
        print("\n🚨 ROOT CAUSE IDENTIFIED:")
        print("   ALL trades are less than 90 days old!")
        print("   The bootstrap script skips trades < 90 days because")
        print("   they don't have enough time elapsed for 90d outcome calculation.")
        print("\n💡 SOLUTION:")
        print("   Option 1: Wait until trades age to 90+ days")
        print("   Option 2: Modify script to calculate partial outcomes (30d/60d)")
        print("   Option 3: Fetch older historical data from SEC EDGAR")
    elif processable < len(df) * 0.5:
        print("\n⚠️  ISSUE: Majority of trades are too recent")
        print(f"   Only {processable} trades can be processed for 90d outcomes")

    # Ticker analysis
    print("\n" + "="*80)
    print("TICKER ANALYSIS")
    print("="*80)

    print(f"\nUnique tickers: {df['ticker'].nunique()}")
    print(f"\nTop 10 most traded tickers:")
    top_tickers = df['ticker'].value_counts().head(10)
    for ticker, count in top_tickers.items():
        print(f"  {ticker:6s} - {count:3d} trades")

    # Sample some tickers for testing
    sample_tickers = df['ticker'].value_counts().head(5).index.tolist()

    print("\n" + "="*80)
    print("SAMPLE TRADES FOR TESTING")
    print("="*80)

    # Get some trades that are >= 90 days old if available
    if processable > 0:
        print("\n✅ Trades that SHOULD be processable (>= 90 days old):")
        sample_processable = df[df['days_old'] >= 90].head(3)
        for _, row in sample_processable.iterrows():
            print(f"   {row['ticker']:6s} | {row['trade_date'].strftime('%Y-%m-%d')} | ${row['entry_price']:.2f} | {row['days_old']} days old")

        return sample_processable
    else:
        print("\n❌ No trades >= 90 days old available for testing")
        print("\n💡 Showing most recent trades (will be used once they age):")
        sample_recent = df.nsmallest(3, 'days_old')
        for _, row in sample_recent.iterrows():
            maturity_date = (row['trade_date'] + timedelta(days=90)).strftime('%Y-%m-%d')
            print(f"   {row['ticker']:6s} | {row['trade_date'].strftime('%Y-%m-%d')} | ${row['entry_price']:.2f} | {row['days_old']} days old → matures on {maturity_date}")

        return None


def test_price_fetching(sample_trades=None):
    """Test price fetching with yfinance"""

    print("\n" + "="*80)
    print("YFINANCE API TEST")
    print("="*80)

    # Test with known good tickers
    print("\n1️⃣  Testing with known good tickers (AAPL, MSFT)...")

    test_cases = [
        ('AAPL', '2024-06-01', 180.0),
        ('MSFT', '2024-06-01', 400.0),
    ]

    for ticker, trade_date, entry_price in test_cases:
        print(f"\n   Testing {ticker} on {trade_date}...")

        try:
            trade_dt = pd.to_datetime(trade_date)
            date_90d = trade_dt + timedelta(days=90)

            start_date = trade_dt - timedelta(days=5)
            end_date = trade_dt + timedelta(days=200)

            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date)

            if hist.empty:
                print(f"      ❌ No data returned from yfinance")
            else:
                hist = hist.reset_index()
                hist['Date'] = pd.to_datetime(hist['Date']).dt.tz_localize(None)

                # Find 90d price
                future_data = hist[hist['Date'] >= date_90d]

                if not future_data.empty:
                    outcome_price = future_data.iloc[0]['Close']
                    returns = ((outcome_price - entry_price) / entry_price) * 100
                    print(f"      ✅ SUCCESS: 90d price = ${outcome_price:.2f} ({returns:+.1f}%)")
                else:
                    print(f"      ⚠️  No price data found for target date {date_90d.strftime('%Y-%m-%d')}")
                    print(f"      Data range: {hist['Date'].min().strftime('%Y-%m-%d')} to {hist['Date'].max().strftime('%Y-%m-%d')}")

        except Exception as e:
            print(f"      ❌ ERROR: {e}")

    # Test with actual trades if available
    if sample_trades is not None and len(sample_trades) > 0:
        print("\n2️⃣  Testing with actual trades from database...")

        for _, row in sample_trades.iterrows():
            ticker = row['ticker']
            trade_date = row['trade_date'].strftime('%Y-%m-%d')
            entry_price = row['entry_price']

            print(f"\n   Testing {ticker} on {trade_date}...")

            try:
                trade_dt = pd.to_datetime(trade_date)
                date_90d = trade_dt + timedelta(days=90)

                start_date = trade_dt - timedelta(days=5)
                end_date = trade_dt + timedelta(days=200)

                stock = yf.Ticker(ticker)
                hist = stock.history(start=start_date, end=end_date)

                if hist.empty:
                    print(f"      ❌ No data returned from yfinance")
                    print(f"      Possible reasons:")
                    print(f"         - Invalid ticker symbol")
                    print(f"         - Delisted company")
                    print(f"         - API rate limiting")
                else:
                    hist = hist.reset_index()
                    hist['Date'] = pd.to_datetime(hist['Date']).dt.tz_localize(None)

                    # Find 90d price
                    future_data = hist[hist['Date'] >= date_90d]

                    if not future_data.empty:
                        outcome_price = future_data.iloc[0]['Close']
                        returns = ((outcome_price - entry_price) / entry_price) * 100
                        print(f"      ✅ SUCCESS: 90d price = ${outcome_price:.2f} ({returns:+.1f}%)")
                    else:
                        print(f"      ⚠️  No price data found for target date {date_90d.strftime('%Y-%m-%d')}")
                        print(f"      Data range: {hist['Date'].min().strftime('%Y-%m-%d')} to {hist['Date'].max().strftime('%Y-%m-%d')}")

            except Exception as e:
                print(f"      ❌ ERROR: {e}")
    else:
        print("\n2️⃣  No processable trades available for testing (all < 90 days old)")


def main():
    """Run all diagnostics"""

    sample_trades = analyze_trades_data()
    test_price_fetching(sample_trades)

    print("\n" + "="*80)
    print("DIAGNOSTICS COMPLETE")
    print("="*80)
    print()


if __name__ == '__main__':
    main()
