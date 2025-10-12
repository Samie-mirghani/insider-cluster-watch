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
    if df is None or df.empty:
        print("No data fetched from OpenInsider.")
        return

    # 2) compute clusters & scores
    cluster_df = cluster_and_score(df, window_days=5, top_n=50)

    if cluster_df is None or cluster_df.empty:
        print("No clusters detected.")
        # Still send an email saying "no signals today"
        send_email(
            f"Daily Insider Report — {datetime.utcnow().strftime('%Y-%m-%d')}",
            "<html><body><p>No significant insider buying activity detected today.</p></body></html>",
            "No significant insider buying activity detected today."
        )
        return

    # 3) append to history CSV
    append_to_history(cluster_df)

    # 4) prepare urgent and daily reports
    urgent_df = cluster_df[cluster_df.apply(lambda r: is_urgent(r), axis=1)].copy()
    daily_html, daily_text = render_daily_html(cluster_df)
    # If urgent signals exist, render urgent email
    if not urgent_df.empty:
        urgent_html, urgent_text = render_urgent_html(urgent_df)
    else:
        urgent_html = None
        urgent_text = None

    # 5) If in test mode, send a forced test email and exit
    if test:
        send_email(f"TEST — Daily Insider Report — {datetime.utcnow().strftime('%Y-%m-%d')}", daily_html, daily_text)
        if urgent_html:
            send_email(f"TEST — URGENT Insider Alert — {datetime.utcnow().strftime('%Y-%m-%d')}", urgent_html, urgent_text)
        return

    # 6) Normal run: send daily email always, urgent only if exists
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
