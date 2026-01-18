# Alpaca Automated Trading System

Production-ready automated trading system for executing insider trading signals via Alpaca Markets API.

**Status**: ✅ Ready for paper trading
**Trading Mode**: Paper (default) / Live
**GitHub Actions**: ✅ Configured

---

## Quick Start

### GitHub Actions Setup (Recommended)

**Add these secrets** in GitHub repo Settings → Secrets → Actions:

```
ALPACA_PAPER_API_KEY = PK7TRISMJQU246CB6XXIN3HKDH
ALPACA_PAPER_SECRET_KEY = 6Mtw12MjTvcT8wK2UJW9hMG8DUEW4SuNaFGBMxLH525J
```

Email credentials (should already exist):
```
GMAIL_USER
GMAIL_APP_PASSWORD
RECIPIENT_EMAIL
```

**Workflows run automatically**:
- **Morning execution**: 9:35 AM ET weekdays
- **Position monitoring**: Every 5 min during market hours
- **End of day summary**: 4:30 PM ET weekdays

---

## Trading Strategy

### Position Sizing (Score-Weighted)

**Uses signal score** to determine position size:

- **Score 6-20** → Position size 5-12% of portfolio
- Higher score = larger position
- Example: Score 15 → ~10%, Score 8 → ~6%

**Why not tier-based?** Most signals are tier4/tier3. Tier-based sizing would reduce capital deployment unnecessarily.

### Stop Losses (Tier-Based)

**Uses tier** to determine stop width:

- **tier1**: 12% stop (widest - high conviction, more room)
- **tier2**: 10% stop
- **tier3**: 8% stop
- **tier4**: 6% stop (tightest - fail fast on lower conviction)

**Why wider stops for higher conviction?** Give best ideas room to work while cutting losses quickly on weaker signals.

### Risk Management

| Limit | Value | Description |
|-------|-------|-------------|
| Max position | 10% | Single position cap |
| Max positions | 10 | Concurrent positions |
| Max exposure | 70% | Total capital deployed |
| Daily loss halt | 5% | Trading stops for day |
| Consecutive losses | 5 | Pause after 5 losers |

---

## GitHub Actions Workflows

### 1. trading_morning.yml
- **When**: 9:35 AM ET weekdays
- **Does**: Execute morning buy signals
- **Frequency**: Once per day

### 2. trading_monitor.yml
- **When**:
  - Every 5 min during market hours (9:35 AM - 4:00 PM ET)
  - Every hour after hours (4:30 PM - 8:30 PM ET)
  - Every 4 hours on weekends
- **Does**: Monitor positions, check exits
- **Frequency**: ~78 times per weekday

### 3. trading_eod.yml
- **When**: 4:30 PM ET weekdays
- **Does**: Daily summary email
- **Frequency**: Once per day

---

## Configuration

### Key Settings (config.py)

```python
# Trading Mode
TRADING_MODE = 'paper'  # Change to 'live' for real money
TRADING_ENABLED = True  # Kill switch

# Position Sizing (Score-Weighted)
MAX_POSITION_PCT = 0.10              # 10% max per position
ENABLE_SCORE_WEIGHTED_SIZING = True
SCORE_WEIGHT_MIN_POSITION_PCT = 0.05 # 5% min (score 6)
SCORE_WEIGHT_MAX_POSITION_PCT = 0.12 # 12% max (score 20)

# Stop Losses (Tier-Based)
MULTI_SIGNAL_STOP_LOSS = {
    'tier1': 0.12,  # 12% (highest conviction)
    'tier2': 0.10,  # 10%
    'tier3': 0.08,  # 8%
    'tier4': 0.06   # 6% (lowest conviction)
}

# Risk Management
STOP_LOSS_PCT = 0.08           # Default 8%
TAKE_PROFIT_PCT = 0.12         # Default 12%
DAILY_LOSS_LIMIT_PCT = 5.0     # 5% = HALT
MAX_CONSECUTIVE_LOSSES = 5     # Pause after 5
```

---

## Recent Bug Fixes (Jan 17, 2026)

### ✅ Fixed Issues

1. **Order Status Normalization** - Handles multiple Alpaca status formats
2. **Type Annotations** - Standardized to `Tuple` from typing
3. **Circuit Breaker Reset** - Manual reset via flag file
4. **Duplicate Order Detection** - Specific error messages
5. **Asset Validation** - Properly logs warnings

### Manual Circuit Breaker Reset

```bash
echo "Investigated issue" > automated_trading/data/circuit_breaker_reset.flag
```

Next workflow run resets circuit breaker.

---

## Monitoring & Alerts

### Email Alerts

Receive emails for:
- ✅ Every trade (BUY/SELL)
- ⚠️ Circuit breaker triggers
- ⚠️ Reconciliation failures
- 📊 Daily summary

**Headers indicate mode**:
- 🧪 **PAPER TRADING** (blue)
- 💰 **LIVE TRADING** (orange)

### Logs

- **GitHub Actions**: Actions → Workflow run → Artifacts
- **Audit trail**: `automated_trading/data/audit_log.jsonl`
- **Never delete audit log** - compliance record

---

## Safety Features

### Circuit Breakers

- **Daily loss > 5%** → HALT trading
- **5 consecutive losses** → PAUSE 24 hours
- **Drawdown > 15%** → HALT new trades

### Order Safety

- Limit orders only (no market orders)
- 0.5% cushion above signal price
- Idempotent order IDs (prevent duplicates)
- Partial fill handling (≥50% fills)

### Reconciliation

- Runs every 15 minutes
- Detects manual trades
- Alerts on discrepancies

---

## Emergency Controls

### Kill Switch

**Option 1**: Disable trading (keeps monitoring):
```yaml
TRADING_ENABLED: "false"
```

**Option 2**: Disable all workflows:
- Actions tab → Workflow → ⋯ → Disable

---

## Going Live

**⚠️ Only after 2-4 weeks paper trading!**

1. Add live API credentials to GitHub Secrets
2. Edit workflows: `ALPACA_TRADING_MODE: live`
3. Start with $500-1000
4. Monitor closely for first week

---

## What to Expect This Week (Paper Trading)

### Daily Activity

**Morning (9:35 AM ET)**:
- System checks for signals (score ≥ 6)
- Executes trades if signals exist
- Email: "BUY {ticker} {shares} @ ${price}"
- Position sizing: 5-12% based on score

**During Market Hours (9:35 AM - 4:00 PM ET)**:
- Checks positions every 5 minutes
- Monitors stop-loss (tier-based: 6-12%)
- Monitors take-profit (12%)
- Updates trailing stops
- Email if exit: "SELL {ticker} - {reason}"

**After Hours (4:30 PM - 8:30 PM ET)**:
- Monitors hourly
- Can still trigger exits

**End of Day (4:30 PM ET)**:
- Summary email:
  - Positions opened/closed
  - Portfolio value
  - Daily P&L
  - Circuit breaker status

### Weekends

- Checks every 4 hours
- Safety monitoring only
- No trading

### Expected Trades (Typical Week)

**Assuming 3-5 signals with typical tier4/tier3 scores**:

**Monday**:
- 2 signals execute (scores 7.5, 9.0)
- Position sizes: ~6%, ~7% of portfolio
- Both tier4 → 6% stop-loss

**Tuesday-Thursday**:
- 1 position hits stop (tier4 tight stop)
- 1 new signal → position opened
- 2 positions monitored

**Friday**:
- 1 position hits target (+12%)
- 1 position open into weekend
- Week total: 3 opened, 2 closed, 1 open

### Email Volume

**3-7 emails per day**:
- 1-3 for morning trades
- 0-2 for exits
- 1 daily summary
- Additional only if issues

### Success Indicators

**System working correctly if**:
- ✅ Trades execute at 9:35 AM when signals exist
- ✅ Position sizes 5-12% (score-weighted)
- ✅ Stops match tier (6-12%)
- ✅ Email alerts arrive for all events
- ✅ Positions appear in Alpaca paper account
- ✅ Daily summary accurate

### Red Flags

**Immediate attention if**:
- ⚠️ Circuit breaker triggers unexpectedly
- ⚠️ Reconciliation failures
- ⚠️ All trades failing
- ⚠️ Position sizes wrong
- ⚠️ No emails when trades execute

### Monitoring Checklist

**Daily (first week)**:
- [ ] Morning email for executions
- [ ] Positions in Alpaca dashboard
- [ ] EOD summary email
- [ ] Workflow logs in GitHub Actions

**Weekly**:
- [ ] All email alerts reviewed
- [ ] Circuit breaker status checked
- [ ] Position count matches expectations
- [ ] Audit log reviewed

### Typical Performance (Week 1)

**Realistic expectations**:
- 3-10 trades executed
- Mostly tier4/tier3 (as expected)
- 30-50% win rate (normal)
- Small loss or small gain overall
- **Goal**: Validate system works, not make money yet

**After 2-4 weeks**:
- Consistent execution pattern
- Position sizing validated
- Circuit breakers tested
- Ready to consider live trading

---

## Troubleshooting

### Workflows Not Running
- Check workflows enabled in Actions tab
- Verify secrets set correctly
- Test manual trigger

### Trades Not Executing
- Check TRADING_ENABLED = true
- Verify market hours (9:35 AM - 3:30 PM ET)
- Check circuit breaker not triggered
- Verify sufficient cash

### No Email Alerts
- Check Gmail credentials in secrets
- Check spam folder
- Review workflow logs

---

## Support

- **Alpaca Docs**: https://alpaca.markets/docs/
- **Alpaca Status**: https://status.alpaca.markets/

---

*Insider Cluster Watch — Automated Trading System v1.0*
*Updated: January 17, 2026*
