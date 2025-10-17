# jobs/process_signals.py
"""
Filter buys, compute cluster and conviction scores, determine suggested action and rationale,
and flag urgent signals according to thresholds.

NEW FEATURES:
- Sector analysis and tracking
- Enhanced quality filters
- Pattern detection (accelerating buys, CEO+CFO patterns, etc.)
"""

import pandas as pd
import math
import time
from datetime import timedelta, datetime
import yfinance as yf

ROLE_WEIGHT = {
    'CEO': 3.0,
    'CFO': 2.5,
    'PRES': 2.0,
    'DIRECTOR': 1.5,
    'VP': 1.2,
    'OFFICER': 1.0,
}

def normalize_title(title):
    if not title or not isinstance(title, str):
        return 'OFFICER'
    t = title.upper()
    if 'CEO' in t: return 'CEO'
    if 'CFO' in t: return 'CFO'
    if 'PRES' in t or 'PRESIDENT' in t: return 'PRES'
    if 'DIRECT' in t: return 'DIRECTOR'
    if 'VP' in t and 'SVP' not in t: return 'VP'
    return 'OFFICER'

def compute_conviction_score(value, role_weight):
    # log-scale dollar weight times role weight
    return math.log1p(max(value, 0)) * role_weight

def enrich_with_market_data(cluster_df):
    """
    Uses yfinance (free) to add currentPrice, marketCap, fiftyTwoWeekLow to cluster_df.
    
    NEW: Also adds sector, industry, and volume data for quality filtering
    """
    import warnings
    import logging
    
    # Suppress yfinance warnings and errors
    warnings.filterwarnings('ignore')
    logging.getLogger('yfinance').setLevel(logging.CRITICAL)
    
    tickers = cluster_df['ticker'].unique().tolist()
    info = {}
    
    print(f"   Fetching market data for {len(tickers)} tickers...")
    successful = 0
    failed = 0
    
    for t in tickers:
        try:
            ticker_obj = yf.Ticker(t)
            q = ticker_obj.info
            
            if q and 'currentPrice' in q:
                info[t] = {
                    'currentPrice': q.get('currentPrice'),
                    'marketCap': q.get('marketCap'),
                    'fiftyTwoWeekLow': q.get('fiftyTwoWeekLow'),
                    'fiftyTwoWeekHigh': q.get('fiftyTwoWeekHigh'),
                    # NEW: Sector and industry info
                    'sector': q.get('sector', 'Unknown'),
                    'industry': q.get('industry', 'Unknown'),
                    # NEW: Liquidity data
                    'averageVolume': q.get('averageVolume', 0),
                    'averageVolume10days': q.get('averageVolume10days', 0),
                }
                successful += 1
            else:
                # No data available, use empty dict
                info[t] = {'sector': 'Unknown', 'industry': 'Unknown'}
                failed += 1
            time.sleep(0.5)
        except Exception as e:
            # Silently skip tickers that fail (404, invalid, etc)
            info[t] = {'sector': 'Unknown', 'industry': 'Unknown'}
            failed += 1
    
    print(f"   Market data: {successful} successful, {failed} failed/unavailable")
    
    cluster_df['currentPrice'] = cluster_df['ticker'].map(lambda x: info.get(x, {}).get('currentPrice'))
    cluster_df['marketCap'] = cluster_df['ticker'].map(lambda x: info.get(x, {}).get('marketCap'))
    cluster_df['fiftyTwoWeekLow'] = cluster_df['ticker'].map(lambda x: info.get(x, {}).get('fiftyTwoWeekLow'))
    cluster_df['fiftyTwoWeekHigh'] = cluster_df['ticker'].map(lambda x: info.get(x, {}).get('fiftyTwoWeekHigh'))
    
    # NEW: Add sector and industry
    cluster_df['sector'] = cluster_df['ticker'].map(lambda x: info.get(x, {}).get('sector', 'Unknown'))
    cluster_df['industry'] = cluster_df['ticker'].map(lambda x: info.get(x, {}).get('industry', 'Unknown'))
    
    # NEW: Add volume data
    cluster_df['averageVolume'] = cluster_df['ticker'].map(lambda x: info.get(x, {}).get('averageVolume', 0))
    
    cluster_df['pct_from_52wk_low'] = None
    
    def pct_from_low(row):
        low = row.get('fiftyTwoWeekLow')
        cur = row.get('currentPrice')
        if low and cur:
            try:
                return (cur - low) / low * 100.0
            except Exception:
                return None
        return None
    
    cluster_df['pct_from_52wk_low'] = cluster_df.apply(pct_from_low, axis=1)
    
    # Re-enable warnings
    warnings.filterwarnings('default')
    
    return cluster_df

def apply_quality_filters(cluster_df):
    """
    NEW FEATURE: Enhanced quality filters to remove low-quality signals
    
    Filters applied:
    1. Minimum price ($2.00) - no penny stocks
    2. Minimum purchase per insider ($50k)
    3. Liquidity requirement (100k+ avg volume)
    4. Maximum recent drawdown (<40% drop in 30 days)
    """
    if cluster_df.empty:
        return cluster_df
    
    original_count = len(cluster_df)
    filtered = cluster_df.copy()
    
    print(f"\n🔍 Applying quality filters to {original_count} signals...")
    
    # Filter 1: No penny stocks (price > $2.00)
    before = len(filtered)
    filtered = filtered[
        (filtered['currentPrice'].isna()) | 
        (filtered['currentPrice'] > 2.0)
    ]
    removed = before - len(filtered)
    if removed > 0:
        print(f"   ❌ Removed {removed} penny stocks (price < $2.00)")
    
    # Filter 2: Minimum purchase per insider ($50k)
    before = len(filtered)
    filtered['avg_purchase_per_insider'] = (
        filtered['total_value'] / filtered['cluster_count']
    )
    filtered = filtered[filtered['avg_purchase_per_insider'] >= 50000]
    removed = before - len(filtered)
    if removed > 0:
        print(f"   ❌ Removed {removed} signals (avg purchase < $50k per insider)")
    
    # Filter 3: Liquidity check (avg volume > 100k shares/day)
    before = len(filtered)
    filtered = filtered[
        (filtered['averageVolume'].isna()) | 
        (filtered['averageVolume'] > 100000)
    ]
    removed = before - len(filtered)
    if removed > 0:
        print(f"   ❌ Removed {removed} illiquid stocks (volume < 100k)")
    
    # Filter 4: Not down >40% in last 30 days (avoid falling knives)
    before = len(filtered)
    
    def check_recent_drawdown(row):
        """Check if stock is down >40% in last 30 days"""
        ticker = row['ticker']
        try:
            # Get 30 days of data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=35)
            hist = yf.download(ticker, start=start_date, end=end_date, progress=False)
            
            if hist.empty or len(hist) < 5:
                return True  # No data, don't filter
            
            high_30d = hist['High'].max()
            current = row.get('currentPrice')
            
            if not current or not high_30d:
                return True
            
            drawdown = (current - high_30d) / high_30d
            
            # Filter out if down more than 40%
            return drawdown > -0.40
            
        except Exception:
            return True  # Error, don't filter
    
    # Apply drawdown filter (this takes time, so we do it last after other filters)
    if len(filtered) <= 20:  # Only check if we have reasonable number of signals
        filtered = filtered[filtered.apply(check_recent_drawdown, axis=1)]
        removed = before - len(filtered)
        if removed > 0:
            print(f"   ❌ Removed {removed} stocks down >40% in 30 days")
    
    total_removed = original_count - len(filtered)
    print(f"   ✅ Quality filters: {len(filtered)} signals remaining ({total_removed} removed)")
    
    return filtered

def detect_patterns(buys_df, cluster_df):
    """
    NEW FEATURE: Detect meaningful insider buying patterns
    
    Patterns detected:
    1. Accelerating Buys - More buys recently than before
    2. CEO + CFO Together - Both top executives buying
    3. Breaking Silence - First buys after long quiet period
    4. Increasing Size - Each buy larger than previous
    """
    if buys_df.empty or cluster_df.empty:
        return cluster_df
    
    print(f"\n🔍 Detecting insider patterns...")
    
    # Add pattern columns
    cluster_df['patterns'] = ''
    cluster_df['pattern_score'] = 0.0
    
    for idx, row in cluster_df.iterrows():
        ticker = row['ticker']
        ticker_buys = buys_df[buys_df['ticker'] == ticker].sort_values('trade_date')
        
        if ticker_buys.empty:
            continue
        
        patterns = []
        pattern_score = 0.0
        
        # Pattern 1: Accelerating Buys
        if len(ticker_buys) >= 3:
            now = pd.Timestamp.now()
            recent_30d = ticker_buys[ticker_buys['trade_date'] >= (now - pd.Timedelta(days=30))]
            older_30d = ticker_buys[
                (ticker_buys['trade_date'] >= (now - pd.Timedelta(days=60))) &
                (ticker_buys['trade_date'] < (now - pd.Timedelta(days=30)))
            ]
            
            if len(recent_30d) > len(older_30d) * 1.5:
                patterns.append(f"🔥 Accelerating ({len(recent_30d)} recent vs {len(older_30d)} older)")
                pattern_score += 1.5
        
        # Pattern 2: CEO + CFO Together (within 5 days)
        ceo_buys = ticker_buys[ticker_buys['role'] == 'CEO']
        cfo_buys = ticker_buys[ticker_buys['role'] == 'CFO']
        
        if not ceo_buys.empty and not cfo_buys.empty:
            for _, ceo_buy in ceo_buys.iterrows():
                for _, cfo_buy in cfo_buys.iterrows():
                    days_apart = abs((ceo_buy['trade_date'] - cfo_buy['trade_date']).days)
                    if days_apart <= 5:
                        patterns.append("👔 CEO+CFO Coordination")
                        pattern_score += 2.0
                        break
        
        # Pattern 3: Breaking Silence (no buys for 90+ days, then cluster)
        if len(ticker_buys) >= 2:
            latest_date = ticker_buys['trade_date'].max()
            earlier_buys = ticker_buys[ticker_buys['trade_date'] < (latest_date - pd.Timedelta(days=90))]
            recent_buys = ticker_buys[ticker_buys['trade_date'] >= (latest_date - pd.Timedelta(days=30))]
            
            if earlier_buys.empty and len(recent_buys) >= 2:
                patterns.append("📅 Breaking Silence (90+ day gap)")
                pattern_score += 1.0
        
        # Pattern 4: Increasing Size
        if len(ticker_buys) >= 3:
            # Check if buy sizes are generally increasing
            recent_3 = ticker_buys.tail(3)
            values = recent_3['value_calc'].tolist()
            
            if len(values) == 3 and values[0] < values[1] < values[2]:
                patterns.append("📈 Increasing Size")
                pattern_score += 1.0
        
        # Update cluster_df
        if patterns:
            cluster_df.at[idx, 'patterns'] = " | ".join(patterns)
            cluster_df.at[idx, 'pattern_score'] = pattern_score
    
    # Count patterns found
    with_patterns = len(cluster_df[cluster_df['patterns'] != ''])
    if with_patterns > 0:
        print(f"   ✅ Found {with_patterns} signals with special patterns")
    
    return cluster_df

def cluster_and_score(df, window_days=5, top_n=50):
    """
    df: raw DataFrame from fetch_openinsider_recent
    returns: DataFrame with per-ticker aggregated cluster info and suggested action/rationale
    
    UPDATED: Now includes sector info, quality filters, and pattern detection
    """
    # filter buys
    buys = df[df['trade_type'].str.upper().str.contains('BUY|PURCHASE|P -', na=False)].copy()
    if buys.empty:
        return pd.DataFrame()

    buys['role'] = buys['title'].apply(normalize_title)
    buys['role_weight'] = buys['role'].map(ROLE_WEIGHT).fillna(1.0)
    # ensure value column - prefer explicit 'value' if present, else qty*price
    buys['value_calc'] = buys.apply(lambda r: r['value'] if (r.get('value',0) and r['value']>0) else (r.get('qty',0)*r.get('price',0)), axis=1)
    buys['conviction'] = buys.apply(lambda r: compute_conviction_score(r['value_calc'], r['role_weight']), axis=1)
    buys = buys.sort_values('trade_date')

    clusters = []
    tickers = buys['ticker'].unique()
    for t in tickers:
        tdf = buys[buys['ticker'] == t].copy().sort_values('trade_date')
        # compute cluster-level aggregates: last trade date, unique insiders in a sliding window
        max_cluster_count = 0
        max_total_value = 0
        last_trade = tdf['trade_date'].max()
        for idx,row in tdf.iterrows():
            start = row['trade_date'] - timedelta(days=window_days)
            end = row['trade_date'] + timedelta(days=window_days)
            window = tdf[(tdf['trade_date'] >= start) & (tdf['trade_date'] <= end)]
            cluster_count = window['insider'].nunique()
            total_value = window['value_calc'].sum()
            avg_conviction = window['conviction'].mean() if not window.empty else 0
            if cluster_count > max_cluster_count or (cluster_count == max_cluster_count and total_value > max_total_value):
                max_cluster_count = cluster_count
                max_total_value = total_value
                best_avg_conviction = avg_conviction
                window_insiders = ", ".join(window['insider'].unique().tolist())
        clusters.append({
            'ticker': t,
            'last_trade_date': last_trade,
            'cluster_count': int(max_cluster_count),
            'total_value': float(max_total_value),
            'avg_conviction': float(best_avg_conviction),
            'insiders': window_insiders if max_cluster_count>0 else "",
        })

    cluster_df = pd.DataFrame(clusters)
    if cluster_df.empty:
        return cluster_df

    # enrich market data (now includes sector info)
    cluster_df = enrich_with_market_data(cluster_df)

    # NEW: Apply quality filters
    cluster_df = apply_quality_filters(cluster_df)
    
    if cluster_df.empty:
        print("   ⚠️  All signals filtered out by quality checks")
        return cluster_df

    # NEW: Detect patterns
    cluster_df = detect_patterns(buys, cluster_df)

    # rank score: simple combination (you can tune)
    # NEW: Include pattern score in ranking
    cluster_df['rank_score'] = (
        cluster_df['cluster_count'] * 2.0 + 
        cluster_df['avg_conviction'] / 10.0 +
        cluster_df['pattern_score'] * 0.5  # Bonus for patterns
    )

    # suggested action and rationale
    cluster_df['suggested_action'] = cluster_df.apply(lambda r: suggest_action(r), axis=1)
    cluster_df['rationale'] = cluster_df.apply(lambda r: build_rationale(r), axis=1)

    # Sort by rank score and return top N
    result = cluster_df.sort_values('rank_score', ascending=False).head(top_n)
        
    # Filter out very low quality signals
    result = result[result['rank_score'] >= 3.0]
        
    return result

# Default urgent thresholds (feel free to tune)
URGENT_THRESHOLDS = {
    'cluster_count': 3,        # >= 3 insiders within window
    'total_value': 250000.0,   # total buy value across insiders (USD)
    'has_c_suite': True,       # at least one of CEO/CFO in insiders list
    'pct_from_52wk_low': 15.0, # within 15% of 52-week low (i.e., discounted)
}

def is_urgent(r, thresholds=URGENT_THRESHOLDS):
    # r: a row from cluster_df
    cond_cluster = r.get('cluster_count',0) >= thresholds['cluster_count']
    cond_value = r.get('total_value',0) >= thresholds['total_value']
    # detect presence of c-suite in the insidees / but we don't have role per insider here; approximate by avg_conviction > some threshold
    cond_c_suite = r.get('avg_conviction',0) >= 7.0 if thresholds.get('has_c_suite', True) else True
    cond_pct_low = True
    pct_low = r.get('pct_from_52wk_low')
    if pct_low is not None:
        cond_pct_low = pct_low <= thresholds['pct_from_52wk_low']
    return cond_cluster and cond_value and cond_c_suite and cond_pct_low

def suggest_action(r):
    """
    Determine suggested action based on signal strength.
    Now includes high-conviction single-insider buys.
    
    Rules:
      - Urgent: Multiple insiders + high conviction + near 52w low
      - Watchlist: 2+ insiders OR single high-conviction insider
      - Monitor: Everything else
    """
    # Check if urgent first
    if is_urgent(r):
        return "URGENT: Consider small entry at open / immediate review"
    
    # Multiple insiders (cluster of 2+)
    if r.get('cluster_count', 0) >= 2 and r.get('rank_score', 0) > 5:
        return "Watchlist - consider small entry after confirmation"
    
    # Single insider but HIGH conviction
    if r.get('cluster_count', 0) == 1:
        total_value = r.get('total_value', 0)
        conviction = r.get('avg_conviction', 0)
        
        # Very high conviction (CEO/CFO with large purchase)
        if conviction >= 12.0 and total_value >= 500000:
            return "Watchlist - strong single-insider signal"
        
        # High conviction with meaningful size
        elif conviction >= 10.0 and total_value >= 250000:
            return "Watchlist - notable insider purchase"
        
        # Large purchase (any insider buying $1M+)
        elif total_value >= 1000000:
            return "Watchlist - significant dollar amount"
        
        # Moderate conviction
        elif conviction >= 8.0 and total_value >= 100000:
            return "Monitor - single insider buying"
    
    # Default
    return "Monitor"

def build_rationale(r):
    parts = []
    parts.append(f"Cluster count: {int(r.get('cluster_count',0))}")
    parts.append(f"Total reported buys: ${int(r.get('total_value',0)):,}")
    if r.get('currentPrice') is not None:
        parts.append(f"Current Price: ${r.get('currentPrice')}")
    if r.get('pct_from_52wk_low') is not None:
        parts.append(f"{r.get('pct_from_52wk_low'):.1f}% above 52-week low")
    
    # NEW: Add sector info
    if r.get('sector') and r.get('sector') != 'Unknown':
        parts.append(f"Sector: {r.get('sector')}")
    
    parts.append(f"Rank Score: {r.get('rank_score'):.2f}")
    
    # NEW: Add pattern info if present
    if r.get('patterns'):
        parts.append(f"Patterns: {r.get('patterns')}")
    
    return " | ".join(parts)

if __name__ == "__main__":
    # quick smoke test - requires fetch_openinsider.py
    import jobs.fetch_openinsider as fio
    df = fio.fetch_openinsider_recent()
    out = cluster_and_score(df)
    print(out.head())