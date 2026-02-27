# Automated Trading Strategy Audit Report

**Date:** February 27, 2026
**System:** Insider Cluster Watch v2.2.0 — Alpaca Live Trading
**Auditor:** Quantitative Strategy Review
**Scope:** Full codebase audit of signal generation, position sizing, risk management, execution, and operational infrastructure

---

## Executive Summary

The system is a **multi-signal insider trading platform** that combines SEC Form 4 insider cluster detection with politician trades, institutional 13F holdings, and short interest data to generate tiered buy signals executed via Alpaca. The architecture is mature and well-engineered with strong operational safeguards.

**Overall Assessment: B+ (Strong Foundation, Targeted Improvements Needed)**

The capital management improvements are clearly working — adaptive exposure, score-weighted sizing, volatility normalization, and tiered stop/target structures are all sound. However, several quantitative gaps remain that, if addressed, would elevate this from a strong retail system to world-class.

---

## 1. POSITION SIZING — Score-Weighted + Volatility-Adjusted

### What's Working Well
- Score-weighted sizing (5%-12% range based on signal score 6-20) is a smart approach
- Volatility normalization via ATR (20-day lookback, 0.5x-1.5x multiplier) equalizes risk per position
- Min position floor at 3% prevents trivial allocations

### Issues Identified

#### ISSUE 1.1: Volatility Multiplier Can Push Position Above MAX_POSITION_PCT (Severity: MEDIUM)
**File:** `automated_trading/execute_trades.py:597-611`

The score-weighted sizing caps at `SCORE_WEIGHT_MAX_POSITION_PCT = 0.12` (12%), but the volatility multiplier (up to 1.5x) is applied *after* the score-based calculation. A signal scoring 20 on a low-volatility stock could get:
```
12% × 1.5 = 18% position
```
This exceeds `MAX_POSITION_PCT = 10%` and even the score-weighted max of 12%. There is no final clamp to `MAX_POSITION_PCT`.

**Recommendation:** Add a hard clamp after volatility adjustment:
```python
position_value = min(position_value, portfolio_value * MAX_POSITION_PCT)
```
Or better, define `ABSOLUTE_MAX_POSITION_PCT = 0.15` as a ceiling that can never be exceeded regardless of score or volatility.

#### ISSUE 1.2: No Correlation-Aware Sizing (Severity: LOW-MEDIUM)
Positions in the same sector are checked for concentration (40% sector cap), but there's no correlation-based size reduction. If you hold 3 tech stocks, the 4th tech stock should be sized smaller even if sector concentration is below 40%, because correlated drawdowns amplify portfolio risk.

**Recommendation:** Consider a sector-penalty multiplier: if sector already has 2+ positions, reduce new position sizing by 15-25%.

#### ISSUE 1.3: ATR Calculation Uses yfinance During Market Hours (Severity: LOW)
**File:** `automated_trading/execute_trades.py:527-561`

The `_calculate_atr_pct()` method downloads price history from yfinance for every signal during morning execution. If yfinance is slow or rate-limited, this could delay order submission during the critical 10:00 AM window.

**Recommendation:** Pre-compute ATR values during the 7:00 AM signal generation job and store them in `approved_signals.json`. The execution engine should only read cached values.

---

## 2. RISK MANAGEMENT — Stop Losses, Trailing Stops, Circuit Breakers

### What's Working Well
- Tiered stop losses (6-12% by conviction tier) with wider stops for higher conviction is textbook-correct
- Trailing stop activation at +6% with 8% trail width is reasonable for multi-week thesis trades
- Dynamic stop tightening for big winners (+20%: 10% trail, +30%: 7% trail) locks in gains
- Circuit breakers (5% daily loss, 5 consecutive losses, 15 trades/day) are well-calibrated
- Unrealized P&L now included in circuit breaker checks (critical fix correctly implemented)

### Issues Identified

#### ISSUE 2.1: Trailing Stop Ratchets Off Current Price, Not Highest Price (Severity: HIGH)
**File:** `automated_trading/position_monitor.py:819`

```python
new_stop = current_price * (1 - trailing_pct)
```

The trailing stop is calculated from `current_price`, but it should be calculated from `highest_price` (the intraday/historical high since entry). The code *does* track `highest_price` and updates it correctly (line 791-792), but then calculates the stop from `current_price` instead.

This matters because: if a stock hits $110 (new high), then retraces to $105, the trailing stop should be $110 × 0.92 = $101.20, not $105 × 0.92 = $96.60. The current code loses $4.60 per share of protection during pullbacks.

The "only raise stop, never lower" check on line 822 partially mitigates this, but only if the stop was already set at a higher level from a previous cycle when the price was at the high. Between monitoring cycles (5 min gap), the stock could peak and retrace without the stop being set at the peak level.

**Recommendation:** Change to:
```python
new_stop = pos['highest_price'] * (1 - trailing_pct)
```

#### ISSUE 2.2: Reward-to-Risk Ratio Exactly 2:1 at 33% Win Rate Is Breakeven (Severity: MEDIUM)
**File:** `automated_trading/config.py:113-120`

The take-profit targets are set to exactly 2:1 R:R with their corresponding stop losses. At a 33% win rate, the Kelly-neutral expected value is:
```
EV = (0.33 × 2R) - (0.67 × 1R) = 0.66R - 0.67R = -0.01R
```
This is essentially **breakeven before costs**. After slippage, partial fills, and the cushion on limit orders, the strategy is slightly negative at 33% WR.

The system's actual win rate matters enormously here. If your realized win rate is 40%+, this is fine. If it's closer to 33%, the current R:R barely clears the hurdle.

**Recommendation:** Either:
1. Widen take-profit targets to 2.5:1 R:R (e.g., tier4: 15% TP with 6% SL), or
2. Implement partial profit-taking: sell 50% at 1.5R, trail the rest. This locks in realized gains while letting runners run.

#### ISSUE 2.3: Time-Based Exits May Cut Winners Short (Severity: MEDIUM)
**File:** `automated_trading/config.py:135-139`

- `MAX_HOLD_STAGNANT_DAYS = 30` with `STAGNANT_THRESHOLD = 3%` exits positions that are +2.9% after 30 days
- `MAX_HOLD_EXTREME_DAYS = 45` with `EXTREME_EXCEPTION = 15%` exits positions at +14.9% after 45 days

Insider buying signals often have a 3-6 month horizon. Academic studies (e.g., Lakonishok & Lee, 2001) show the bulk of alpha from insider cluster buys materializes in months 2-6. A 45-day hard cap may be cutting off the highest-alpha period.

**Recommendation:**
- Increase `MAX_HOLD_EXTREME_DAYS` to 60-90 for tier1/tier2 signals
- Lower the stagnant threshold to 1.5% (positions barely above water at 30 days are more likely to mean-revert)
- Make time-based exits tier-dependent: high-conviction trades get more runway

#### ISSUE 2.4: Stop Loss Does Not Account for Earnings Dates (Severity: MEDIUM)
No earnings date awareness exists in the system. An 8% stop loss on a stock reporting earnings tomorrow could easily gap through the stop. Conversely, insider buying before earnings is often the strongest signal.

**Recommendation:**
- Flag positions with earnings within 5 trading days
- Options: (a) tighten stop to 4% pre-earnings, (b) exit before earnings if P&L is marginal, or (c) widen stop through earnings for high-conviction (tier1/tier2) signals
- At minimum, add earnings dates to the monitoring alerts

#### ISSUE 2.5: No Maximum Drawdown Tracking at Portfolio Level (Severity: MEDIUM)
**File:** `automated_trading/config.py:153`

`MAX_DRAWDOWN_HALT_PCT = 15%` is defined but the drawdown check in `check_circuit_breakers()` only checks daily P&L and consecutive losses — **not cumulative drawdown from peak portfolio value**. The config variable exists but is never enforced.

**Recommendation:** Track high-water mark of portfolio value and halt new entries when drawdown exceeds threshold:
```python
if (peak_portfolio_value - current_portfolio_value) / peak_portfolio_value > MAX_DRAWDOWN_HALT_PCT / 100:
    halt("Peak-to-trough drawdown exceeds limit")
```

---

## 3. SIGNAL GENERATION — Clustering, Scoring, Quality Filters

### What's Working Well
- 5-day clustering window is appropriate for insider filing delays
- Mega-cluster exception (3+ insiders, $1M+ total, $300K avg) correctly overrides volume filters
- Dynamic per-insider thresholds ($30K-$50K scaling by cluster size) reduce noise
- Holiday mode (20% threshold reduction) accounts for seasonal patterns
- Dollar volume thresholds (not share volume) are the correct approach for cross-price comparison
- Deduplication of amended Form 4 filings prevents double-counting
- Multi-source data (OpenInsider + SEC EDGAR fallback) provides redundancy

### Issues Identified

#### ISSUE 3.1: Conviction Score Uses log1p Without Normalization (Severity: LOW-MEDIUM)
**File:** `jobs/process_signals.py:681`

```python
def compute_conviction_score(value, role_weight):
    return math.log1p(max(value, 0)) * role_weight
```

This produces scores on an unbounded log scale. A $10M purchase by a CEO scores `log1p(10,000,000) × 3.0 = 48.3`, while a $50K purchase by a Director scores `log1p(50,000) × 1.5 = 16.2`. The 200x dollar difference only produces a 3x score difference, which may under-weight the extraordinary conviction of very large purchases.

**Recommendation:** Consider a piecewise or power-law scoring function that better discriminates at the high end:
```python
# Power-law with diminishing returns but better large-value sensitivity
score = (value / 100_000) ** 0.5 * role_weight  # Normalized to $100K baseline
```

#### ISSUE 3.2: No Sell-Side Signal Processing (Severity: MEDIUM)
The system only processes buy signals (`filter buys only`). While the strategy is long-only, insider selling is a valuable *negative* signal. If a company has heavy insider selling, it should disqualify or down-weight buy signals from that same company.

**Recommendation:** Track insider selling clusters and:
1. Flag tickers with net insider selling in the past 30 days
2. Down-weight buy signals where selling volume exceeds buying volume
3. Hard-reject signals where >3 insiders are selling while 1 is buying

#### ISSUE 3.3: 10% Owner Classification as "OFFICER" (Severity: LOW)
**File:** `jobs/process_signals.py:268`

10% owners (activist investors, PE firms) are classified as `OFFICER` with weight 1.0. These should have their own category. A 10% owner buying more shares is one of the strongest signals in the market — it's a concentrated bet by someone with board-level access.

**Recommendation:** Add a `10% OWNER` role with weight 2.5-3.0, comparable to CEO.

---

## 4. EXECUTION QUALITY — Order Management, Slippage, Fill Rates

### What's Working Well
- Market-cap-tiered limit order cushions (0.75% large, 1.25% mid, 1.75% small) are well-calibrated
- 30-minute delay after market open (10:00 AM execution) avoids opening volatility
- Idempotent order IDs prevent duplicate submissions
- Partial fill handling with 50% threshold
- Execution metrics tracking with slippage monitoring

### Issues Identified

#### ISSUE 4.1: Limit Orders Use DAY Time-in-Force Only (Severity: LOW-MEDIUM)
All buy orders expire at market close. If a stock opens +2% (above the cushion), the order never fills and the signal is lost. For high-conviction signals, this could miss the best opportunities — stocks gapping up on insider buying are often the strongest signals.

**Recommendation:** For tier1/tier2 signals, consider:
1. Using IOC (Immediate-or-Cancel) with a wider cushion, or
2. Implementing a two-tranche approach: 60% at limit, 40% at market if limit doesn't fill within 30 minutes
3. Monitoring unfilled orders and re-submitting with adjusted prices mid-day

#### ISSUE 4.2: Sell Orders Use Market Orders Exclusively (Severity: LOW)
**File:** `automated_trading/execute_trades.py:814`

All exits use `close_position()` which is a market order. For stop-loss triggers in illiquid names, this could result in significant slippage.

**Recommendation:** For positions in stocks with market cap < $2B, use limit sell orders with a small cushion (0.5-1% below current bid) to provide some price protection. Only fall back to market orders if the limit doesn't fill within the 5-minute monitoring cycle.

#### ISSUE 4.3: No VWAP or TWAP Execution for Larger Positions (Severity: LOW)
For a small account this is fine, but as the account scales, a single market order for the full position could move the price in small-cap names. Consider implementing TWAP (time-weighted average price) splitting for positions > $10K in stocks with < $1M daily dollar volume.

---

## 5. CAPITAL MANAGEMENT — Exposure, Redeployment, Adaptive Sizing

### What's Working Well
- Adaptive exposure (50%-62.5% based on win rate) is excellent — automatically de-risks during drawdowns
- The mathematical relationship between max exposure (62.5%) × trailing stop (8%) = 5% max loss is correctly maintained against the daily loss limit
- Intraday capital redeployment with safeguards (±3% price tolerance, 5/day max, 30 min before close cutoff)
- Score-weighted sizing allocates more capital to higher-conviction signals
- 30% cash buffer provides dry powder for opportunities

### Issues Identified

#### ISSUE 5.1: Adaptive Exposure Uses Last 100 Trades Without Time Weighting (Severity: MEDIUM)
**File:** `automated_trading/execute_trades.py:417-429`

The win rate calculation reads the last 100 `POSITION_CLOSED` events and computes a simple ratio. This treats a trade from 6 months ago the same as yesterday's trade. In a regime change (market shift from bull to bear), the exposure won't adapt quickly enough.

**Recommendation:** Apply exponential time-decay to the win rate calculation:
```python
# Weight recent trades more heavily
weight = exp(-days_since_close / 30)  # 30-day half-life
weighted_wins = sum(weight_i for winning trades)
weighted_total = sum(weight_i for all trades)
win_rate = weighted_wins / weighted_total
```

#### ISSUE 5.2: Cash Utilization Check Uses 95% of Cash (Severity: LOW)
**File:** `automated_trading/execute_trades.py:383`

```python
if position_value > cash * 0.95:
    return False, "Insufficient cash"
```

This leaves only a 5% buffer over the position value, which could result in the order being rejected by Alpaca due to buying power calculations that account for pending orders, regulatory requirements, or margin requirements. A tighter check against `buying_power` from the Alpaca API would be more reliable.

#### ISSUE 5.3: No Kelly Criterion or Optimal f Sizing (Severity: LOW)
The current sizing is score-based (5-12%) with volatility adjustment, which is practical. However, the system has enough historical data (audit log with win rates and average win/loss) to compute a Kelly fraction or fractional Kelly for optimal geometric growth.

**Recommendation:** As a long-term enhancement, compute Kelly fraction from historical data:
```
f* = (W/L × p - q) / (W/L)
# Where p = win rate, q = 1-p, W = avg win, L = avg loss
# Use 0.25 × f* (quarter Kelly) for safety
```
This could inform the adaptive exposure ceiling.

---

## 6. SIGNAL QUALITY & FILTERING

### What's Working Well
- 7-day cooldown after closing a position prevents churning
- Go-private detection (single insider >30% of market cap) prevents M&A traps
- Single-insider micro-cap filter ($500K minimum buy value) reduces noise
- Downtrend filter (price >3% below 5-day SMA) avoids catching falling knives
- Sector concentration limit (40%) prevents over-concentration

### Issues Identified

#### ISSUE 6.1: Downtrend Filter Uses Only 5-Day SMA (Severity: MEDIUM)
**File:** `automated_trading/execute_trades.py:314-328`

A 5-day SMA is extremely short-term and will filter out stocks in normal healthy pullbacks (which is often when insiders buy). A stock that dropped 4% in 3 days but is up 20% over 30 days would be rejected.

**Recommendation:** Use a multi-timeframe approach:
1. Short-term: Current price vs 5-day SMA (existing)
2. Medium-term: 20-day SMA slope (should be flat or positive)
3. Long-term: Current price vs 50-day SMA (should be above)

Only reject if the short-term AND medium-term signals are both negative (confirmed downtrend, not just a pullback).

#### ISSUE 6.2: No Earnings Surprise or Catalyst Filtering (Severity: LOW-MEDIUM)
Insiders sometimes buy after bad earnings (contrarian) or before good earnings (informed). The system should cross-reference signal timing with:
1. Recent earnings dates (was this purchase within 5 days of earnings?)
2. Recent price gaps (>5% gap in either direction)
3. News sentiment already exists (`news_sentiment.py`) but doesn't appear to be used as a hard filter

#### ISSUE 6.3: Signal Score Threshold of 6.0 May Be Too Low (Severity: LOW)
**File:** `automated_trading/config.py:79`

`MIN_SIGNAL_SCORE_THRESHOLD = 6.0` with scores ranging from 6-20+. If the score distribution is heavily left-skewed (most signals scoring 6-9), the threshold may not be discriminating enough.

**Recommendation:** Log the distribution of scores over time and set the threshold at the 40th percentile dynamically, or raise to 7.0-8.0 if the win rate on 6.0-7.0 scored signals is below 30%.

---

## 7. OPERATIONAL RESILIENCE

### What's Working Well
- GitHub Actions cron scheduling with 5 separate workflows is well-architected
- Broker sync on initialization ensures positions are always tracked after restarts
- Audit log backfill from Alpaca fills gaps when monitoring jobs miss events
- File locking on audit log prevents corruption from concurrent writes
- Circuit breaker state persists to disk and resets daily
- Manual circuit breaker reset via flag file is a good operational escape hatch

### Issues Identified

#### ISSUE 7.1: GitHub Actions Ephemeral Runners Lose State (Severity: MEDIUM)
Each GitHub Actions run gets a fresh environment. The system handles this via broker sync and exits_today persistence, but there's an inherent race condition: if the monitor job runs at 10:05 AM and the morning job hasn't committed its state changes yet, the monitor may not see the morning's orders.

**Recommendation:** Use Alpaca as the authoritative source of truth for all state, not local JSON files. The current broker sync approach is close to this but still relies on local files for signal history, stop levels, and tier assignments.

#### ISSUE 7.2: yfinance Dependency Is a Single Point of Failure (Severity: MEDIUM)
The system uses yfinance for:
1. ATR calculation (position sizing)
2. Current price lookups (exit checks)
3. Downtrend detection (signal validation)
4. 52-week range data

yfinance is an unofficial API that can break without warning. If it goes down during market hours, exit checks fall back to `last_known_price` which could be stale.

**Recommendation:**
1. Use Alpaca's market data API as primary for real-time prices (already partially done via `get_position()`)
2. Cache all yfinance data during the pre-market signal generation job
3. Consider adding a secondary data source (e.g., Alpha Vantage free tier) as fallback

#### ISSUE 7.3: No Heartbeat or Dead Man's Switch (Severity: LOW-MEDIUM)
If GitHub Actions silently fails (quota exceeded, credentials expired), there is no mechanism to detect that monitoring has stopped. Positions could go unmonitored for hours or days.

**Recommendation:** Implement a heartbeat check:
1. Each monitoring cycle writes a timestamp to a known location (e.g., GitHub Gist, S3, or the repo itself)
2. A separate lightweight health check (can be a simple cron or uptime monitor) alerts if the heartbeat is stale >15 minutes during market hours

---

## 8. BACKTESTING & PERFORMANCE TRACKING

### What's Working Well
- Weekly backtesting on 1-week and 1-month horizons
- Hit rate and alpha vs SPY tracking
- Sector-level performance breakdown
- Individual insider performance scoring with time-decay
- Execution metrics (slippage, fill rates) tracked per trade

### Issues Identified

#### ISSUE 8.1: No Out-of-Sample Walk-Forward Validation (Severity: MEDIUM)
The backtest uses historical signals and checks if they were profitable. This is in-sample validation. There's no walk-forward or out-of-sample testing framework to detect overfitting.

**Recommendation:** Implement a rolling walk-forward backtest:
1. Train signal parameters on months 1-6
2. Test on month 7
3. Roll forward: train on months 2-7, test on month 8
4. Report average OOS performance vs in-sample to detect overfitting

#### ISSUE 8.2: No Risk-Adjusted Performance Metrics Beyond Sharpe (Severity: LOW)
The system tracks win rate and Sharpe. World-class quant systems also track:
- **Sortino Ratio** (penalizes downside volatility only)
- **Calmar Ratio** (return / max drawdown)
- **Profit Factor** (gross profits / gross losses)
- **Expected Value per Trade** (average P&L per position)
- **Maximum Adverse Excursion (MAE)** — how far does a winning trade go against you before recovering?

MAE analysis is especially valuable: if most winning trades never draw down more than 4%, you could tighten stops from 8% to 5% without cutting winners.

---

## 9. STRUCTURAL & CODE QUALITY

#### ISSUE 9.1: Dual Config Files Create Sync Risk (Severity: LOW-MEDIUM)
`jobs/config.py` and `automated_trading/config.py` duplicate many parameters (stop losses, position sizing, tier definitions). Comments say "matches automated_trading/config.py" but there's no enforcement. If one is updated without the other, paper trading and live trading will diverge.

**Recommendation:** Create a shared `common_config.py` that both modules import, or have one module import from the other.

#### ISSUE 9.2: No Unit Tests for Critical Financial Logic (Severity: MEDIUM)
There are no unit tests for:
- Position sizing calculation
- Stop loss / trailing stop logic
- Circuit breaker triggering
- Conviction score computation
- Exposure calculations

These are the highest-risk code paths where a bug could directly cause financial loss.

**Recommendation:** Add targeted unit tests for all functions in `execute_trades.py`, `position_monitor.py`, and `config.py` that involve financial calculations. Aim for 100% branch coverage on these modules.

---

## 10. PRIORITY IMPROVEMENT ROADMAP

### Immediate (This Week) — High Impact, Low Effort
| # | Issue | Severity | Effort |
|---|-------|----------|--------|
| 1 | **2.1** Fix trailing stop to use `highest_price` | HIGH | 1 line change |
| 2 | **1.1** Clamp position size after volatility adjustment | MEDIUM | 3 lines |
| 3 | **2.5** Implement max drawdown tracking | MEDIUM | ~20 lines |

### Short-Term (Next 2 Weeks) — Strategic Improvements
| # | Issue | Severity | Effort |
|---|-------|----------|--------|
| 4 | **2.2** Partial profit-taking at 1.5R | MEDIUM | Moderate |
| 5 | **5.1** Time-weighted win rate for adaptive exposure | MEDIUM | Moderate |
| 6 | **6.1** Multi-timeframe downtrend filter | MEDIUM | Moderate |
| 7 | **2.4** Earnings date awareness | MEDIUM | Moderate |
| 8 | **3.2** Sell-side signal processing | MEDIUM | Moderate |

### Medium-Term (Next Month) — Platform Hardening
| # | Issue | Severity | Effort |
|---|-------|----------|--------|
| 9 | **9.2** Unit tests for financial calculations | MEDIUM | Large |
| 10 | **7.2** Reduce yfinance dependency | MEDIUM | Moderate |
| 11 | **7.3** Heartbeat monitoring | LOW-MED | Small |
| 12 | **8.1** Walk-forward backtest framework | MEDIUM | Large |
| 13 | **9.1** Unify config files | LOW-MED | Small |

### Long-Term (Quarterly) — World-Class Enhancements
| # | Issue | Severity | Effort |
|---|-------|----------|--------|
| 14 | **5.3** Kelly criterion sizing | LOW | Moderate |
| 15 | **8.2** MAE analysis + advanced risk metrics | LOW | Moderate |
| 16 | **1.2** Correlation-aware sizing | LOW-MED | Large |
| 17 | **2.3** Tier-dependent hold periods | MEDIUM | Moderate |

---

## Summary of Key Metrics to Track

To validate that improvements are working, track these weekly:

| Metric | Current Target | World-Class Target |
|--------|---------------|-------------------|
| Win Rate | >33% (breakeven) | >40% |
| Average Winner / Average Loser | 2.0:1 | 2.5:1+ |
| Profit Factor | >1.0 | >1.5 |
| Max Drawdown | <15% | <10% |
| Sharpe Ratio | >0.5 | >1.0 |
| Sortino Ratio | Not tracked | >1.5 |
| Average Slippage | <1% | <0.5% |
| Fill Rate | Not tracked | >85% |
| EV per Trade | Positive | >1% of position |

---

*This audit reflects the state of the codebase as of February 27, 2026. Re-audit recommended after implementing the immediate and short-term fixes.*
