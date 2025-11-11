# Multi-Signal Detection Features

## Overview

Your insider cluster watch pipeline has been enhanced with powerful multi-signal detection capabilities that combine multiple data sources to identify the strongest investment opportunities.

## New Features

### 🏛️ 1. Capitol Trades Scraper (FREE Politician Trading Data)

**File:** `jobs/capitol_trades_scraper.py`

Scrapes politician trading data from Capitol Trades website (free alternative to paid APIs).

#### Features:
- ✅ Robust web scraping with retries and error handling
- ✅ Rate limiting to avoid getting blocked
- ✅ Politician performance weighting (e.g., Nancy Pelosi trades weighted 2x)
- ✅ Detects politician clusters (multiple politicians buying same stock)
- ✅ Bipartisan detection (higher conviction when both parties buy)
- ✅ Calculates disclosure lag (how long politicians took to report)

#### Key Politicians Tracked:
- Nancy Pelosi & Paul Pelosi (2.0x weight)
- Josh Gottheimer (1.8x)
- Dan Crenshaw (1.5x)
- Marjorie Taylor Greene (1.4x)
- Tommy Tuberville (1.4x)
- And many more...

#### Usage:
```python
from capitol_trades_scraper import CapitolTradesScraper

scraper = CapitolTradesScraper()

# Scrape recent trades
trades = scraper.scrape_recent_trades(days_back=30, max_pages=5)

# Detect clusters
clusters = scraper.detect_politician_clusters(trades)

# Get trades for specific ticker
ticker_trades = scraper.get_trades_for_ticker('AAPL', days_back=90)
```

---

### 📊 2. SEC 13F Parser (Institutional Holdings)

**File:** `jobs/sec_13f_parser.py`

Parses 13F filings from SEC EDGAR to track what major hedge funds and institutions are buying.

#### Features:
- ✅ Tracks 15 priority institutional investors
- ✅ FREE data from SEC EDGAR API
- ✅ Quarterly filing analysis
- ✅ Holdings validation

#### Priority Funds Tracked:
- Berkshire Hathaway (Warren Buffett)
- Bridgewater Associates (Ray Dalio)
- Renaissance Technologies
- Two Sigma
- Citadel (Ken Griffin)
- Point72 (Steve Cohen)
- Tiger Global
- Soros Fund Management
- Pershing Square (Bill Ackman)
- Bill & Melinda Gates Foundation
- And more...

#### Usage:
```python
from sec_13f_parser import SEC13FParser

parser = SEC13FParser(user_agent="YourCompany admin@example.com")

# Check institutional interest
holdings = parser.check_institutional_interest('AAPL', 2024, 4)

# Get summary
summary = parser.get_13f_summary_for_ticker('AAPL')
```

**Note:** You MUST provide a valid User-Agent when making SEC requests as required by SEC.gov

---

### 🎯 3. Multi-Signal Detector (Combines All Sources)

**File:** `jobs/multi_signal_detector.py`

Combines insider trades, politician trades, 13F holdings, and short interest into tiered signals.

#### Signal Tiers:

**Tier 1 (🔥 HIGHEST):** 3+ signals
- Insider cluster + Politician activity + Institutional interest
- Largest position size (100%)
- Widest stop loss (12%)

**Tier 2 (⚡ HIGH):** 2 signals
- Insider + Politician OR Insider + Institutional
- 75% position size
- 10% stop loss

**Tier 3 (✓ MODERATE):** 1 strong signal
- Strong insider cluster alone
- 50% position size
- 8% stop loss

**Tier 4 (→ WATCH):** Watch list
- Weak signals but worth monitoring
- 25% position size
- 6% stop loss

#### Conviction Scoring:
- **Insider trades:** 35% weight
- **Politician trades:** 30% weight
- **Institutional holdings:** 20% weight
- **Short interest:** 15% weight

#### Usage:
```python
from multi_signal_detector import MultiSignalDetector

detector = MultiSignalDetector(sec_user_agent="YourApp admin@example.com")

# Run full scan
results = detector.run_full_scan(
    insider_clusters=your_cluster_df,
    check_13f=True,
    quarter_year=2024,
    quarter=4
)

# Access tiered signals
tier1_signals = results['tier1']  # Highest conviction
tier2_signals = results['tier2']  # High conviction
tier3_signals = results['tier3']  # Moderate
tier4_signals = results['tier4']  # Watch list
```

---

### 💰 4. Enhanced Paper Trading (Position Sizing by Signal Strength)

**File:** `jobs/paper_trading_multi_signal.py`

Paper trading system that adjusts position sizing based on signal tier.

#### Features:
- ✅ Dynamic position sizing (25% - 100% based on tier)
- ✅ Tiered stop losses (6% - 12% based on conviction)
- ✅ Automatic risk management
- ✅ Detailed entry reasoning

#### Position Sizing:
```
Tier 1: 100% of base position (10% of portfolio)
Tier 2: 75% of base position (7.5% of portfolio)
Tier 3: 50% of base position (5% of portfolio)
Tier 4: 25% of base position (2.5% of portfolio)
```

---

## Configuration

All settings are in `jobs/config.py`:

```python
# Multi-Signal Detection Settings
ENABLE_MULTI_SIGNAL = True  # Enable politician and institutional detection
ENABLE_POLITICIAN_SCRAPING = True  # Scrape Capitol Trades
ENABLE_13F_CHECKING = False  # Check 13F filings (optional, slower)

# Politician Trading
POLITICIAN_LOOKBACK_DAYS = 30  # Days to look back for politician trades
POLITICIAN_MAX_PAGES = 5  # Max pages to scrape from Capitol Trades
MIN_POLITICIANS_FOR_CLUSTER = 2  # Min politicians needed for cluster signal

# Signal Tier Thresholds
TIER_1_MIN_SIGNALS = 3  # Tier 1: 3+ signals (highest conviction)
TIER_2_MIN_SIGNALS = 2  # Tier 2: 2 signals (high conviction)

# SEC EDGAR Settings
SEC_USER_AGENT = "InsiderClusterWatch admin@example.com"  # Required by SEC
```

---

## Integration with Existing Pipeline

The multi-signal detection is **automatically integrated** into your main pipeline (`jobs/main.py`).

### How It Works:

1. **Existing insider detection runs first** (your current pipeline)
2. **Multi-signal detection enriches the results**:
   - Scrapes politician trades
   - Checks 13F institutional holdings (if enabled)
   - Detects overlaps and assigns tiers
3. **Signals are boosted based on confirmation**:
   - Tier 1 signals: rank_score × 1.5
   - Tier 2 signals: rank_score × 1.25
4. **Email reports show enhanced signals**:
   - 🔥 TIER1 indicator for 3+ signals
   - ⚡ TIER2 indicator for 2 signals
   - 🏛️ POLITICIAN flag when politicians are buying

---

## Output Examples

### Multi-Signal Detection Output:
```
🔍 Running multi-signal detection...
   • Scanning politician trades

MULTI-SIGNAL DETECTION SCAN
============================================================

Step 1: Scraping politician trades...
✓ Scraped 127 trades total
✓ Detected 8 politician clusters

Analyzing AAPL...
  ✓ Politician signal: 3 politicians
  ✓ Institutional signal: 5 priority funds
  🔥 TIER 1: 3 signals!

Analyzing TSLA...
  ✓ Politician signal: 2 politicians
  ⚡ TIER 2: Insider + Politician

SCAN COMPLETE
Tier 1 (3+ signals): 2
Tier 2 (2 signals):  3
Tier 3 (1 signal):   5
Tier 4 (watch list): 2
============================================================

   ✅ Found 5 stocks with multiple signals!
      • Tier 1 (3+ signals): 2
      • Tier 2 (2 signals): 3
      • Tier 1 tickers: AAPL, MSFT
```

### Enhanced Signal Display:
```
📊 New signals:
   AAPL: Cluster=4, Score=18.50, Quality=8.5, Technology, $850,000 🔥 TIER1 🏛️ POLITICIAN
   TSLA: Cluster=3, Score=14.25, Quality=7.8, Consumer Cyclical, $620,000 ⚡ TIER2 🏛️ POLITICIAN
   NVDA: Cluster=5, Score=16.00, Quality=9.2, Technology, $1,200,000 🔥 TIER1
```

---

## Testing

### Test Capitol Trades Scraper:
```bash
cd jobs
python3 capitol_trades_scraper.py
```

### Test SEC 13F Parser:
```bash
cd jobs
python3 sec_13f_parser.py
```

### Test Multi-Signal Detector:
```python
# Create test file: test_multi_signal.py
import pandas as pd
from multi_signal_detector import MultiSignalDetector

# Create sample insider cluster
test_cluster = pd.DataFrame([{
    'ticker': 'AAPL',
    'cluster_count': 4,
    'total_value': 500000,
    'rank_score': 15.0
}])

detector = MultiSignalDetector("TestApp admin@example.com")
results = detector.run_full_scan(test_cluster, check_13f=False)

print(f"Tier 1: {len(results['tier1'])}")
print(f"Tier 2: {len(results['tier2'])}")
```

---

## Important Notes

### Capitol Trades Scraping:
- ⚠️ Web scraping may break if Capitol Trades changes their HTML structure
- ✅ Includes robust retry logic and error handling
- ✅ Rate limiting built-in to avoid getting blocked
- 💡 Consider caching results to avoid excessive requests

### SEC 13F Data:
- ⚠️ 13F filings have a 45-day lag (reported quarterly)
- ⚠️ You MUST provide a valid User-Agent for SEC requests
- ✅ Data is free and official from SEC.gov
- 💡 Full 13F parsing is complex - current implementation is simplified

### Performance:
- Politician scraping: ~10-30 seconds (5 pages)
- 13F checking: ~2-5 seconds per ticker (if enabled)
- Recommended: Enable politician scraping, disable 13F for faster runs

---

## Troubleshooting

### "Capitol Trades scraping failed"
- Capitol Trades may have changed their HTML structure
- Check if the website is accessible
- Increase retry attempts in scraper

### "SEC request blocked"
- Make sure you're providing a valid User-Agent
- Format: "CompanyName AdminEmail@example.com"
- SEC requires identifying yourself in requests

### "No multi-signal overlaps detected"
- This is normal - overlaps are rare but valuable
- Try increasing `POLITICIAN_LOOKBACK_DAYS`
- Check if politician scraper is finding data

---

## Future Enhancements

Potential additions you could implement:

1. **Short Interest Data**
   - Add FINRA short interest tracking
   - Detect potential short squeezes
   - Already has placeholder in code

2. **Email Templates**
   - Beautiful HTML email alerts
   - Tier-based formatting
   - Multi-signal highlights

3. **Historical Performance Tracking**
   - Track politician trade outcomes
   - Adjust weights based on historical accuracy
   - Fund performance tracking

4. **Options Flow Data**
   - Add unusual options activity
   - Smart money detection
   - Whale trades

---

## Support

For questions or issues:
1. Check the code comments in each module
2. Review the `TRAINING_GUIDE.md` for general pipeline info
3. Test individual modules before full integration

---

## Credits

These features integrate:
- OpenInsider (existing insider data)
- Capitol Trades (politician trading data)
- SEC EDGAR (institutional 13F filings)
- Your existing cluster detection logic

All data sources are **FREE** and **publicly available**! 🎉
