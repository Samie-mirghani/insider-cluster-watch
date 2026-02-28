# Alpaca Automated Trading System

Production-ready automated trading system for executing insider trading signals via Alpaca Markets API. Integrates with the Insider Cluster Watch signal pipeline to automatically trade approved signals with full risk management, circuit breakers, and audit logging.

**Status**: Active (paper + live)
**Trading Mode**: Paper (default) / Live
**GitHub Actions**: Configured

---

## Quick Start

### GitHub Actions Setup (Recommended)

**Add these secrets** in GitHub repo Settings -> Secrets -> Actions:

```
ALPACA_PAPER_API_KEY=your-paper-api-key
ALPACA_PAPER_SECRET_KEY=your-paper-secret-key
```

For live trading (only after 2-4 weeks paper):
```
ALPACA_LIVE_API_KEY=your-live-api-key
ALPACA_LIVE_SECRET_KEY=your-live-secret-key
```

Email credentials (should already exist from main pipeline):
```
GMAIL_USER
GMAIL_APP_PASSWORD
RECIPIENT_EMAIL
```

**Workflows run automatically**:
- **Morning execution**: 9:35 AM ET weekdays
- **Position monitoring**: Every 5 min during market hours
- **End of day summary**: 4:30 PM ET weekdays

### Local Setup (Alternative)

Create a `.env` file in the project root:

```bash
ALPACA_PAPER_API_KEY=your-paper-api-key
ALPACA_PAPER_SECRET_KEY=your-paper-secret-key
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-password
RECIPIENT_EMAIL=your-email@gmail.com
```

---

## Architecture

```
Main Pipeline (jobs/)                    Automated Trading
┌──────────────────────┐                ┌──────────────────────┐
│ daily_job.yml        │                │ trading_morning.yml  │
│  - Fetch signals     │                │  - Read signal queue │
│  - Score & rank      │  approved      │  - Execute buys      │
│  - Paper trade sim   │──signals.json──│  - Set stop/TP       │
│  - Generate reports  │                │  - Send alerts       │
└──────────────────────┘                └──────────────────────┘
                                                  │
                                        ┌─────────┴──────────┐
                                        │ trading_monitor.yml │
                                        │  - Check positions  │
                                        │  - Stop-loss exits  │
                                        │  - Take-profit exits│
                                        │  - Trailing stops   │
                                        │  - Time-based exits │
                                        │  - Redeployment     │
                                        │  - Reconciliation   │
                                        └─────────┬──────────┘
                                                  │
                                        ┌─────────┴──────────┐
                                        │ trading_eod.yml    │
                                        │  - Daily summary   │
                                        │  - Portfolio status │
                                        │  - P&L report      │
                                        └────────────────────┘
```

---

## Trading Strategy

### Position Sizing (Score-Weighted)

**Uses signal score** to determine position size:

| Score | Position Size | Example |
|-------|--------------|---------|
| 6 (min) | 5% | $100 of $2,000 |
| 10 | ~7% | $140 of $2,000 |
| 15 | ~10% | $200 of $2,000 |
| 20 (max) | 12% | $240 of $2,000 |

**Why not tier-based?** Most signals are tier4/tier3. Tier-based sizing would reduce capital deployment unnecessarily. Signal score provides better granularity.

**Volatility adjustment:** Position sizes are further adjusted by ATR (Average True Range):
- High-volatility stocks: 0.5x size (smaller positions)
- Low-volatility stocks: 1.5x size (larger positions)
- Target: Normalize risk per position

### Stop Losses (Tier-Based)

**Uses tier** to determine stop width:

| Tier | Stop Loss | Take Profit | R:R Ratio | Rationale |
|------|-----------|-------------|-----------|-----------|
| **tier1** (3+ signals) | 12% | 24% | 2:1 | Widest - high conviction, more room |
| **tier2** (2 signals) | 10% | 20% | 2:1 | |
| **tier3** (1 signal) | 8% | 16% | 2:1 | |
| **tier4** (watch list) | 6% | 12% | 2:1 | Tightest - fail fast on lower conviction |

**Why wider stops for higher conviction?** Give best ideas room to work while cutting losses quickly on weaker signals. All tiers maintain a 2:1 reward-to-risk ratio, which is profitable at 33%+ win rate.

### Trailing Stops

- **Activation:** 8% trailing stop triggered after +6% gain
- **Big winner (+20%):** Tightens to 10% trailing stop
- **Huge winner (+30%):** Tightens to 7% trailing stop
- **Old position (21+ days, <10% gain):** 10% stop from high watermark

### Time-Based Exits

| Condition | Days | Action |
|-----------|------|--------|
| Losing money | 21 days | Exit |
| Barely positive (<3%) | 30 days | Exit |
| Any performance | 45 days | Exit (unless +15%) |

### Risk Management

| Limit | Value | Description |
|-------|-------|-------------|
| Max position | 10% | Single position cap |
| Max positions | 10 | Concurrent positions |
| Max exposure | 70% (static) | Total capital deployed fallback |
| Adaptive exposure | 50-62.5% | Dynamic based on win rate |
| Daily loss halt | 5% | Trading stops for the day |
| Daily loss warning | 2.5% | Warning alert |
| Consecutive losses | 5 | Pause 24 hours after 5 losers |
| Max drawdown halt | 15% | Halt new trades |
| Max drawdown warning | 10% | Warning alert |
| Sector concentration | 40% | Max in one sector |
| Daily trade limit | 15 | Max trades (buys + sells) per day |

### Adaptive Exposure

Dynamically scales maximum exposure based on recent win rate:
- Below 30% win rate -> 50% max exposure (pull back)
- Above 50% win rate -> 62.5% max exposure (deploy more)
- Linear interpolation between thresholds
- Requires 10+ completed trades before adapting
- Falls back to 70% static limit until enough data

**Safety math:** Max exposure (62.5%) x trailing stop (8%) = 5.0% worst-case portfolio hit, exactly matching the daily loss halt limit.

### Intraday Capital Redeployment

When a position is sold during market hours, freed capital can be deployed to queued signals:
- Price must be within 3% of original signal price
- No trading in last 30 minutes before close
- Max 5 redeployments per day
- Minimum $100 freed capital required
- Signal must be less than 24 hours old

### Order Execution

**Limit orders only** (no market orders) for price protection:
- Market-cap-tiered cushion above signal price:
  - Large cap (>$10B): 0.75% cushion
  - Mid cap ($2-10B): 1.25% cushion
  - Small cap (<$2B): 1.75% cushion
  - Unknown: 1.25% default
- Retry up to 3 times with exponential backoff (2s, 4s, 8s)
- Accept partial fills >= 50%, cancel below 50%
- Idempotent order IDs prevent duplicate orders
- Gap-down protection: Market sell if price gaps 2%+ below stop

---

## Module Overview

| File | Purpose |
|------|---------|
| `config.py` | All configuration parameters with validation |
| `alpaca_client.py` | Alpaca API wrapper (paper + live endpoints) |
| `execute_trades.py` | Trade execution logic with position sizing |
| `position_monitor.py` | Position monitoring, exits, trailing stops |
| `order_manager.py` | Order lifecycle (submit, track, cancel, partial fills) |
| `signal_queue.py` | Signal queue management and prioritization |
| `reconciliation.py` | Account reconciliation (every 15 min) |
| `execution_metrics.py` | Trade metrics, PnL tracking, performance stats |
| `alerts.py` | Email alerts for all trading events |
| `utils.py` | Shared utilities |
| `init_data_dir.py` | Data directory initialization |

---

## GitHub Actions Workflows

### 1. trading_morning.yml
- **When**: 9:35 AM ET weekdays
- **Does**: Execute morning buy signals from approved queue
- **Frequency**: Once per day

### 2. trading_monitor.yml
- **When**:
  - Every 5 min during market hours (9:35 AM - 4:00 PM ET)
  - Every hour after hours (4:30 PM - 8:30 PM ET)
  - Every 4 hours on weekends
- **Does**: Monitor positions, check exits, reconcile, redeploy capital
- **Frequency**: ~78 times per weekday

### 3. trading_eod.yml
- **When**: 4:30 PM ET weekdays
- **Does**: Daily summary email with full portfolio status
- **Frequency**: Once per day

---

## Configuration

### Key Settings (config.py)

```python
# Trading Mode
TRADING_MODE = 'paper'               # Change to 'live' for real money
TRADING_ENABLED = True               # Kill switch

# Position Sizing (Score-Weighted)
MAX_POSITION_PCT = 0.10              # 10% max per position
ENABLE_SCORE_WEIGHTED_SIZING = True
SCORE_WEIGHT_MIN_POSITION_PCT = 0.05 # 5% min (score 6)
SCORE_WEIGHT_MAX_POSITION_PCT = 0.12 # 12% max (score 20)

# Volatility-Adjusted Sizing
ENABLE_VOLATILITY_ADJUSTED_SIZING = True
VOLATILITY_TARGET_ATR_PCT = 2.0      # Target daily ATR %
VOLATILITY_SIZE_MIN_MULTIPLIER = 0.5 # 0.5x for high vol
VOLATILITY_SIZE_MAX_MULTIPLIER = 1.5 # 1.5x for low vol

# Adaptive Exposure
ENABLE_ADAPTIVE_EXPOSURE = True
ADAPTIVE_EXPOSURE_MIN = 0.50         # 50% during drawdowns
ADAPTIVE_EXPOSURE_MAX = 0.625        # 62.5% when winning

# Stop Losses (Tier-Based)
MULTI_SIGNAL_STOP_LOSS = {
    'tier1': 0.12,   # 12% (highest conviction)
    'tier2': 0.10,   # 10%
    'tier3': 0.08,   # 8%
    'tier4': 0.06    # 6% (lowest conviction)
}

# Take Profits (2:1 R:R)
MULTI_SIGNAL_TAKE_PROFIT = {
    'tier1': 0.24,   # 24%
    'tier2': 0.20,   # 20%
    'tier3': 0.16,   # 16%
    'tier4': 0.12    # 12%
}

# Risk Management
STOP_LOSS_PCT = 0.08                 # Default 8%
TAKE_PROFIT_PCT = 0.12              # Default 12%
TRAILING_STOP_PCT = 0.08            # 8% trail (was 5%)
TRAILING_TRIGGER_PCT = 0.06         # After +6% gain (was 3%)
DAILY_LOSS_LIMIT_PCT = 5.0          # 5% = HALT
MAX_CONSECUTIVE_LOSSES = 5          # Pause after 5
MAX_DRAWDOWN_HALT_PCT = 15.0        # Halt new trades

# Intraday Redeployment
ENABLE_INTRADAY_REDEPLOYMENT = True
REDEPLOYMENT_PRICE_TOLERANCE_PCT = 3.0
REDEPLOYMENT_MAX_PER_DAY = 5

# Order Execution
USE_LIMIT_ORDERS = True
LIMIT_ORDER_CUSHION_BY_CAP = {
    'large_cap': 0.75,              # Tight for liquid names
    'mid_cap': 1.25,                # Moderate
    'small_cap': 1.75               # Wide for thin books
}
GAP_DOWN_THRESHOLD_PCT = 2.0        # Market sell on gap-down

# Market Hours
EXECUTION_START_TIME = time(10, 0)  # 30 min after open
EXECUTION_END_TIME = time(15, 30)   # 30 min before close
```

---

## Safety Features

### Circuit Breakers

| Trigger | Action | Reset |
|---------|--------|-------|
| Daily loss > 5% | HALT all trading | Next trading day |
| 5 consecutive losses | PAUSE 24 hours | Automatic after 24h |
| Drawdown > 15% | HALT new trades | Manual / high-water mark recovery |

**Manual circuit breaker reset:**
```bash
echo "Investigated issue" > automated_trading/data/circuit_breaker_reset.flag
```
Next workflow run resets the circuit breaker.

### Order Safety

- Limit orders only (no market orders)
- Market-cap-tiered cushion (0.75-1.75% above signal price)
- Idempotent order IDs (prevent duplicate orders)
- Partial fill handling (accept >= 50%, cancel below)
- Gap-down protection (market sell if gaps 2%+ below stop)
- 15 trade/day limit to prevent overtrading

### Reconciliation

- Runs every 15 minutes during market hours
- Detects manual trades or unexpected position changes
- Alerts on discrepancies between internal state and broker
- Syncs entry dates and signal metadata on broker-side additions

---

## Monitoring & Alerts

### Email Alerts

Receive emails for:
- Every trade execution (BUY/SELL with price, size, reason)
- Circuit breaker triggers
- Reconciliation failures
- Intraday capital redeployments
- Daily summary (4:30 PM ET)

**Headers indicate mode**:
- **PAPER TRADING** (blue header)
- **LIVE TRADING** (orange header)

### Logs

- **GitHub Actions**: Actions -> Workflow run -> View logs
- **Audit trail**: `automated_trading/data/audit_log.jsonl`
- **Trading log**: `automated_trading/data/alpaca_trading.log`
- **Never delete audit log** - compliance record

### Data Files

| File | Purpose |
|------|---------|
| `data/live_positions.json` | Current open positions |
| `data/pending_orders.json` | Orders awaiting fill |
| `data/queued_signals.json` | Signals awaiting execution |
| `data/daily_state.json` | Daily P&L and circuit breaker state |
| `data/exits_today.json` | Positions closed today (for redeployment) |
| `data/audit_log.jsonl` | Full audit trail (append-only) |
| `data/trade_history.csv` | Historical trade log |
| `data/execution_metrics.json` | Performance metrics and PnL |
| `data/high_water_mark.json` | Portfolio high-water mark for drawdown |

---

## Emergency Controls

### Kill Switch

**Option 1**: Disable trading (keeps monitoring):
```yaml
# In GitHub Secrets or .env
TRADING_ENABLED: "false"
```

**Option 2**: Disable all workflows:
- Actions tab -> select workflow -> ... menu -> Disable

**Option 3**: Close all positions via Alpaca dashboard:
- https://app.alpaca.markets (paper)
- Close positions manually if system is unresponsive

---

## Going Live

**Only after 2-4 weeks of paper trading with validated results.**

1. Verify paper trading results:
   - Consistent execution pattern
   - Position sizing within expected ranges
   - Circuit breakers tested and working
   - Win rate and P&L tracking correctly
2. Add live API credentials to GitHub Secrets:
   - `ALPACA_LIVE_API_KEY`
   - `ALPACA_LIVE_SECRET_KEY`
3. Edit workflows: set `ALPACA_TRADING_MODE: live`
4. Start with small account ($500-1000)
5. Monitor closely for the first week
6. Check daily summary emails and Alpaca dashboard

---

## What to Expect (Paper Trading)

### Daily Activity

**Morning (9:35 AM ET)**:
- System checks for approved signals (score >= 6)
- Executes trades if signals exist and capital available
- Email: "BUY {ticker} {shares} @ ${price}"
- Position sizing: 5-12% based on score, adjusted for volatility

**During Market Hours (9:35 AM - 4:00 PM ET)**:
- Checks positions every 5 minutes
- Monitors stop-loss (tier-based: 6-12%)
- Monitors take-profit (tier-based: 12-24%)
- Updates trailing stops (8% trail after +6% gain)
- Checks time-based exits (21-45 days)
- Redeploys capital from closed positions to queued signals
- Email if exit: "SELL {ticker} - {reason}"

**End of Day (4:30 PM ET)**:
- Summary email with positions opened/closed, portfolio value, daily P&L, circuit breaker status

### Expected Trade Frequency

**Typical week (3-5 signals):**
- 2-4 trades opened
- 1-3 positions closed (stop/target/time)
- 3-7 emails per day (trades + summary)
- 30-50% win rate (normal)

### Success Indicators

**System working correctly if:**
- Trades execute at 9:35 AM when signals exist
- Position sizes 5-12% (score-weighted)
- Stops match tier (6-12%)
- Email alerts arrive for all events
- Positions appear in Alpaca paper account
- Daily summary is accurate
- Reconciliation reports no discrepancies

### Red Flags

**Immediate attention if:**
- Circuit breaker triggers unexpectedly
- Reconciliation failures
- All trades failing to execute
- Position sizes outside expected range
- No emails when trades execute
- Gap between internal state and Alpaca dashboard

---

## Troubleshooting

### Workflows Not Running
- Check workflows enabled in Actions tab
- Verify all secrets set correctly (API keys + email)
- Test with manual trigger

### Trades Not Executing
- Check `TRADING_ENABLED` is not set to `false`
- Verify market hours (execution window: 10:00 AM - 3:30 PM ET)
- Check circuit breaker not triggered (review daily_state.json)
- Verify sufficient buying power in Alpaca account
- Check signal queue has approved signals (queued_signals.json)

### No Email Alerts
- Check Gmail credentials in secrets
- Check spam folder
- Review workflow logs for email errors

### Unexpected Position Sizes
- Verify score-weighted sizing is enabled
- Check volatility adjustment multiplier in logs
- Confirm adaptive exposure limits

### Stale Data After Restart
- Run `python -m automated_trading.init_data_dir` to initialize data directory
- Check that `data/approved_signals.json` exists from main pipeline

---

## Support

- **Alpaca Docs**: https://alpaca.markets/docs/
- **Alpaca Status**: https://status.alpaca.markets/
- **Project Issues**: https://github.com/Samie-mirghani/insider-cluster-watch/issues

---

*Insider Cluster Watch - Automated Trading System v2.0*
*Updated: February 2026*
