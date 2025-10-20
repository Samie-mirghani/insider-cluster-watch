# jobs/config.py
"""
Configuration for Paper Trading System

Centralized configuration for all paper trading parameters.
"""

# Portfolio Settings
STARTING_CAPITAL = 10000  # $10k starting capital

# Position Sizing
MAX_POSITION_PCT = 0.05  # 5% max per position
MAX_TOTAL_EXPOSURE = 0.25  # 25% max total exposure
MAX_POSITIONS = 5  # Max 5 concurrent positions

# Risk Management
STOP_LOSS_PCT = 0.05  # 5% initial stop loss
TAKE_PROFIT_PCT = 0.08  # 8% profit target
TRAILING_STOP_PCT = 0.05  # 5% trailing stop
TRAILING_TRIGGER_PCT = 0.03  # Enable trailing after +3% gain

# Position Scaling
ENABLE_SCALING = True  # Enable 2-tranche entries
SCALING_INITIAL_PCT = 0.6  # 60% first tranche
SCALING_SECOND_PCT = 0.4  # 40% second tranche
SCALING_TRIGGER_PCT = 0.02  # -2% pullback triggers second tranche
SCALING_EXPIRY_DAYS = 5  # Second tranche expires after 5 days

# Time Limits
TIME_STOP_DAYS = 21  # Exit after 21 days
MAX_DAILY_TRADES = 3  # Limit new positions per day

# Health Monitoring
MAX_DAILY_LOSS_PCT = 5.0  # Alert if down >5% in one day
MAX_DRAWDOWN_ALERT = 10.0  # Alert if drawdown >10%
MIN_WIN_RATE_ALERT = 35.0  # Alert if win rate <35%
MAX_EXPOSURE_ALERT = 30.0  # Alert if exposure >30%

# Logging
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR
LOG_FILE = 'data/paper_trading.log'