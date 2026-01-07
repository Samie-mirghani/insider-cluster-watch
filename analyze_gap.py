#!/usr/bin/env python3
"""
Analyze insider trading activity gap between Dec 23 - Jan 6
to determine why no clusters were detected.
"""

import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

# Load insider trades history
df = pd.read_csv('data/insider_trades_history.csv')

# Filter to date range of interest: Dec 24, 2025 - Jan 6, 2026
df['trade_date'] = pd.to_datetime(df['trade_date'])
start_date = pd.to_datetime('2025-12-24')
end_date = pd.to_datetime('2026-01-06')

gap_trades = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)].copy()

print("=" * 80)
print("INSIDER TRADING ACTIVITY ANALYSIS: Dec 24, 2025 - Jan 6, 2026")
print("=" * 80)
print()

# 1. Overall Statistics
print("1. OVERALL STATISTICS")
print("-" * 80)
print(f"Total trades in period: {len(gap_trades)}")
print(f"Unique tickers: {gap_trades['ticker'].nunique()}")
print(f"Unique insiders: {gap_trades['insider_canonical'].nunique() if 'insider_canonical' in gap_trades.columns else gap_trades['insider_name'].nunique()}")
print()

# 2. Daily breakdown
print("2. DAILY TRADE COUNT")
print("-" * 80)
daily_counts = gap_trades.groupby(gap_trades['trade_date'].dt.date).size().sort_index()
for date, count in daily_counts.items():
    print(f"{date}: {count} trades")
print()

# 3. Tickers with multiple insiders (potential clusters)
print("3. TICKERS WITH MULTIPLE INSIDERS (5-day windows)")
print("-" * 80)

ticker_groups = gap_trades.groupby('ticker')
potential_clusters = []

for ticker, group in ticker_groups:
    if len(group) >= 2:
        # Sort by date
        group_sorted = group.sort_values('trade_date')
        dates = group_sorted['trade_date'].tolist()

        # Check if any fall within 5-day window
        for i in range(len(dates)):
            window_end = dates[i] + timedelta(days=5)
            trades_in_window = [d for d in dates if dates[i] <= d <= window_end]

            if len(trades_in_window) >= 2:
                # Get unique insiders in this window
                window_trades = group_sorted[
                    (group_sorted['trade_date'] >= dates[i]) &
                    (group_sorted['trade_date'] <= window_end)
                ]
                insider_col = 'insider_canonical' if 'insider_canonical' in window_trades.columns else 'insider_name'
                unique_insiders = window_trades[insider_col].nunique()

                if unique_insiders >= 2:
                    total_value = window_trades['value'].sum()
                    potential_clusters.append({
                        'ticker': ticker,
                        'start_date': dates[i].date(),
                        'end_date': window_end.date(),
                        'insider_count': unique_insiders,
                        'total_value': total_value,
                        'trades': len(window_trades)
                    })
                    break  # Only report first cluster for this ticker

if potential_clusters:
    for cluster in potential_clusters:
        print(f"{cluster['ticker']}: {cluster['insider_count']} insiders, "
              f"${cluster['total_value']:,.0f} total value, "
              f"{cluster['start_date']} to {cluster['end_date']}")
else:
    print("❌ NO CLUSTERS FOUND (need 2+ unique insiders within 5 days on same ticker)")
print()

# 4. Near-misses: Single insiders with large purchases
print("4. NEAR-MISSES: Large Single-Insider Purchases (>$50k)")
print("-" * 80)
large_purchases = gap_trades[gap_trades['value'] > 50000].sort_values('value', ascending=False)
if len(large_purchases) > 0:
    print(f"Found {len(large_purchases)} large purchases:")
    for _, trade in large_purchases.head(20).iterrows():
        insider_col = 'insider_canonical' if 'insider_canonical' in trade.index else 'insider_name'
        print(f"{trade['trade_date'].date()} - {trade['ticker']}: "
              f"{trade[insider_col]} ({trade.get('title', 'N/A')}), "
              f"${trade['value']:,.0f}")
else:
    print("No purchases over $50k found")
print()

# 5. Tickers with single insider (1 away from cluster)
print("5. TICKERS WITH SINGLE INSIDER (one more needed for cluster)")
print("-" * 80)
single_insider_tickers = []
for ticker, group in ticker_groups:
    insider_col = 'insider_canonical' if 'insider_canonical' in group.columns else 'insider_name'
    if group[insider_col].nunique() == 1 and len(group) >= 1:
        total_value = group['value'].sum()
        if total_value > 20000:  # Filter noise
            single_insider_tickers.append({
                'ticker': ticker,
                'insider': group[insider_col].iloc[0],
                'trades': len(group),
                'total_value': total_value,
                'date': group['trade_date'].min().date()
            })

single_insider_tickers = sorted(single_insider_tickers, key=lambda x: x['total_value'], reverse=True)
if single_insider_tickers:
    print(f"Found {len(single_insider_tickers)} tickers with single insiders:")
    for item in single_insider_tickers[:20]:
        print(f"{item['date']} - {item['ticker']}: {item['insider']}, "
              f"${item['total_value']:,.0f} ({item['trades']} trades)")
else:
    print("No significant single-insider positions found")
print()

# 6. Compare to baseline (previous 14 days)
print("6. COMPARISON TO BASELINE (Dec 9-23, 2025)")
print("-" * 80)
baseline_start = pd.to_datetime('2025-12-09')
baseline_end = pd.to_datetime('2025-12-23')
baseline_trades = df[(df['trade_date'] >= baseline_start) & (df['trade_date'] <= baseline_end)]

print(f"Baseline period (Dec 9-23): {len(baseline_trades)} trades")
print(f"Gap period (Dec 24-Jan 6): {len(gap_trades)} trades")
print(f"Change: {len(gap_trades) - len(baseline_trades)} trades "
      f"({((len(gap_trades) / len(baseline_trades) - 1) * 100) if len(baseline_trades) > 0 else 0:.1f}% change)")
print()

# 7. Quality filters check
print("7. QUALITY FILTER CHECK")
print("-" * 80)
print("Trades that might fail quality filters:")

# Get price data if available
if 'price' in gap_trades.columns:
    penny_stocks = gap_trades[gap_trades['price'] <= 2.0]
    print(f"  - Penny stocks (price <= $2): {len(penny_stocks)} trades")

small_purchases = gap_trades[gap_trades['value'] < 50000]
print(f"  - Small purchases (<$50k): {len(small_purchases)} trades ({len(small_purchases)/len(gap_trades)*100:.1f}%)")

print()
print("=" * 80)
print("SUMMARY")
print("=" * 80)

if len(potential_clusters) > 0:
    print(f"✅ {len(potential_clusters)} potential clusters detected in raw data")
    print("   → Issue likely: Quality filters or scoring thresholds")
else:
    print("❌ NO clusters detected in raw data (2+ insiders per ticker)")
    print("   → Issue: Market reality - low clustering activity during holidays")

avg_daily_trades = len(gap_trades) / 14
baseline_avg = len(baseline_trades) / 15 if len(baseline_trades) > 0 else 0
print(f"\nDaily average: {avg_daily_trades:.1f} trades (baseline: {baseline_avg:.1f})")

if avg_daily_trades < baseline_avg * 0.5:
    print("⚠️  ALERT: Trading activity significantly below baseline (>50% drop)")
elif avg_daily_trades < baseline_avg * 0.8:
    print("⚠️  NOTE: Trading activity moderately below baseline")
else:
    print("✓ Trading activity normal compared to baseline")
