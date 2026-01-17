# GitHub Actions Setup for Automated Trading

This guide explains how to configure GitHub Actions to run the automated trading system.

## Overview

The trading system uses three GitHub Actions workflows:

1. **`trading_morning.yml`** - Executes trades at 9:35 AM ET (market open + 5 min)
2. **`trading_monitor.yml`** - Monitors positions throughout the day and weekends
   - Every 5 minutes during market hours (9:35 AM - 4:00 PM ET)
   - Every hour after hours (4:30 PM - 8:30 PM ET)
   - Every 4 hours on weekends for safety
3. **`trading_eod.yml`** - End of day summary at 4:30 PM ET

## Required GitHub Secrets

You must configure these secrets in your GitHub repository:

### 1. Alpaca API Credentials

Go to **Repository Settings → Secrets and variables → Actions → New repository secret**

#### Paper Trading (for testing):
```
ALPACA_PAPER_API_KEY
Value: PK7TRISMJQU246CB6XXIN3HKDH
```

```
ALPACA_PAPER_SECRET_KEY
Value: 6Mtw12MjTvcT8wK2UJW9hMG8DUEW4SuNaFGBMxLH525J
```

#### Live Trading (when ready):
```
ALPACA_LIVE_API_KEY
Value: <your-live-api-key>
```

```
ALPACA_LIVE_SECRET_KEY
Value: <your-live-secret-key>
```

### 2. Email Alert Credentials (Already Configured)

These should already exist from the daily insider report job:
- `GMAIL_USER`
- `GMAIL_APP_PASSWORD`
- `RECIPIENT_EMAIL`

If not, add them:
```
GMAIL_USER
Value: your-email@gmail.com
```

```
GMAIL_APP_PASSWORD
Value: your-16-character-app-password
```

```
RECIPIENT_EMAIL
Value: recipient@gmail.com
```

## Initial Setup Steps

### 1. Add GitHub Secrets

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add all required secrets listed above

### 2. Initialize Data Directory (One-Time)

The workflows will automatically run this, but you can test it locally:

```bash
python automated_trading/init_data_dir.py
```

This creates:
- `automated_trading/data/` directory
- Empty JSON state files
- Empty audit log
- `.gitkeep` to track directory in git

### 3. Verify Workflows Are Enabled

1. Go to **Actions** tab in your repository
2. You should see three workflows:
   - Trading - Morning Execution
   - Trading - Position Monitor
   - Trading - End of Day Summary
3. Each can be manually triggered using **Run workflow** button for testing

## Testing Before Live Trading

### Test in Paper Trading Mode (CRITICAL)

The workflows are configured to use **paper trading mode** by default:

```yaml
ALPACA_TRADING_MODE: paper
```

**DO NOT change this to `live` until:**
1. You've run paper trading for at least 2 weeks
2. You've verified all trades execute correctly
3. You've tested all circuit breakers
4. You understand the system completely

### Manual Testing

You can manually trigger any workflow:

1. Go to **Actions** tab
2. Select a workflow (e.g., "Trading - Morning Execution")
3. Click **Run workflow** button
4. Select branch and click **Run workflow**

This is useful for:
- Testing outside market hours
- Debugging issues
- Verifying configuration

### Monitor Execution

After workflows run, you can:

1. **View logs**: Click on a workflow run → Click on the job → Expand steps
2. **Download artifacts**: Logs are saved as artifacts (available for 7-30 days)
3. **Check email**: You'll receive alerts for trades, circuit breakers, etc.

## Trading Mode Configuration

### Paper Trading (Default - SAFE)

The workflows use paper trading by default:
- Uses Alpaca paper trading API
- No real money at risk
- Ideal for testing and learning

### Live Trading (Real Money)

**⚠️ WARNING: Only switch to live trading after thorough testing!**

To enable live trading:

1. **Add live API credentials** to GitHub Secrets:
   - `ALPACA_LIVE_API_KEY`
   - `ALPACA_LIVE_SECRET_KEY`

2. **Edit each workflow file** and change:
   ```yaml
   ALPACA_TRADING_MODE: paper  # Change this line
   ```
   to:
   ```yaml
   ALPACA_TRADING_MODE: live   # ⚠️ REAL MONEY
   ```

3. **Start with small capital** ($500-1000) to test
4. **Monitor closely** for first few days
5. **Review circuit breaker settings** in `automated_trading/config.py`

## Emergency Kill Switch

If you need to halt all trading immediately:

### Option 1: Disable Trading (Keeps Monitoring)

Edit each workflow and change:
```yaml
TRADING_ENABLED: "true"
```
to:
```yaml
TRADING_ENABLED: "false"
```

This will:
- ✅ Stop new trade execution
- ✅ Continue monitoring existing positions
- ✅ Exit positions if stop losses trigger

### Option 2: Disable Workflows Completely

1. Go to **Actions** tab
2. Click on a workflow
3. Click **⋯** (three dots) → **Disable workflow**
4. Repeat for all three workflows

This will:
- ❌ Stop all automated activity
- ❌ Stop position monitoring
- ⚠️ Use only in emergencies

## Workflow Schedule Details

### Market Hours Reference (ET)
- Market open: 9:30 AM ET
- Trading start: 9:35 AM ET (we wait 5 min)
- Trading end: 3:30 PM ET (stop 30 min before close)
- Market close: 4:00 PM ET
- EOD summary: 4:30 PM ET

### Cron Schedule Conversion (ET → UTC)

- Eastern Time = UTC - 5 hours (EST) or UTC - 4 hours (EDT)
- **IMPORTANT**: Workflows use UTC times
- Example: 9:35 AM ET = 14:35 UTC (EST) or 13:35 UTC (EDT)

**Note**: GitHub Actions doesn't handle daylight saving time automatically. You may need to adjust cron times twice a year.

### Current Schedule (UTC, assumes EST = UTC-5)

| Workflow | ET Time | UTC Time | Frequency |
|----------|---------|----------|-----------|
| Morning | 9:35 AM | 14:35 | Weekdays only |
| Monitor (Market hours) | 9:35 AM - 4:00 PM | 14:35-21:00 | Every 5 min, weekdays |
| Monitor (After hours) | 4:30 PM - 8:30 PM | 21:30-01:30 | Every hour, weekdays |
| Monitor (Weekends) | All day | All day | Every 4 hours, Sat/Sun |
| EOD | 4:30 PM | 21:30 | Weekdays only |

## Monitoring and Alerts

### Email Alerts

You'll receive emails for:
- ✅ Every trade executed (BUY/SELL)
- ⚠️ Circuit breaker triggers (daily loss limit, consecutive losses)
- ⚠️ Position reconciliation failures
- 📊 Daily summary (EOD)

### Email Headers Indicate Mode

- **🧪 PAPER TRADING** (blue header) = Paper trading mode
- **💰 LIVE TRADING** (orange header) = Live trading mode

This makes it **very obvious** which mode generated the alert.

### Logs

Workflow logs are uploaded as artifacts:
- **Morning/EOD logs**: Kept for 30 days
- **Monitor logs**: Kept for 7 days (only on failure)

Download from **Actions** → **Workflow run** → **Artifacts**

## Circuit Breaker Configuration

Review and adjust in `automated_trading/config.py`:

```python
# Daily loss limits - HALT trading if exceeded
DAILY_LOSS_LIMIT_PCT = 5.0       # 5% of portfolio = hard stop

# Drawdown limits
MAX_DRAWDOWN_HALT_PCT = 15.0     # Halt if drawdown > 15%

# Consecutive loss protection
MAX_CONSECUTIVE_LOSSES = 5       # Pause after 5 consecutive losers
```

For a $2,000 account:
- Daily loss halt = $100 loss
- Daily loss warning = $50 loss

## Position Sizing Configuration

Review in `automated_trading/config.py`:

```python
MAX_POSITION_PCT = 0.10          # 10% max per position
MAX_POSITIONS = 10               # Max concurrent positions
MAX_TOTAL_EXPOSURE = 0.70        # 70% max exposure
```

## Troubleshooting

### Workflows Not Running

1. **Check workflow is enabled**: Actions → Workflow → Should show green "Active"
2. **Check secrets are set**: Settings → Secrets → Should see all required secrets
3. **Check cron syntax**: Use [crontab.guru](https://crontab.guru/) to verify times
4. **Manual trigger**: Use "Run workflow" to test immediately

### Trades Not Executing

1. **Check logs**: Actions → Workflow run → View logs
2. **Check trading mode**: Verify `ALPACA_TRADING_MODE` in workflow
3. **Check trading enabled**: Verify `TRADING_ENABLED: "true"` in workflow
4. **Check API credentials**: Verify secrets are correct
5. **Check market hours**: System only trades during market hours
6. **Check circuit breaker**: May be halted due to daily loss limit

### No Email Alerts

1. **Check Gmail secrets**: Verify `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `RECIPIENT_EMAIL`
2. **Check spam folder**: Alerts might be filtered
3. **Check workflow logs**: Look for email sending errors

### Position Reconciliation Failures

This means local state doesn't match Alpaca:
- ⚠️ **Manual trade in Alpaca UI?**
- ⚠️ **System crash during execution?**
- ⚠️ **Order filled but not recorded?**

**Action**: Check email alert for discrepancy details, then investigate manually.

## Best Practices

### 1. Start Small
- Begin with paper trading for 2-4 weeks
- Then try live trading with $500-1000
- Gradually scale up after validation

### 2. Monitor Daily
- Check email alerts every day
- Review workflow execution logs weekly
- Monitor circuit breaker status

### 3. Keep the Kill Switch Ready
- Know how to disable `TRADING_ENABLED` quickly
- Know how to disable workflows completely
- Have Alpaca app installed for manual overrides

### 4. Review Configuration Regularly
- Adjust position sizing as account grows
- Review circuit breaker thresholds
- Update stop loss percentages based on performance

### 5. Maintain the Audit Log
- **NEVER delete `audit_log.jsonl`**
- This is your compliance record
- Useful for debugging and performance analysis

## Support

For issues:
1. Check workflow logs first
2. Check `automated_trading/README.md` for detailed documentation
3. Review `audit_log.jsonl` for system events
4. Check Alpaca API status: [status.alpaca.markets](https://status.alpaca.markets)

---

**⚠️ IMPORTANT REMINDERS**

1. **Start with paper trading** - Don't rush into live trading
2. **Test circuit breakers** - Make sure they work before going live
3. **Monitor closely** - Automated doesn't mean unattended
4. **Start small** - Use capital you can afford to lose
5. **Keep kill switch ready** - Know how to stop everything quickly

---

*Insider Cluster Watch — Automated Trading System*
