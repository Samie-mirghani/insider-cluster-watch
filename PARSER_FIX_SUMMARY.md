# Capitol Trades Parser - Fix Summary

## Problem Identified

The Capitol Trades scraper was successfully loading pages with Selenium (12 table rows found) but extracting **0 trades** due to HTML structure mismatch.

### Root Cause

Capitol Trades uses a complex React/Next.js component structure with specific CSS classes:

```html
<!-- Politician Name -->
<h2 class="politician-name">
  <a href="/politicians/P000197">Nancy Pelosi</a>
</h2>

<!-- Ticker -->
<span class="issuer-ticker">AAPL:US</span>

<!-- Transaction Type -->
<span class="tx-type tx-type--buy">buy</span>
<!-- or -->
<span class="tx-type tx-type--sell">sell</span>

<!-- Date -->
<div class="text-center">
  <div>09:05</div>
  <div>Today</div>
</div>
```

The original parser used generic `cell.get_text(strip=True)` which didn't target these specific elements.

## Fixes Applied

### 1. Capitol Trades-Specific Extraction Methods

**`_extract_politician_name()`** - jobs/capitol_trades_scraper.py:383-396
- Targets `h2.politician-name > a` for politician names
- Fallback to generic text extraction

**`_extract_ticker()`** - jobs/capitol_trades_scraper.py:398-441
- Targets `span.issuer-ticker` for tickers
- Parses "MCK:US" format to extract just "MCK"
- Multiple fallback strategies for compatibility

**`_extract_transaction_type()`** - jobs/capitol_trades_scraper.py:443-455
- Targets `span.tx-type` with regex for buy/sell variants
- **Critical fix**: Removed generic text fallback to prevent false positives

### 2. Enhanced Date Parsing

**`_parse_date()`** - jobs/capitol_trades_scraper.py:457-481
- Added support for relative dates: "Today", "Yesterday"
- Multiple date format fallbacks

### 3. Bug Fixes

**Logger initialization** - jobs/capitol_trades_scraper.py:17-19
- Moved logger setup before Selenium imports to prevent NameError

**Session fallback** - jobs/capitol_trades_scraper.py:74-84
- Always create HTTP session as fallback when Selenium fails
- Prevents AttributeError when falling back to HTTP requests

### 4. Improved Debugging

**Enhanced logging** - jobs/capitol_trades_scraper.py:324-389
- INFO level logging for trade parsing details
- Shows why trades are skipped (not purchase/buy vs missing fields)
- Logs first 3 rows with full cell contents

## Test Results

```
Testing Capitol Trades Extraction Methods
============================================================
Total trades parsed: 1

Trades found:

1. Nancy Pelosi
   Ticker: AAPL
   Type: buy
   Date: 2025-11-10 20:26:28
   Amount: $15,001 - $50,000

✓ Extraction methods working correctly!
```

**Verification:**
- ✓ Politician name extracted: "Nancy Pelosi"
- ✓ Ticker parsed from "AAPL:US" → "AAPL"
- ✓ Transaction type: "buy"
- ✓ Date parsed: "Yesterday" → datetime
- ✓ Sell transactions correctly filtered
- ✓ Jonathan Jackson - MCK - sell → Skipped (not purchase)

## Current Status

### Working ✓
- HTML parsing with BeautifulSoup
- Capitol Trades-specific extraction methods
- Ticker format parsing ("MCK:US" → "MCK")
- Relative date parsing ("Today", "Yesterday")
- Transaction type filtering (buy/purchase only)
- Fallback to HTTP requests when Selenium unavailable

### Environment Setup Required
- **Chrome/Chromium browser** - Not currently installed in environment
- ChromeDriver is present at `/opt/node22/bin/chromedriver` v142.0.7444.61
- Selenium package installed via pip

### Next Steps

1. **Install Chrome/Chromium** in your environment:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install chromium-browser

   # Or download Chrome for Testing
   # Selenium Manager will handle this automatically if Chrome is not found
   ```

2. **Test live scraping** once Chrome is installed:
   ```bash
   cd jobs
   python3 test_capitol_trades_debug.py
   ```

3. **Verify extraction** from real Capitol Trades data:
   - Should see "Using Selenium for JavaScript rendering"
   - Should see "✓ Table loaded"
   - Should see trades extracted with politician names, tickers, and types

4. **Enable in production** after successful test:
   - Set `ENABLE_POLITICIAN_SCRAPING = True` in `jobs/config.py`
   - Run full pipeline test

## Files Modified

- `jobs/capitol_trades_scraper.py` - Parser improvements and bug fixes
- `jobs/test_extraction_minimal.py` - New test with minimal HTML sample (NEW)
- `jobs/test_parser_only.py` - Test with saved HTML file (NEW)

## Commit

```
commit 5a8ed04
Fix Capitol Trades parser to extract data from React components

Capitol Trades uses complex nested React/Next.js component structure
with specific CSS classes. Updated extraction methods to target:

- h2.politician-name > a for politician names
- span.issuer-ticker for tickers (format "MCK:US")
- span.tx-type.tx-type--buy/sell for transaction types
- Added support for relative dates ("Today", "Yesterday")
```

## Technical Notes

### Why the Parser Failed Before

The extraction loop was finding transaction types using generic text extraction:

```python
# BEFORE (Broken)
def _extract_transaction_type(self, cell) -> str:
    tx_elem = cell.find('span', class_=re.compile(r'tx-type'))
    if tx_elem:
        return tx_elem.get_text(strip=True)

    # This fallback caused the bug!
    return self._extract_text(cell)  # Returns ANY text in cell
```

When searching `cells[0]` for transaction type, the fallback would return the politician name ("Jonathan Jackson"), causing all trades to be filtered out since:

```python
if 'purchase' in trade['transaction_type'].lower() or 'buy' in trade['transaction_type'].lower():
    # "Jonathan Jackson" contains neither 'purchase' nor 'buy' → filtered out!
```

### The Fix

```python
# AFTER (Working)
def _extract_transaction_type(self, cell) -> str:
    tx_elem = cell.find('span', class_=re.compile(r'tx-type'))
    if tx_elem:
        return tx_elem.get_text(strip=True)

    # Only return if we found the specific element
    return ""  # Don't fallback to generic text
```

Now the search loop continues until it finds the actual `span.tx-type` element in the correct cell.
