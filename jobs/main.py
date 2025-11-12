# jobs/main.py
import os
import argparse
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from fetch_openinsider import fetch_openinsider_recent
from fetch_sec_edgar import fetch_sec_edgar_data
from process_signals import cluster_and_score, is_urgent
from generate_report import render_daily_html, render_urgent_html, render_no_activity_html
from send_email import send_email
from paper_trade import PaperTradingPortfolio
from news_sentiment import check_news_for_signals
from paper_trade_monitor import PaperTradingMonitor

# Multi-signal detection imports
try:
    from multi_signal_detector import MultiSignalDetector, combine_insider_and_politician_signals
    from config import (
        ENABLE_MULTI_SIGNAL, ENABLE_POLITICIAN_SCRAPING, ENABLE_13F_CHECKING,
        SEC_USER_AGENT, POLITICIAN_LOOKBACK_DAYS, POLITICIAN_MAX_PAGES
    )
    MULTI_SIGNAL_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Multi-signal detection not available: {e}")
    MULTI_SIGNAL_AVAILABLE = False
    ENABLE_MULTI_SIGNAL = False

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
HISTORY_CSV = os.path.join(DATA_DIR, 'signals_history.csv')

def load_recent_signals(days_back=7):
    """
    Load signals from the last N days to check for duplicates.
    Returns set of (ticker, date) tuples.
    """
    if not os.path.exists(HISTORY_CSV):
        return set()
    
    df = pd.read_csv(HISTORY_CSV, parse_dates=['date'])
    cutoff = datetime.utcnow() - timedelta(days=days_back)
    recent = df[df['date'] >= cutoff]
    
    # Return set of (ticker, date_str) for quick lookup
    return set(zip(recent['ticker'], recent['date'].dt.strftime('%Y-%m-%d')))

def filter_new_signals(cluster_df, recent_signals):
    """
    Filter out signals that were already sent in the last 7 days,
    UNLESS there's been new insider activity.
    
    Logic: A signal is "new" if:
    1. Ticker hasn't been signaled in last 7 days, OR
    2. The last_trade_date is more recent than the last signal date
    """
    if cluster_df is None or cluster_df.empty:
        return pd.DataFrame()
    
    today = datetime.utcnow().strftime('%Y-%m-%d')
    new_signals = []
    
    for _, row in cluster_df.iterrows():
        ticker = row['ticker']
        
        # Check if this ticker was signaled recently
        recent_dates = [date_str for (t, date_str) in recent_signals if t == ticker]
        
        if not recent_dates:
            # Never signaled before - include it
            new_signals.append(row)
            print(f"   ✅ {ticker}: NEW signal (first time)")
        else:
            # Ticker was signaled before - check if there's new activity
            last_signal_date = max(recent_dates)  # Most recent signal date
            
            # Get the last trade date from this signal
            last_trade = row.get('last_trade_date')
            if pd.isna(last_trade):
                # No trade date available, skip to be safe
                print(f"   ⏭️  {ticker}: SKIPPED (no trade date, already signaled on {last_signal_date})")
                continue
            
            last_trade_str = last_trade.strftime('%Y-%m-%d') if hasattr(last_trade, 'strftime') else str(last_trade)[:10]
            
            # If the last trade is AFTER the last signal, it's new activity
            if last_trade_str > last_signal_date:
                new_signals.append(row)
                print(f"   ✅ {ticker}: NEW activity (last trade {last_trade_str} > last signal {last_signal_date})")
            else:
                print(f"   ⏭️  {ticker}: SKIPPED (already signaled on {last_signal_date}, no new activity)")
    
    if not new_signals:
        return pd.DataFrame()
    
    return pd.DataFrame(new_signals)

def detect_heavy_selling(df):
    """
    Detect concerning insider selling patterns.
    Returns: DataFrame of tickers with heavy selling, or empty DataFrame
    """
    if df is None or df.empty:
        return pd.DataFrame()
    
    # Filter for sales
    sells = df[df['trade_type'].str.upper().str.contains('SALE|SELL', na=False)].copy()
    
    if sells.empty:
        return pd.DataFrame()
    
    # Identify C-suite roles
    def is_c_suite(title):
        if not title or not isinstance(title, str):
            return False
        t = title.upper()
        return any(x in t for x in ['CEO', 'CFO', 'PRESIDENT', 'CHIEF'])
    
    sells['is_c_suite'] = sells['title'].apply(is_c_suite)
    sells['value_calc'] = sells.apply(
        lambda r: abs(r['value']) if (r.get('value', 0) and r['value'] != 0) 
        else (abs(r.get('qty', 0)) * r.get('price', 0)), axis=1
    )
    
    # Flag concerning sells
    concerning = sells[
        (sells['is_c_suite'] == True) | 
        (sells['value_calc'] > 1000000)
    ].copy()
    
    if concerning.empty:
        return pd.DataFrame()
    
    # Group by ticker
    ticker_groups = concerning.groupby('ticker').agg({
        'insider': lambda x: list(x.unique()),
        'value_calc': 'sum',
        'is_c_suite': 'any'
    }).reset_index()
    
    ticker_groups['num_sellers'] = ticker_groups['insider'].apply(len)
    ticker_groups['total_sold'] = ticker_groups['value_calc']
    
    # Filter for significant selling
    significant = ticker_groups[
        (ticker_groups['num_sellers'] >= 2) |
        (ticker_groups['total_sold'] >= 2000000) |
        (ticker_groups['is_c_suite'] == True)
    ].copy()
    
    return significant[['ticker', 'num_sellers', 'total_sold', 'is_c_suite']]

def format_sell_warning(sell_df):
    """Format the selling warning banner as HTML and plain text"""
    if sell_df.empty:
        return "", ""
    
    html_lines = ['<div style="background-color:#fff3cd;border:2px solid #ffc107;padding:15px;margin:20px 0;border-radius:5px;">']
    html_lines.append('<h3 style="color:#856404;margin-top:0;">⚠️ Insider Selling Alert</h3>')
    html_lines.append('<p style="color:#856404;">The following stocks show concerning insider selling activity. Consider avoiding new positions or reviewing existing holdings:</p>')
    html_lines.append('<ul style="color:#856404;">')
    
    text_lines = ['\n' + '='*60]
    text_lines.append('⚠️  INSIDER SELLING ALERT')
    text_lines.append('='*60)
    text_lines.append('The following stocks show concerning insider selling activity.')
    text_lines.append('Consider avoiding new positions or reviewing existing holdings:')
    text_lines.append('')
    
    for _, row in sell_df.iterrows():
        ticker = row['ticker']
        num = int(row['num_sellers'])
        total = int(row['total_sold'])
        c_suite = row['is_c_suite']
        
        detail = f"{ticker}: {num} insider{'s' if num > 1 else ''} sold ${total:,}"
        if c_suite:
            detail += " (includes C-suite)"
        
        html_lines.append(f'<li><b>{detail}</b></li>')
        text_lines.append(f'  • {detail}')
    
    html_lines.append('</ul>')
    html_lines.append('</div>')
    text_lines.append('='*60 + '\n')
    
    return '\n'.join(html_lines), '\n'.join(text_lines)

def append_to_history(cluster_df):
    """
    Append new signals to the historical tracking CSV.
    Now includes sector, quality_score, and multi-signal fields.
    """
    if cluster_df is None or cluster_df.empty:
        return

    rows = []
    for _, r in cluster_df.iterrows():
        rows.append({
            'date': datetime.utcnow().strftime('%Y-%m-%d'),
            'ticker': r.get('ticker'),
            'signal_score': float(r.get('rank_score', 0)),
            'action': r.get('suggested_action'),
            'cluster_count': int(r.get('cluster_count', 0)),
            'total_value': float(r.get('total_value', 0)),
            'sector': r.get('sector', 'Unknown'),
            'quality_score': float(r.get('quality_score', 0)),
            'pattern_detected': r.get('pattern_detected', 'None'),
            'multi_signal_tier': r.get('multi_signal_tier', 'none'),
            'has_politician_signal': bool(r.get('has_politician_signal', False))
        })

    new_df = pd.DataFrame(rows)
    
    if os.path.exists(HISTORY_CSV):
        old = pd.read_csv(HISTORY_CSV)
        combined = pd.concat([old, new_df], ignore_index=True)
    else:
        combined = new_df
    
    combined.to_csv(HISTORY_CSV, index=False)
    print(f"✅ Saved {len(new_df)} signal(s) to history (total: {len(combined)} signals tracked)")

def main(test=False, urgent_test=False, enable_paper_trading=True):
    print(f"{'='*60}")
    print(f"🔍 Insider Cluster Watch - {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")
    
    # Initialize paper trading simulator
    paper_trader = None
    if enable_paper_trading:
        paper_trader = PaperTradingPortfolio.load()
        portfolio_value = paper_trader.get_portfolio_value()
        total_return = ((portfolio_value - paper_trader.starting_capital) / paper_trader.starting_capital) * 100

        print(f"📊 Paper Trading: Enabled")
        print(f"   Portfolio Value: ${portfolio_value:,.2f}")
        print(f"   Cash: ${paper_trader.cash:,.2f}")
        print(f"   Open Positions: {len(paper_trader.positions)}\n")
    
    # 1) Fetch insider trading data
    print("📥 Fetching recent insider transactions from OpenInsider...")
    df = fetch_openinsider_recent()
    
    if df is None or df.empty:
        print("⚠️  OpenInsider returned no data, trying SEC EDGAR backup...")
        df = fetch_sec_edgar_data(days_back=3, max_filings=50)

        if df is None or df.empty:
            print("❌ No data available from either OpenInsider or SEC EDGAR")
            html, text = render_no_activity_html(
                total_transactions=0,
                buy_count=0,
                sell_warning_html=""
            )
            send_email(f"Daily Insider Report — {datetime.utcnow().strftime('%Y-%m-%d')}", html, text)
            return
        else:
            print(f"✅ Using SEC EDGAR data: {len(df)} transaction(s)")

    print(f"✅ Fetched {len(df)} transaction(s)")
    
    # Show breakdown
    buy_count = df[df['trade_type'].str.upper().str.contains('BUY|PURCHASE|P -', na=False)].shape[0]
    sell_count = df[df['trade_type'].str.upper().str.contains('SALE|SELL|S -', na=False)].shape[0]
    print(f"   • {buy_count} buy transaction(s)")
    print(f"   • {sell_count} sale transaction(s)\n")

    # 2) Check for concerning insider selling
    print("🔍 Analyzing insider selling patterns...")
    sell_warnings = detect_heavy_selling(df)
    sell_warning_html, sell_warning_text = format_sell_warning(sell_warnings)
    
    if not sell_warnings.empty:
        print(f"⚠️  WARNING: Detected concerning selling activity in {len(sell_warnings)} ticker(s):")
        for _, row in sell_warnings.iterrows():
            c_suite_indicator = " (C-suite)" if row['is_c_suite'] else ""
            print(f"   • {row['ticker']}: {row['num_sellers']} seller(s), ${int(row['total_sold']):,}{c_suite_indicator}")
        print()
    else:
        print("✅ No concerning selling activity detected\n")

    # 3) Process buy signals and compute cluster scores (with enhanced features)
    print("🔎 Processing buy signals with enhanced features...")
    print("   • Quality filtering (penny stocks, small buys)")
    print("   • Sector analysis")
    print("   • Pattern detection (accelerating buys, CEO clusters)")
    cluster_df = cluster_and_score(df, window_days=5, top_n=50)

    if cluster_df is None or cluster_df.empty:
        print("ℹ️  No significant insider buying clusters detected")
        
        total_tx = len(df) if df is not None and not df.empty else 0
        html, text = render_no_activity_html(
            total_transactions=total_tx,
            buy_count=buy_count,
            sell_warning_html=sell_warning_html if not sell_warnings.empty else ""
        )
        
        send_email(f"Daily Insider Report — {datetime.utcnow().strftime('%Y-%m-%d')}", html, text)
        print(f"\n{'='*60}")
        print("✅ Report complete - no-activity email sent")
        print(f"{'='*60}\n")
        return

    print(f"✅ Found {len(cluster_df)} buy cluster(s)")
    
    # Show quality and sector breakdown
    if 'quality_score' in cluster_df.columns:
        high_quality = len(cluster_df[cluster_df['quality_score'] >= 7])
        print(f"   • {high_quality} high-quality signals (score ≥7)")
    
    if 'sector' in cluster_df.columns:
        sector_counts = cluster_df['sector'].value_counts()
        print(f"   • Sectors: {dict(sector_counts.head(3))}")
    
    if 'pattern_detected' in cluster_df.columns:
        patterns = cluster_df[cluster_df['pattern_detected'] != 'None']['pattern_detected'].value_counts()
        if not patterns.empty:
            print(f"   • Patterns: {dict(patterns)}")

    # 3.5) Multi-signal detection (politician + institutional)
    multi_signal_data = None
    if MULTI_SIGNAL_AVAILABLE and ENABLE_MULTI_SIGNAL and ENABLE_POLITICIAN_SCRAPING:
        print("\n🔍 Running multi-signal detection...")
        print("   • Scanning politician trades")
        if ENABLE_13F_CHECKING:
            print("   • Checking 13F institutional holdings")

        try:
            detector = MultiSignalDetector(SEC_USER_AGENT)

            # Get current quarter for 13F checks
            now = datetime.utcnow()
            quarter = (now.month - 1) // 3 + 1
            year = now.year
            if quarter == 1:
                quarter = 4
                year -= 1
            else:
                quarter -= 1

            # Run full scan
            multi_signal_results = detector.run_full_scan(
                cluster_df,
                check_13f=ENABLE_13F_CHECKING,
                quarter_year=year,
                quarter=quarter
            )

            # Enrich cluster_df with multi-signal data
            tier1_tickers = [s['ticker'] for s in multi_signal_results['tier1']]
            tier2_tickers = [s['ticker'] for s in multi_signal_results['tier2']]

            # Create lookup dictionary for detailed multi-signal data
            multi_signal_lookup = {}
            for signal in multi_signal_results['tier1'] + multi_signal_results['tier2']:
                ticker = signal['ticker']

                # Extract politician details
                politician_names = []
                politician_details = []
                if signal['has_politician'] and signal['politician_data']:
                    pol_data = signal['politician_data']
                    if 'trades' in pol_data:
                        for trade in pol_data['trades'][:5]:  # Top 5 politicians
                            name = trade.get('politician', 'Unknown')
                            trade_type = trade.get('transaction_type', 'trade').upper()
                            amount = trade.get('amount', 0)
                            politician_names.append(name)
                            if amount > 0:
                                politician_details.append(f"{name} ({trade_type}, ${amount:,})")
                            else:
                                politician_details.append(f"{name} ({trade_type})")

                # Extract institutional details
                institutional_names = []
                institutional_details = []
                if signal['has_institutional'] and signal['institutional_data'] is not None:
                    inst_data = signal['institutional_data']
                    if hasattr(inst_data, 'iterrows'):  # DataFrame
                        for idx, row in inst_data.head(10).iterrows():  # Top 10 institutions
                            name = row.get('name', 'Unknown Fund')
                            value = row.get('value', 0)
                            institutional_names.append(name)
                            if value > 1_000_000_000:
                                institutional_details.append(f"{name} (${value/1_000_000_000:.1f}B)")
                            elif value > 1_000_000:
                                institutional_details.append(f"{name} (${value/1_000_000:.1f}M)")
                            else:
                                institutional_details.append(f"{name} (${value:,.0f})")

                # Create explanation text
                signals = []
                if signal['has_politician']:
                    signals.append("Politician Trading")
                if signal['has_institutional']:
                    signals.append("Institutional Holdings (13F)")
                if signal['has_high_short']:
                    signals.append("High Short Interest")

                explanation = f"Insider Buying + {' + '.join(signals)}" if signals else "Insider Buying"

                multi_signal_lookup[ticker] = {
                    'tier': 'tier1' if ticker in tier1_tickers else 'tier2',
                    'politician_names': politician_names,
                    'politician_details': politician_details,
                    'institutional_names': institutional_names,
                    'institutional_details': institutional_details,
                    'explanation': explanation,
                    'has_politician': signal['has_politician'],
                    'has_institutional': signal['has_institutional'],
                    'politician_count': signal['politician_count'],
                    'institutional_count': signal['institutional_count']
                }

            # Apply multi-signal data to cluster_df
            def enrich_with_multi_signal(row):
                ticker = row['ticker']
                if ticker in multi_signal_lookup:
                    ms_data = multi_signal_lookup[ticker]
                    row['multi_signal_tier'] = ms_data['tier']
                    row['has_politician_signal'] = ms_data['has_politician']
                    row['politician_names'] = ms_data['politician_names']
                    row['politician_details'] = ms_data['politician_details']
                    row['institutional_names'] = ms_data['institutional_names']
                    row['institutional_details'] = ms_data['institutional_details']
                    row['multi_signal_explanation'] = ms_data['explanation']
                    row['politician_count'] = ms_data['politician_count']
                    row['institutional_count'] = ms_data['institutional_count']
                else:
                    row['multi_signal_tier'] = 'none'
                    row['has_politician_signal'] = False
                    row['politician_names'] = []
                    row['politician_details'] = []
                    row['institutional_names'] = []
                    row['institutional_details'] = []
                    row['multi_signal_explanation'] = ''
                    row['politician_count'] = 0
                    row['institutional_count'] = 0
                return row

            cluster_df = cluster_df.apply(enrich_with_multi_signal, axis=1)

            # Boost rank_score for multi-signal stocks
            cluster_df.loc[cluster_df['multi_signal_tier'] == 'tier1', 'rank_score'] *= 1.5
            cluster_df.loc[cluster_df['multi_signal_tier'] == 'tier2', 'rank_score'] *= 1.25

            # Re-sort by updated rank score
            cluster_df = cluster_df.sort_values('rank_score', ascending=False)

            # Log results
            total_multi = len(tier1_tickers) + len(tier2_tickers)
            if total_multi > 0:
                print(f"   ✅ Found {total_multi} stocks with multiple signals!")
                print(f"      • Tier 1 (3+ signals): {len(tier1_tickers)}")
                print(f"      • Tier 2 (2 signals): {len(tier2_tickers)}")

                if tier1_tickers:
                    print(f"      • Tier 1 tickers: {', '.join(tier1_tickers[:5])}")
            else:
                print(f"   ℹ️  No multi-signal overlaps detected")

            multi_signal_data = multi_signal_results

        except Exception as e:
            print(f"   ⚠️  Multi-signal detection failed: {e}")
            import traceback
            traceback.print_exc()

    # 4) Check news sentiment for signals
    print("\n📰 Checking news sentiment...")
    cluster_df = check_news_for_signals(cluster_df)
    
    if cluster_df.empty:
        print("⚠️  All signals filtered out due to negative news")
        total_tx = len(df) if df is not None and not df.empty else 0
        html, text = render_no_activity_html(
            total_transactions=total_tx,
            buy_count=buy_count,
            sell_warning_html=sell_warning_html if not sell_warnings.empty else ""
        )
        send_email(f"Daily Insider Report — {datetime.utcnow().strftime('%Y-%m-%d')}", html, text)
        print(f"\n{'='*60}")
        print("✅ Report complete - no signals passed news filter")
        print(f"{'='*60}\n")
        return
    
    # 5) Filter out duplicate signals
    print("\n🔍 Checking for duplicate signals...")
    recent_signals = load_recent_signals(days_back=7)
    print(f"   Loaded {len(recent_signals)} recent signals from last 7 days")
    
    new_cluster_df = filter_new_signals(cluster_df, recent_signals)
    
    if new_cluster_df.empty:
        print("\n⚠️  All signals are duplicates - no new insider activity")
        print("   Sending no-activity report\n")
        
        total_tx = len(df) if df is not None and not df.empty else 0
        html, text = render_no_activity_html(
            total_transactions=total_tx,
            buy_count=buy_count,
            sell_warning_html=sell_warning_html if not sell_warnings.empty else ""
        )
        
        send_email(f"Daily Insider Report — {datetime.utcnow().strftime('%Y-%m-%d')}", html, text)
        print(f"{'='*60}")
        print("✅ Report complete - no new signals to report")
        print(f"{'='*60}\n")
        return
    
    print(f"\n✅ Found {len(new_cluster_df)} NEW signal(s) to report\n")
    
    # Use new_cluster_df instead of cluster_df from here on
    cluster_df = new_cluster_df
    
    # Show top signals with enhanced info
    print("📊 New signals:")
    for idx, row in cluster_df.head(5).iterrows():
        quality = f", Quality={row.get('quality_score', 0):.1f}" if 'quality_score' in row else ""
        sector = f", {row.get('sector', 'N/A')}" if 'sector' in row else ""
        pattern = f", Pattern: {row.get('pattern_detected', 'None')}" if 'pattern_detected' in row and row.get('pattern_detected') != 'None' else ""

        # Add multi-signal tier indicator
        multi_tier = ""
        if 'multi_signal_tier' in row and row.get('multi_signal_tier') != 'none':
            tier = row['multi_signal_tier'].upper()
            emoji = "🔥" if tier == "TIER1" else "⚡"
            multi_tier = f" {emoji} {tier}"

        politician_flag = " 🏛️ POLITICIAN" if row.get('has_politician_signal', False) else ""

        print(f"   {row['ticker']}: Cluster={row['cluster_count']}, Score={row['rank_score']:.2f}{quality}{sector}{pattern}, ${int(row['total_value']):,}{multi_tier}{politician_flag}")
    print()

    
    # 6) Paper trading: Process signals
    if paper_trader:
        print("\n" + "="*60)
        print("📈 PAPER TRADING - SIGNAL PROCESSING")
        print("="*60)
        
        # Initialize monitor
        monitor = PaperTradingMonitor()
        start_value = paper_trader.get_portfolio_value()
        monitor.set_start_of_day_value(start_value)
        
        # Show current status
        stats = paper_trader.get_performance_summary()
        print(f"\n📊 Current Portfolio Status:")
        print(f"   Portfolio Value: ${stats['current_value']:,.2f}")
        print(f"   Cash: ${stats['cash']:,.2f}")
        print(f"   Open Positions: {stats['open_positions']}")
        print(f"   Pending Entries: {stats['pending_entries']}")
        print(f"   Total Return: {stats['total_return_pct']:+.2f}%")
        print(f"   Exposure: {stats['exposure_pct']:.1f}%")
        
        # Check exits first (stops, targets, scaling)
        print(f"\n🔍 Checking exits and updates...")
        closed = paper_trader.check_exits()
        
        # Process new signals
        print(f"\n📊 Processing {len(cluster_df)} new signal(s)...")
        signals_executed = 0
        signals_skipped = 0

        for _, signal_row in cluster_df.iterrows():
            entry_price = signal_row.get('currentPrice')
            
            # Skip if no valid price (market data fetch failed)
            if entry_price is None or pd.isna(entry_price) or entry_price <= 0:
                signals_skipped += 1
                continue
            
            # Execute signal if price is valid
            signal = {
                'ticker': signal_row['ticker'],
                'entry_price': entry_price,
                'signal_date': datetime.utcnow().strftime('%Y-%m-%d'),
                'signal_score': signal_row.get('rank_score', 0),
                'cluster_count': signal_row.get('cluster_count', 0),
                'sector': signal_row.get('sector', 'Unknown'),
                'multi_signal_tier': signal_row.get('multi_signal_tier', 'none'),
                'has_politician_signal': signal_row.get('has_politician_signal', False)
            }
            
            if paper_trader.execute_signal(signal):
                signals_executed += 1
        
        # Run health check
        print(f"\n🏥 Running portfolio health check...")
        status, alerts = monitor.check_portfolio_health(paper_trader)
        
        if alerts:
            print(monitor.format_alerts_report(status, alerts))
            monitor.log_alerts(status, alerts)
        else:
            print("   ✅ Portfolio health: HEALTHY")
        
        # Save portfolio
        paper_trader.save()
        
        # Final summary
        final_stats = paper_trader.get_performance_summary()
        print(f"\n📊 Paper Trading Summary:")
        print(f"   Executed: {signals_executed} position(s)")
        if signals_skipped > 0:
            print(f"   Skipped: {signals_skipped} signal(s) (no price data)")
        if closed:
            print(f"   Closed: {len(closed)} position(s)")
        print(f"   Portfolio Value: ${final_stats['current_value']:,.2f}")
        print(f"   Total Return: {final_stats['total_return_pct']:+.2f}%")
        print(f"   Win Rate: {final_stats['win_rate']:.1f}%")
        print(f"   Active Positions: {final_stats['open_positions']}")
        print(f"   Pending Entries: {final_stats['pending_entries']}")
        print("="*60 + "\n")

    # 7) Save signals to history
    print("💾 Saving signals to history...")
    append_to_history(cluster_df)
    print()

    # 8) Check for urgent signals
    urgent_df = cluster_df[cluster_df.apply(lambda r: is_urgent(r), axis=1)].copy()
    
    if not urgent_df.empty:
        print(f"🚨 URGENT: {len(urgent_df)} high-conviction signal(s) detected:")
        for _, row in urgent_df.iterrows():
            print(f"   • {row['ticker']} - {row['suggested_action']}")
        print()

    # 9) Generate reports
    print("📧 Generating email reports...")
    daily_html, daily_text = render_daily_html(cluster_df)
    
    # Insert sell warning banner
    if not sell_warnings.empty:
        daily_html = daily_html.replace('</h2>', f'</h2>{sell_warning_html}')
        daily_text = sell_warning_text + '\n\n' + daily_text
    
    # Generate urgent email if needed
    if not urgent_df.empty:
        urgent_html, urgent_text = render_urgent_html(urgent_df)
        if not sell_warnings.empty:
            urgent_html = urgent_html.replace('</h2>', f'</h2>{sell_warning_html}')
            urgent_text = sell_warning_text + '\n\n' + urgent_text
    else:
        urgent_html = None
        urgent_text = None

    # 10) Send emails
    if test:
        print("📬 Sending TEST emails...")
        send_email(f"TEST — Daily Insider Report — {datetime.utcnow().strftime('%Y-%m-%d')}", daily_html, daily_text)
        if urgent_html:
            send_email(f"TEST — URGENT Insider Alert — {datetime.utcnow().strftime('%Y-%m-%d')}", urgent_html, urgent_text)
    else:
        print("📬 Sending daily report...")
        send_email(f"Daily Insider Report — {datetime.utcnow().strftime('%Y-%m-%d')}", daily_html, daily_text)
        if urgent_html:
            print("📬 Sending urgent alert...")
            send_email(f"URGENT Insider Alert — {datetime.utcnow().strftime('%Y-%m-%d')}", urgent_html, urgent_text)
    
    print(f"\n{'='*60}")
    print("✅ All done! Reports sent successfully")
    if paper_trader:
        portfolio_value = paper_trader.get_portfolio_value()
        total_return = ((portfolio_value - paper_trader.starting_capital) / paper_trader.starting_capital) * 100
        print(f"📊 Paper Portfolio: ${portfolio_value:,.2f} ({total_return:+.2f}%)")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='Send test emails and exit')
    parser.add_argument('--urgent-test', action='store_true', help='Generate a fake urgent email for testing')
    parser.add_argument('--no-paper-trading', action='store_true', help='Disable paper trading simulation')
    args = parser.parse_args()
    
    if args.urgent_test:
        # Generate a fake urgent HTML so you can test templates
        print("🧪 Generating test urgent alert...\n")
        fake = pd.DataFrame([{
            'ticker':'FAKE',
            'last_trade_date':pd.Timestamp.now(),
            'cluster_count':4,
            'total_value':500000,
            'avg_conviction':20,
            'insiders':'CEO, CFO, DIRECTOR',
            'currentPrice': 5.25,
            'pct_from_52wk_low': 10.0,
            'rank_score': 15.0,
            'suggested_action': 'URGENT: Consider small entry at open / immediate review',
            'rationale': 'Cluster count:4 | Total reported buys: $500,000 | Current Price: $5.25 | 10.0% above 52-week low | Rank Score: 15.00',
            'sector': 'Technology',
            'quality_score': 8.5,
            'pattern_detected': 'CEO Cluster',
            'news_sentiment': 'positive'
        }])
        from generate_report import render_urgent_html
        html, text = render_urgent_html(fake)
        send_email("URGENT TEST INSIDER ALERT", html, text)
    else:
        main(test=args.test, enable_paper_trading=not args.no_paper_trading)
