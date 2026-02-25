# automated_trading/config.py
"""
Configuration for Alpaca Automated Trading System

This module contains all configuration parameters for the live trading system.
Parameters are designed for safety-first operation with conservative defaults.
"""

from dotenv import load_dotenv
load_dotenv()

import math
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

# =============================================================================
# PORTFOLIO PARAMETERS (Scalable Design)
# =============================================================================
# Starting capital is read from Alpaca account, not hardcoded
# These percentages scale with account size

# Position sizing (as percentage of portfolio)
MAX_POSITION_PCT = 0.10          # 10% max per position
MIN_POSITION_PCT = 0.03          # 3% minimum position (avoid tiny positions)
MAX_POSITIONS = 10               # Max concurrent positions
MAX_TOTAL_EXPOSURE = 0.70        # 70% max exposure (keep 30% cash buffer) — static fallback

# Performance-adaptive exposure: dynamically scale max exposure based on
# recent win rate.  Pulls back when losing and deploys more when winning.
ENABLE_ADAPTIVE_EXPOSURE = True
ADAPTIVE_EXPOSURE_MIN = 0.50           # Floor: 50% max exposure during drawdowns
ADAPTIVE_EXPOSURE_MAX = 0.80           # Ceiling: 80% when strategy is performing
ADAPTIVE_EXPOSURE_WIN_RATE_LOW = 0.30  # Below 30% WR → use min exposure
ADAPTIVE_EXPOSURE_WIN_RATE_HIGH = 0.50 # Above 50% WR → use max exposure
ADAPTIVE_EXPOSURE_MIN_TRADES = 10      # Need 10+ completed trades before adapting

# Score-weighted position sizing
ENABLE_SCORE_WEIGHTED_SIZING = True
SCORE_WEIGHT_MIN_POSITION_PCT = 0.05   # 5% for lowest qualifying score
SCORE_WEIGHT_MAX_POSITION_PCT = 0.12   # 12% for highest scores
SCORE_WEIGHT_MIN_SCORE = 6.0
SCORE_WEIGHT_MAX_SCORE = 20.0

# Volatility-adjusted position sizing
# Normalizes position size by realized volatility so high-vol stocks get smaller
# allocations and low-vol stocks get larger ones, evening out risk per position.
ENABLE_VOLATILITY_ADJUSTED_SIZING = True
VOLATILITY_TARGET_ATR_PCT = 2.0        # Target daily ATR as % of price
VOLATILITY_SIZE_MIN_MULTIPLIER = 0.5   # Floor: halve position for very volatile names
VOLATILITY_SIZE_MAX_MULTIPLIER = 1.5   # Ceiling: 50% larger for very stable names
VOLATILITY_ATR_LOOKBACK_DAYS = 20      # Days of history for ATR calculation

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
# Previous: 5% trail triggered at +3% — too tight for multi-week thesis trades.
# A stock hitting +3% then retracing 2% would get stopped at ~breakeven,
# converting winners into scratches.  Widened to give trades room to develop.
TRAILING_STOP_PCT = 0.08         # 8% trailing stop (was 5%)
TRAILING_TRIGGER_PCT = 0.06      # Enable trailing after +6% gain (was 3%)

# Tiered stop losses (multi-signal trades)
# Risk Management Strategy:
# - Higher conviction (tier1) = WIDER stops (12%) - allow more price movement
# - Lower conviction (tier4) = TIGHTER stops (6%) - fail fast to preserve capital
# This is intentional: we give high-conviction signals more room to work,
# while cutting losses quickly on lower-conviction trades.
#
# NOTE: Position sizing is NOT tier-based. It uses score-weighted sizing instead.
# Since most signals are tier4 with some tier3, tier-based sizing would reduce
# capital deployment unnecessarily. Signal score determines position size.
MULTI_SIGNAL_STOP_LOSS = {
    'tier1': 0.12,  # -12% stop for highest conviction (widest - most room)
    'tier2': 0.10,  # -10% stop for high conviction
    'tier3': 0.08,  # -8% stop for medium conviction
    'tier4': 0.06   # -6% stop for lower conviction (tightest - fail fast)
}

# Tiered take-profit targets (must maintain >= 2:1 R:R at 33% win rate)
# R:R = TP / SL.  At 33% WR, break-even requires R:R >= 2.03:1.
MULTI_SIGNAL_TAKE_PROFIT = {
    'tier1': 0.24,  # +24% TP for highest conviction  (R:R 2.0:1 with 12% SL)
    'tier2': 0.20,  # +20% TP for high conviction      (R:R 2.0:1 with 10% SL)
    'tier3': 0.16,  # +16% TP for medium conviction     (R:R 2.0:1 with 8% SL)
    'tier4': 0.12   # +12% TP for lower conviction      (R:R 2.0:1 with 6% SL)
}

# Sector concentration limits (hard reject above threshold)
SECTOR_HIGH_CONCENTRATION_THRESHOLD = 0.40  # 40% in one sector = reject entry

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

# Daily trade limit - prevents overtrading in volatile markets
MAX_TRADES_PER_DAY = 15          # Maximum 15 trades (buys + sells) per day

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
REDEPLOYMENT_MAX_PER_DAY = 5     # Max 5 intraday redeployments per day
REDEPLOYMENT_MIN_FREED_CAPITAL = 100  # Minimum freed capital to trigger ($100)

# =============================================================================
# ORDER EXECUTION PARAMETERS
# =============================================================================
# Order types and timing
# Limit orders with a market-cap-tiered cushion protect against slippage while
# keeping entries tight.  Large caps are liquid enough for a narrow cushion;
# small caps need more room to fill.
USE_LIMIT_ORDERS = True          # Use limit orders for price protection
STOP_LIMIT_SPREAD_PCT = 2.0      # 2% below stop for stop-limit orders

# Market cap tier boundaries (used for slippage cushion selection)
MARKET_CAP_LARGE_THRESHOLD = 10_000_000_000   # >= $10B = large cap
MARKET_CAP_MID_THRESHOLD   =  2_000_000_000   # >= $2B  = mid cap
                                               # <  $2B  = small cap

# Limit order cushion by market cap tier (% above signal price for buys)
LIMIT_ORDER_CUSHION_BY_CAP = {
    'large_cap': 0.75,   # Liquid names — tight cushion
    'mid_cap':   1.25,   # Moderate liquidity
    'small_cap': 1.75,   # Thinner books — more room to fill
}
LIMIT_ORDER_CUSHION_DEFAULT = 1.25  # Fallback when market_cap is unknown

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
# NOTE: Executing at 10:00 AM (30 min after open) allows volatility to settle
# and spreads to tighten, improving limit order fill rates
EXECUTION_START_TIME = time(10, 0)  # Start 30 min after open for better fills
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
EXITS_TODAY_FILE = os.path.join(DATA_DIR, 'exits_today.json')
AUDIT_LOG_FILE = os.path.join(DATA_DIR, 'audit_log.jsonl')
TRADE_HISTORY_FILE = os.path.join(DATA_DIR, 'trade_history.csv')
SIGNAL_HISTORY_FILE = os.path.join(DATA_DIR, 'signal_history.json')
EXECUTION_METRICS_FILE = os.path.join(DATA_DIR, 'execution_metrics.json')

# Path to approved signals from main pipeline (for tier lookup during broker sync)
# Note: This is in the main data/ directory, not automated_trading/data/
APPROVED_SIGNALS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'approved_signals.json')

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
# INTERNAL TUNABLE PARAMETERS
# =============================================================================
# Previously hardcoded values promoted to config for tunability.
ACCOUNT_CACHE_TIMEOUT_SECONDS = 60   # Account data cache lifetime (non-forced fetches)
ORDER_EXPIRATION_HOURS = 24          # Remove stale pending orders after this many hours
SIGNAL_STALENESS_HOURS = 24          # Queued signals expire for redeployment after this
PARTIAL_FILL_TIMEOUT_MINUTES = 15    # Cancel unfilled order remainder after this many minutes

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_api_credentials():
    """Get the appropriate API credentials based on trading mode."""
    if TRADING_MODE == 'live':
        return {
            'api_key': ALPACA_LIVE_API_KEY,
            'secret_key': ALPACA_LIVE_SECRET_KEY,
        }
    else:
        return {
            'api_key': ALPACA_PAPER_API_KEY,
            'secret_key': ALPACA_PAPER_SECRET_KEY,
        }


def get_daily_loss_limit_dollars(portfolio_value):
    """Calculate daily loss limit in dollars based on portfolio value."""
    return portfolio_value * (DAILY_LOSS_LIMIT_PCT / 100)


def get_daily_loss_warning_dollars(portfolio_value):
    """Calculate daily loss warning threshold in dollars."""
    return portfolio_value * (DAILY_LOSS_WARNING_PCT / 100)


def get_adaptive_max_exposure(win_rate: float, total_trades: int) -> float:
    """
    Return the max exposure limit based on recent win rate.

    If adaptive exposure is disabled or we don't have enough trades yet,
    falls back to the static MAX_TOTAL_EXPOSURE.
    """
    if not ENABLE_ADAPTIVE_EXPOSURE:
        return MAX_TOTAL_EXPOSURE
    if total_trades < ADAPTIVE_EXPOSURE_MIN_TRADES:
        return MAX_TOTAL_EXPOSURE

    # Linear interpolation between min and max exposure
    if win_rate <= ADAPTIVE_EXPOSURE_WIN_RATE_LOW:
        return ADAPTIVE_EXPOSURE_MIN
    if win_rate >= ADAPTIVE_EXPOSURE_WIN_RATE_HIGH:
        return ADAPTIVE_EXPOSURE_MAX

    # Interpolate
    wr_range = ADAPTIVE_EXPOSURE_WIN_RATE_HIGH - ADAPTIVE_EXPOSURE_WIN_RATE_LOW
    normalized = (win_rate - ADAPTIVE_EXPOSURE_WIN_RATE_LOW) / wr_range
    return ADAPTIVE_EXPOSURE_MIN + normalized * (ADAPTIVE_EXPOSURE_MAX - ADAPTIVE_EXPOSURE_MIN)


def get_market_cap_tier(market_cap) -> str:
    """Classify a market cap value into a tier label.

    Handles None, NaN, strings, and other non-numeric types safely —
    all fall back to 'default' rather than crashing.
    """
    if market_cap is None:
        return 'default'
    try:
        market_cap = float(market_cap)
    except (TypeError, ValueError):
        return 'default'
    # math.isnan check: float('nan') comparisons always return False,
    # which would silently misclassify NaN as small_cap.
    if math.isnan(market_cap):
        return 'default'
    if market_cap >= MARKET_CAP_LARGE_THRESHOLD:
        return 'large_cap'
    if market_cap >= MARKET_CAP_MID_THRESHOLD:
        return 'mid_cap'
    return 'small_cap'


def get_limit_order_cushion(market_cap) -> float:
    """Return the limit-order cushion % for the given market cap."""
    tier = get_market_cap_tier(market_cap)
    return LIMIT_ORDER_CUSHION_BY_CAP.get(tier, LIMIT_ORDER_CUSHION_DEFAULT)


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
  Trailing:     {TRAILING_STOP_PCT*100:.0f}% (after +{TRAILING_TRIGGER_PCT*100:.0f}%)

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
