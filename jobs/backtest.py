# jobs/backtest.py
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os

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
                'action': row.get('action')
            })

    results_df = pd.DataFrame(results)
    if results_df.empty:
        print("No backtest results (no valid price series).")
        return results_df

    # summary metrics
    for label in ['1w','1m']:
        subset = results_df[results_df['horizon']==label]
        if subset.empty:
            continue
        hit_rate = (subset['ticker_return'] > 0).mean()
        avg_alpha = subset['alpha'].mean()
        avg_return = subset['ticker_return'].mean()
        print(f"=== Horizon: {label} ===")
        print(f"Signals tested: {len(subset)}  Hit rate (pos return): {hit_rate*100:.2f}%")
        print(f"Avg return: {avg_return*100:.2f}%   Avg alpha vs SPY: {avg_alpha*100:.2f}%")

    results_df.to_csv(OUT_CSV, index=False)
    print(f"Wrote backtest results to {OUT_CSV}")
    return results_df

if __name__ == "__main__":
    run_backtest()
