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
            'total_value': float(r.get('total_value', 0))
        })
    
    new_df = pd.DataFrame(rows)
    
    if os.path.exists(HISTORY_CSV):
        old = pd.read_csv(HISTORY_CSV)
        combined = pd.concat([old, new_df], ignore_index=True)
    else:
        combined = new_df
    
    combined.to_csv(HISTORY_CSV, index=False)
    print(f"✅ Saved {len(new_df)} signal(s) to history (total: {len(combined)} signals tracked)")

def main(test=False, urgent_test=False):
    print(f"{'='*60}")
    print(f"🔍 Insider Cluster Watch - {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")
    
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

    # 3) Process buy signals and compute cluster scores
    print("🔎 Processing buy signals and clustering...")
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
    
    # 4) Filter out duplicate signals (NEW STEP)
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
    
    # Show top signals
    print("📊 New signals:")
    for idx, row in cluster_df.head(5).iterrows():
        print(f"   {row['ticker']}: Cluster={row['cluster_count']}, Score={row['rank_score']:.2f}, ${int(row['total_value']):,}")
    print()

    # 5) Save signals to history
    print("💾 Saving signals to history...")
    append_to_history(cluster_df)
    print()

    # 6) Check for urgent signals
    urgent_df = cluster_df[cluster_df.apply(lambda r: is_urgent(r), axis=1)].copy()
    
    if not urgent_df.empty:
        print(f"🚨 URGENT: {len(urgent_df)} high-conviction signal(s) detected:")
        for _, row in urgent_df.iterrows():
            print(f"   • {row['ticker']} - {row['suggested_action']}")
        print()

    # 7) Generate reports
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

    # 8) Send emails
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
    print(f"{'='*60}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='Send test emails and exit')
    parser.add_argument('--urgent-test', action='store_true', help='Generate a fake urgent email for testing')
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
            'rationale': 'Cluster count:4 | Total reported buys: $500,000 | Current Price: $5.25 | 10.0% above 52-week low | Rank Score: 15.00'
        }])
        from generate_report import render_urgent_html
        html, text = render_urgent_html(fake)
        send_email("URGENT TEST INSIDER ALERT", html, text)
    else:
        main(test=args.test)
