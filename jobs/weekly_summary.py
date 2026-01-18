# jobs/weekly_summary.py
"""
Generate and send weekly performance summary email.
Analyzes backtest results with enhanced metrics and paper trading performance.
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from send_email import send_email
from paper_trade import PaperTradingPortfolio
from dotenv import load_dotenv
from generate_report import (
    sanitize_dict_for_template,
    is_valid_value,
    GITHUB_ICON_BASE_URL,
    _get_hosted_icon,
    _get_hosted_logo
)

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
BACKTEST_CSV = os.path.join(DATA_DIR, 'backtest_results.csv')
HISTORY_CSV = os.path.join(DATA_DIR, 'signals_history.csv')
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'templates')

def calculate_sharpe_ratio(returns, risk_free_rate=0.0):
    """
    Calculate annualized Sharpe ratio.
    
    Args:
        returns: Series of returns (fractional, not percentage)
        risk_free_rate: Annual risk-free rate (default 0%)
    
    Returns:
        Sharpe ratio (annualized)
    """
    if len(returns) == 0 or returns.std() == 0:
        return 0.0
    
    # Annualize assuming ~252 trading days
    excess_returns = returns - (risk_free_rate / 252)
    sharpe = np.sqrt(252) * (excess_returns.mean() / returns.std())
    return sharpe

def calculate_max_drawdown(returns):
    """
    Calculate maximum drawdown from a series of returns.
    
    Args:
        returns: Series of returns (fractional)
    
    Returns:
        Maximum drawdown as negative percentage
    """
    if len(returns) == 0:
        return 0.0
    
    # Calculate cumulative returns
    cum_returns = (1 + returns).cumprod()
    
    # Calculate running maximum
    running_max = cum_returns.expanding().max()
    
    # Calculate drawdown
    drawdown = (cum_returns - running_max) / running_max
    
    # Return maximum drawdown (most negative value)
    max_dd = drawdown.min()
    return max_dd * 100  # Convert to percentage

def calculate_win_loss_ratio(returns):
    """
    Calculate average win / average loss ratio.
    
    Args:
        returns: Series of returns (fractional)
    
    Returns:
        Win/loss ratio
    """
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    
    if len(wins) == 0 or len(losses) == 0:
        return 0.0
    
    avg_win = wins.mean()
    avg_loss = abs(losses.mean())
    
    return avg_win / avg_loss if avg_loss != 0 else 0.0

def analyze_by_sector(history_df, backtest_df):
    """
    Analyze performance breakdown by sector.
    
    Returns:
        List of dicts with sector performance
    """
    if 'sector' not in history_df.columns or backtest_df.empty:
        return []
    
    # Merge history with backtest results
    merged = backtest_df.merge(
        history_df[['ticker', 'date', 'sector']], 
        left_on=['ticker', 'signal_date'],
        right_on=['ticker', 'date'],
        how='left'
    )
    
    # Filter for 1-month horizon
    merged_1m = merged[merged['horizon'] == '1m'].copy()
    
    if merged_1m.empty:
        return []
    
    # Group by sector
    sector_stats = []
    for sector in merged_1m['sector'].dropna().unique():
        sector_data = merged_1m[merged_1m['sector'] == sector]
        
        if len(sector_data) >= 3:  # Only include sectors with 3+ signals
            hit_rate = (sector_data['ticker_return'] > 0).mean() * 100
            avg_return = sector_data['ticker_return'].mean() * 100
            count = len(sector_data)
            
            sector_stats.append({
                'sector': sector,
                'count': count,
                'hit_rate': round(hit_rate, 1),
                'avg_return': round(avg_return, 2)
            })
    
    # Sort by hit rate descending
    sector_stats.sort(key=lambda x: x['hit_rate'], reverse=True)
    
    return sector_stats

def analyze_by_pattern(history_df, backtest_df):
    """
    Analyze performance breakdown by detected pattern.
    
    Returns:
        List of dicts with pattern performance
    """
    if 'pattern_detected' not in history_df.columns or backtest_df.empty:
        return []
    
    # Merge history with backtest results
    merged = backtest_df.merge(
        history_df[['ticker', 'date', 'pattern_detected']], 
        left_on=['ticker', 'signal_date'],
        right_on=['ticker', 'date'],
        how='left'
    )
    
    # Filter for 1-month horizon
    merged_1m = merged[merged['horizon'] == '1m'].copy()
    
    if merged_1m.empty:
        return []
    
    # Group by pattern
    pattern_stats = []
    for pattern in merged_1m['pattern_detected'].dropna().unique():
        if pattern == 'None':
            continue
            
        pattern_data = merged_1m[merged_1m['pattern_detected'] == pattern]
        
        if len(pattern_data) >= 2:  # Only include patterns with 2+ occurrences
            hit_rate = (pattern_data['ticker_return'] > 0).mean() * 100
            avg_return = pattern_data['ticker_return'].mean() * 100
            count = len(pattern_data)
            
            pattern_stats.append({
                'pattern': pattern,
                'count': count,
                'hit_rate': round(hit_rate, 1),
                'avg_return': round(avg_return, 2)
            })
    
    # Sort by hit rate descending
    pattern_stats.sort(key=lambda x: x['hit_rate'], reverse=True)
    
    return pattern_stats

def calculate_performance_stats():
    """
    Calculate comprehensive performance statistics from backtest results.
    Returns dict with all necessary stats for the email template.
    """
    if not os.path.exists(BACKTEST_CSV):
        print("No backtest results found yet.")
        return None
    
    df = pd.read_csv(BACKTEST_CSV, parse_dates=['signal_date'])
    
    if df.empty:
        print("Backtest results file is empty.")
        return None
    
    # Load history for sector/pattern analysis
    history_df = None
    if os.path.exists(HISTORY_CSV):
        history_df = pd.read_csv(HISTORY_CSV, parse_dates=['date'])
    
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
        
        # Enhanced metrics
        stats['sharpe_ratio_1m'] = round(calculate_sharpe_ratio(df_1m['ticker_return']), 2)
        stats['max_drawdown_1m'] = round(calculate_max_drawdown(df_1m['ticker_return']), 2)
        stats['win_loss_ratio_1m'] = round(calculate_win_loss_ratio(df_1m['ticker_return']), 2)
        stats['median_return_1m'] = round(df_1m['ticker_return'].median() * 100, 2)
        stats['best_return_1m'] = round(df_1m['ticker_return'].max() * 100, 2)
        stats['worst_return_1m'] = round(df_1m['ticker_return'].min() * 100, 2)
        
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
        
        # Worst 3 performers (for learning)
        bottom = df_1m.nsmallest(3, 'ticker_return')[['ticker', 'signal_date', 'ticker_return', 'alpha']].copy()
        stats['worst_performers'] = [
            {
                'ticker': row['ticker'],
                'signal_date': row['signal_date'].strftime('%b %d'),
                'return_pct': f"{round(row['ticker_return'] * 100, 1)}",
                'alpha_pct': f"{round(row['alpha'] * 100, 1)}"
            }
            for _, row in bottom.iterrows()
        ]
    else:
        stats['total_signals_1m'] = 0
        stats['winners_1m'] = 0
        stats['hit_rate_1m'] = 0
        stats['avg_return_1m'] = 0
        stats['avg_alpha_1m'] = 0
        stats['sharpe_ratio_1m'] = 0
        stats['max_drawdown_1m'] = 0
        stats['win_loss_ratio_1m'] = 0
        stats['median_return_1m'] = 0
        stats['best_return_1m'] = 0
        stats['worst_return_1m'] = 0
        stats['top_performers'] = []
        stats['worst_performers'] = []
    
    # 1-Week Statistics (supplementary)
    if not df_1w.empty:
        stats['total_signals_1w'] = len(df_1w)
        stats['winners_1w'] = len(df_1w[df_1w['ticker_return'] > 0])
        stats['hit_rate_1w'] = round((stats['winners_1w'] / stats['total_signals_1w']) * 100, 1)
        stats['avg_return_1w'] = round(df_1w['ticker_return'].mean() * 100, 2)
        stats['avg_alpha_1w'] = round(df_1w['alpha'].mean() * 100, 2)
        stats['sharpe_ratio_1w'] = round(calculate_sharpe_ratio(df_1w['ticker_return']), 2)
    else:
        stats['total_signals_1w'] = 0
        stats['winners_1w'] = 0
        stats['hit_rate_1w'] = 0
        stats['avg_return_1w'] = 0
        stats['avg_alpha_1w'] = 0
        stats['sharpe_ratio_1w'] = 0
    
    # Sector analysis
    if history_df is not None:
        stats['sector_analysis'] = analyze_by_sector(history_df, df)
        stats['pattern_analysis'] = analyze_by_pattern(history_df, df)
    else:
        stats['sector_analysis'] = []
        stats['pattern_analysis'] = []
    
    # Paper trading stats
    try:
        paper_trader = PaperTradingPortfolio.load()
        if paper_trader:
            paper_stats = paper_trader.get_performance_summary()
            
            stats['paper_trading'] = {
                'enabled': True,
                'portfolio_value': paper_stats['current_value'],
                'total_return': paper_stats['total_return_pct'],
                'total_trades': paper_stats['total_trades'],
                'winning_trades': paper_stats['winning_trades'],
                'losing_trades': paper_stats['losing_trades'],
                'hit_rate': paper_stats['win_rate'],
                'open_positions': paper_stats['open_positions'],
                'pending_entries': paper_stats['pending_entries'],
                'realized_pnl': paper_stats['realized_pnl'],
                'avg_win': paper_stats['avg_win'],
                'avg_loss': paper_stats['avg_loss'],
                'avg_win_pct': paper_stats['avg_win_pct'],
                'avg_loss_pct': paper_stats['avg_loss_pct'],
                'avg_hold_days': paper_stats['avg_hold_days'],
                'max_drawdown': paper_stats['max_drawdown'],
                'exposure_pct': paper_stats['exposure_pct'],
                'cash': paper_stats['cash']
            }
            
            # Add health check
            from paper_trade_monitor import PaperTradingMonitor
            monitor = PaperTradingMonitor()
            health_status, health_alerts = monitor.check_portfolio_health(paper_trader)
            
            stats['paper_trading']['health_status'] = health_status
            stats['paper_trading']['health_alerts'] = len(health_alerts)
            
        else:
            stats['paper_trading'] = {'enabled': False}
    except (FileNotFoundError, Exception) as e:
        logger.warning(f"Could not load paper trading stats: {e}")
        stats['paper_trading'] = {'enabled': False}
        
    return stats

def render_weekly_performance_email(stats):
    """
    Render the weekly performance email template with enhanced metrics.
    """
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    # Add custom filter for checking valid values
    env.filters['is_valid'] = is_valid_value
    template = env.get_template('weekly_performance.html')

    # CRITICAL: Sanitize all dict values to prevent "nan" from appearing in emails
    stats = sanitize_dict_for_template(stats)

    # Pass GitHub-hosted icons to template
    icons = {
        'logo': _get_hosted_logo(24, 24),
        'trending': _get_hosted_icon('trending_up', 16, 16),
        'chart': _get_hosted_icon('trending_up', 16, 16),
        'dollar': _get_hosted_icon('dollar', 16, 16),
        'trophy': _get_hosted_icon('star', 16, 16),
        'down': _get_hosted_icon('trending_up', 16, 16),  # Will be styled to point down
        'check': _get_hosted_icon('check', 16, 16),
        'warning': _get_hosted_icon('warning', 16, 16),
        'critical': _get_hosted_icon('warning', 16, 16),
        'search': _get_hosted_icon('search', 16, 16),
        'building': _get_hosted_icon('building', 16, 16),
        'inbox': _get_hosted_icon('inbox', 16, 16),
        'target': _get_hosted_icon('target', 16, 16),
        'zap': _get_hosted_icon('zap', 16, 16),
    }

    html = template.render(
        date=datetime.now().strftime("%B %d, %Y"),
        icons=icons,
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
            "PERFORMANCE SUMMARY (1-Month Horizon)",
            "=" * 60,
            f"Total Signals: {stats['total_signals_1m']}",
            f"Hit Rate: {stats['hit_rate_1m']}% ({stats['winners_1m']} winners)",
            f"Avg Return: {stats['avg_return_1m']}%",
            f"Avg Alpha: {stats['avg_alpha_1m']}%",
            "",
            "ENHANCED METRICS",
            "=" * 60,
            f"Sharpe Ratio: {stats['sharpe_ratio_1m']}",
            f"Max Drawdown: {stats['max_drawdown_1m']}%",
            f"Win/Loss Ratio: {stats['win_loss_ratio_1m']}",
            f"Median Return: {stats['median_return_1m']}%",
            f"Best Trade: +{stats['best_return_1m']}%",
            f"Worst Trade: {stats['worst_return_1m']}%",
            ""
        ])
        
        # Paper trading stats
        if stats['paper_trading']['enabled']:
            pt = stats['paper_trading']
            text_lines.extend([
                "PAPER TRADING PERFORMANCE",
                "=" * 60,
                f"Portfolio Value: ${pt['portfolio_value']:,.2f}",
                f"Total Return: {pt['total_return']:+.2f}%",
                f"Total Trades: {pt['total_trades']}",
                f"Win Rate: {pt['hit_rate']:.1f}%",
                f"Open Positions: {pt['open_positions']}",
                f"Realized P&L: ${pt['realized_pnl']:,.2f}",
                ""
            ])
        
        # Sector analysis
        if stats['sector_analysis']:
            text_lines.extend([
                "SECTOR PERFORMANCE",
                "=" * 60
            ])
            for sector in stats['sector_analysis'][:5]:
                text_lines.append(
                    f"  {sector['sector']}: {sector['hit_rate']}% hit rate, "
                    f"{sector['avg_return']:+.2f}% avg return ({sector['count']} signals)"
                )
            text_lines.append("")
        
        # Pattern analysis
        if stats['pattern_analysis']:
            text_lines.extend([
                "PATTERN PERFORMANCE",
                "=" * 60
            ])
            for pattern in stats['pattern_analysis']:
                text_lines.append(
                    f"  {pattern['pattern']}: {pattern['hit_rate']}% hit rate, "
                    f"{pattern['avg_return']:+.2f}% avg return ({pattern['count']} occurrences)"
                )
            text_lines.append("")
        
        # Top performers
        if stats['top_performers']:
            text_lines.extend([
                "TOP PERFORMERS",
                "=" * 60
            ])
            for p in stats['top_performers']:
                text_lines.append(f"  {p['ticker']}: {p['return_pct']}% (Alpha: {p['alpha_pct']}%)")
            text_lines.append("")
        
        # Performance assessment
        sharpe = float(stats['sharpe_ratio_1m'])
        hit_rate = float(stats['hit_rate_1m'])
        alpha = float(stats['avg_alpha_1m'])
        
        text_lines.extend([
            "ASSESSMENT",
            "=" * 60
        ])

        if sharpe >= 1.0 and alpha > 0 and hit_rate >= 55:
            text_lines.append("[+] EXCELLENT: Strong Sharpe ratio, positive alpha, good hit rate")
        elif sharpe >= 0.5 and alpha > 0:
            text_lines.append("[+] GOOD: Positive alpha with acceptable risk-adjusted returns")
        elif alpha > 0 and hit_rate >= 50:
            text_lines.append("[!] MODERATE: Positive alpha but needs improvement")
        else:
            text_lines.append("[!] UNDERPERFORMING: Strategy needs review")
        
    else:
        text_lines.extend([
            "BUILDING TRACK RECORD",
            "=" * 60,
            "Not enough historical data yet. Keep monitoring!",
            ""
        ])
    
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
    print(f"Weekly Performance Summary - {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    # Calculate performance stats
    print("Calculating enhanced performance statistics...")
    stats = calculate_performance_stats()

    if stats is None:
        print("No backtest data available yet")
        print("   Run the backtest first: python jobs/backtest.py")
        return

    # Display stats summary
    print(f"\nPerformance Summary:")
    print(f"   Total Signals (1m): {stats['total_signals_1m']}")
    if stats['total_signals_1m'] > 0:
        print(f"   Hit Rate: {stats['hit_rate_1m']}%")
        print(f"   Avg Alpha: {stats['avg_alpha_1m']}%")
        print(f"   Sharpe Ratio: {stats['sharpe_ratio_1m']}")
        print(f"   Max Drawdown: {stats['max_drawdown_1m']}%")
        print(f"   Win/Loss Ratio: {stats['win_loss_ratio_1m']}")
    
    if stats['paper_trading']['enabled']:
        pt = stats['paper_trading']
        print(f"\nPaper Trading:")
        print(f"   Portfolio: ${pt['portfolio_value']:,.2f} ({pt['total_return']:+.2f}%)")
        print(f"   Win Rate: {pt['hit_rate']:.1f}%")

    if stats['sector_analysis']:
        print(f"\nBest Performing Sectors:")
        for sector in stats['sector_analysis'][:3]:
            print(f"   {sector['sector']}: {sector['hit_rate']}% hit rate")

    if stats['pattern_analysis']:
        print(f"\nBest Performing Patterns:")
        for pattern in stats['pattern_analysis'][:3]:
            print(f"   {pattern['pattern']}: {pattern['hit_rate']}% hit rate")

    # Generate email
    print(f"\nGenerating weekly performance email...")
    html, text = render_weekly_performance_email(stats)

    # Send email
    subject = f"Weekly Performance Report — {datetime.now().strftime('%B %d, %Y')}"
    send_email(subject, html, text)

    print(f"\n{'='*60}")
    print("Weekly performance summary sent successfully!")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()