# jobs/backtest.py
"""
Enhanced backtesting with professional trading metrics

NEW FEATURES:
- Sharpe ratio (risk-adjusted returns)
- Maximum drawdown
- Win/loss ratio
- Consecutive losses tracking
- Profit factor
- Sector performance analysis
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
HISTORY_CSV = os.path.join(DATA_DIR, 'signals_history.csv')
OUT_CSV = os.path.join(DATA_DIR, 'backtest_results.csv')

def fetch_forward_returns(ticker, start_date, days_forward):
    """
    Fetch daily close prices from start_date (inclusive) to start_date + days_forward (inclusive).
    Returns (start_price, price_at_horizon, return_fraction)
    """
    start = start_date
    end = start_date + timedelta(days=days_forward+3)  # buffer for weekends/holidays
    try:
        df = yf.download(ticker, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'), progress=False)
        if df.empty:
            return None
        # normalize indices, pick first usable close as start, and close at ~days_forward (approx)
        df = df.reset_index()
        start_price = df['Close'].iloc[0]
        idx_horizon = min(days_forward, len(df)-1)
        horizon_price = df['Close'].iloc[idx_horizon]
        ret = (horizon_price - start_price) / start_price
        return start_price, horizon_price, ret
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

def calculate_advanced_metrics(results_df, horizon_label):
    """
    NEW: Calculate professional trading metrics
    
    Returns dict with:
    - Sharpe ratio
    - Max drawdown
    - Win/loss ratio
    - Consecutive losses
    - Profit factor
    """
    if results_df.empty:
        return {}
    
    returns = results_df['ticker_return']
    
    metrics = {}
    
    # Sharpe Ratio (annualized, assuming risk-free rate = 0)
    if returns.std() > 0:
        if horizon_label == '1w':
            # Annualize: sqrt(52) for weekly
            metrics['sharpe_ratio'] = (returns.mean() / returns.std()) * np.sqrt(52)
        else:  # 1m
            # Annualize: sqrt(12) for monthly
            metrics['sharpe_ratio'] = (returns.mean() / returns.std()) * np.sqrt(12)
    else:
        metrics['sharpe_ratio'] = 0.0
    
    # Maximum Drawdown
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    metrics['max_drawdown'] = drawdown.min()
    
    # Win/Loss Ratio
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    
    if len(losses) > 0 and losses.mean() != 0:
        metrics['win_loss_ratio'] = abs(wins.mean() / losses.mean())
    else:
        metrics['win_loss_ratio'] = 0.0
    
    # Max Consecutive Losses
    metrics['max_consecutive_losses'] = max_consecutive_losses(returns)
    
    # Profit Factor (total wins / total losses)
    total_wins = wins.sum()
    total_losses = abs(losses.sum())
    
    if total_losses > 0:
        metrics['profit_factor'] = total_wins / total_losses
    else:
        metrics['profit_factor'] = 0.0
    
    # Expectancy (avg $ per trade if you risked $100)
    metrics['expectancy_pct'] = returns.mean() * 100
    
    return metrics

def max_consecutive_losses(returns):
    """Calculate maximum consecutive losing trades"""
    consecutive = 0
    max_consecutive = 0
    
    for ret in returns:
        if ret < 0:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0
    
    return max_consecutive

def calculate_sector_performance(results_df, history_df):
    """
    NEW: Analyze performance by sector
    
    Returns DataFrame with sector-level statistics
    """
    if results_df.empty or history_df.empty:
        return pd.DataFrame()
    
    # Merge to get sector info
    merged = results_df.merge(
        history_df[['ticker', 'date', 'sector']],
        left_on=['ticker', 'signal_date'],
        right_on=['ticker', 'date'],
        how='left'
    )
    
    if 'sector' not in merged.columns or merged['sector'].isna().all():
        return pd.DataFrame()
    
    # Group by sector
    sector_stats = merged.groupby('sector').agg({
        'ticker_return': ['count', 'mean', lambda x: (x > 0).mean()],
        'alpha': 'mean'
    }).round(4)
    
    sector_stats.columns = ['count', 'avg_return', 'hit_rate', 'avg_alpha']
    sector_stats = sector_stats[sector_stats['count'] >= 3]  # Min 3 signals
    sector_stats = sector_stats.sort_values('avg_return', ascending=False)
    
    return sector_stats

def run_backtest():
    if not os.path.exists(HISTORY_CSV):
        print(f"No history file at {HISTORY_CSV}. Run main to generate signals history first.")
        return
    
    df = pd.read_csv(HISTORY_CSV, parse_dates=['date'])
    results = []
    spy_ticker = 'SPY'
    
    for _, row in df.iterrows():
        ticker = row['ticker']
        sig_date = row['date'].to_pydatetime() if hasattr(row['date'],'to_pydatetime') else row['date']
        try:
            sig_date = pd.to_datetime(row['date']).to_pydatetime()
        except Exception:
            continue
        
        # 1-week (~5 trading days) and 1-month (~21 trading days)
        for horizon_days, label in [(5, '1w'), (21, '1m')]:
            res_t = fetch_forward_returns(ticker, sig_date, horizon_days)
            res_spy = fetch_forward_returns(spy_ticker, sig_date, horizon_days)
            if not res_t or not res_spy:
                continue
            _, _, ret_t = res_t
            _, _, ret_spy = res_spy
            alpha = ret_t - ret_spy
            results.append({
                'ticker': ticker,
                'signal_date': sig_date,
                'horizon': label,
                'ticker_return': ret_t,
                'spy_return': ret_spy,
                'alpha': alpha,
                'signal_score': row.get('signal_score'),
                'action': row.get('action'),
                'sector': row.get('sector', 'Unknown')  # NEW
            })

    results_df = pd.DataFrame(results)
    if results_df.empty:
        print("No backtest results (no valid price series).")
        return results_df

    # Summary metrics for each horizon
    print("\n" + "="*60)
    print("BACKTEST RESULTS")
    print("="*60)
    
    for label in ['1w','1m']:
        subset = results_df[results_df['horizon']==label]
        if subset.empty:
            continue
        
        hit_rate = (subset['ticker_return'] > 0).mean()
        avg_alpha = subset['alpha'].mean()
        avg_return = subset['ticker_return'].mean()
        
        print(f"\n=== Horizon: {label} ===")
        print(f"Signals tested: {len(subset)}  Hit rate (pos return): {hit_rate*100:.2f}%")
        print(f"Avg return: {avg_return*100:.2f}%   Avg alpha vs SPY: {avg_alpha*100:.2f}%")
        
        # NEW: Advanced metrics
        adv_metrics = calculate_advanced_metrics(subset, label)
        if adv_metrics:
            print(f"\n📊 Advanced Metrics ({label}):")
            print(f"   Sharpe Ratio: {adv_metrics['sharpe_ratio']:.2f}")
            print(f"   Max Drawdown: {adv_metrics['max_drawdown']*100:.2f}%")
            print(f"   Win/Loss Ratio: {adv_metrics['win_loss_ratio']:.2f}")
            print(f"   Max Consecutive Losses: {int(adv_metrics['max_consecutive_losses'])}")
            print(f"   Profit Factor: {adv_metrics['profit_factor']:.2f}")
            print(f"   Expectancy: {adv_metrics['expectancy_pct']:.2f}%")
    
    # NEW: Sector performance analysis
    print("\n" + "="*60)
    print("SECTOR PERFORMANCE ANALYSIS (1-month)")
    print("="*60)
    
    sector_perf = calculate_sector_performance(
        results_df[results_df['horizon'] == '1m'], 
        df
    )
    
    if not sector_perf.empty:
        print("\nSector Stats:")
        for sector, row in sector_perf.iterrows():
            print(f"\n{sector}:")
            print(f"  Signals: {int(row['count'])}")
            print(f"  Hit Rate: {row['hit_rate']*100:.1f}%")
            print(f"  Avg Return: {row['avg_return']*100:.2f}%")
            print(f"  Avg Alpha: {row['avg_alpha']*100:.2f}%")
    else:
        print("\n⚠️  Not enough sector data yet for analysis")

    results_df.to_csv(OUT_CSV, index=False)
    print(f"\n✅ Wrote backtest results to {OUT_CSV}")
    print("="*60 + "\n")
    
    return results_df

if __name__ == "__main__":
    run_backtest()