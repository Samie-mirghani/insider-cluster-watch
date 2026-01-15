# automated_trading/config.py
"""
Configuration for Alpaca Automated Trading System

This module contains all configuration parameters for the live trading system.
Parameters are designed for safety-first operation with conservative defaults.
"""

import os
from datetime import time

# =============================================================================
# TRADING MODE
# =============================================================================
# CRITICAL: Set to 'paper' for testing, 'live' for real money
# The system behaves identically in both modes - the only difference is the API endpoint
TRADING_MODE = os.getenv('ALPACA_TRADING_MODE', 'paper')  # 'paper' or 'live'

# Manual kill switch - set to 'false' to halt all trading
TRADING_ENABLED = os.getenv('TRADING_ENABLED', 'true').lower() == 'true'

# =============================================================================
# ALPACA API CREDENTIALS
# =============================================================================
# Paper trading credentials (separate from live)
ALPACA_PAPER_API_KEY = os.getenv('ALPACA_PAPER_API_KEY')
ALPACA_PAPER_SECRET_KEY = os.getenv('ALPACA_PAPER_SECRET_KEY')

# Live trading credentials (only used when TRADING_MODE='live')
ALPACA_LIVE_API_KEY = os.getenv('ALPACA_LIVE_API_KEY')
ALPACA_LIVE_SECRET_KEY = os.getenv('ALPACA_LIVE_SECRET_KEY')

# API base URLs
ALPACA_PAPER_BASE_URL = 'https://paper-api.alpaca.markets'
ALPACA_LIVE_BASE_URL = 'https://api.alpaca.markets'

# =============================================================================
# PORTFOLIO PARAMETERS (Scalable Design)
# =============================================================================
# Starting capital is read from Alpaca account, not hardcoded
# These percentages scale with account size

# Position sizing (as percentage of portfolio)
MAX_POSITION_PCT = 0.10          # 10% max per position
MIN_POSITION_PCT = 0.03          # 3% minimum position (avoid tiny positions)
MAX_POSITIONS = 10               # Max concurrent positions
MAX_TOTAL_EXPOSURE = 0.70        # 70% max exposure (keep 30% cash buffer)

# Score-weighted position sizing
ENABLE_SCORE_WEIGHTED_SIZING = True
SCORE_WEIGHT_MIN_POSITION_PCT = 0.05   # 5% for lowest qualifying score
SCORE_WEIGHT_MAX_POSITION_PCT = 0.12   # 12% for highest scores
SCORE_WEIGHT_MIN_SCORE = 6.0
SCORE_WEIGHT_MAX_SCORE = 20.0

# Minimum thresholds
MIN_SIGNAL_SCORE_THRESHOLD = 6.0       # Minimum score to trade
MIN_POSITION_VALUE = 50.0              # $50 minimum position (avoid fractional share issues)

# =============================================================================
# RISK MANAGEMENT - STOP LOSSES AND TARGETS
# =============================================================================
# Base stop loss (can be overridden by tier)
STOP_LOSS_PCT = 0.08             # 8% default stop loss
TAKE_PROFIT_PCT = 0.12           # 12% take profit target

# Trailing stops
TRAILING_STOP_PCT = 0.05         # 5% trailing stop
TRAILING_TRIGGER_PCT = 0.03      # Enable trailing after +3% gain

# Tiered stop losses (multi-signal trades)
MULTI_SIGNAL_STOP_LOSS = {
    'tier1': 0.12,  # -12% stop for highest conviction
    'tier2': 0.10,  # -10% stop
    'tier3': 0.08,  # -8% stop
    'tier4': 0.06   # -6% stop (tighter for lower conviction)
}

# Dynamic stop tightening
ENABLE_DYNAMIC_STOPS = True
BIG_WINNER_THRESHOLD = 20.0      # Tighten stop after +20% gain
BIG_WINNER_STOP_PCT = 0.10       # 10% trailing stop for big winners
HUGE_WINNER_THRESHOLD = 30.0     # Further tighten after +30%
HUGE_WINNER_STOP_PCT = 0.07      # 7% trailing stop for huge winners

# =============================================================================
# TIME-BASED EXITS
# =============================================================================
MAX_HOLD_LOSS_DAYS = 21          # Exit after 21 days if losing
MAX_HOLD_STAGNANT_DAYS = 30      # Exit after 30 days if barely positive
MAX_HOLD_STAGNANT_THRESHOLD = 3.0  # "Barely positive" = < 3%
MAX_HOLD_EXTREME_DAYS = 45       # Max hold regardless of performance
MAX_HOLD_EXTREME_EXCEPTION = 15.0  # Exception: keep if +15%

# =============================================================================
# CIRCUIT BREAKERS (SAFETY CRITICAL)
# =============================================================================
# Daily loss limits - HALT trading if exceeded
DAILY_LOSS_LIMIT_PCT = 5.0       # 5% of portfolio = hard stop for the day
DAILY_LOSS_WARNING_PCT = 2.5     # 2.5% = warning alert

# For a $2,000 account, these translate to:
# - $100 daily loss = HALT
# - $50 daily loss = WARNING

# Drawdown limits
MAX_DRAWDOWN_HALT_PCT = 15.0     # Halt new trades if drawdown > 15%
MAX_DRAWDOWN_WARNING_PCT = 10.0  # Warning if drawdown > 10%

# Consecutive loss protection
MAX_CONSECUTIVE_LOSSES = 5       # Pause after 5 consecutive losers
CONSECUTIVE_LOSS_COOLDOWN_HOURS = 24  # Wait 24 hours before resuming

# Slippage monitoring
MAX_SLIPPAGE_ALERT_PCT = 3.0     # Alert if execution differs > 3% from signal

# =============================================================================
# INTRADAY CAPITAL REDEPLOYMENT
# =============================================================================
# When a position is sold, can freed capital be deployed to queued signals?
ENABLE_INTRADAY_REDEPLOYMENT = True

# Safeguards for intraday redeployment
REDEPLOYMENT_PRICE_TOLERANCE_PCT = 3.0  # Only if price within ±3% of signal
REDEPLOYMENT_MIN_TIME_BEFORE_CLOSE = 30  # Minutes before close (don't trade last 30 min)
REDEPLOYMENT_MAX_PER_DAY = 1     # Max 1 intraday redeployment per day
REDEPLOYMENT_MIN_FREED_CAPITAL = 100  # Minimum freed capital to trigger ($100)

# =============================================================================
# ORDER EXECUTION PARAMETERS
# =============================================================================
# Order types and timing
USE_LIMIT_ORDERS = True          # Use limit orders (safer than market)
LIMIT_ORDER_CUSHION_PCT = 0.5    # 0.5% above signal price for buys
STOP_LIMIT_SPREAD_PCT = 2.0      # 2% below stop for stop-limit orders

# Time in force
DEFAULT_TIME_IN_FORCE = 'day'    # Orders expire at market close
STOP_TIME_IN_FORCE = 'gtc'       # Stops are good-til-cancelled

# Retry settings
ORDER_RETRY_MAX_ATTEMPTS = 3
ORDER_RETRY_DELAY_SECONDS = 2    # Exponential backoff: 2, 4, 8 seconds

# Partial fill handling
ACCEPT_PARTIAL_FILL_PCT = 50.0   # Accept partial if >= 50% filled
CANCEL_PARTIAL_BELOW_PCT = 50.0  # Cancel if < 50% filled

# =============================================================================
# MARKET HOURS (US Eastern Time)
# =============================================================================
MARKET_OPEN_TIME = time(9, 30)   # 9:30 AM ET
MARKET_CLOSE_TIME = time(16, 0)  # 4:00 PM ET
PRE_MARKET_START = time(4, 0)    # 4:00 AM ET
AFTER_HOURS_END = time(20, 0)    # 8:00 PM ET

# Trading window (when we execute)
EXECUTION_START_TIME = time(9, 35)  # Start 5 min after open (avoid volatility)
EXECUTION_END_TIME = time(15, 30)   # Stop 30 min before close

# =============================================================================
# MONITORING INTERVALS
# =============================================================================
MONITOR_INTERVAL_MINUTES = 5     # Check positions every 5 minutes
RECONCILIATION_INTERVAL_MINUTES = 15  # Full reconciliation every 15 min
DAILY_SUMMARY_TIME = time(16, 30)  # Send daily summary at 4:30 PM ET

# =============================================================================
# DATA FILES
# =============================================================================
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

LIVE_POSITIONS_FILE = os.path.join(DATA_DIR, 'live_positions.json')
PENDING_ORDERS_FILE = os.path.join(DATA_DIR, 'pending_orders.json')
QUEUED_SIGNALS_FILE = os.path.join(DATA_DIR, 'queued_signals.json')
DAILY_STATE_FILE = os.path.join(DATA_DIR, 'daily_state.json')
AUDIT_LOG_FILE = os.path.join(DATA_DIR, 'audit_log.jsonl')
TRADE_HISTORY_FILE = os.path.join(DATA_DIR, 'trade_history.csv')

# =============================================================================
# EMAIL ALERTS
# =============================================================================
# Uses same credentials as existing pipeline
GMAIL_USER = os.getenv('GMAIL_USER')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL')

# Alert levels
ALERT_LEVEL_CRITICAL = 'CRITICAL'  # Immediate attention required
ALERT_LEVEL_WARNING = 'WARNING'    # Review recommended
ALERT_LEVEL_INFO = 'INFO'          # Informational only

# =============================================================================
# LOGGING
# =============================================================================
LOG_LEVEL = os.getenv('ALPACA_LOG_LEVEL', 'INFO')
LOG_FILE = os.path.join(DATA_DIR, 'alpaca_trading.log')

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_api_credentials():
    """Get the appropriate API credentials based on trading mode."""
    if TRADING_MODE == 'live':
        return {
            'api_key': ALPACA_LIVE_API_KEY,
            'secret_key': ALPACA_LIVE_SECRET_KEY,
            'base_url': ALPACA_LIVE_BASE_URL
        }
    else:
        return {
            'api_key': ALPACA_PAPER_API_KEY,
            'secret_key': ALPACA_PAPER_SECRET_KEY,
            'base_url': ALPACA_PAPER_BASE_URL
        }


def get_daily_loss_limit_dollars(portfolio_value):
    """Calculate daily loss limit in dollars based on portfolio value."""
    return portfolio_value * (DAILY_LOSS_LIMIT_PCT / 100)


def get_daily_loss_warning_dollars(portfolio_value):
    """Calculate daily loss warning threshold in dollars."""
    return portfolio_value * (DAILY_LOSS_WARNING_PCT / 100)


def validate_config():
    """Validate critical configuration settings."""
    errors = []

    # Check API credentials
    creds = get_api_credentials()
    if not creds['api_key']:
        errors.append(f"Missing API key for {TRADING_MODE} trading")
    if not creds['secret_key']:
        errors.append(f"Missing secret key for {TRADING_MODE} trading")

    # Check email credentials
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not RECIPIENT_EMAIL:
        errors.append("Missing email credentials (GMAIL_USER, GMAIL_APP_PASSWORD, RECIPIENT_EMAIL)")

    # Validate trading mode
    if TRADING_MODE not in ['paper', 'live']:
        errors.append(f"Invalid TRADING_MODE: {TRADING_MODE} (must be 'paper' or 'live')")

    # Validate percentages
    if MAX_POSITION_PCT > 0.20:
        errors.append(f"MAX_POSITION_PCT ({MAX_POSITION_PCT}) > 20% is very risky")

    if MAX_TOTAL_EXPOSURE > 0.90:
        errors.append(f"MAX_TOTAL_EXPOSURE ({MAX_TOTAL_EXPOSURE}) > 90% leaves insufficient cash buffer")

    return errors


def print_config_summary():
    """Print a summary of current configuration."""
    mode_emoji = "🧪" if TRADING_MODE == 'paper' else "💰"
    enabled_status = "✅ ENABLED" if TRADING_ENABLED else "🛑 DISABLED"

    print(f"""
{'='*60}
{mode_emoji} ALPACA TRADING CONFIGURATION
{'='*60}

Mode:           {TRADING_MODE.upper()} TRADING
Status:         {enabled_status}

Position Sizing:
  Max Position: {MAX_POSITION_PCT*100:.1f}%
  Max Exposure: {MAX_TOTAL_EXPOSURE*100:.1f}%
  Max Positions: {MAX_POSITIONS}

Risk Management:
  Stop Loss:    {STOP_LOSS_PCT*100:.1f}%
  Take Profit:  {TAKE_PROFIT_PCT*100:.1f}%
  Trailing:     {TRAILING_STOP_PCT*100:.1f}% (after +{TRAILING_TRIGGER_PCT*100:.1f}%)

Circuit Breakers:
  Daily Loss Halt:    {DAILY_LOSS_LIMIT_PCT:.1f}%
  Max Drawdown Halt:  {MAX_DRAWDOWN_HALT_PCT:.1f}%
  Max Consecutive L:  {MAX_CONSECUTIVE_LOSSES}

Intraday Redeployment: {'ENABLED' if ENABLE_INTRADAY_REDEPLOYMENT else 'DISABLED'}

{'='*60}
""")


if __name__ == '__main__':
    # Run validation when module is executed directly
    print_config_summary()

    errors = validate_config()
    if errors:
        print("⚠️  Configuration Errors:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("✅ Configuration validated successfully")
