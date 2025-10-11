# fetch_openinsider.py
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

OPENINS_URL = "http://openinsider.com/screener"

def fetch_openinsider_recent():
    # This is a lightweight approach — query screener by default filters
    params = {
        's': 'o',  # order
        'o': '1',  # sort
        'srt': 'date'  # sort by date
    }
    r = requests.get(OPENINS_URL, params=params, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    table = soup.find('table', {'class': 'tinytable'})
    rows = []
    if not table:
        return pd.DataFrame()
    for tr in table.find_all('tr')[1:]:
        cols = [td.get_text(strip=True) for td in tr.find_all('td')]
        if len(cols) < 12:
            continue
        # Example columns: X, Filing Date, Trade Date, Ticker, Insider Name, Title, Trade Type, Qty, Price, Owned, ...
        rows.append({
            'filing_date': cols[1],
            'trade_date': cols[2],
            'ticker': cols[3],
            'insider': cols[4],
            'title': cols[5],
            'trade_type': cols[6],  # e.g., Buy, Sell
            'qty': cols[7].replace(',', ''),
            'price': cols[8].replace('$','').replace(',',''),
            'owned': cols[9].replace(',',''),
            'value': cols[10].replace('$','').replace(',','')
        })
    df = pd.DataFrame(rows)
    # cast types
    for c in ['qty','price','owned','value']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce')
    df['filing_date'] = pd.to_datetime(df['filing_date'], errors='coerce')
    return df

if __name__ == "__main__":
    df = fetch_openinsider_recent()
    print(df.head())
