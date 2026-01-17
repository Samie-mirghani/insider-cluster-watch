# Alpaca Automated Trading System

Production-ready automated trading system using Alpaca API for executing insider cluster signals.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Manual Setup Steps](#manual-setup-steps)
4. [Configuration](#configuration)
5. [Running the System](#running-the-system)
6. [Risk Management](#risk-management)
7. [Safety Features](#safety-features)
8. [Intraday Capital Redeployment](#intraday-capital-redeployment)
9. [Monitoring & Alerts](#monitoring--alerts)
10. [Scaling Up](#scaling-up)
11. [Risk Disclosure](#risk-disclosure)

---

## Overview

This system executes trades automatically based on insider cluster signals detected by the main pipeline. It's designed with safety-first principles:

- **Circuit breakers** halt trading if daily losses exceed thresholds
- **Position reconciliation** ensures local state matches broker
- **Idempotent orders** prevent duplicate submissions
- **Comprehensive audit logging** for compliance and debugging

### Key Features

| Feature | Description |
|---------|-------------|
| Daily Loss Limit | Halts trading if 5% daily loss (configurable) |
| Order Management | Tracks order states with idempotency |
| Trailing Stops | Dynamic stop tightening for winners |
| Intraday Redeployment | Deploy freed capital to queued signals |
| Email Alerts | Trade notifications matching existing styling |

---

## Architecture

```
Signal Pipeline (existing):
  fetch_openinsider → process_signals → cluster_and_score
                              ↓
                    approved_signals.json
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  AUTOMATED TRADING ENGINE                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  execute_trades.py (Morning - 9:35 AM ET)                  │
│  ├── Load approved_signals.json                            │
│  ├── Validate each signal                                  │
│  ├── Submit orders via Alpaca                              │
│  └── Queue signals that couldn't execute                   │
│                                                             │
│  execute_trades.py monitor (Every 5 min during market)     │
│  ├── Check pending order fills                             │
│  ├── Update trailing stops                                 │
│  ├── Check exit conditions (stops, targets, time)          │
│  ├── Execute sells as needed                               │
│  └── Redeploy freed capital if conditions met              │
│                                                             │
│  execute_trades.py eod (4:30 PM ET)                        │
│  ├── Send daily summary email                              │
│  └── Cleanup expired orders/signals                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### File Structure

```
automated_trading/
├── __init__.py              # Package initialization
├── config.py                # Configuration and circuit breakers
├── alpaca_client.py         # Alpaca API wrapper
├── order_manager.py         # Order state management
├── signal_queue.py          # Queued signals for redeployment
├── position_monitor.py      # Position tracking and exits
├── reconciliation.py        # Broker state sync
├── alerts.py                # Email notifications
├── execute_trades.py        # Main orchestration
├── utils.py                 # Utility functions
├── README.md                # This file
└── data/
    ├── live_positions.json  # Current positions
    ├── pending_orders.json  # Orders awaiting fill
    ├── queued_signals.json  # Signals waiting for capital
    ├── daily_state.json     # Circuit breaker state
    └── audit_log.jsonl      # Immutable audit trail
```

---

## Manual Setup Steps

### Step 1: Create Alpaca Account

1. Go to [Alpaca Markets](https://alpaca.markets/) and sign up
2. Complete identity verification (required for real trading)
3. Start with **Paper Trading** - this is critical for testing

### Step 2: Get API Keys

1. Log into Alpaca dashboard
2. Go to **Paper Trading** section
3. Generate API keys (Key ID and Secret Key)
4. **Important**: Paper and Live have SEPARATE keys

### Step 3: Set Environment Variables

Add to your `.env` file or export in your shell:

```bash
# Paper Trading (START HERE)
export ALPACA_PAPER_API_KEY="your-paper-key-id"
export ALPACA_PAPER_SECRET_KEY="your-paper-secret-key"

# Live Trading (only after testing!)
export ALPACA_LIVE_API_KEY="your-live-key-id"
export ALPACA_LIVE_SECRET_KEY="your-live-secret-key"

# Trading Mode (paper or live)
export ALPACA_TRADING_MODE="paper"

# Enable/disable trading (kill switch)
export TRADING_ENABLED="true"

# Email alerts (use existing Gmail credentials)
export GMAIL_USER="your-email@gmail.com"
export GMAIL_APP_PASSWORD="your-app-password"
export RECIPIENT_EMAIL="your-email@gmail.com"
```

### Step 4: Install Dependencies

```bash
pip install alpaca-py yfinance pytz
```

**Required packages**:
- `alpaca-py` - Alpaca trading API client
- `yfinance` - Yahoo Finance for backup price data
- `pytz` - Timezone handling for market hours

### Step 5: Initialize Data Directory

```bash
python automated_trading/init_data_dir.py
```

This creates all required data files:
- `live_positions.json` - Current positions
- `pending_orders.json` - Orders awaiting fill
- `queued_signals.json` - Signals waiting for capital
- `daily_state.json` - Circuit breaker state
- `audit_log.jsonl` - Immutable audit trail

### Step 6: Test Connection

```bash
cd insider-cluster-watch
python -c "from automated_trading.alpaca_client import create_alpaca_client; c = create_alpaca_client(); print(f'Connected! Portfolio: \${c.get_portfolio_value():,.2f}')"
```

### Step 7: Set Up Automation

#### Option A: GitHub Actions (Recommended)

GitHub Actions workflows are pre-configured and ready to use:

```bash
# See detailed setup instructions
cat automated_trading/GITHUB_ACTIONS_SETUP.md
```

The workflows will:
- Execute morning trades at 9:35 AM ET weekdays
- Monitor positions every 5 min during market hours
- Monitor hourly after hours and every 4 hours on weekends
- Send daily summary at 4:30 PM ET

**To enable**: Add GitHub Secrets (see `GITHUB_ACTIONS_SETUP.md`)

#### Option B: Local Cron Jobs

Add these to your crontab (`crontab -e`):

```cron
# Morning execution (9:35 AM ET = 14:35 UTC)
35 14 * * 1-5 cd /path/to/insider-cluster-watch && python -m automated_trading.execute_trades morning >> /path/to/logs/morning.log 2>&1

# Monitoring (every 5 min during market hours, 9:35 AM - 4:00 PM ET)
*/5 14-20 * * 1-5 cd /path/to/insider-cluster-watch && python -m automated_trading.execute_trades monitor >> /path/to/logs/monitor.log 2>&1

# End of day (4:30 PM ET = 21:30 UTC)
30 21 * * 1-5 cd /path/to/insider-cluster-watch && python -m automated_trading.execute_trades eod >> /path/to/logs/eod.log 2>&1
```

---

## Configuration

All configuration is in `config.py`. Key parameters:

### Position Sizing (Scalable)

```python
MAX_POSITION_PCT = 0.10      # 10% max per position
MAX_POSITIONS = 10           # Max concurrent positions
MAX_TOTAL_EXPOSURE = 0.70    # 70% max exposure (30% cash buffer)
```

### Circuit Breakers

```python
DAILY_LOSS_LIMIT_PCT = 5.0   # Halt trading if down 5% in a day
MAX_CONSECUTIVE_LOSSES = 5   # Pause after 5 consecutive losers
MAX_DRAWDOWN_HALT_PCT = 15.0 # Halt new trades if drawdown > 15%
```

For a $2,000 account:
- **Daily Loss Halt**: $100 loss
- **Warning Alert**: $50 loss

### Intraday Redeployment

```python
ENABLE_INTRADAY_REDEPLOYMENT = True
REDEPLOYMENT_PRICE_TOLERANCE_PCT = 3.0  # Price must be within ±3%
REDEPLOYMENT_MIN_TIME_BEFORE_CLOSE = 30  # Minutes before close
REDEPLOYMENT_MAX_PER_DAY = 1  # Max 1 redeployment per day
```

---

## Running the System

### Test Mode (Recommended First)

```bash
# Check connection and account
python -m automated_trading.execute_trades status

# Dry run - see what would execute
TRADING_ENABLED=false python -m automated_trading.execute_trades morning
```

### Production Mode

```bash
# Morning execution
python -m automated_trading.execute_trades morning

# Monitoring cycle
python -m automated_trading.execute_trades monitor

# End of day summary
python -m automated_trading.execute_trades eod
```

### Kill Switch

To immediately halt all trading:

```bash
export TRADING_ENABLED="false"
```

Or create a `.trading_disabled` file in the project root.

---

## Risk Management

### Stop Losses

| Signal Tier | Stop Loss |
|-------------|-----------|
| Tier 1 (3+ signals) | -12% |
| Tier 2 (2 signals) | -10% |
| Tier 3 (1 signal) | -8% |
| Default | -8% |

### Trailing Stops

| Gain Level | Trailing Stop |
|------------|---------------|
| +3% | Enable 5% trailing |
| +20% | Tighten to 10% |
| +30% | Tighten to 7% |

### Time-Based Exits

| Condition | Action |
|-----------|--------|
| 21 days + losing | EXIT |
| 30 days + < 3% gain | EXIT |
| 45 days + < 15% gain | EXIT |
| 45 days + > 15% gain | HOLD (winner exception) |

---

## Safety Features

### 1. Circuit Breakers

The system automatically halts trading when:
- Daily loss exceeds 5% of portfolio
- 5 consecutive losing trades
- Maximum drawdown exceeded

When halted:
- New positions are blocked
- Existing position monitoring continues
- Stop losses still trigger
- Alert email sent immediately

### 2. Position Reconciliation

Every monitoring cycle compares local state with Alpaca:
- Detects positions added/removed externally
- Alerts on quantity mismatches
- Does NOT auto-fix (requires manual review)

### 3. Idempotent Orders

Each order has a unique client ID:
- Format: `{TICKER}-{ACTION}-{YYYYMMDD}-{HHMMSS}-{HASH}`
- Prevents duplicate orders on restart
- Enables order tracking across sessions

### 4. Audit Trail

All actions logged to `audit_log.jsonl`:
- Order submissions
- Fills and rejections
- Circuit breaker triggers
- Reconciliation results

**Never delete the audit log.**

---

## Intraday Capital Redeployment

### How It Works

When a position is sold during market hours:

1. System checks if redeployment is allowed
2. Validates queued signals (price within ±3%, time before close)
3. Selects highest-scoring eligible signal
4. Executes buy if all conditions met

### Safeguards

| Check | Requirement |
|-------|-------------|
| Price Tolerance | Within ±3% of original signal price |
| Time | At least 30 min before market close |
| Daily Limit | Max 1 redeployment per day |
| Minimum Capital | At least $100 freed |

### Answering Your Hypothetical

> "If we have 4 signals flagged for a day, and over the course of the day we sell one of our positions for any reason. Should we be able to move liquid capital into that signal during market hours?"

**Yes, with safeguards:**

1. Signals that couldn't execute (insufficient capital, max positions) are queued
2. When capital is freed (position sold), the system:
   - Checks if the signal is still valid (price hasn't moved >3%)
   - Ensures sufficient time before close (30+ min)
   - Executes if all conditions met
3. Limited to 1 redeployment per day (conservative start)
4. Tracked separately for performance analysis

This is **optional** and can be disabled:
```python
ENABLE_INTRADAY_REDEPLOYMENT = False
```

---

## Monitoring & Alerts

### Alert Types

| Level | Trigger | Delivery |
|-------|---------|----------|
| CRITICAL | Circuit breaker, system error | Email (immediate) |
| WARNING | Reconciliation fail, large loss | Email |
| INFO | Trade executed, daily summary | Email |

### Email Styling

Alerts match your existing email theme with one distinction:
- **Paper Trading**: Blue header banner (🧪 PAPER TRADING)
- **Live Trading**: Orange header banner (💰 LIVE TRADING)

This provides a subtle but clear indication of which mode generated the alert.

---

## Scaling Up

### Phase 1: Paper Trading (2-4 weeks)

1. Start with Alpaca paper account
2. Run parallel with existing paper trading
3. Compare results daily
4. Target: 95%+ matching execution

### Phase 2: Small Live Test ($500-1000, 2 weeks)

```python
# Ultra-conservative limits
MAX_POSITIONS = 2
MAX_POSITION_PCT = 0.10  # $50-100 per position
DAILY_LOSS_LIMIT_PCT = 5.0  # $25-50 max daily loss
```

### Phase 3: Scale Gradually

After successful Phase 2:
1. Increase capital gradually ($500 increments)
2. Increase max positions proportionally
3. Keep paper trading running as validation

### Handling Deposits/Withdrawals

The system reads portfolio value from Alpaca directly:
- **Deposits**: Automatically reflected, positions can grow
- **Withdrawals**: System sees reduced cash, adjusts position sizes

No code changes needed - just deposit/withdraw via Alpaca.

---

## Risk Disclosure

### What Could Go Wrong

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Duplicate orders | LOW | MEDIUM | Idempotency keys |
| Stop gap-through | LOW | HIGH | Position sizing limits |
| API timeout | MEDIUM | MEDIUM | Retry logic, order queries |
| Data feed failure | MEDIUM | MEDIUM | Multiple price sources |
| Manual UI trade | MEDIUM | MEDIUM | Reconciliation + alerts |

### Financial Risk Warning

**This is automated trading with real money (when in live mode).**

- Past performance (68%+ win rate) does not guarantee future results
- Markets can gap through stops, causing larger losses than expected
- System errors can result in unintended trades
- You should only use capital you can afford to lose

### Recommended Precautions

1. **Start with paper trading** - Run for at least 2 weeks
2. **Use small capital initially** - $500-1000 max
3. **Monitor daily** - Check positions and P&L
4. **Keep the kill switch ready** - `TRADING_ENABLED=false`
5. **Maintain the audit log** - Never delete for compliance

---

## Support

For issues with the automated trading system:
1. Check the audit log for errors
2. Verify Alpaca API status
3. Check configuration settings
4. Review this README

For Alpaca-specific issues: [Alpaca Support](https://alpaca.markets/support)

---

*Insider Cluster Watch — Automated Trading System v1.0*
