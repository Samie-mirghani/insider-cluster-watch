# jobs/fetch_openinsider.py
"""
Fetch recent insider transactions from OpenInsider.
Returns a pandas.DataFrame with columns:
  filing_date, trade_date, ticker, insider, title, trade_type, qty, price, owned, value
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import logging
from ticker_validator import validate_and_normalize_ticker

logger = logging.getLogger(__name__)

# Try HTTPS first, fall back to HTTP if network unreachable
OPENINS_URLS = [
    "https://openinsider.com/screener",  # Preferred
    "http://openinsider.com/screener"    # Fallback for restricted networks
]

def fetch_openinsider_recent(max_retries=3):
    """
    Fetch recent insider transactions with retry logic.

    Args:
        max_retries: Number of retry attempts if request fails

    Returns:
        DataFrame with insider transaction data
    """
    # Request last 7 days to only get RECENT filings
    # This prevents re-detecting old clusters from stale data
    # Historical data for 90d outcomes is already saved in insider_trades_history.csv
    params = {
        'fd': '7',         # Last 7 days (reduced from 180 to prevent duplicate signals)
        'xp': '1',         # Exclude options (we want open market)
        'sortcol': '0',    # Sort by filing date
        'cnt': '5000',     # Max results (increased from 1000)
        'page': '1'        # First page
    }

    # Add browser-like headers to avoid bot detection
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0'
    }

    # Use a session for better connection handling
    session = requests.Session()
    session.headers.update(headers)

    # Track connection errors to trigger HTTP fallback
    https_failed = False

    for attempt in range(max_retries):
        # Determine which URL to use based on HTTPS connectivity
        if https_failed:
            # If HTTPS failed, use HTTP fallback
            url = OPENINS_URLS[1]  # HTTP fallback
        else:
            # Try HTTPS first
            url = OPENINS_URLS[0]  # HTTPS preferred

        try:
            protocol = "HTTPS" if url.startswith("https") else "HTTP"
            print(f"📥 Fetching from OpenInsider via {protocol} (attempt {attempt + 1}/{max_retries})...")

            # Add a small delay between retries to avoid rate limiting
            if attempt > 0:
                time.sleep(2)

            r = session.get(url, params=params, timeout=30)

            # Check for common blocking scenarios
            if r.status_code == 403:
                print(f"⚠️  Access forbidden (403) - OpenInsider may be blocking automated requests")
                if 'x-deny-reason' in r.headers:
                    print(f"   Reason: {r.headers['x-deny-reason']}")
                if attempt < max_retries - 1:
                    continue
                else:
                    return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])

            r.raise_for_status()

            soup = BeautifulSoup(r.text, 'html.parser')
            table = soup.find('table', {'class': 'tinytable'})

            if not table:
                print("⚠️  Warning: Could not find data table on OpenInsider")
                print(f"   Page length: {len(r.text)} bytes")
                print(f"   Status code: {r.status_code}")
                # Try to find any table to help diagnose
                all_tables = soup.find_all('table')
                if all_tables:
                    print(f"   Found {len(all_tables)} table(s) with classes: {[t.get('class') for t in all_tables]}")
                return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])

            rows = []
            table_rows = table.find_all('tr')[1:]  # Skip header row
            
            print(f"   Parsing {len(table_rows)} rows from OpenInsider...")
            
            for tr in table_rows:
                cols = [td.get_text(strip=True) for td in tr.find_all('td')]
                
                # OpenInsider table has these columns:
                # 0: X (indicator)
                # 1: Filing Date
                # 2: Trade Date
                # 3: Ticker
                # 4: Company Name (we'll skip this)
                # 5: Insider Name
                # 6: Title
                # 7: Trans Type (P/S/etc)
                # 8: Last Price
                # 9: Qty
                # 10: Owned
                # 11: ΔOwn
                # 12: Value
                
                if len(cols) < 13:  # Need at least 13 columns
                    continue
                    
                try:
                    # Correct column mapping
                    trade_type = cols[7]  # Transaction type (P/S/M/etc)
                    
                    # Skip if not a clear buy or sale
                    if not trade_type or trade_type == '-':
                        continue
                    
                    row_data = {
                        'filing_date': cols[1],      # Filing date
                        'trade_date': cols[2],       # Trade date  
                        'ticker': cols[3],           # Ticker symbol
                        'insider': cols[5],          # Insider name (skip company name at cols[4])
                        'title': cols[6],            # Title/position
                        'trade_type': trade_type,    # Transaction type
                        'qty': cols[9].replace(',','').replace('+',''),           # Quantity
                        'price': cols[8].replace('$','').replace(',',''),         # Price
                        'owned': cols[10].replace(',','').replace('+',''),        # Owned after
                        'value': cols[12].replace('$','').replace(',','').replace('+','')  # Value
                    }
                    
                    rows.append(row_data)
                    
                except Exception as e:
                    # Skip rows that don't parse correctly
                    continue

            if not rows:
                print("⚠️  No rows successfully parsed")
                return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])
            
            df = pd.DataFrame(rows)
            
            # Convert data types
            for c in ['qty','price','owned','value']:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            
            df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce')
            df['filing_date'] = pd.to_datetime(df['filing_date'], errors='coerce')
            
            # Filter to keep only recent trades (last 14 days)
            # Historical data is already saved for outcome tracking
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=14)
            df = df[df['trade_date'] >= cutoff_date]
            
            # Map transaction codes to readable format
            def map_transaction_type(code):
                code = str(code).upper().strip()
                if code in ['P', 'P - PURCHASE']:
                    return 'P - Purchase'
                elif code in ['S', 'S - SALE']:
                    return 'S - Sale'
                elif code in ['M']:
                    return 'M - Option Exercise'
                elif code in ['A']:
                    return 'A - Award'
                elif code in ['G']:
                    return 'G - Gift'
                else:
                    return code
            
            df['trade_type'] = df['trade_type'].apply(map_transaction_type)

            # TICKER VALIDATION: Normalize and validate all tickers
            # Remove .Q, .G, .M suffixes and filter out invalid tickers
            initial_count = len(df)

            # Create mapping of raw -> normalized tickers
            ticker_mapping = {}
            invalid_tickers = []

            for raw_ticker in df['ticker'].unique():
                normalized_ticker, error, _ = validate_and_normalize_ticker(raw_ticker)
                if normalized_ticker:
                    ticker_mapping[raw_ticker] = normalized_ticker
                else:
                    invalid_tickers.append((raw_ticker, error))

            # Apply normalization using map (avoids SettingWithCopyWarning)
            df['ticker'] = df['ticker'].map(lambda t: ticker_mapping.get(t, t))

            # Filter out invalid tickers (those not in mapping)
            df = df[df['ticker'].isin(ticker_mapping.values())].copy()

            if invalid_tickers:
                logger.info(f"Filtered out {len(invalid_tickers)} invalid tickers from OpenInsider data")
                for ticker, reason in invalid_tickers[:5]:  # Log first 5
                    logger.debug(f"  Skipped '{ticker}': {reason}")

            print(f"✅ Successfully fetched {len(df)} records from OpenInsider ({initial_count - len(df)} invalid tickers filtered)")

            # Show breakdown
            if not df.empty:
                buy_count = len(df[df['trade_type'].str.contains('Purchase|P -', case=False, na=False)])
                sale_count = len(df[df['trade_type'].str.contains('Sale|S -', case=False, na=False)])
                other_count = len(df) - buy_count - sale_count
                print(f"   📊 Breakdown: {buy_count} buys, {sale_count} sales, {other_count} other")
                
                if buy_count > 0:
                    print(f"   ✅ Found {buy_count} purchase transactions!")
            
            return df
            
        except requests.exceptions.Timeout:
            print(f"⚠️  Request timed out (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"   Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print("❌ All retry attempts failed - OpenInsider is not responding")
                return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])

        except requests.exceptions.HTTPError as e:
            print(f"❌ HTTP Error {e.response.status_code}: {e}")
            if e.response.status_code == 403:
                print("   OpenInsider is blocking the request - may need proxy or alternative approach")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"   Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print("❌ All attempts failed - unable to access OpenInsider")
                return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])

        except requests.exceptions.ConnectionError as e:
            error_str = str(e)

            # Check if this is an HTTPS connectivity issue
            if url.startswith("https") and not https_failed:
                if "Network is unreachable" in error_str or "Failed to establish" in error_str:
                    print(f"⚠️  HTTPS connection failed: Network unreachable")
                    print(f"🔄 Trying HTTP fallback...")
                    https_failed = True
                    # Don't count this as a retry attempt, just switch protocols
                    continue

            # For HTTP failures or repeated failures, handle normally
            print(f"❌ Connection error: {type(e).__name__}")
            logger.error(f"Connection error details: {e}")

            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"   Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print("❌ All connection attempts failed - OpenInsider is unreachable")
                return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])

        except Exception as e:
            print(f"❌ Unexpected error: {type(e).__name__}: {e}")
            logger.exception("Error fetching OpenInsider data")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"   Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print("❌ All attempts failed")
                return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])
    
    return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])

if __name__ == "__main__":
    print("="*60)
    print("Testing OpenInsider Data Fetch")
    print("="*60)
    
    df = fetch_openinsider_recent()
    
    print(f"\n{'='*60}")
    print(f"Results Summary")
    print(f"{'='*60}")
    print(f"Total records fetched: {len(df)}")
    
    if not df.empty:
        print(f"\nTransaction type breakdown:")
        print(df['trade_type'].value_counts())
        
        print(f"\nDate range:")
        print(f"Oldest: {df['trade_date'].min()}")
        print(f"Newest: {df['trade_date'].max()}")
        
        # Check for buys specifically
        buys = df[df['trade_type'].str.contains('Purchase|P -', case=False, na=False)]
        print(f"\n🛒 BUY TRANSACTIONS: {len(buys)}")
        
        if len(buys) > 0:
            print("\nSample buys:")
            print(buys[['ticker', 'insider', 'title', 'trade_type', 'value', 'trade_date']].head(10))
            
            # Show tickers with multiple buyers
            ticker_counts = buys['ticker'].value_counts()
            multi_buyer = ticker_counts[ticker_counts > 1]
            if len(multi_buyer) > 0:
                print(f"\n🎯 Tickers with multiple buyers (potential clusters):")
                for ticker, count in multi_buyer.items():
                    print(f"   {ticker}: {count} insiders buying")
        
        # Sales
        sales = df[df['trade_type'].str.contains('Sale|S -', case=False, na=False)]
        print(f"\n📉 Sale transactions: {len(sales)}")
        
    else:
        print("\n⚠️  No data returned")