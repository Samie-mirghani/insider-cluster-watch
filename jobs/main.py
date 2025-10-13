# jobs/main.py
import os
import argparse
from datetime import datetime
import pandas as pd

from fetch_openinsider import fetch_openinsider_recent
from process_signals import cluster_and_score, is_urgent
from generate_report import render_daily_html, render_urgent_html
from send_email import send_email

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
HISTORY_CSV = os.path.join(DATA_DIR, 'signals_history.csv')

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
    
    # Flag concerning sells:
    # 1. C-suite selling
    # 2. Large value (>$1M)
    # 3. Multiple insiders selling same ticker
    concerning = sells[
        (sells['is_c_suite'] == True) | 
        (sells['value_calc'] > 1000000)
    ].copy()
    
    if concerning.empty:
        return pd.DataFrame()
    
    # Group by ticker to find clusters of selling
    ticker_groups = concerning.groupby('ticker').agg({
        'insider': lambda x: list(x.unique()),
        'value_calc': 'sum',
        'is_c_suite': 'any'
    }).reset_index()
    
    ticker_groups['num_sellers'] = ticker_groups['insider'].apply(len)
    ticker_groups['total_sold'] = ticker_groups['value_calc']
    
    # Filter for significant selling (multiple sellers OR large value OR c-suite)
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
    cluster_df expected columns: ticker,last_trade_date,cluster_count,total_value,avg_conviction,insiders,currentPrice,...
    We'll save: date,ticker,signal_score,action
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
    print(f"Appended {len(new_df)} signals to {HISTORY_CSV}")

def main(test=False, urgent_test=False):
    # 1) fetch
    df = fetch_openinsider_recent()
    
    # DEBUG output
    print(f"DEBUG: Fetched {len(df) if df is not None else 0} raw records")
    if df is not None and not df.empty:
        print(f"DEBUG: Trade types: {df['trade_type'].value_counts()}")
    
    if df is None or df.empty:
        print("No data fetched from OpenInsider.")
        html = "<html><body><p>No data available from OpenInsider today (possibly weekend/holiday)</p></body></html>"
        text = "No data available from OpenInsider today"
        send_email(f"Daily Insider Report — {datetime.utcnow().strftime('%Y-%m-%d')}", html, text)
        return

    # 2) Check for heavy selling BEFORE processing buys
    sell_warnings = detect_heavy_selling(df)
    sell_warning_html, sell_warning_text = format_sell_warning(sell_warnings)
    
    if not sell_warnings.empty:
        print(f"⚠️  Warning: Detected concerning selling in {len(sell_warnings)} ticker(s)")

    # 3) compute clusters & scores (buys only)
    cluster_df = cluster_and_score(df, window_days=5, top_n=50)
    
    print(f"DEBUG: Found {len(cluster_df) if cluster_df is not None else 0} clusters")

    if cluster_df is None or cluster_df.empty:
        print("No clusters detected.")
        # Send email with just the sell warnings if they exist
        if sell_warnings.empty:
            html = "<html><body><p>No significant insider buying clusters detected today</p></body></html>"
            text = "No significant insider buying clusters detected today"
        else:
            html = f"<html><body><p>No significant insider buying clusters detected today</p>{sell_warning_html}</body></html>"
            text = f"No significant insider buying clusters detected today\n{sell_warning_text}"
        send_email(f"Daily Insider Report — {datetime.utcnow().strftime('%Y-%m-%d')}", html, text)
        return

    # 4) append to history CSV
    append_to_history(cluster_df)

    # 5) prepare urgent and daily reports
    urgent_df = cluster_df[cluster_df.apply(lambda r: is_urgent(r), axis=1)].copy()
    daily_html, daily_text = render_daily_html(cluster_df)
    
    # Insert sell warning banner into the reports
    if not sell_warnings.empty:
        # Insert warning after the header in HTML
        daily_html = daily_html.replace('</h2>', f'</h2>{sell_warning_html}')
        # Insert warning at the top in text
        daily_text = sell_warning_text + '\n\n' + daily_text
    
    # If urgent signals exist, render urgent email
    if not urgent_df.empty:
        urgent_html, urgent_text = render_urgent_html(urgent_df)
        # Add sell warnings to urgent emails too
        if not sell_warnings.empty:
            urgent_html = urgent_html.replace('</h2>', f'</h2>{sell_warning_html}')
            urgent_text = sell_warning_text + '\n\n' + urgent_text
    else:
        urgent_html = None
        urgent_text = None

    # 6) If in test mode, send a forced test email and exit
    if test:
        send_email(f"TEST — Daily Insider Report — {datetime.utcnow().strftime('%Y-%m-%d')}", daily_html, daily_text)
        if urgent_html:
            send_email(f"TEST — URGENT Insider Alert — {datetime.utcnow().strftime('%Y-%m-%d')}", urgent_html, urgent_text)
        return

    # 7) Normal run: send daily email always, urgent only if exists
    send_email(f"Daily Insider Report — {datetime.utcnow().strftime('%Y-%m-%d')}", daily_html, daily_text)
    if urgent_html:
        send_email(f"URGENT Insider Alert — {datetime.utcnow().strftime('%Y-%m-%d')}", urgent_html, urgent_text)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='Send test emails and exit')
    parser.add_argument('--urgent-test', action='store_true', help='Generate a fake urgent email for testing')
    args = parser.parse_args()
    if args.urgent_test:
        # generate a fake urgent HTML so you can test templates
        import pandas as pd
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
        html, text = render_urgent_html(fake)
        send_email("URGENT TEST INSIDER ALERT", html, text)
    else:
        main(test=args.test)
