# jobs/fetch_sec_edgar.py
"""
Fetch Form 4 filings directly from SEC EDGAR as a backup to OpenInsider.
Parses the EDGAR RSS feed and individual Form 4 XML files.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import time
import re
from xml.etree import ElementTree as ET

SEC_RSS_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
SEC_HEADERS = {
    'User-Agent': 'InsiderClusterWatch your-email@example.com',  # SEC requires identification
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

def fetch_recent_form4_filings(days_back=3, max_filings=100):
    """
    Fetch recent Form 4 filings from SEC EDGAR.
    
    Args:
        days_back: Number of days to look back
        max_filings: Maximum number of filings to retrieve
    
    Returns:
        List of filing URLs to parse
    """
    print(f"📥 Fetching Form 4 filings from SEC EDGAR (last {days_back} days)...")
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    # SEC EDGAR search parameters
    params = {
        'action': 'getcompany',
        'type': '4',  # Form 4
        'dateb': end_date.strftime('%Y%m%d'),
        'datea': start_date.strftime('%Y%m%d'),
        'owner': 'include',  # Include insider filings
        'start': 0,
        'count': min(max_filings, 100),  # SEC limits to 100 per request
        'output': 'atom'  # Get results in XML format
    }
    
    filing_urls = []
    
    try:
        response = requests.get(
            SEC_RSS_URL,
            params=params,
            headers=SEC_HEADERS,
            timeout=30
        )
        response.raise_for_status()
        
        # Parse the ATOM/XML feed
        root = ET.fromstring(response.content)
        
        # Extract filing URLs from the feed
        namespace = {'atom': 'http://www.w3.org/2005/Atom'}
        entries = root.findall('.//atom:entry', namespace)
        
        for entry in entries[:max_filings]:
            link = entry.find('.//atom:link[@rel="alternate"]', namespace)
            if link is not None:
                filing_url = link.get('href')
                if filing_url:
                    # Convert to documents page
                    filing_url = filing_url.replace('-index.htm', '.txt')
                    filing_urls.append(filing_url)
        
        print(f"✅ Found {len(filing_urls)} Form 4 filings")
        return filing_urls
        
    except Exception as e:
        print(f"❌ Error fetching from SEC EDGAR: {e}")
        return []

def parse_form4_xml(filing_url, max_retries=2):
    """
    Parse a Form 4 XML file and extract transaction data.
    
    Returns:
        List of transaction dictionaries
    """
    transactions = []
    
    for attempt in range(max_retries):
        try:
            # Fetch the filing
            response = requests.get(filing_url, headers=SEC_HEADERS, timeout=20)
            response.raise_for_status()
            
            # Parse XML
            content = response.text
            
            # Extract XML portion (Form 4s have XML embedded in text)
            xml_match = re.search(r'<XML>(.*?)</XML>', content, re.DOTALL)
            if not xml_match:
                return []
            
            xml_content = xml_match.group(1)
            root = ET.fromstring(xml_content)
            
            # Extract issuer (company) information
            issuer = root.find('.//issuer')
            if issuer is None:
                return []
            
            ticker_elem = issuer.find('.//issuerTradingSymbol')
            ticker = ticker_elem.text if ticker_elem is not None else None
            
            if not ticker:
                return []
            
            # Extract reporting owner (insider) information
            owner = root.find('.//reportingOwner')
            if owner is None:
                return []
            
            owner_name_elem = owner.find('.//rptOwnerName')
            owner_name = owner_name_elem.text if owner_name_elem is not None else 'Unknown'
            
            # Extract relationship/title
            relationship = owner.find('.//reportingOwnerRelationship')
            title_parts = []
            if relationship is not None:
                if relationship.find('.//isDirector') is not None and relationship.find('.//isDirector').text == '1':
                    title_parts.append('Director')
                if relationship.find('.//isOfficer') is not None and relationship.find('.//isOfficer').text == '1':
                    officer_title = relationship.find('.//officerTitle')
                    if officer_title is not None:
                        title_parts.append(officer_title.text)
            
            title = ', '.join(title_parts) if title_parts else 'Insider'
            
            # Extract transactions (both non-derivative and derivative)
            for tx_type in ['.//nonDerivativeTransaction', './/derivativeTransaction']:
                for transaction in root.findall(tx_type):
                    try:
                        # Transaction date
                        tx_date_elem = transaction.find('.//transactionDate/value')
                        if tx_date_elem is None:
                            continue
                        tx_date = pd.to_datetime(tx_date_elem.text)
                        
                        # Transaction code (P=Purchase, S=Sale, etc.)
                        tx_code_elem = transaction.find('.//transactionCode')
                        if tx_code_elem is None:
                            continue
                        tx_code = tx_code_elem.text
                        
                        # Map transaction codes to types
                        if tx_code in ['P', 'M']:  # P=Purchase, M=Option Exercise
                            trade_type = 'P - Purchase'
                        elif tx_code in ['S']:  # S=Sale
                            trade_type = 'S - Sale'
                        else:
                            continue  # Skip other transaction types
                        
                        # Shares/Quantity
                        qty_elem = transaction.find('.//transactionShares/value')
                        qty = float(qty_elem.text) if qty_elem is not None else 0
                        
                        # Price per share
                        price_elem = transaction.find('.//transactionPricePerShare/value')
                        price = float(price_elem.text) if price_elem is not None else 0
                        
                        # Shares owned after transaction
                        owned_elem = transaction.find('.//sharesOwnedFollowingTransaction/value')
                        owned = float(owned_elem.text) if owned_elem is not None else 0
                        
                        # Calculate value
                        value = qty * price if price > 0 else 0
                        
                        # Add transaction
                        transactions.append({
                            'filing_date': datetime.now(),  # Today
                            'trade_date': tx_date,
                            'ticker': ticker.strip().upper(),
                            'insider': owner_name.strip(),
                            'title': title,
                            'trade_type': trade_type,
                            'qty': qty,
                            'price': price,
                            'owned': owned,
                            'value': value
                        })
                        
                    except Exception as e:
                        print(f"   Warning: Error parsing transaction: {e}")
                        continue
            
            # Rate limiting - be respectful to SEC servers
            time.sleep(0.2)
            return transactions
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"   Retry {attempt + 1}/{max_retries} for {filing_url}")
                time.sleep(2)
            else:
                print(f"   Error parsing {filing_url}: {e}")
                return []
    
    return []

def fetch_sec_edgar_data(days_back=3, max_filings=50):
    """
    Main function to fetch and parse SEC EDGAR Form 4 data.
    
    Returns:
        DataFrame with same structure as OpenInsider data
    """
    # Get filing URLs
    filing_urls = fetch_recent_form4_filings(days_back=days_back, max_filings=max_filings)
    
    if not filing_urls:
        print("No Form 4 filings found on SEC EDGAR")
        return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])
    
    # Parse each filing
    all_transactions = []
    print(f"📄 Parsing {len(filing_urls)} filings...")
    
    for i, url in enumerate(filing_urls, 1):
        if i % 10 == 0:
            print(f"   Progress: {i}/{len(filing_urls)} filings parsed")
        
        transactions = parse_form4_xml(url)
        all_transactions.extend(transactions)
        
        # Rate limiting
        time.sleep(0.15)
    
    if not all_transactions:
        print("No transactions extracted from filings")
        return pd.DataFrame(columns=['filing_date','trade_date','ticker','insider','title','trade_type','qty','price','owned','value'])
    
    # Convert to DataFrame
    df = pd.DataFrame(all_transactions)
    
    # Ensure proper data types
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['filing_date'] = pd.to_datetime(df['filing_date'])
    
    for col in ['qty', 'price', 'owned', 'value']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    print(f"✅ Extracted {len(df)} transactions from SEC EDGAR")
    return df

if __name__ == "__main__":
    # Test the SEC EDGAR fetcher
    df = fetch_sec_edgar_data(days_back=2, max_filings=20)
    if not df.empty:
        print("\nSample data:")
        print(df.head())
        print(f"\nBuy transactions: {len(df[df['trade_type'].str.contains('Purchase', na=False)])}")
        print(f"Sale transactions: {len(df[df['trade_type'].str.contains('Sale', na=False)])}")