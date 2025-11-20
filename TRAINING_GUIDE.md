# Training Guide: Using Insider Cluster Watch

> **A practical guide to understanding and using your automated insider trading signals**

---

## 📋 Table of Contents

1. [Understanding Your Emails](#understanding-your-emails)
2. [Signal Quality Assessment](#signal-quality-assessment)
3. [Validating Signals](#validating-signals)
4. [Paper Trading System](#paper-trading-system)
5. [Performance Monitoring](#performance-monitoring)
6. [Common Questions](#common-questions)

---

## Understanding Your Emails

You receive three types of automated emails from the system:

### 1. Daily Reports (Mon-Fri, 7:05 AM ET)

**When:** Every weekday morning before market open

**What's included:**
- All detected insider buying signals
- Sorted by rank score (highest conviction first)
- Sell warnings (when detected)
- Signal metrics and suggested actions

**Example signal:**
```
MTDR (Matador Resources)
  • Insiders: CEO, CFO, and 11 others (13 total)
  • Total Reported: $1,408,102
  • Conviction Score: 15.2 / 20
  • Rank Score: 30.97
  • Current Price: $37.94
  • 12.3% above 52-week low
  • Suggested Action: URGENT: Consider small entry
  • Rationale: Cluster count: 13 | Total buys: $1.4M |
              Near 52-week lows
```

**What to look for:**
- **Cluster count (insiders):** More = stronger signal
- **Total value:** Larger purchases = more conviction
- **Rank score:** Higher = better signal quality
- **Distance from 52w low:** Closer = better value entry
- **Suggested action:** System's recommendation

### 2. Urgent Alerts (As Needed)

**When:** Immediately when high-conviction signals are detected

**Criteria for urgent:**
- ≥3 insiders buying
- ≥$250k total purchase value
- High conviction score (≥7.0)
- Price within 15% of 52-week low

**What makes it urgent:**
These signals historically have higher hit rates and represent coordinated buying by multiple insiders, often including C-suite executives.

**Key differences from daily report:**
- Red/urgent color scheme
- Only shows signals meeting urgent criteria
- Sent immediately (not waiting for daily schedule)
- Warrants faster research and decision-making

### 3. Weekly Performance Summaries (Sundays, 9 AM ET)

**When:** Every Sunday morning

**What's included:**
- Paper trading portfolio status
- Win rate and profit/loss metrics
- Risk-adjusted returns (Sharpe ratio)
- Maximum drawdown
- Sector and pattern performance
- Top 3 and worst 3 performers
- Strategy assessment

**Why it matters:**
Helps you track whether the signals are actually working and identify patterns in what works best.

### 4. No Activity Reports (When Applicable)

**When:** On days with no significant signals

**What's included:**
- Explanation of why no signals were generated
- Transaction statistics (total analyzed, buy count)
- Confirmation system is monitoring correctly
- Optional sell warnings

**What it means:**
Not every day has actionable insider buying. This is normal and shows the system's filters are working correctly.

---

## Signal Quality Assessment

Not all signals are equal. Here's how to evaluate them:

### Signal Strength Tiers

**Excellent (Rank Score >10.0)**
- ✅ Priority signals - research first
- ✅ Multiple insiders (3+)
- ✅ High conviction scores
- ✅ Often includes C-suite
- ✅ Meaningful purchase amounts

**Good (Rank Score 7.0-10.0)**
- ✅ Trade if comfortable after research
- ✅ 2-3 insiders typically
- ✅ Solid conviction
- ✅ Worth investigating

**Okay (Rank Score 5.0-7.0)**
- ⚠️ Requires extra research
- ⚠️ Often 2 insiders or single large buy
- ⚠️ Lower conviction
- ⚠️ Consider skipping unless you have strong conviction

**Skip (Rank Score <5.0)**
- ❌ Low conviction
- ❌ Often single insider
- ❌ Small purchase amounts
- ❌ Better to wait for stronger signals

### Red Flags to Watch For

Even high-scoring signals can have issues:

**❌ Recent Negative News**
- Lawsuits announced
- Accounting scandals
- Major executive departures
- Bankruptcy concerns
- Regulatory issues

**❌ Downtrend on Chart**
- Falling knife pattern
- No support levels nearby
- High volume selling
- Bearish technical indicators

**❌ Sector Weakness**
- Entire sector under pressure
- Regulatory headwinds
- Macro factors working against industry

**❌ Timing Issues**
- Earnings tomorrow (high volatility risk)
- Major news event pending
- Market-wide selloff in progress

### Suggested Action Guide

The system provides action recommendations:

**"URGENT: Consider small entry"**
- Meets all urgent criteria
- Multiple insiders + high conviction
- Consider 2-4% position if comfortable
- Research quickly but thoroughly

**"Watchlist - consider small entry after confirmation"**
- Good signal quality (2+ insiders or high conviction)
- May want to wait for price confirmation
- Consider 2-3% position
- Take time to research properly

**"Monitor"**
- Lower conviction signal
- Single insider or smaller amounts
- Keep on radar but don't prioritize
- Consider skipping unless exceptional circumstances

---

## Validating Signals

Before acting on any signal, do quick research (10-15 minutes):

### Step 1: Check the Chart (2-3 minutes)

Use TradingView, Yahoo Finance, or your broker's charts:

**Questions to answer:**
- Is it in a clear downtrend? (More risky)
- Is it bouncing off support? (Good entry)
- Is it breaking out? (Don't chase)
- What's the recent volume trend?

**Green flags:**
- ✅ Bouncing off support level
- ✅ Sideways consolidation
- ✅ Low volume dip (quiet selling)
- ✅ Breaking above resistance

**Red flags:**
- ❌ Falling knife (steep decline)
- ❌ No clear support nearby
- ❌ High volume selloff
- ❌ Already extended/overbought

### Step 2: Google News Check (5 minutes)

Google: "[TICKER] news"

**Look through last 3-7 days of headlines:**

**Green flags:**
- ✅ Positive earnings
- ✅ New contracts/partnerships
- ✅ Analyst upgrades
- ✅ Product launches
- ✅ Quiet period (no major news)

**Red flags:**
- ❌ Lawsuits
- ❌ Accounting issues
- ❌ Executive departures
- ❌ Analyst downgrades
- ❌ Regulatory problems

### Step 3: Verify Insider Buying (Optional, 5 minutes)

Go to: https://www.sec.gov/cgi-bin/browse-edgar

**Steps:**
1. Company name: Enter ticker
2. Filing Type: "4" (Form 4 = insider transactions)
3. Look at recent filings
4. Verify: Open-market purchases (not option exercises)
5. Check: Match the dates and amounts in your email

**Why verify:**
- Confirms data accuracy
- Shows transaction details
- Identifies any unusual patterns
- Builds confidence in the signal

### Step 4: Quick Fundamentals (2 minutes)

Look up basic metrics on Yahoo Finance:

**Minimum checks:**
- Market cap: >$100M preferred (avoid micro-caps if new)
- Average volume: >500k shares/day (ensure liquidity)
- Price: >$2 (avoid penny stocks)

**Optional deeper dive:**
- Recent earnings trends
- Revenue growth
- Profit margins
- Debt levels

---

## Paper Trading System

Your system includes automated paper trading simulation:

### How It Works

**Automatic execution:**
1. Signal generated with rank score ≥5.0
2. System calculates position size (2% of portfolio)
3. "Buys" at current market price
4. Sets stop loss (-5%)
5. Sets take profit (+8%)
6. Tracks performance

**Position sizing:**
- Normal signals: 2% of portfolio
- Strong signals (>10.0): Up to 3%
- Maximum concurrent: 10 positions
- Starting capital: $10,000

**Exit strategy:**
- **Stop loss:** Triggers at -5% loss
- **Take profit:** Triggers at +8% gain
- **Time stop:** Evaluates after 3 weeks if no movement

**Scaling entries:**
- 50% initial position
- 25% added on +2% confirmation
- 25% added on +4% confirmation

### Tracking Performance

The paper trading system tracks:

**Portfolio metrics:**
- Current cash balance
- Active positions (tickers, entry prices, P&L)
- Pending orders (stops, take profits, scaling entries)
- Total portfolio value
- Overall return %

**Performance metrics:**
- Win rate (% profitable trades)
- Average winner vs average loser
- Profit factor (wins/losses ratio)
- Maximum drawdown
- Sharpe ratio (risk-adjusted returns)

**Trade history:**
- Entry/exit dates and prices
- Holding periods
- Profit/loss amounts
- Reasons for exit (stop/target/time)

### Interpreting Results

**After 4-8 weeks, evaluate:**

**Good signs:**
- ✅ Win rate >55%
- ✅ Average winner > average loser
- ✅ Positive total return
- ✅ Sharpe ratio >1.0
- ✅ Drawdown <15%

**Warning signs:**
- ❌ Win rate <45%
- ❌ Average loser > average winner
- ❌ Negative total return
- ❌ Sharpe ratio <0.5
- ❌ Drawdown >20%

**What to do if performance is poor:**
1. Review which signals are failing
2. Check if certain sectors underperform
3. Consider adjusting thresholds
4. Evaluate market conditions (bear market?)
5. Give it more time (minimum 8 weeks)

---

## Performance Monitoring

### Daily Monitoring (Optional)

**Time required:** 2-5 minutes

**What to check:**
- New signals in daily email
- Paper trading position updates
- Any stops or targets hit
- Overall portfolio status

**What NOT to do:**
- Don't obsessively check prices
- Don't manually interfere with paper trades
- Don't second-guess the system daily
- Don't panic on small losses

### Weekly Review (Recommended)

**Every Sunday morning:**

1. **Read weekly performance email**
   - Check overall win rate
   - Review top performers
   - Note worst performers
   - Read strategy assessment

2. **Analyze patterns**
   - Which sectors work best?
   - Which signal types win most?
   - What's the average holding period?
   - Are stops too tight or too loose?

3. **Adjust if needed**
   - Refine signal preferences
   - Update position sizing
   - Modify stop/target levels
   - Skip certain sectors

### Monthly Deep Dive (Highly Recommended)

**Once per month:**

1. **Calculate statistics**
   - Total return %
   - Win rate over month
   - Profit factor
   - Sharpe ratio

2. **Review backtest results**
   - Compare paper trading to backtest
   - Check if results are consistent
   - Identify divergences

3. **Identify improvements**
   - Best performing patterns
   - Worst performing patterns
   - Optimal holding periods
   - Sector preferences

4. **Update strategy**
   - Adjust parameters if needed
   - Document lessons learned
   - Set goals for next month

---

## Common Questions

### Q: Should I act on every signal?

**A:** No. Focus on signals with rank score >7.0 and do your own research. It's better to skip marginal signals than to take low-quality ones.

### Q: How many signals should I expect per week?

**A:** Varies widely. Expect:
- 0-5 signals on quiet days
- 5-15 signals on active days
- 1-2 urgent signals per week (on average)
- More activity during earnings seasons

### Q: Why so much activity recently?

**A:** Several factors can cause increased signal volume:
- Earnings season (insiders buying before results)
- Market volatility (insiders see value)
- Sector rotation (specific industries active)
- End of quarter (window for insider buying)

**System now includes deduplication** to prevent inflated counts from amended filings.

### Q: What if I see the same ticker multiple times in a week?

**A:** This is by design. If new insiders join the buying cluster, it generates a new signal. This indicates strengthening conviction.

**How to handle:**
- First signal: Do full research, consider entry
- Second signal (new insiders): Consider adding to position
- Third signal: Likely near peak, proceed cautiously

### Q: How do I know if the paper trading is accurate?

**A:** The paper trading uses:
- Real market prices (from yfinance)
- Realistic execution (assumes market orders)
- Conservative fills (uses worst-case scenarios)

It won't match live trading perfectly but provides good estimates.

### Q: Should I trust urgent alerts more than regular signals?

**A:** Urgent alerts have historically shown higher hit rates because they meet stricter criteria. However:
- Still do your research
- Higher conviction doesn't mean guaranteed
- Market conditions still matter
- Risk management still required

### Q: What if I disagree with the system's ranking?

**A:** Trust your research. The system provides data-driven signals, but you should:
- Use signals as starting points for research
- Apply your own analysis
- Skip signals you're not comfortable with
- Develop your own preferences over time

### Q: How do I handle sell warnings?

**A:** Sell warnings indicate concerning selling activity:
- **If you own the stock:** Consider your position carefully
- **If considering buying:** Proceed with extra caution
- **If it's a minor warning:** May not be significant
- **If it's a major warning (C-suite, large amounts):** Likely skip

### Q: When should I start real trading (if ever)?

**A:** Only after:
- ✅ 8+ weeks of paper trading
- ✅ Win rate >55% consistently
- ✅ Positive total returns
- ✅ You understand the system thoroughly
- ✅ You have capital you can afford to lose
- ✅ You've developed your research process

**Never:**
- ❌ Trade with money you can't afford to lose
- ❌ Skip the research process
- ❌ Oversize positions (>5%)
- ❌ Trade on margin initially
- ❌ Blindly follow every signal

### Q: How do I track my own performance if I'm trading live?

**A:** Create a simple spreadsheet with:
- Date, Ticker, Entry, Exit, Shares, P/L ($), P/L (%), Days Held
- Signal Score, Outcome (stop/target/time), Notes

Calculate monthly:
- Total trades
- Win rate
- Average winner/loser
- Total return
- Compare to paper trading

### Q: What if the system generates signals for stocks I can't trade?

**A:** Some signals may be for:
- OTC stocks (may require special approval)
- Foreign stocks (may need international trading)
- Low liquidity stocks (hard to enter/exit)

**Solution:** Skip these signals and focus on liquid, exchange-traded stocks with volume >500k shares/day.

### Q: How often should I check my email?

**A:** Recommended schedule:
- **Morning (7:30-9:00 AM ET):** Check daily email before market open
- **Occasional:** Check for urgent alerts (maybe 2-3x/week)
- **Sunday morning:** Read weekly performance summary
- **Avoid:** Constant checking throughout the day

### Q: What if I miss the morning email?

**A:** If you miss the 7:05 AM email:
- Don't chase gaps up at market open
- Wait for pullback or next day
- There will be more signals
- Better to miss one than enter poorly

### Q: How do I know if something is a bug vs. real activity?

**A:** With recent fixes:
- ✅ Deduplication prevents duplicate counting
- ✅ Dynamic counts show accurate numbers
- ✅ Re-signaling on new activity is intentional

**If you suspect a bug:**
1. Check recent commits/updates
2. Compare to SEC.gov directly
3. Review paper trading logs
4. Open an issue on GitHub

---

## Best Practices

### ✅ DO:

1. **Read daily emails before market open**
2. **Focus on high-quality signals (>7.0)**
3. **Do 10-15 minutes of research per signal**
4. **Monitor weekly performance summaries**
5. **Track patterns in what works**
6. **Trust the paper trading system**
7. **Be patient with results (8+ weeks)**
8. **Skip signals you're not comfortable with**

### ❌ DON'T:

1. **Don't follow every signal blindly**
2. **Don't skip the research process**
3. **Don't panic on small losses**
4. **Don't constantly check prices**
5. **Don't overtrade (quality > quantity)**
6. **Don't ignore sell warnings**
7. **Don't chase stocks that gap up**
8. **Don't second-guess stops after they trigger**

---

## Troubleshooting

### Issue: Too many signals to research

**Solution:**
- Focus only on rank score >8.0
- Skip signals in sectors you don't know
- Limit yourself to 2-3 new positions per week

### Issue: Emails going to spam

**Solution:**
- Mark first email as "Not Spam"
- Add sender to contacts
- Create Gmail filter to never send to spam

### Issue: Paper trading shows losses

**Solution:**
- Give it more time (minimum 8 weeks)
- Check if market conditions are poor (bear market)
- Review which types of signals are failing
- Consider adjusting parameters after sufficient data

### Issue: Urgent alerts seem too frequent

**Solution:**
- This can happen during earnings seasons or volatile periods
- System thresholds can be adjusted in `process_signals.py`
- More alerts = more market activity (not necessarily bad)
- Continue filtering by quality (rank score)

### Issue: Can't verify signals on SEC.gov

**Solution:**
- Filings can lag by 2-3 days
- Some filings may be amendments (duplicates now filtered)
- Check multiple insider names if unsure
- OpenInsider is usually accurate but verify important signals

---

## Next Steps

### Week 1-2: Learning Phase
- Read all daily emails
- Note which signals look interesting
- Don't take action yet
- Learn the patterns
- Get comfortable with the format

### Week 3-4: Research Phase
- Start researching high-quality signals
- Practice the 10-15 minute research process
- Compare your assessments to outcomes
- Build confidence in evaluation

### Week 5-8: Paper Trading Monitoring
- Actively monitor paper trading performance
- Track which signals work best
- Identify your preferences
- Develop your strategy

### Week 9+: Decide Next Steps
- Review 8+ weeks of paper trading results
- Decide if strategy is working
- Consider live trading with small positions (if confident)
- Continue refining your approach

---

## Additional Resources

**System Documentation:**
- README.md - Full system documentation
- GitHub Issues - Report bugs or request features
- Commit history - See recent changes and fixes

**External Resources:**
- [SEC EDGAR](https://www.sec.gov/edgar) - Verify Form 4 filings
- [OpenInsider](http://openinsider.com) - Browse insider activity
- [TradingView](https://www.tradingview.com) - Chart analysis
- [Yahoo Finance](https://finance.yahoo.com) - Quick fundamentals

**Best Practices:**
- Start small (paper trading first)
- Be patient (8+ weeks minimum)
- Do your research (10-15 min per signal)
- Track your results (spreadsheet or app)
- Learn continuously (identify patterns)

---

**Remember: This is a tool to help identify potential opportunities, not a guarantee of profits. Always do your own research, manage risk properly, and never invest more than you can afford to lose.**

---

*Last Updated: November 2025*
*Version: 2.0.0*

*This is educational content only. Not financial advice.*
