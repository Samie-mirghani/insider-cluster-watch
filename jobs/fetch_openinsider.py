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

OPENINS_URL = "http://openinsider.com/screener"

def fetch_openinsider_recent(max_retries=3):
    """
    Fetch recent insider transactions with retry logic.
    
    Args:
        max_retries: Number of retry attempts if request fails
    
    Returns:
        DataFrame with insider transaction data
    """
    params = {
        's': 'o',  # ordering
        'o': '1',  # sort
        'srt': 'date'  # sort by date
    }
    
    for attempt in range(max_retries):
        try:
            print(f"Attempting to fetch from OpenInsider (attempt {attempt + 1}/{max_retries})...")
            r = requests.get(OPENINS_URL, params=params, timeout=30)  # Increased to 30 seconds
            r.raise_for_status()
            
            # Successfully fetched, parse the data
            soup = BeautifulSoup(r.text, 'html.parser')
            table = soup.find('table', {'class': 'tinytable'})
            rows = []
            
            if not table:
                print("Warning: Could not find data table on OpenInsider")
                return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])

            for tr in table.find_all('tr')[1:]:
                cols = [td.get_text(strip=True) for td in tr.find_all('td')]
                if len(cols) < 12:
                    continue
                try:
                    rows.append({
                        'filing_date': cols[1],
                        'trade_date': cols[2],
                        'ticker': cols[3],
                        'insider': cols[4],
                        'title': cols[5],
                        'trade_type': cols[6],
                        'qty': cols[7].replace(',',''),
                        'price': cols[8].replace('$','').replace(',',''),
                        'owned': cols[9].replace(',',''),
                        'value': cols[10].replace('$','').replace(',','')
                    })
                except Exception as e:
                    print(f"Error parsing row: {e}")
                    continue

            df = pd.DataFrame(rows)
            
            if df.empty:
                print("No rows parsed from OpenInsider")
                return df
            
            # Convert data types
            for c in ['qty','price','owned','value']:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce')
            df['filing_date'] = pd.to_datetime(df['filing_date'], errors='coerce')
            
            print(f"✅ Successfully fetched {len(df)} records from OpenInsider")
            return df
            
        except requests.exceptions.Timeout:
            print(f"⚠️ Request timed out (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5  # Exponential backoff: 5s, 10s, 15s
                print(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print("❌ All retry attempts failed - OpenInsider is not responding")
                # Return empty DataFrame with proper columns
                return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching from OpenInsider: {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print("❌ All retry attempts failed")
                return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])
        
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])
    
    # Should never reach here, but just in case
    return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])

if __name__ == "__main__":
    df = fetch_openinsider_recent()
    print(f"\nFetched {len(df)} records")
    if not df.empty:
        print(df.head())
