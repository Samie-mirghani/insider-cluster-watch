# Insider Cluster Watch

Automated pipeline to detect and score insider open-market buys (Form 4), generate daily HTML/plain-text email reports with ranked signals, simulate paper trading, execute live trades via Alpaca Markets, and track performance over time. Built as a DIY-first, low-cost stack: Python scripts + GitHub Actions scheduler + Gmail for email.

> **Repo owner:** Samie-Mirghani

---

## What This Does

- **Scrapes** recent insider filings from OpenInsider and SEC EDGAR (Form 4 data)
- **Filters** for meaningful open-market buys (ignores routine sales and option exercises)
- **Deduplicates** transactions to prevent double-counting from amended filings
- **Clusters** multiple insider buys within a time window to identify conviction
- **Scores** signals based on cluster size, dollar amounts, and insider roles (CEO/CFO weighted higher)
- **Enriches** with market data via yfinance (current price, 52-week low distance, volatility)
- **Multi-Signal Detection** - Combines insider trades with politician trades (Capitol Trades) and institutional holdings (SEC 13F) for confirmation
- **Politician-Only Signals** - Detects standalone high-conviction politician clusters (Tier 0) without requiring insider confirmation
- **Tiered Signals** - Classifies signals into 5 tiers based on confirmation count (Tier 0 = politician-only through Tier 4 = watch list)
- **Insider Performance Tracking** - Scores individual insiders by historical trade outcomes (Follow-the-Smart-Money)
- **Short Interest Analysis** - Identifies high short interest and potential squeeze setups
- **Sector Relative Analysis** - Detects contrarian and momentum sector opportunities
- **Detects** concerning insider selling patterns and adds warning banners to reports
- **Generates** daily HTML + plain-text email reports with ranked buy signals and multi-signal badges
- **Sends** urgent alerts when high-conviction clusters are detected (3+ insiders, $250k+)
- **Tracks** all signals in CSV for historical backtesting
- **Simulates** paper trading with score-weighted position sizing (5-12%), volatility-adjusted sizing, adaptive exposure, and dynamic stop losses
- **Executes** live trades via Alpaca Markets API with full risk management (optional, paper mode by default)
- **Backtests** signals automatically every Sunday to measure hit rate and alpha vs SPY
- **Reports** weekly performance summaries with advanced metrics (Sharpe ratio, max drawdown, win rate)
- **Serves** an interactive web dashboard for signal visualization
- **Runs** automatically on a daily schedule via GitHub Actions (weekdays at 7AM ET)

---

## Key Features

### 1. Buy Signal Clustering
Groups insider purchases by ticker within a 5-day window to identify coordinated buying (a strong bullish indicator).

### 2. Transaction Deduplication
Removes duplicate transactions that can occur from amended Form 4 filings, preventing inflated cluster counts and values.

### 3. Conviction Scoring
Weights purchases by:
- **Insider role** (CEO=3.0x, CFO=2.5x, President=2.0x, Director=1.5x, VP=1.2x, Officer=1.0x)
- **Dollar amount** (log-scaled to handle wide ranges)
- **Insider track record** (historical performance multiplier from 0.5x to 2.0x)

### 4. Sell Warning System
Automatically detects concerning selling patterns:
- C-suite executives selling
- Large sales (>$1M)
- Multiple insiders selling the same ticker

Adds a prominent warning banner to your daily emails when detected.

### 5. Paper Trading Simulation
Real-time portfolio simulation with:
- **Score-weighted position sizing** (5-12% based on signal score)
- **Volatility-adjusted sizing** (normalizes by ATR so high-vol stocks get smaller allocations)
- **Adaptive exposure** (50-62.5% based on win rate, pulls back during drawdowns)
- **Tiered stop losses** (6-12% based on signal tier)
- **Tiered take-profit targets** (12-24%, maintaining 2:1 R:R ratio)
- **Trailing stops** (8% trail triggered at +6% gain)
- **Dynamic stop tightening** (10% trail at +20%, 7% trail at +30%)
- **Scaling entries** (60% initial, 40% second tranche on -2% pullback)
- **Performance-based max hold** (21-45 days depending on P&L)
- **Realistic execution** (slippage modeling, opening price entries, sector concentration limits)
- **Max 10 concurrent positions**, $10k starting capital

### 6. Automated Live Trading (Alpaca Markets)
Optional production-ready live trading via Alpaca Markets API:
- Paper trading mode (default) with live trading option
- Score-weighted position sizing matching paper trading parameters
- Tier-based stop losses and take-profit targets with 2:1 R:R
- Intraday capital redeployment when positions are sold
- Market-cap-tiered limit order cushions (0.75-1.75%)
- Gap-down protection with market sell fallback
- Circuit breakers (5% daily loss halt, 15% drawdown halt, 5 consecutive loss pause)
- Full audit trail and reconciliation
- See [`automated_trading/README.md`](automated_trading/README.md) for details

### 7. Automated Performance Tracking
- Every night: Saves new signals to `data/signals_history.csv`
- Every Sunday: Runs backtest on historical signals
- Calculates: Hit rate, average return, alpha vs SPY (1-week and 1-month horizons)
- Generates: Performance charts and weekly email summaries

### 8. Urgent Alerts
Separate email sent when signals meet all criteria:
- 3+ insiders buying
- $250k+ total purchase value
- High conviction score (7.0+)
- Price within 15% of 52-week low

### 9. News Sentiment Analysis
Checks recent news for each signal to identify potential catalysts or red flags.

### 10. No-Activity Reports
When no significant signals are detected, sends a summary explaining why and showing transaction statistics.

### 11. Multi-Signal Detection
Enhances insider signals by checking for confirmation from other data sources:
- **Politician Trades:** Scrapes Capitol Trades for congressional trading activity (tracks 15+ high-performing politicians)
- **Automated Time-Decay System:** Intelligently handles retiring/retired politicians
  - Fully automated using Congress.gov API (zero manual work)
  - Active: Full weight | Retiring: 1.5x boost | Retired: Exponential decay (90-day half-life, 20% floor)
  - Preserves historical data for analysis
- **Institutional Holdings:** Validates with SEC 13F filings from 15 priority funds (Berkshire, Bridgewater, Renaissance Technologies, etc.)
- **Politician-Only Signals (Tier 0):** Standalone politician clusters without insider overlap
  - Requires 3+ politicians (vs 2 for multi-signal enhancement)
  - Quality gates: Bipartisan support OR high-conviction politician OR high aggregate value (>$150K)
  - Conservative sizing: 40% position (~2-3% of portfolio)
- **Tiered Classification:** Assigns signals to tiers based on confirmation count
  - **Tier 0** (politician-only): 40% positions, 8% stops, 16% take-profit
  - **Tier 1** (3+ signals): Full positions, 12% stops, 24% take-profit
  - **Tier 2** (2 signals): 75% positions, 10% stops, 20% take-profit
  - **Tier 3** (1 signal): 50% positions, 8% stops, 16% take-profit
  - **Tier 4** (watch list): 25% positions, 6% stops, 12% take-profit

### 12. Insider Performance Tracking (Follow-the-Smart-Money)
Tracks and scores individual insider performance over time:
- Analyzes 3+ years of historical trade outcomes
- Scores insiders 0-100 based on win rate, average return, and consistency
- Multiplies conviction score (0.5x for poor performers, up to 2.0x for top performers)
- Automatically queues and updates outcome data daily
- Requires minimum 3 trades for a reliable score

### 13. Short Interest Analysis
Identifies high short interest and squeeze potential:
- Tracks short interest percentage and days to cover
- Thresholds: 20%+ = high, 30%+ = very high
- Conviction boost (+1.0) for high short interest, additional +0.5 for squeeze setups
- Weekly cached data (short interest updates bi-monthly)

### 14. Sector Relative Analysis
Analyzes sector performance relative to SPY:
- Contrarian detection: Sector down 10-15%+ vs SPY = opportunity
- Momentum detection: Sector up 10-15%+ vs SPY = caution
- Conviction adjustments: +1.0 for contrarian setups, -0.5 for late momentum
- Sector concentration limits: 40% max in one sector
- FMP API integration for accurate industry classification

### 15. Intelligent Signal Detection Enhancements
Advanced filtering system that catches high-quality trades while maintaining signal standards:

**Mega-Cluster Exception** - Bypasses volume filters for rare, high-conviction clusters:
- Criteria: 3+ insiders AND $1M+ total AND $300k+ per insider
- Safeguards: Must still pass price, market cap, and other quality filters

**Dynamic Per-Insider Thresholds** - Scales minimum purchase requirements by cluster size:
- 7+ insiders: $30k per insider (requires $200k total)
- 4-6 insiders: $40k per insider (requires $150k total)
- 1-3 insiders: $50k per insider (baseline)

**Holiday Mode** - Automatically reduces all thresholds by 20% during slow trading periods:
- Year-End (Dec 20 - Jan 5), Thanksgiving (Nov 20 - Nov 30), Summer (Jul 1 - Aug 15), Tax Season (Apr 1 - Apr 20)

**Tiered Dollar Volume Thresholds** - Fair comparison across price ranges:
- 7+ insiders: $100k/day minimum
- 4-6 insiders: $150k/day minimum
- 1-3 insiders: $200k/day minimum

### 16. Web Dashboard
Interactive HTML dashboards for signal visualization and insider performance leaderboards:
- `index.html` - Dashboard homepage
- `dashboard.html` / `dashboard-v2.html` - Interactive signal and performance dashboards
- Public performance data export via `public_performance.json`

---

## Project Layout

```
insider-cluster-watch/
├── jobs/                                  # Core signal processing & reporting
│   ├── main.py                            # Main orchestration script
│   ├── fetch_openinsider.py               # Scrapes OpenInsider data
│   ├── fetch_sec_edgar.py                 # SEC EDGAR backup data source
│   ├── process_signals.py                 # Clustering, scoring, deduplication logic
│   ├── capitol_trades_scraper.py          # Politician trading API client (PoliticianTradeTracker)
│   ├── politician_tracker.py              # Time-decay weighting for retiring politicians
│   ├── automated_politician_checker.py    # Automated status updates via Congress.gov API
│   ├── sec_13f_parser.py                  # Institutional holdings parser (SEC 13F)
│   ├── multi_signal_detector.py           # Multi-signal detection engine
│   ├── paper_trading_multi_signal.py      # Enhanced paper trading with tiers
│   ├── paper_trade.py                     # Paper trading portfolio simulation
│   ├── paper_trade_monitor.py             # Portfolio monitoring and metrics
│   ├── insider_performance_tracker.py     # Individual insider score tracking
│   ├── insider_performance_auto_tracker.py # Continuous outcome tracking
│   ├── sector_analyzer.py                 # Sector-relative performance analysis
│   ├── short_interest_analyzer.py         # Short interest tracking and squeeze detection
│   ├── fmp_api.py                         # Financial Modeling Prep API client
│   ├── ticker_validator.py                # Ticker normalization and validation
│   ├── news_sentiment.py                  # News analysis for signals
│   ├── generate_report.py                 # Jinja2 template rendering
│   ├── send_email.py                      # Gmail SMTP email sender
│   ├── backtest.py                        # Performance backtesting (1w & 1m horizons)
│   ├── weekly_summary.py                  # Weekly performance report generation
│   ├── visualize.py                       # Generate performance charts
│   ├── validate_data_integrity.py         # Data validation and corruption detection
│   ├── generate_public_performance.py     # Public leaderboard data export
│   ├── export_public_insider_performance.py # Public insider performance data
│   └── config.py                          # Configuration settings
│
├── automated_trading/                     # Alpaca live trading integration (optional)
│   ├── config.py                          # Live trading parameters
│   ├── alpaca_client.py                   # Alpaca API wrapper
│   ├── execute_trades.py                  # Trade execution logic
│   ├── position_monitor.py                # Position monitoring and exit logic
│   ├── order_manager.py                   # Order lifecycle management
│   ├── signal_queue.py                    # Signal queue management
│   ├── reconciliation.py                  # Account reconciliation
│   ├── execution_metrics.py               # Trade metrics and PnL tracking
│   ├── alerts.py                          # Email alerts for trades
│   ├── utils.py                           # Shared utilities
│   ├── init_data_dir.py                   # Data directory initialization
│   ├── data/                              # Runtime data (audit logs, position state)
│   └── README.md                          # Alpaca setup and monitoring guide
│
├── templates/                             # Jinja2 email templates
│   ├── daily_report.html                  # Daily signal email
│   ├── urgent_alert.html                  # High-conviction alert email
│   ├── no_activity_report.html            # No-activity fallback report
│   └── weekly_performance.html            # Weekly summary template
│
├── .github/workflows/                     # GitHub Actions automation
│   ├── daily_job.yml                      # Daily signal generation (Mon-Fri 7AM ET)
│   ├── weekly_backtest.yml                # Weekly backtest (Sun 8AM ET)
│   ├── trading_morning.yml                # Alpaca morning execution (9:35 AM ET)
│   ├── trading_monitor.yml                # Alpaca position monitoring (every 5 min)
│   └── trading_eod.yml                    # Alpaca end-of-day summary (4:30 PM ET)
│
├── data/                                  # Persistent data storage
│   ├── signals_history.csv                # Historical signal tracking
│   ├── backtest_results.csv               # Backtest performance data
│   ├── paper_portfolio.json               # Paper trading portfolio state
│   ├── paper_trades.csv                   # Paper trading execution log
│   ├── paper_trading.log                  # Trading activity log
│   ├── insider_trades_history.csv         # Insider outcome tracking
│   ├── insider_profiles.json              # Insider performance scores
│   ├── insider_tracking_queue.json        # Pending outcome updates
│   ├── politician_registry.json           # Politician metadata and status
│   ├── politician_trades_cache.json       # Cached Capitol Trades data
│   ├── company_profiles_cache.json        # FMP company data cache
│   ├── approved_signals.json              # Approved signals for live trading
│   ├── api_rate_limit.json                # API call rate limiting
│   ├── fmp_analytics.json                 # FMP API usage analytics
│   └── plots/                             # Performance visualizations
│
├── docs/                                  # Documentation assets
│   ├── insider_performance_public.json    # Public performance data
│   └── assets/icons/                      # Hosted PNG icons for email templates
│
├── index.html                             # Dashboard homepage
├── dashboard.html                         # Interactive dashboard
├── dashboard-v2.html                      # Alternative dashboard view
├── public_performance.json                # Public leaderboard data
├── requirements.txt                       # Python dependencies
├── TRAINING_GUIDE.md                      # User training guide
├── .gitignore
└── README.md
```

---

## Prerequisites

- **Python 3.10+** (3.8+ may work but 3.10 recommended)
- **Git & GitHub account** (for automated workflows)
- **Gmail account** with app password for SMTP sending
- **RapidAPI key** for PoliticianTradeTracker (free tier: 100 calls/month)
- **(Optional)** Congress.gov API key for automated politician status updates (free, 5,000 requests/hour)
- **(Optional)** FMP API key for company profile and industry classification data
- **(Optional)** Alpaca Markets account for automated trading (free paper trading)
- **(Optional)** Local setup for testing before deploying to GitHub Actions

---

## Install & Run Locally

### 1. Clone the repository

```bash
git clone git@github.com:Samie-mirghani/insider-cluster-watch.git
cd insider-cluster-watch
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up environment variables

Create a `.env` file in the root directory:

```bash
# Required: Email delivery
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-16-char-app-password
RECIPIENT_EMAIL=your-email@gmail.com

# Required: Politician trade data
RAPIDAPI_KEY=your-rapidapi-key-here

# Optional: Automated politician status updates
CONGRESS_GOV_API_KEY=your-api-key-here

# Optional: Company profile data (industry classification, market cap)
FMP_API_KEY=your-fmp-api-key-here

# Optional: Alpaca automated trading
ALPACA_PAPER_API_KEY=your-alpaca-paper-key
ALPACA_PAPER_SECRET_KEY=your-alpaca-paper-secret
```

**Notes:**
- You need a [Gmail app password](https://support.google.com/accounts/answer/185833) (not your regular password)
- Get a free RapidAPI key at https://rapidapi.com/politician-trade-tracker1 (100 calls/month free)
- Get a free Congress.gov API key at https://api.congress.gov/sign-up/ (optional but recommended)
- Get a free FMP API key at https://financialmodelingprep.com/ (optional, enhances sector analysis)
- Get a free Alpaca account at https://alpaca.markets/ (optional, for automated trading)

### 4. Test the script locally

```bash
cd jobs
python main.py --test
```

This sends a test email and exits without saving to history.

### 5. Generate a fake urgent alert (optional)

```bash
python main.py --urgent-test
```

This creates a fake urgent signal with multiple insiders to test the urgent email template.

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GMAIL_USER` | Yes | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Yes | Gmail app-specific password |
| `RECIPIENT_EMAIL` | Yes | Email to receive reports |
| `RAPIDAPI_KEY` | Yes | RapidAPI key for politician trade data (100 calls/month free) |
| `CONGRESS_GOV_API_KEY` | No | Congress.gov API key for automated politician status updates (free) |
| `FMP_API_KEY` | No | Financial Modeling Prep API key for company profiles |
| `ALPACA_PAPER_API_KEY` | No | Alpaca paper trading API key |
| `ALPACA_PAPER_SECRET_KEY` | No | Alpaca paper trading secret key |
| `ALPACA_LIVE_API_KEY` | No | Alpaca live trading API key (use with caution) |
| `ALPACA_LIVE_SECRET_KEY` | No | Alpaca live trading secret key |

### Tuning Signal Parameters

Edit `jobs/process_signals.py` to adjust:

**Clustering window:**
```python
cluster_df = cluster_and_score(df, window_days=5, top_n=50)
# window_days: Days +/- trade date to look for clustering (default: 5)
# top_n: Max signals to include in daily report (default: 50)
```

**Signal detection enhancements (lines 31-70):**
```python
# Mega-Cluster Exception
MEGA_CLUSTER_MIN_INSIDERS = 3              # Min insiders for exception
MEGA_CLUSTER_MIN_TOTAL_VALUE = 1_000_000   # Min total $ (bypasses volume)
MEGA_CLUSTER_MIN_AVG_PER_INSIDER = 300_000 # Min avg/insider (conviction)

# Dynamic Thresholds
DYNAMIC_THRESHOLD_BASE = 50_000            # 1-3 insiders
DYNAMIC_THRESHOLD_MEDIUM = 40_000          # 4-6 insiders
DYNAMIC_THRESHOLD_LARGE = 30_000           # 7+ insiders

# Holiday Mode
HOLIDAY_THRESHOLD_REDUCTION = 0.20         # 20% reduction during slow periods

# Quality Filters
MIN_STOCK_PRICE = 2.0                      # No penny stocks
MAX_RECENT_DRAWDOWN = -0.40                # Avoid falling knives

# Tiered Dollar Volume Thresholds
DOLLAR_VOLUME_THRESHOLD_LARGE = 100_000    # 7+ insiders: $100k/day
DOLLAR_VOLUME_THRESHOLD_MEDIUM = 150_000   # 4-6 insiders: $150k/day
DOLLAR_VOLUME_THRESHOLD_SMALL = 200_000    # 1-3 insiders: $200k/day
```

**Paper trading settings (`jobs/config.py`):**
```python
# Portfolio
STARTING_CAPITAL = 10000                   # $10k starting capital
MAX_POSITION_PCT = 0.10                    # 10% max per position
MAX_POSITIONS = 10                         # Max concurrent positions
MAX_TOTAL_EXPOSURE = 0.70                  # 70% max exposure (static fallback)

# Score-Weighted Position Sizing
ENABLE_SCORE_WEIGHTED_SIZING = True
SCORE_WEIGHT_MIN_POSITION_PCT = 0.05       # 5% min (for score 6)
SCORE_WEIGHT_MAX_POSITION_PCT = 0.12       # 12% max (for score 20)

# Adaptive Exposure
ENABLE_ADAPTIVE_EXPOSURE = True
ADAPTIVE_EXPOSURE_MIN = 0.50               # 50% during drawdowns
ADAPTIVE_EXPOSURE_MAX = 0.625              # 62.5% when winning

# Risk Management
STOP_LOSS_PCT = 0.08                       # 8% initial stop loss
TAKE_PROFIT_PCT = 0.12                     # 12% profit target
TRAILING_STOP_PCT = 0.08                   # 8% trailing stop
TRAILING_TRIGGER_PCT = 0.06               # Activate trailing after +6% gain

# Scaling Entries
SCALING_INITIAL_PCT = 0.6                  # 60% first tranche
SCALING_SECOND_PCT = 0.4                   # 40% second tranche
SCALING_TRIGGER_PCT = 0.02                 # -2% pullback triggers second tranche

# Realistic Trading
TRADING_SLIPPAGE_PCT = 0.15               # 0.15% slippage modeling
USE_OPENING_PRICE_FOR_ENTRY = True         # Use next day's open price
```

**Multi-signal settings (`jobs/config.py`):**
```python
ENABLE_MULTI_SIGNAL = True                 # Enable multi-signal detection
ENABLE_POLITICIAN_SCRAPING = True          # Scrape Capitol Trades
ENABLE_13F_CHECKING = True                 # Check 13F filings

# Tiered position sizing (multiplier x base position)
MULTI_SIGNAL_POSITION_SIZES = {
    'tier0': 0.40,   # 40% - politician-only
    'tier1': 1.0,    # 100% - 3+ signals
    'tier2': 0.75,   # 75% - 2 signals
    'tier3': 0.50,   # 50% - 1 signal
    'tier4': 0.25    # 25% - watch list
}

# Tiered stop losses (wider for higher conviction)
MULTI_SIGNAL_STOP_LOSS = {
    'tier0': 0.08,   # 8% stop
    'tier1': 0.12,   # 12% stop
    'tier2': 0.10,   # 10% stop
    'tier3': 0.08,   # 8% stop
    'tier4': 0.06    # 6% stop
}

# Tiered take-profit (2:1 R:R ratio maintained)
MULTI_SIGNAL_TAKE_PROFIT = {
    'tier0': 0.16,   # 16% TP
    'tier1': 0.24,   # 24% TP
    'tier2': 0.20,   # 20% TP
    'tier3': 0.16,   # 16% TP
    'tier4': 0.12    # 12% TP
}
```

---

## GitHub Actions - Automated Workflows

### Setup GitHub Secrets

1. Go to your repo -> **Settings** -> **Secrets and variables** -> **Actions**
2. Add these secrets:
   - `GMAIL_USER` (required)
   - `GMAIL_APP_PASSWORD` (required)
   - `RECIPIENT_EMAIL` (required)
   - `RAPIDAPI_KEY` (required - for politician trade data)
   - `CONGRESS_GOV_API_KEY` (optional - for automated politician status updates)
   - `FMP_API_KEY` (optional - for company profile data)
   - `ALPACA_PAPER_API_KEY` (optional - for automated trading)
   - `ALPACA_PAPER_SECRET_KEY` (optional - for automated trading)

### Daily Signal Generation (Mon-Fri 7AM ET)

**File:** `.github/workflows/daily_job.yml`

- Validates data integrity
- Scrapes insider data from OpenInsider and SEC EDGAR
- Deduplicates transactions
- Generates buy signals with multi-signal detection
- Detects sell warnings
- Simulates paper trading execution
- Sends daily and urgent emails
- Updates insider performance tracking
- Commits updated data files to repo

**Manual trigger:** Actions tab -> Daily Insider Report -> Run workflow

### Weekly Backtest (Sunday 8AM ET)

**File:** `.github/workflows/weekly_backtest.yml`

- Reads historical signals from `signals_history.csv`
- Fetches actual stock returns (1-week and 1-month)
- Calculates hit rate and alpha vs SPY
- Generates performance visualizations
- Commits `backtest_results.csv` to repo

**Manual trigger:** Actions tab -> Weekly Backtest -> Run workflow

### Alpaca Trading Workflows (Optional)

**Morning Execution** (`.github/workflows/trading_morning.yml`):
- Runs at 9:35 AM ET weekdays
- Executes morning buy signals from approved signal queue

**Position Monitoring** (`.github/workflows/trading_monitor.yml`):
- Every 5 min during market hours (9:35 AM - 4:00 PM ET)
- Hourly after hours (4:30 PM - 8:30 PM ET)
- Monitors stop-losses, take-profits, trailing stops, and time-based exits

**End-of-Day Summary** (`.github/workflows/trading_eod.yml`):
- Runs at 4:30 PM ET weekdays
- Sends daily summary email with portfolio status, P&L, and circuit breaker status

---

## Email Report Types

### Daily Report
Shows all signals detected with:
- Ticker and company name
- Number of insiders buying (cluster count)
- Total purchase value
- Conviction and rank scores
- Multi-signal tier badges
- Current price and distance from 52-week low
- Short interest data and sector context
- Suggested action (Urgent / Watchlist / Monitor)

### Urgent Alert
Sent immediately when high-conviction signals are detected:
- Dynamic signal count
- Multiple signal cards with key metrics
- Red/urgent color scheme

### No Activity Report
Sent when no significant signals are found:
- Explains why no signals were generated
- Shows transaction statistics
- Confirms system is monitoring correctly

### Weekly Performance Summary
Comprehensive performance report including:
- Paper trading portfolio status
- Win rate and profit/loss metrics
- Risk-adjusted returns (Sharpe ratio)
- Maximum drawdown analysis
- Sector and pattern performance breakdown
- Top 3 and worst 3 performers

### Trading Alerts (Alpaca)
Real-time alerts for automated trading:
- Every trade execution (BUY/SELL)
- Circuit breaker triggers
- Reconciliation failures
- Intraday capital redeployment

---

## Backtesting & Performance

### Running Backtest Manually

```bash
python jobs/backtest.py
```

**Output example:**
```
=== Horizon: 1w ===
Signals tested: 25  Hit rate (pos return): 64.00%
Avg return: 2.30%   Avg alpha vs SPY: 0.85%

=== Horizon: 1m ===
Signals tested: 25  Hit rate (pos return): 58.00%
Avg return: 5.20%   Avg alpha vs SPY: 1.40%

Wrote backtest results to data/backtest_results.csv
```

### Generating Visualizations

```bash
python jobs/visualize.py
```

Creates:
- `data/plots/rolling_hit_rate_20.png` - Rolling 20-signal hit rate
- `data/plots/cumulative_alpha_1m.png` - Cumulative alpha vs SPY

### Monitoring Paper Trading

```bash
python jobs/test_paper_trading.py
```

Displays current portfolio status, performance metrics, and position details.

---

## Testing & Validation

### Local Testing Options

```bash
cd jobs

# Test with current data (sends email)
python main.py --test

# Test urgent alert template
python main.py --urgent-test

# Run without paper trading
python main.py --no-paper-trading

# Run backtest (requires history)
python backtest.py

# Generate performance charts
python visualize.py
```

### Verify GitHub Actions

1. **Check workflow runs:** Actions tab in GitHub
2. **View logs:** Click on any workflow run to see detailed logs
3. **Verify commits:** Check that data files are being updated daily
4. **Review emails:** Confirm daily and urgent emails are arriving

---

## Security & Operational Notes

### Security Best Practices

- **Never commit `.env` file** (it's in `.gitignore`)
- **Use GitHub Secrets** for credentials in Actions
- **Use Gmail app passwords**, not regular passwords
- **Review OpenInsider's robots.txt** and be respectful with scraping
- **Verify transactions on SEC.gov** for important signals
- **Never commit API keys** in source code

### Rate Limiting

**PoliticianTradeTracker API (RapidAPI):**
- Free tier: 100 calls/month (~3 calls/day)
- Built-in rate limiting and caching
- Auto-resets monthly
- Automatic fallback to 24-hour cache

**yfinance (Yahoo Finance):**
- Free but rate-limited
- Code includes 0.5-second delays between requests
- For production, consider paid alternatives (Alpha Vantage, Polygon.io)

**FMP API (Financial Modeling Prep):**
- Free tier available with rate limits
- 30-day cache for company profiles (industry rarely changes)
- Built-in analytics tracking for API usage

**OpenInsider:**
- Publicly available but be respectful
- Runs once daily (not aggressive)
- SEC EDGAR provides backup data source

**SEC EDGAR:**
- Required User-Agent header
- 30-second timeout with exponential backoff retry
- 72-hour cache for 13F filings

### Data Integrity

**Transaction Deduplication:**
- Automatically removes duplicate transactions from amended Form 4 filings
- Prevents inflated cluster counts and purchase values
- Logs when duplicates are detected and removed

**Data Validation:**
- `validate_data_integrity.py` checks for data corruption on every run
- Backup files maintained for critical data

**Data Tracking:**
- `signals_history.csv` - Signal tracking
- `backtest_results.csv` - Performance data
- `paper_portfolio.json` - Portfolio state
- `paper_trades.csv` - Trade execution log
- `insider_profiles.json` - Insider performance scores
- `audit_log.jsonl` - Alpaca trading audit trail (never delete)
- `.env` file - Credentials (excluded from git)

---

## How It Works (Technical Details)

### Signal Generation Pipeline

```
1. Validate data integrity
   |
2. Fetch data from OpenInsider + SEC EDGAR
   |
3. Parse and combine transaction data
   |
4. Filter for BUY transactions only
   |
5. Deduplicate transactions (prevent double-counting)
   |
6. Compute conviction scores (role x log(dollars) x insider_performance)
   |
7. Cluster by ticker (5-day window)
   |
8. Enrich with yfinance market data
   |
9. Multi-Signal Detection (if enabled)
   |-- Fetch politician trades via PoliticianTradeTracker API
   |-- Check SEC 13F for institutional holdings
   |-- Assign tier based on confirmation count
   |-- Boost rank score for multi-signal stocks
   |
10. Short interest analysis
   |
11. Sector relative analysis
   |
12. Check news sentiment
   |
13. Rank by composite score
   |
14. Simulate paper trading execution (tier-based sizing)
   |
15. Queue approved signals for Alpaca trading
   |
16. Generate HTML/text reports (with tier badges)
   |
17. Send emails via Gmail SMTP
   |
18. Save to signals_history.csv (with tier data)
   |
19. Update insider performance tracking queue
```

### Scoring Algorithm

**Conviction Score (per transaction):**
```python
conviction = log(1 + purchase_value) x role_weight x insider_performance_multiplier

Role weights:
- CEO: 3.0x
- CFO: 2.5x
- President: 2.0x
- Director: 1.5x
- VP: 1.2x
- Officer: 1.0x

Insider performance multiplier: 0.5x (poor) to 2.0x (top performer)
```

**Cluster Score (per ticker):**
```python
cluster_score = (num_insiders x 2.0) + (avg_conviction / 10.0)
```

**Urgent Criteria (all must be true):**
```
cluster_count >= 3
total_value >= $250,000
avg_conviction >= 7.0
price within 15% of 52-week low
```

### Position Sizing Algorithm

```python
# 1. Base size from signal score (linear interpolation)
base_size = interpolate(score, min=5%, max=12%, score_range=6-20)

# 2. Adjust for volatility (ATR-based)
vol_multiplier = target_atr / actual_atr  # 0.5x to 1.5x

# 3. Apply tier multiplier
tier_size = base_size * tier_multiplier  # 25% to 100%

# 4. Cap at max position and check exposure limit
final_size = min(tier_size * vol_multiplier, max_position_pct)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Language** | Python 3.10+ |
| **Data Processing** | pandas, numpy, scipy |
| **Market Data** | yfinance, FMP API |
| **Scraping** | BeautifulSoup4, requests, selenium |
| **String Matching** | rapidfuzz (ticker validation) |
| **Email** | Jinja2 templates, Gmail SMTP |
| **Trading** | Alpaca Markets API (optional) |
| **APIs** | RapidAPI (politician trades), Congress.gov (politician status), SEC EDGAR (Form 4, 13F) |
| **Scheduling** | GitHub Actions (no server required) |
| **Storage** | CSV, JSON files in `/data` directory |
| **Visualization** | matplotlib |
| **News** | feedparser (Google News RSS) |
| **Configuration** | python-dotenv |

---

## Expected Performance

Based on insider trading research and backtesting:

| Metric | Target | Notes |
|--------|--------|-------|
| **Hit Rate (1w)** | 55-65% | % of signals with positive return |
| **Hit Rate (1m)** | 50-60% | Longer horizon = more noise |
| **Avg Return (1w)** | 2-4% | Average gain per signal |
| **Avg Return (1m)** | 4-8% | Better returns over longer period |
| **Alpha vs SPY** | 0.5-2% | Outperformance vs market |
| **Sharpe Ratio** | 1.0-2.0 | Risk-adjusted returns |
| **Max Drawdown** | -10% to -15% | Portfolio downside |

**Reality check:** Not every signal wins. Expect 35-45% of signals to lose money. Success comes from:
- Larger winners than losers (2:1 R:R ratio across all tiers)
- Score-weighted position sizing (5-12% per signal)
- Tier-based stop losses (6-12%)
- Tiered take-profit targets (12-24%)
- Adaptive exposure that pulls back during drawdowns

---

## Roadmap

### Current Status
- Daily signal generation with deduplication
- Email reports with sell warnings and multi-signal badges
- Urgent alerts with dynamic counts
- Paper trading simulation with score-weighted and volatility-adjusted sizing
- Multi-signal detection (politician trades + institutional holdings)
- Tiered signal classification (Tier 0-4) with 2:1 R:R targets
- Insider performance tracking (Follow-the-Smart-Money scoring)
- Short interest analysis and squeeze detection
- Sector relative analysis with FMP API
- Weekly backtesting and performance summaries
- News sentiment analysis
- Performance tracking and visualization
- Automated live trading via Alpaca Markets
- Intraday capital redeployment
- Interactive web dashboard
- Data integrity validation

### Future Improvements
- [ ] Options flow data integration
- [ ] Enhanced pattern detection (CEO clusters, C-suite coordination)
- [ ] Mobile push notifications (Pushover, Telegram)
- [ ] Machine learning scoring model (vs. rule-based)
- [ ] 10b5-1 plan detection (filter routine sales)
- [ ] Options activity correlation

---

## Troubleshooting

### Email Not Sending

**Error:** `Missing GMAIL_USER / GMAIL_APP_PASSWORD`
- **Fix:** Set environment variables or GitHub secrets

**Error:** `Authentication failed`
- **Fix:** Use Gmail [app password](https://support.google.com/accounts/answer/185833), not regular password
- Ensure 2FA is enabled on your Google account

**Emails going to spam:**
- Mark first email as "Not Spam"
- Add sender to contacts

### No Signals Generated

**Issue:** "No clusters detected" every day
- **Cause:** Weekend, or only insider sales (no buys)
- **Fix:** Normal behavior. Insider buying is less frequent than you might expect.

**Issue:** Duplicate signals showing inflated counts
- **Fix:** Transaction deduplication is enabled by default
- Check logs for "Removed X duplicate transactions" message

### GitHub Actions Failing

**Error:** `push failed`
- **Fix:** Settings -> Actions -> General -> Workflow permissions -> "Read and write"

**Error:** `No history file`
- **Fix:** Run `main.py` for several days to build history first

### Automated Trading Issues

**Issue:** Trades not executing
- Check `TRADING_ENABLED` is not set to `false`
- Verify market hours (9:35 AM - 3:30 PM ET)
- Check circuit breaker not triggered
- Verify Alpaca API credentials in GitHub Secrets

**Issue:** Circuit breaker triggered
- Check `automated_trading/data/audit_log.jsonl` for details
- Reset manually: `echo "Investigated issue" > automated_trading/data/circuit_breaker_reset.flag`

---

## License & Disclaimer

### License
MIT License - Free to use, modify, and distribute.

### Important Disclaimers

**NOT FINANCIAL ADVICE**

This tool is for **educational and informational purposes only**. It is not financial advice.

- **Do your own research** before making any investment decisions
- **Past performance does not guarantee future results**
- **Insider buying is not a guarantee** of stock price appreciation
- **You can lose money** trading stocks

**Risk Warnings:**
- Insider buying can be wrong (insiders lose money too)
- Form 4 data can be incomplete or delayed
- Market conditions change rapidly
- Small/micro-cap stocks are more volatile
- Always use stop losses and proper position sizing

**Data Accuracy:**
- Data is scraped from public sources (OpenInsider, SEC EDGAR)
- No guarantee of accuracy or completeness
- Always verify important trades on SEC.gov
- Market data from yfinance may have delays

**No Liability:**
The creators and maintainers of this project assume no liability for any financial losses resulting from use of this tool.

---

## Additional Resources

### Learning About Insider Trading
- [SEC Insider Trading Overview](https://www.sec.gov/fast-answers/answersinsiderhtm.html)
- [Form 4 Filing Requirements](https://www.sec.gov/files/forms-3-4-5.pdf)
- [OpenInsider Website](http://openinsider.com)

### Technical Setup
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)
- [Alpaca Markets Documentation](https://alpaca.markets/docs/)
- [Python Virtual Environments](https://docs.python.org/3/tutorial/venv.html)

---

## Contact

- **GitHub Issues:** [Report bugs or request features](https://github.com/Samie-mirghani/insider-cluster-watch/issues)
- **Owner:** Samie-Mirghani

---

## Acknowledgments

Built with:
- [OpenInsider](http://openinsider.com) - Public Form 4 data aggregation
- [SEC EDGAR](https://www.sec.gov/edgar) - Official SEC filings
- [yfinance](https://github.com/ranaroussi/yfinance) - Market data API
- [Alpaca Markets](https://alpaca.markets) - Brokerage API for automated trading
- [Financial Modeling Prep](https://financialmodelingprep.com/) - Company profile data
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) - HTML parsing
- [Jinja2](https://jinja.palletsprojects.com/) - Email templating
- [GitHub Actions](https://github.com/features/actions) - Automation

---

**Last Updated:** February 2026
**Version:** 3.0.0

**Recent Updates:**
- Automated live trading via Alpaca Markets with full risk management
- Insider performance tracking (Follow-the-Smart-Money scoring)
- Short interest analysis and squeeze detection
- Sector relative analysis with FMP API integration
- Score-weighted and volatility-adjusted position sizing
- Adaptive exposure management (50-62.5% based on win rate)
- Tiered take-profit targets maintaining 2:1 R:R ratio
- Intraday capital redeployment for Alpaca trading
- Gap-down protection and market-cap-tiered limit orders
- Interactive web dashboard
- Data integrity validation

---

## Quick Start Checklist

- [ ] Clone repository
- [ ] Install dependencies (`pip install -r requirements.txt`)
- [ ] Create Gmail app password
- [ ] Set up `.env` file with credentials
- [ ] Test locally (`python jobs/main.py --test`)
- [ ] Test urgent alerts (`python jobs/main.py --urgent-test`)
- [ ] Set up GitHub Secrets
- [ ] Enable GitHub Actions workflow permissions (read and write)
- [ ] Wait 1 week for initial signal history to build
- [ ] Review first backtest results
- [ ] Monitor paper trading performance
- [ ] Review weekly performance summaries
- [ ] (Optional) Set up Alpaca paper trading
- [ ] (Optional) Monitor Alpaca for 2-4 weeks before considering live
