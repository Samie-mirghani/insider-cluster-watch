# process_signals.py
import pandas as pd
from datetime import timedelta
import yfinance as yf

ROLE_WEIGHT = {
    'CEO': 3.0,
    'CFO': 2.5,
    'PRES': 2.0,
    'DIRECTOR': 1.5,
    'VP': 1.2,
    'OFFICER': 1.2,
}

def normalize_title(title):
    if title is None: return ''
    t = title.upper()
    if 'CEO' in t: return 'CEO'
    if 'CFO' in t: return 'CFO'
    if 'PRES' in t or 'PRESIDENT' in t: return 'PRES'
    if 'DIRECT' in t: return 'DIRECTOR'
    if 'VP' in t and 'SVP' not in t: return 'VP'
    return 'OFFICER'

def compute_conviction_score(row):
    # Simple dollar-value normalized score (log scale) * role weight
    value = max(row.get('value', 0), row.get('qty',0)*row.get('price',0))
    import math
    sz_score = math.log1p(value)  # attenuate huge buys
    return sz_score * row.get('role_weight', 1.0)

def cluster_and_score(df, window_days=5, top_n=10):
    # Filter for buys only and open-market buys (OpenInsider 'Buy' label)
    buys = df[df['trade_type'].str.upper().str.contains('BUY', na=False)].copy()
    if buys.empty:
        return pd.DataFrame()
    buys['role'] = buys['title'].apply(normalize_title)
    buys['role_weight'] = buys['role'].map(ROLE_WEIGHT).fillna(1.0)
    # compute conviction score
    buys['conviction'] = buys.apply(compute_conviction_score, axis=1)
    # cluster: per ticker, count unique insiders within window
    buys = buys.sort_values('trade_date')
    clusters = []
    tickers = buys['ticker'].unique()
    for t in tickers:
        tdf = buys[buys['ticker']==t].copy()
        tdf = tdf.sort_values('trade_date')
        for idx, row in tdf.iterrows():
            start = row['trade_date'] - pd.Timedelta(days=window_days)
            end = row['trade_date'] + pd.Timedelta(days=window_days)
            window = tdf[(tdf['trade_date'] >= start) & (tdf['trade_date'] <= end)]
            cluster_count = window['insider'].nunique()
            total_value = window['value'].sum()
            clusters.append({
                'ticker': t,
                'last_trade_date': row['trade_date'],
                'cluster_count': cluster_count,
                'total_value': total_value,
                'avg_conviction': window['conviction'].mean(),
            })
    cluster_df = pd.DataFrame(clusters).drop_duplicates(subset=['ticker']).sort_values(['cluster_count','avg_conviction'], ascending=False)
    # enrich with price data to compute % from 52-week low etc
    tickers = cluster_df['ticker'].unique().tolist()
    info = {}
    for t in tickers:
        try:
            q = yf.Ticker(t).info
            info[t] = {
                'currentPrice': q.get('currentPrice'),
                'marketCap': q.get('marketCap'),
                'fiftyTwoWeekLow': q.get('fiftyTwoWeekLow'),
                'fiftyTwoWeekHigh': q.get('fiftyTwoWeekHigh'),
            }
        except Exception:
            info[t] = {}
    cluster_df['currentPrice'] = cluster_df['ticker'].map(lambda x: info.get(x, {}).get('currentPrice'))
    cluster_df['marketCap'] = cluster_df['ticker'].map(lambda x: info.get(x, {}).get('marketCap'))
    cluster_df['pct_from_52wk_low'] = (cluster_df['currentPrice'] - cluster_df['ticker'].map(lambda x: info.get(x, {}).get('fiftyTwoWeekLow', cluster_df['currentPrice']))) / cluster_df['ticker'].map(lambda x: info.get(x, {}).get('fiftyTwoWeekLow', cluster_df['currentPrice'])) * 100
    # ranking score (simple)
    cluster_df['rank_score'] = cluster_df['cluster_count']*2 + cluster_df['avg_conviction']
    return cluster_df.sort_values('rank_score', ascending=False).head(top_n)

if __name__ == "__main__":
    import fetch_openinsider as fio
    df = fio.fetch_openinsider_recent()
    out = cluster_and_score(df)
    print(out)
