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

# Multi-Signal Detection Settings
ENABLE_MULTI_SIGNAL = True  # Enable politician and institutional detection
ENABLE_POLITICIAN_SCRAPING = True  # Scrape Capitol Trades (requires selenium and ChromeDriver)
ENABLE_13F_CHECKING = True  # Check 13F filings (with improved error handling and caching)

# Politician Trading
POLITICIAN_LOOKBACK_DAYS = 30  # Days to look back for politician trades
POLITICIAN_MAX_PAGES = 5  # Max pages to scrape from Capitol Trades
MIN_POLITICIANS_FOR_CLUSTER = 2  # Min politicians needed for cluster signal

# Signal Tier Thresholds
TIER_1_MIN_SIGNALS = 3  # Tier 1: 3+ signals (highest conviction)
TIER_2_MIN_SIGNALS = 2  # Tier 2: 2 signals (high conviction)

# SEC EDGAR Settings
SEC_USER_AGENT = "InsiderClusterWatch admin@example.com"  # Required by SEC

# Multi-Signal Position Sizing (overrides standard sizing for multi-signal trades)
MULTI_SIGNAL_POSITION_SIZES = {
    'tier1': 1.0,   # Full position (3+ signals)
    'tier2': 0.75,  # 75% position (2 signals)
    'tier3': 0.50,  # 50% position (1 strong signal)
    'tier4': 0.25   # 25% position (watch list)
}

# Multi-Signal Risk Management
MULTI_SIGNAL_STOP_LOSS = {
    'tier1': 0.12,  # -12% stop for highest conviction
    'tier2': 0.10,  # -10% stop
    'tier3': 0.08,  # -8% stop
    'tier4': 0.06   # -6% stop (tighter for lower conviction)
}