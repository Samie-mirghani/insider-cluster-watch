# Insider Cluster Watch

Automated pipeline to detect and score insider open-market buys (Form 4), generate daily HTML/plain-text email reports with ranked signals, and track performance over time. Built as a DIY-first, low-cost stack: Python scripts + GitHub Actions scheduler + Gmail for email.

> **Repo owner:** Samie-Mirghani

---

## 🎯 What This Does

- **Scrapes** recent insider filings from OpenInsider (Form 4 data)
- **Filters** for meaningful open-market buys (ignores routine sales)
- **Clusters** multiple insider buys within a time window to identify conviction
- **Scores** signals based on cluster size, dollar amounts, and insider roles (CEO/CFO weighted higher)
- **Enriches** with market data via yfinance (current price, 52-week low distance)
- **Detects** concerning insider selling patterns and adds warning banners to reports
- **Generates** daily HTML + plain-text email reports with ranked buy signals
- **Sends** urgent alerts when high-conviction clusters are detected
- **Tracks** all signals in a CSV for historical backtesting
- **Backtests** signals automatically every Sunday to measure hit rate and alpha vs SPY
- **Runs** automatically on a nightly schedule via GitHub Actions (weekdays at 7PM ET)

---

## 📊 Key Features

### 1. **Buy Signal Clustering**
Groups insider purchases by ticker within a 5-day window to identify coordinated buying (a strong bullish indicator).

### 2. **Conviction Scoring**
Weights purchases by:
- **Insider role** (CEO=3.0x, CFO=2.5x, Director=1.5x, etc.)
- **Dollar amount** (log-scaled to handle wide ranges)

### 3. **Sell Warning System** ⚠️
Automatically detects concerning selling patterns:
- C-suite executives selling
- Large sales (>$1M)
- Multiple insiders selling the same ticker

Adds a prominent warning banner to your daily emails when detected.

### 4. **Automated Performance Tracking**
- Every night: Saves new signals to `data/signals_history.csv`
- Every Sunday: Runs backtest on historical signals
- Calculates: Hit rate, average return, alpha vs SPY (1-week and 1-month horizons)

### 5. **Urgent Alerts**
Separate email sent when signals meet all criteria:
- ≥3 insiders buying
- ≥$250k total purchase value
- High conviction score (≥7.0)
- Price within 15% of 52-week low

---

## 📁 Project Layout

```
insider-cluster-watch/
├── jobs/
│   ├── main.py                  # Main orchestration script
│   ├── fetch_openinsider.py     # Scrapes OpenInsider data
│   ├── process_signals.py       # Clustering, scoring, filtering logic
│   ├── generate_report.py       # Jinja2 template rendering
│   ├── send_email.py            # Gmail SMTP email sender
│   ├── backtest.py              # Performance backtesting (1w & 1m horizons)
│   └── visualize.py             # Generate performance charts
├── templates/
│   ├── daily_report.html        # Daily email template
│   └── urgent_alert.html        # Urgent alert template
├── .github/
│   └── workflows/
│       ├── nightly.yml          # Daily signal generation (Mon-Fri 7PM ET)
│       └── weekly_backtest.yml  # Weekly backtest (Sun 8AM ET)
├── data/
│   ├── signals_history.csv      # Historical signal tracking
│   ├── backtest_results.csv     # Backtest performance data
│   └── plots/                   # Performance visualizations
├── requirements.txt
├── .gitignore
└── README.md
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

---

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GMAIL_USER` | Yes | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Yes | Gmail app-specific password |
| `RECIPIENT_EMAIL` | Yes | Email to receive reports |
| `MARKET_DATA_API_KEY` | No | Not currently used (reserved for future paid API) |

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

---

## 🤖 GitHub Actions — Automated Workflows

### Setup GitHub Secrets

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Add these secrets:
   - `GMAIL_USER`
   - `GMAIL_APP_PASSWORD`
   - `RECIPIENT_EMAIL`

### Nightly Report (Mon-Fri 7PM ET)

**File:** `.github/workflows/nightly.yml`

- Scrapes insider data
- Generates buy signals
- Detects sell warnings
- Sends daily email
- Commits `signals_history.csv` to repo

**Manual trigger:** Actions tab → Daily Insider Report → Run workflow

### Weekly Backtest (Sunday 8AM ET)

**File:** `.github/workflows/weekly_backtest.yml`

- Reads historical signals from `signals_history.csv`
- Fetches actual stock returns (1-week and 1-month)
- Calculates hit rate and alpha vs SPY
- Commits `backtest_results.csv` to repo

**Manual trigger:** Actions tab → Weekly Backtest → Run workflow

---

## 📧 Email Report Format

### Daily Report Example

```
📈 Daily Insider Trade Report — November 14, 2025

⚠️ Insider Selling Alert
The following stocks show concerning insider selling activity:
  • SNAP: 3 insiders sold $4,200,000 (includes C-suite)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SOFI
  • Insiders: CEO Noto, CFO Lapointe, Director Smith
  • Cluster Score: 3
  • Conviction Score: 8.45
  • Total Reported: $450,000
  • Suggested Action: Watchlist - consider small entry after confirmation
  • Rationale: Cluster count:3 | Total reported buys: $450,000 | 
              Current Price: $9.25 | 8.5% above 52-week low | Rank Score: 9.22

NVDA
  • Insiders: Director Cohen, Director Williams
  • Cluster Score: 2
  • Conviction Score: 6.20
  • Total Reported: $280,000
  • Suggested Action: Monitor
  • Rationale: Cluster count:2 | Total reported buys: $280,000 | 
              Current Price: $142.50 | 12.3% above 52-week low | Rank Score: 5.82
```

### Urgent Alert Example

```
🚨 Urgent Insider Alert — November 14, 2025

High-conviction cluster buys detected.

PLTR
  • Insiders: CEO Karp, CFO Sankar, Director Thiel, Director Cohen
  • Cluster Score: 4
  • Conviction Score: 15.20
  • Total Reported: $1,200,000
  • Suggested Action: URGENT: Consider small entry at open / immediate review
  • Rationale: Cluster count:4 | Total reported buys: $1,200,000 | 
              Current Price: $25.50 | 8.2% above 52-week low | Rank Score: 14.52
```

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

---

## 🧪 Testing & Validation

### Local Testing

```bash
# Test with current data (sends email)
cd jobs
python main.py --test

# Test urgent alert template
python main.py --urgent-test

# Run backtest (requires history)
python backtest.py

# Generate performance charts
python visualize.py
```

### Verify GitHub Actions

1. **Check workflow runs:** Actions tab in GitHub
2. **View logs:** Click on any workflow run to see detailed logs
3. **Verify commits:** Check that `signals_history.csv` and `backtest_results.csv` are being updated

---

## 🔒 Security & Operational Notes

### Security Best Practices

- **Never commit `.env` file** (it's in `.gitignore`)
- **Use GitHub Secrets** for credentials in Actions
- **Use Gmail app passwords**, not regular passwords
- **Review OpenInsider's robots.txt** and be respectful with scraping

### Rate Limiting

**yfinance (Yahoo Finance):**
- Free but rate-limited
- Code includes 0.5-second delays between requests
- For production, consider paid alternatives (Alpha Vantage, Polygon.io)

**OpenInsider:**
- Publicly available but be respectful
- Runs once daily (not aggressive)
- Consider caching data to reduce requests

### Data Tracking

**What's tracked in git:**
- ✅ `signals_history.csv` - Signal tracking
- ✅ `backtest_results.csv` - Performance data
- ❌ `.env` file - Credentials (excluded)
- ❌ `data/plots/*.png` - Charts (optional, can be regenerated)

---

## 🛣️ Roadmap / Next Steps

### Phase 1: Current (Paper Trading)
- ✅ Daily signal generation
- ✅ Email reports with sell warnings
- ✅ Weekly backtesting
- ✅ Performance tracking

### Phase 2: Validation (Weeks 1-8)
- [ ] Collect 4-8 weeks of signal history
- [ ] Verify hit rate >55%
- [ ] Confirm alpha vs SPY is positive
- [ ] Fine-tune thresholds based on results

### Phase 3: Live Trading (Optional)
- [ ] Integrate with Alpaca or similar broker API
- [ ] Implement position sizing logic
- [ ] Add stop-loss and take-profit automation
- [ ] Paper trade for 4 more weeks before real money

### Future Enhancements
- [ ] Add 10b5-1 plan detection (filter routine sales)
- [ ] Implement ML scoring model (vs. rule-based)
- [ ] Add sector/industry clustering
- [ ] Support for options activity correlation
- [ ] Mobile push notifications (Pushover, Telegram)
- [ ] Web dashboard for visualizing signals

---

## 📊 Expected Performance

Based on insider trading research and initial testing:

| Metric | Target | Notes |
|--------|--------|-------|
| **Hit Rate (1w)** | 55-65% | % of signals with positive return |
| **Hit Rate (1m)** | 50-60% | Longer horizon = more noise |
| **Avg Return (1w)** | 2-4% | Average gain per signal |
| **Avg Return (1m)** | 4-8% | Better returns over longer period |
| **Alpha vs SPY** | 0.5-2% | Outperformance vs market |

**Reality check:** Not every signal wins. Expect 35-45% of signals to lose money. Success comes from:
- Larger winners than losers
- Proper position sizing (2-5% per signal)
- Using stop losses (-5% to -7%)
- Taking profits at targets (+8% to +12%)

---

## 💡 Trading Strategy Recommendations

### Position Sizing
```
Portfolio size: $10,000
Per-signal allocation: 3% = $300
Typical # of signals/week: 2-3
Max concurrent positions: 5-7
```

### Entry Strategy
1. **Receive email** before market open (7:05 AM)
2. **Quick research** (10-15 minutes)
   - Check chart for support/resistance
   - Google recent news
   - Verify Form 4 on SEC.gov (optional)
3. **Place limit order** slightly above current price
4. **Set stop loss** immediately after fill (-5%)
5. **Set take-profit** at target (+8-10%)

### Exit Strategy
- **Target hit:** Take profits automatically
- **Stop hit:** Accept small loss, move on
- **Time-based:** Exit after 3-4 weeks if no movement
- **News-driven:** Exit on negative fundamental news

### Risk Management
- **Max 5% per position**
- **Max 20% total in signals** (rest in index funds)
- **Never add to losing positions**
- **Always use stop losses**

---

## 🐛 Troubleshooting

### Email Not Sending

**Error:** `Missing GMAIL_USER / GMAIL_APP_PASSWORD`
- **Fix:** Set environment variables or GitHub secrets

**Error:** `Authentication failed`
- **Fix:** Use Gmail [app password](https://support.google.com/accounts/answer/185833), not regular password
- Ensure 2FA is enabled on your Google account

**Emails going to spam:**
- **Fix:** Mark first email as "Not Spam"
- Add sender to contacts
- Check Gmail filters

### No Signals Generated

**Issue:** "No clusters detected" every day
- **Cause:** Weekend, or only insider sales (no buys)
- **Fix:** Normal behavior. Wait for weekdays when insider buys occur.

**Issue:** Signals generated but not saved to history
- **Cause:** `.gitignore` blocking CSV files
- **Fix:** Remove `data/*.csv` from `.gitignore`

### Backtest Failing

**Error:** `No history file at data/signals_history.csv`
- **Cause:** No signals have been generated yet
- **Fix:** Run `main.py` for several days to build history first

**Error:** `No backtest results (no valid price series)`
- **Cause:** Tickers are invalid or delisted
- **Fix:** Normal for some signals. Backtest skips invalid tickers.

### GitHub Actions Failing

**Error:** `fatal: pathspec 'data/backtest_results.csv' did not match any files`
- **Cause:** `.gitignore` blocking CSV files, or no history to backtest
- **Fix:** 
  1. Update `.gitignore` to allow CSV files
  2. Ensure `signals_history.csv` exists with data
  3. Workflow will auto-fix once data exists

**Error:** `push failed`
- **Cause:** Workflow doesn't have write permissions
- **Fix:** Settings → Actions → General → Workflow permissions → Select "Read and write"

### yfinance Errors

**Error:** `Failed to fetch market data for TICKER`
- **Cause:** Yahoo Finance rate limiting or ticker invalid
- **Fix:** Code continues with missing data. Consider paid API for reliability.

---

## 📚 How It Works (Technical Details)

### Signal Generation Pipeline

```
1. OpenInsider Scraping
   ↓
2. Parse HTML table → DataFrame
   ↓
3. Filter for BUY transactions
   ↓
4. Compute conviction scores (role × log(dollars))
   ↓
5. Cluster by ticker (5-day window)
   ↓
6. Enrich with yfinance market data
   ↓
7. Rank by composite score
   ↓
8. Generate HTML/text report
   ↓
9. Send email via Gmail SMTP
   ↓
10. Save to signals_history.csv
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

### Sell Warning Criteria

Flags tickers where:
```python
(C-suite executive selling) OR
(Sale > $1M) OR
(Multiple insiders selling same ticker)

AND

(Multiple sellers OR Total sold > $2M OR C-suite involved)
```

---

## 🤝 Contributing

This is a personal project, but suggestions are welcome!

### To suggest improvements:
1. Open an issue with your idea
2. Describe the problem and proposed solution
3. Include example data if relevant

### Areas for contribution:
- Better scraping reliability
- Alternative data sources
- Improved scoring models
- Additional alert channels (SMS, Slack, etc.)
- Performance optimizations

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
- Data is scraped from public sources (OpenInsider)
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

### Trading Education
- [Position Sizing Guide](https://www.investopedia.com/terms/p/positionsizing.asp)
- [Stop Loss Strategies](https://www.investopedia.com/articles/stocks/09/use-stop-loss.asp)
- [Risk Management Basics](https://www.investopedia.com/terms/r/riskmanagement.asp)

### Technical Setup
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)
- [Python Virtual Environments](https://docs.python.org/3/tutorial/venv.html)

---

## 💬 Support & Questions

### Common Questions

**Q: How much money do I need to start?**  
A: Minimum $5,000-$10,000 to properly diversify across 3-5 signals with 2-3% position sizing.

**Q: What's a realistic return expectation?**  
A: 5-15% annually if strategy works. NOT a get-rich-quick scheme.

**Q: Should I follow every signal?**  
A: No. Do your own research. Skip signals you're not comfortable with.

**Q: What if I miss the morning email?**  
A: Set up phone notifications. If you miss it, wait for the next signal. Don't chase.

**Q: Can I paper trade first?**  
A: Absolutely! Track signals on paper for 4-8 weeks before risking real money.

**Q: How do I know if it's working?**  
A: Check the backtest results after 4+ weeks. Look for >55% hit rate and positive alpha.

**Q: What brokers work best?**  
A: Any broker works (Robinhood, Fidelity, Schwab, IBKR). Use whichever you prefer.

**Q: Should I use margin?**  
A: Not recommended for beginners. Master the strategy with cash first.

---

## 📞 Contact

- **GitHub Issues:** [Report bugs or request features](https://github.com/Samie-mirghani/insider-cluster-watch/issues)
- **Email:** Open an issue instead (keeps discussion public)
- **Owner:** Samie-Mirghani

---

## 🙏 Acknowledgments

Built with:
- [OpenInsider](http://openinsider.com) - Public Form 4 data aggregation
- [yfinance](https://github.com/ranaroussi/yfinance) - Market data API
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) - HTML parsing
- [Jinja2](https://jinja.palletsprojects.com/) - Email templating
- [GitHub Actions](https://github.com/features/actions) - Automation

---

**Last Updated:** October 2025  
**Version:** 1.0.0

---

## Quick Start Checklist

- [ ] Clone repository
- [ ] Install dependencies (`pip install -r requirements.txt`)
- [ ] Create Gmail app password
- [ ] Set up `.env` file with credentials
- [ ] Test locally (`python jobs/main.py --test`)
- [ ] Set up GitHub secrets
- [ ] Enable GitHub Actions
- [ ] Update `.gitignore` to allow CSV tracking
- [ ] Wait 1 week for initial signal history
- [ ] Review first backtest results
- [ ] Paper trade for 4-8 weeks
- [ ] Start with small position sizes (2-3%)
- [ ] Track your personal results
- [ ] Adjust strategy based on performance

**Good luck and trade safely! 🚀📈**
