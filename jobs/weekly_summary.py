# jobs/weekly_summary.py
"""
Generate and send weekly performance summary email.
Analyzes backtest results and sends statistics without image attachments.
"""

import os
import pandas as pd
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from send_email import send_email

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
BACKTEST_CSV = os.path.join(DATA_DIR, 'backtest_results.csv')
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'templates')

def calculate_performance_stats():
    """
    Calculate performance statistics from backtest results.
    Returns dict with all necessary stats for the email template.
    """
    if not os.path.exists(BACKTEST_CSV):
        print("No backtest results found yet.")
        return None
    
    df = pd.read_csv(BACKTEST_CSV, parse_dates=['signal_date'])
    
    if df.empty:
        print("Backtest results file is empty.")
        return None
    
    # Separate 1-week and 1-month results
    df_1w = df[df['horizon'] == '1w'].copy()
    df_1m = df[df['horizon'] == '1m'].copy()
    
    stats = {}
    
    # 1-Month Statistics (primary)
    if not df_1m.empty:
        stats['total_signals_1m'] = len(df_1m)
        stats['winners_1m'] = len(df_1m[df_1m['ticker_return'] > 0])
        stats['hit_rate_1m'] = round((stats['winners_1m'] / stats['total_signals_1m']) * 100, 1)
        stats['avg_return_1m'] = round(df_1m['ticker_return'].mean() * 100, 2)
        stats['avg_alpha_1m'] = round(df_1m['alpha'].mean() * 100, 2)
        
        # Top 3 performers
        top = df_1m.nlargest(3, 'alpha')[['ticker', 'signal_date', 'ticker_return', 'alpha', 'signal_score']].copy()
        stats['top_performers'] = [
            {
                'ticker': row['ticker'],
                'signal_date': row['signal_date'].strftime('%b %d'),
                'return_pct': f"+{round(row['ticker_return'] * 100, 1)}" if row['ticker_return'] > 0 else f"{round(row['ticker_return'] * 100, 1)}",
                'alpha_pct': f"+{round(row['alpha'] * 100, 1)}" if row['alpha'] > 0 else f"{round(row['alpha'] * 100, 1)}",
                'signal_score': round(row['signal_score'], 1) if pd.notna(row['signal_score']) else 'N/A'
            }
            for _, row in top.iterrows()
        ]
    else:
        stats['total_signals_1m'] = 0
        stats['winners_1m'] = 0
        stats['hit_rate_1m'] = 0
        stats['avg_return_1m'] = 0
        stats['avg_alpha_1m'] = 0
        stats['top_performers'] = []
    
    # 1-Week Statistics (supplementary)
    if not df_1w.empty:
        stats['total_signals_1w'] = len(df_1w)
        stats['winners_1w'] = len(df_1w[df_1w['ticker_return'] > 0])
        stats['hit_rate_1w'] = round((stats['winners_1w'] / stats['total_signals_1w']) * 100, 1)
        stats['avg_return_1w'] = round(df_1w['ticker_return'].mean() * 100, 2)
        stats['avg_alpha_1w'] = round(df_1w['alpha'].mean() * 100, 2)
    else:
        stats['total_signals_1w'] = 0
        stats['winners_1w'] = 0
        stats['hit_rate_1w'] = 0
        stats['avg_return_1w'] = 0
        stats['avg_alpha_1w'] = 0
    
    return stats

def render_weekly_performance_email(stats):
    """
    Render the weekly performance email template.
    """
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template('weekly_performance.html')
    
    html = template.render(
        date=datetime.now().strftime("%B %d, %Y"),
        **stats
    )
    
    # Plain text version
    text_lines = [
        f"Weekly Performance Report — {datetime.now().strftime('%Y-%m-%d')}",
        "=" * 60,
        ""
    ]
    
    if stats['total_signals_1m'] > 0:
        text_lines.extend([
            f"Total Signals: {stats['total_signals_1m']}",
            f"Hit Rate (1m): {stats['hit_rate_1m']}% ({stats['winners_1m']} of {stats['total_signals_1m']} profitable)",
            f"Avg Return (1m): {stats['avg_return_1m']}%",
            f"Avg Alpha (1m): {stats['avg_alpha_1m']}%",
            ""
        ])
        
        if stats['total_signals_1w'] > 0:
            text_lines.extend([
                f"Hit Rate (1w): {stats['hit_rate_1w']}%",
                f"Avg Alpha (1w): {stats['avg_alpha_1w']}%",
                ""
            ])
        
        if stats['top_performers']:
            text_lines.append("Top Performers:")
            for p in stats['top_performers']:
                text_lines.append(f"  {p['ticker']}: {p['return_pct']}% (Alpha: {p['alpha_pct']}%)")
            text_lines.append("")
        
        # Performance assessment
        if float(stats['avg_alpha_1m']) > 0 and float(stats['hit_rate_1m']) >= 55:
            text_lines.append("✅ Strategy is working - outperforming SPY with good hit rate")
        elif float(stats['avg_alpha_1m']) > 0:
            text_lines.append("⚠️  Positive alpha but hit rate below target")
        else:
            text_lines.append("⚠️  Underperforming SPY - review strategy")
    else:
        text_lines.append("Not enough historical data yet. Keep monitoring!")
    
    text_lines.extend([
        "",
        "=" * 60,
        "View detailed charts in your GitHub repo at data/plots/",
        "=" * 60
    ])
    
    text = "\n".join(text_lines)
    
    return html, text

def main():
    print(f"{'='*60}")
    print(f"📊 Weekly Performance Summary - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")
    
    # Calculate performance stats
    print("📈 Calculating performance statistics...")
    stats = calculate_performance_stats()
    
    if stats is None:
        print("⚠️  No backtest data available yet")
        print("   Run the backtest first: python jobs/backtest.py")
        return
    
    # Display stats summary
    print(f"\n📊 Performance Summary:")
    print(f"   Total Signals (1m): {stats['total_signals_1m']}")
    if stats['total_signals_1m'] > 0:
        print(f"   Hit Rate: {stats['hit_rate_1m']}%")
        print(f"   Avg Alpha: {stats['avg_alpha_1m']}%")
    
    # Generate email
    print(f"\n📧 Generating weekly performance email...")
    html, text = render_weekly_performance_email(stats)
    
    # Send email
    subject = f"Weekly Performance Report — {datetime.now().strftime('%B %d, %Y')}"
    send_email(subject, html, text)
    
    print(f"\n{'='*60}")
    print("✅ Weekly performance summary sent successfully!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()