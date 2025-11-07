# Insider Cluster Watch

Automated pipeline to detect and score insider open-market buys (Form 4), generate daily HTML/plain-text email reports with ranked signals, simulate paper trading, and track performance over time. Built as a DIY-first, low-cost stack: Python scripts + GitHub Actions scheduler + Gmail for email.

> **Repo owner:** Samie-Mirghani

---

## 🎯 What This Does

- **Scrapes** recent insider filings from OpenInsider and SEC EDGAR (Form 4 data)
- **Filters** for meaningful open-market buys (ignores routine sales and option exercises)
- **Deduplicates** transactions to prevent double-counting from amended filings
- **Clusters** multiple insider buys within a time window to identify conviction
- **Scores** signals based on cluster size, dollar amounts, and insider roles (CEO/CFO weighted higher)
- **Enriches** with market data via yfinance (current price, 52-week low distance)
- **Detects** concerning insider selling patterns and adds warning banners to reports
- **Generates** daily HTML + plain-text email reports with ranked buy signals
- **Sends** urgent alerts when high-conviction clusters are detected (3+ insiders, $250k+)
- **Tracks** all signals in CSV for historical backtesting
- **Simulates** paper trading with automatic position sizing, stop losses, and take profits
- **Backtests** signals automatically every Sunday to measure hit rate and alpha vs SPY
- **Reports** weekly performance summaries with advanced metrics (Sharpe ratio, max drawdown, win rate)
- **Runs** automatically on a nightly schedule via GitHub Actions (weekdays at 7PM ET)

---

## 📊 Key Features

### 1. Buy Signal Clustering
Groups insider purchases by ticker within a 5-day window to identify coordinated buying (a strong bullish indicator).

### 2. Transaction Deduplication
Removes duplicate transactions that can occur from amended Form 4 filings, preventing inflated cluster counts and values.

### 3. Conviction Scoring
Weights purchases by:
- **Insider role** (CEO=3.0x, CFO=2.5x, Director=1.5x, etc.)
- **Dollar amount** (log-scaled to handle wide ranges)

### 4. Sell Warning System
Automatically detects concerning selling patterns:
- C-suite executives selling
- Large sales (>$1M)
- Multiple insiders selling the same ticker

Adds a prominent warning banner to your daily emails when detected.

### 5. Paper Trading Simulation
Real-time portfolio simulation with:
- Automatic position sizing (2-5% per signal)
- Stop losses (-5% to -7%)
- Take profit targets (+8% to +12%)
- Scaling entry strategy (50% initial, 25% on confirmation)
- Performance tracking and metrics

### 6. Automated Performance Tracking
- Every night: Saves new signals to `data/signals_history.csv`
- Every Sunday: Runs backtest on historical signals
- Calculates: Hit rate, average return, alpha vs SPY (1-week and 1-month horizons)
- Generates: Performance charts and weekly email summaries

### 7. Urgent Alerts
Separate email sent when signals meet all criteria:
- ≥3 insiders buying
- ≥$250k total purchase value
- High conviction score (≥7.0)
- Price within 15% of 52-week low

### 8. News Sentiment Analysis
Checks recent news for each signal to identify potential catalysts or red flags.

### 9. No-Activity Reports
When no significant signals are detected, sends a summary explaining why and showing transaction statistics.

---

## 📁 Project Layout

```
insider-cluster-watch/
├── jobs/
│   ├── main.py                   # Main orchestration script
│   ├── fetch_openinsider.py      # Scrapes OpenInsider data
│   ├── fetch_sec_edgar.py        # SEC EDGAR backup data source
│   ├── process_signals.py        # Clustering, scoring, deduplication logic
│   ├── generate_report.py        # Jinja2 template rendering
│   ├── send_email.py             # Gmail SMTP email sender
│   ├── paper_trade.py            # Paper trading portfolio simulation
│   ├── paper_trade_monitor.py    # Portfolio monitoring and metrics
│   ├── news_sentiment.py         # News analysis for signals
│   ├── backtest.py               # Performance backtesting (1w & 1m horizons)
│   ├── weekly_summary.py         # Weekly performance report generation
│   ├── visualize.py              # Generate performance charts
│   └── config.py                 # Configuration settings
├── templates/
│   ├── daily_report.html         # Daily email template
│   ├── urgent_alert.html         # Urgent alert template
│   ├── no_activity_report.html   # No-activity fallback report
│   └── weekly_performance.html   # Weekly summary template
├── .github/
│   └── workflows/
│       ├── nightly.yml           # Daily signal generation (Mon-Fri 7PM ET)
│       ├── weekly_backtest.yml   # Weekly backtest (Sun 8AM ET)
│       └── weekly_summary.yml    # Weekly performance report
├── data/
│   ├── signals_history.csv       # Historical signal tracking
│   ├── backtest_results.csv      # Backtest performance data
│   ├── paper_portfolio.json      # Paper trading portfolio state
│   ├── paper_trades.csv          # Paper trading execution log
│   └── plots/                    # Performance visualizations
├── requirements.txt
├── .gitignore
├── README.md
└── TRAINING_GUIDE.md
```

---

## 🔧 Prerequisites

- **Python 3.10+** (3.8+ may work but 3.10 recommended)
- **Git & GitHub account** (for automated workflows)
- **Gmail account** with app password for SMTP sending
- **(Optional)** Local setup for testing before deploying to GitHub Actions

---

## 🚀 Install & Run Locally

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
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-16-char-app-password
RECIPIENT_EMAIL=your-email@gmail.com
```

**Note:** You need a [Gmail app password](https://support.google.com/accounts/answer/185833) (not your regular password).

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

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GMAIL_USER` | Yes | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Yes | Gmail app-specific password |
| `RECIPIENT_EMAIL` | Yes | Email to receive reports |

### Tuning Signal Parameters

Edit `jobs/process_signals.py` to adjust:

**Clustering window:**
```python
cluster_df = cluster_and_score(df, window_days=5, top_n=50)
# window_days: Days ±trade date to look for clustering (default: 5)
# top_n: Max signals to include in daily report (default: 50)
```

**Urgent alert thresholds:**
```python
URGENT_THRESHOLDS = {
    'cluster_count': 3,        # Min insiders buying together
    'total_value': 250000.0,   # Min total $ purchased
    'has_c_suite': True,       # Require CEO/CFO involvement
    'pct_from_52wk_low': 15.0, # Max % above 52-week low
}
```

**Sell warning thresholds:**
```python
# In detect_heavy_selling() function in jobs/main.py
concerning = sells[
    (sells['is_c_suite'] == True) |   # C-suite selling
    (sells['value_calc'] > 1000000)   # >$1M sales
]
```

**Paper trading settings:**
```python
# In jobs/paper_trade.py
PORTFOLIO_CONFIG = {
    'starting_capital': 10000,        # Initial capital
    'position_size': 0.02,            # 2% per position
    'max_positions': 10,              # Max concurrent
    'stop_loss': 0.05,                # -5% stop
    'take_profit': 0.08,              # +8% target
}
```

---

## 🤖 GitHub Actions — Automated Workflows

### Setup GitHub Secrets

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Add these secrets:
   - `GMAIL_USER`
   - `GMAIL_APP_PASSWORD`
   - `RECIPIENT_EMAIL`

### Daily Signal Generation (Mon-Fri 7PM ET)

**File:** `.github/workflows/nightly.yml`

- Scrapes insider data from OpenInsider and SEC EDGAR
- Deduplicates transactions
- Generates buy signals
- Detects sell warnings
- Simulates paper trading execution
- Sends daily and urgent emails
- Commits updated data files to repo

**Manual trigger:** Actions tab → Daily Insider Report → Run workflow

### Weekly Backtest (Sunday 8AM ET)

**File:** `.github/workflows/weekly_backtest.yml`

- Reads historical signals from `signals_history.csv`
- Fetches actual stock returns (1-week and 1-month)
- Calculates hit rate and alpha vs SPY
- Generates performance visualizations
- Commits `backtest_results.csv` to repo

**Manual trigger:** Actions tab → Weekly Backtest → Run workflow

### Weekly Performance Summary (Sunday 9AM ET)

**File:** `.github/workflows/weekly_summary.yml`

- Analyzes paper trading performance
- Calculates advanced metrics (Sharpe ratio, max drawdown, win/loss ratio)
- Breaks down performance by sector and pattern
- Identifies top performers and worst performers
- Sends comprehensive weekly email report

**Manual trigger:** Actions tab → Weekly Performance Summary → Run workflow

---

## 📧 Email Report Examples

### Daily Report

Shows all signals detected with:
- Ticker and company name
- Number of insiders buying (cluster count)
- Total purchase value
- Conviction and rank scores
- Current price and distance from 52-week low
- Suggested action (Urgent / Watchlist / Monitor)
- Signal rationale

Includes sell warnings when concerning selling activity is detected.

### Urgent Alert

Sent immediately when high-conviction signals are detected:
- Dynamic signal count (shows actual number)
- Multiple signal cards with proper spacing
- No duplicate footers
- Current date (not hardcoded)
- Red/urgent color scheme
- Key metrics prominently displayed

### No Activity Report

Sent when no significant signals are found:
- Explains why no signals were generated
- Shows transaction statistics
- Confirms system is monitoring correctly
- Optional insider selling warnings

### Weekly Performance Summary

Comprehensive performance report including:
- Paper trading portfolio status
- Win rate and profit/loss metrics
- Risk-adjusted returns (Sharpe ratio)
- Maximum drawdown analysis
- Sector and pattern performance breakdown
- Top 3 and worst 3 performers
- Strategy assessment and recommendations

---

## 📈 Backtesting & Performance

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

## 🧪 Testing & Validation

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

# Check paper trading status
python test_paper_trading.py
```

### Verify GitHub Actions

1. **Check workflow runs:** Actions tab in GitHub
2. **View logs:** Click on any workflow run to see detailed logs
3. **Verify commits:** Check that data files are being updated daily
4. **Review emails:** Confirm daily and urgent emails are arriving

---

## 🔒 Security & Operational Notes

### Security Best Practices

- **Never commit `.env` file** (it's in `.gitignore`)
- **Use GitHub Secrets** for credentials in Actions
- **Use Gmail app passwords**, not regular passwords
- **Review OpenInsider's robots.txt** and be respectful with scraping
- **Verify transactions on SEC.gov** for important signals

### Rate Limiting

**yfinance (Yahoo Finance):**
- Free but rate-limited
- Code includes 0.5-second delays between requests
- For production, consider paid alternatives (Alpha Vantage, Polygon.io)

**OpenInsider:**
- Publicly available but be respectful
- Runs once daily (not aggressive)
- SEC EDGAR provides backup data source

### Data Integrity

**Transaction Deduplication:**
- Automatically removes duplicate transactions from amended Form 4 filings
- Prevents inflated cluster counts and purchase values
- Logs when duplicates are detected and removed

**Data Tracking:**
- ✅ `signals_history.csv` - Signal tracking
- ✅ `backtest_results.csv` - Performance data
- ✅ `paper_portfolio.json` - Portfolio state
- ✅ `paper_trades.csv` - Trade execution log
- ❌ `.env` file - Credentials (excluded)

---

## 🛣️ Roadmap

### Current Status
- ✅ Daily signal generation with deduplication
- ✅ Email reports with sell warnings
- ✅ Urgent alerts with dynamic counts
- ✅ Paper trading simulation
- ✅ Weekly backtesting
- ✅ Weekly performance summaries
- ✅ News sentiment analysis
- ✅ Performance tracking and visualization

### Near-Term Improvements
- [ ] Enhanced pattern detection (CEO clusters, C-suite coordination)
- [ ] Sector-specific scoring adjustments
- [ ] Improved news sentiment integration
- [ ] Mobile push notifications (Pushover, Telegram)
- [ ] Advanced technical indicators

### Long-Term Vision
- [ ] Machine learning scoring model (vs. rule-based)
- [ ] 10b5-1 plan detection (filter routine sales)
- [ ] Options activity correlation
- [ ] Live trading integration (Alpaca API)
- [ ] Web dashboard for signal visualization

---

## 📊 Expected Performance

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
- Larger winners than losers
- Proper position sizing (2-5% per signal)
- Using stop losses (-5% to -7%)
- Taking profits at targets (+8% to +12%)

---

## 🐛 Troubleshooting

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
- **Fix:** Transaction deduplication is now enabled (as of recent update)
- Check logs for "Removed X duplicate transactions" message

### GitHub Actions Failing

**Error:** `push failed`
- **Fix:** Settings → Actions → General → Workflow permissions → "Read and write"

**Error:** `No history file`
- **Fix:** Run `main.py` for several days to build history first

### Template Issues

**Issue:** Email shows hardcoded counts or dates
- **Fix:** Ensure you're using latest version of templates
- Check that `{{ variables }}` are properly rendering
- Run `python main.py --urgent-test` to verify

---

## 📚 How It Works (Technical Details)

### Signal Generation Pipeline

```
1. Fetch data from OpenInsider + SEC EDGAR
   ↓
2. Parse and combine transaction data
   ↓
3. Filter for BUY transactions only
   ↓
4. Deduplicate transactions (prevent double-counting)
   ↓
5. Compute conviction scores (role × log(dollars))
   ↓
6. Cluster by ticker (5-day window)
   ↓
7. Enrich with yfinance market data
   ↓
8. Check news sentiment
   ↓
9. Rank by composite score
   ↓
10. Simulate paper trading execution
   ↓
11. Generate HTML/text reports
   ↓
12. Send emails via Gmail SMTP
   ↓
13. Save to signals_history.csv
```

### Scoring Algorithm

**Conviction Score (per transaction):**
```python
conviction = log(1 + purchase_value) × role_weight

Role weights:
- CEO: 3.0x
- CFO: 2.5x
- President: 2.0x
- Director: 1.5x
- VP: 1.2x
- Officer: 1.0x
```

**Cluster Score (per ticker):**
```python
cluster_score = (num_insiders × 2.0) + (avg_conviction / 10.0)
```

**Urgent Criteria (all must be true):**
```python
✓ cluster_count >= 3
✓ total_value >= $250,000
✓ avg_conviction >= 7.0
✓ price within 15% of 52-week low
```

### Transaction Deduplication

**Purpose:** Prevents duplicate transactions from amended Form 4 filings from inflating cluster counts and values.

**Method:** Deduplicates on combination of:
- Ticker symbol
- Insider name
- Trade date
- Transaction type
- Quantity
- Price

**Implementation:** Applied in `process_signals.py` before clustering logic.

---

## ⚖️ License & Disclaimer

### License
MIT License - Free to use, modify, and distribute.

### Important Disclaimers

**⚠️ NOT FINANCIAL ADVICE**

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

## 📖 Additional Resources

### Learning About Insider Trading
- [SEC Insider Trading Overview](https://www.sec.gov/fast-answers/answersinsiderhtm.html)
- [Form 4 Filing Requirements](https://www.sec.gov/files/forms-3-4-5.pdf)
- [OpenInsider Website](http://openinsider.com)

### Technical Setup
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)
- [Python Virtual Environments](https://docs.python.org/3/tutorial/venv.html)

---

## 📞 Contact

- **GitHub Issues:** [Report bugs or request features](https://github.com/Samie-mirghani/insider-cluster-watch/issues)
- **Owner:** Samie-Mirghani

---

## 🙏 Acknowledgments

Built with:
- [OpenInsider](http://openinsider.com) - Public Form 4 data aggregation
- [SEC EDGAR](https://www.sec.gov/edgar) - Official SEC filings
- [yfinance](https://github.com/ranaroussi/yfinance) - Market data API
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) - HTML parsing
- [Jinja2](https://jinja.palletsprojects.com/) - Email templating
- [GitHub Actions](https://github.com/features/actions) - Automation

---

**Last Updated:** November 2025
**Version:** 2.0.0

---

## Quick Start Checklist

- [ ] Clone repository
- [ ] Install dependencies (`pip install -r requirements.txt`)
- [ ] Create Gmail app password
- [ ] Set up `.env` file with credentials
- [ ] Test locally (`python jobs/main.py --test`)
- [ ] Test urgent alerts (`python jobs/main.py --urgent-test`)
- [ ] Set up GitHub secrets
- [ ] Enable GitHub Actions workflow permissions (read and write)
- [ ] Wait 1 week for initial signal history to build
- [ ] Review first backtest results
- [ ] Monitor paper trading performance
- [ ] Review weekly performance summaries
- [ ] Track your personal results

**Good luck and trade safely! 🚀📈**
