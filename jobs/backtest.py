# jobs/backtest.py
"""
Backtest historical insider trading signals.
Calculates returns at 1-week and 1-month horizons and compares to SPY benchmark.
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
import warnings
import logging
import sys

# Suppress all warnings
warnings.filterwarnings('ignore')

# Suppress yfinance logging
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# Context manager to suppress stderr output
class SuppressStderr:
    """Suppress stderr output (used for yfinance error messages)"""
    def __enter__(self):
        self._original_stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr.close()
        sys.stderr = self._original_stderr

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
HISTORY_CSV = os.path.join(DATA_DIR, 'signals_history.csv')
OUT_CSV = os.path.join(DATA_DIR, 'backtest_results.csv')

def fetch_forward_returns(ticker, start_date, days_forward):
    """
    Fetch daily close prices from start_date to start_date + days_forward.
    
    Args:
        ticker: Stock ticker symbol
        start_date: Starting date for price fetch
        days_forward: Number of trading days forward
    
    Returns:
        Tuple of (start_price, horizon_price, return_fraction) or None if error
    """
    start = start_date
    end = start_date + timedelta(days=days_forward+5)  # Buffer for weekends/holidays
    
    try:
        # Download data with suppressed output
        with SuppressStderr():
            df = yf.download(
                ticker, 
                start=start.strftime('%Y-%m-%d'), 
                end=end.strftime('%Y-%m-%d'), 
                progress=False,
                auto_adjust=True
            )
        
        # Check if we got valid data
        if df.empty or 'Close' not in df.columns:
            return None
        
        # Reset index to access by position
        df = df.reset_index()
        
        # Ensure we have enough data
        if len(df) == 0:
            return None
        
        # Get start price (first available close)
        start_price = float(df['Close'].iloc[0])
        
        # Get horizon price (at days_forward or last available)
        idx_horizon = min(days_forward, len(df) - 1)
        horizon_price = float(df['Close'].iloc[idx_horizon])
        
        # Calculate return as scalar float
        ret = float((horizon_price - start_price) / start_price)
        
        return start_price, horizon_price, ret
        
    except Exception:
        # Silently skip errors (delisted stocks, etc.)
        return None

def run_backtest():
    """
    Main backtest function.
    Reads signals_history.csv and calculates forward returns for each signal.
    """
    print("=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    
    # Check if history file exists
    if not os.path.exists(HISTORY_CSV):
        print(f"❌ No history file at {HISTORY_CSV}")
        print("   Run main.py to generate signals history first.")
        return
    
    # Load signals history
    df = pd.read_csv(HISTORY_CSV, parse_dates=['date'])
    
    if df.empty:
        print("❌ Signals history file is empty")
        return
    
    print(f"📊 Analyzing {len(df)} historical signals...")
    
    # Prepare results storage
    results = []
    spy_ticker = 'SPY'
    failed_tickers = set()
    
    # Process each signal
    for idx, row in df.iterrows():
        ticker = row['ticker']
        
        # Parse signal date
        try:
            sig_date = pd.to_datetime(row['date']).to_pydatetime()
        except Exception:
            continue
        
        # Test both 1-week (~5 trading days) and 1-month (~21 trading days)
        for horizon_days, label in [(5, '1w'), (21, '1m')]:
            # Get ticker returns
            res_ticker = fetch_forward_returns(ticker, sig_date, horizon_days)
            
            # Get SPY returns for comparison
            res_spy = fetch_forward_returns(spy_ticker, sig_date, horizon_days)
            
            # Skip if either failed
            if not res_ticker or not res_spy:
                failed_tickers.add(ticker)
                continue
            
            # Extract returns
            _, _, ret_ticker = res_ticker
            _, _, ret_spy = res_spy
            
            # Calculate alpha (excess return vs SPY)
            alpha = ret_ticker - ret_spy
            
            # Store result
            results.append({
                'ticker': ticker,
                'signal_date': sig_date,
                'horizon': label,
                'ticker_return': float(ret_ticker),
                'spy_return': float(ret_spy),
                'alpha': float(alpha),
                'signal_score': float(row.get('signal_score', 0)) if pd.notna(row.get('signal_score')) else 0.0,
                'action': str(row.get('action', ''))
            })
    
    # Show summary of failed tickers
    if failed_tickers:
        print(f"   ⚠️  Skipped {len(failed_tickers)} ticker(s) (delisted/invalid): {', '.join(sorted(failed_tickers))}")
    
    # Convert to DataFrame
    results_df = pd.DataFrame(results)
    
    if results_df.empty:
        print("\n⚠️  No backtest results generated")
        print("   Possible reasons:")
        print("   - All tickers are delisted or invalid")
        print("   - Signals are too recent (not enough price history)")
        print("   - Yahoo Finance data unavailable")
        return results_df
    
    # Ensure all numeric columns are proper floats
    for col in ['ticker_return', 'spy_return', 'alpha', 'signal_score']:
        results_df[col] = pd.to_numeric(results_df[col], errors='coerce')
    
    # Drop any rows with NaN values
    results_df = results_df.dropna(subset=['ticker_return', 'spy_return', 'alpha'])
    
    if results_df.empty:
        print("\n⚠️  No valid backtest results after cleaning")
        return results_df
    
    # Print summary statistics
    print("\n" + "=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)
    
    for label in ['1w', '1m']:
        subset = results_df[results_df['horizon'] == label].copy()
        
        if subset.empty:
            continue
        
        # Calculate metrics
        total_signals = len(subset)
        hit_rate = (subset['ticker_return'] > 0).mean()
        avg_return = subset['ticker_return'].mean()
        avg_alpha = subset['alpha'].mean()
        median_return = subset['ticker_return'].median()
        best_return = subset['ticker_return'].max()
        worst_return = subset['ticker_return'].min()
        
        print(f"\n📊 {label.upper()} HORIZON:")
        print(f"   Signals Tested: {total_signals}")
        print(f"   Hit Rate: {hit_rate*100:.1f}% ({int(hit_rate*total_signals)} profitable)")
        print(f"   Avg Return: {avg_return*100:+.2f}%")
        print(f"   Median Return: {median_return*100:+.2f}%")
        print(f"   Avg Alpha vs SPY: {avg_alpha*100:+.2f}%")
        print(f"   Best Trade: {best_return*100:+.2f}%")
        print(f"   Worst Trade: {worst_return*100:+.2f}%")
    
    # Save results to CSV
    results_df.to_csv(OUT_CSV, index=False)
    print(f"\n💾 Backtest results saved to: {OUT_CSV}")
    
    print("\n" + "=" * 60)
    print("BACKTEST COMPLETE")
    print("=" * 60)
    
    return results_df

if __name__ == "__main__":
    run_backtest()