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
SEC_USER_AGENT = "InsiderClusterWatch samie.mirghani@gmail.com"  # Required by SEC

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

# Follow-the-Smart-Money Scoring Settings
ENABLE_INSIDER_SCORING = True  # Enable tracking of individual insider performance
INSIDER_LOOKBACK_YEARS = 3  # Years of history to analyze for insider performance
MIN_TRADES_FOR_INSIDER_SCORE = 3  # Minimum trades needed to calculate reliable score
INSIDER_OUTCOME_UPDATE_BATCH_SIZE = 50  # Max trades to update per run (rate limit protection)
INSIDER_API_RATE_LIMIT_DELAY = 0.3  # Delay between API calls in seconds
INSIDER_SCORE_WEIGHT = 0.15  # Weight of insider score in overall ranking (0-1)

# Insider Score Multiplier Range
# Top performers (score 100) get 2.0x conviction boost
# Average performers (score 50) get 1.0x (no change)
# Poor performers (score 0) get 0.5x reduction
INSIDER_SCORE_MULTIPLIER_MIN = 0.5
INSIDER_SCORE_MULTIPLIER_MAX = 2.0

# 13F Data Settings
SEC_13F_CACHE_HOURS = 168  # Cache duration in hours (168 hours = 7 days)
# 13F filings are quarterly, so weekly refresh is sufficient
# Set to lower value if you want more frequent checks (minimum 24 hours recommended)

# Realistic Paper Trading Settings
REALISTIC_TRADING_MODE = True  # Enable realistic trading constraints
MARKET_OPEN_HOUR = 9  # 9:30 AM ET
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16  # 4:00 PM ET
MARKET_CLOSE_MINUTE = 0
TRADING_COMMISSION_PER_SHARE = 0.0  # Most brokers are $0, but can set to 0.005 for realism
TRADING_SLIPPAGE_PCT = 0.15  # 0.15% slippage on entry/exit (realistic for mid-cap stocks)
MIN_ENTRY_SLIPPAGE_PCT = 0.10  # Minimum slippage even with good liquidity
MAX_ENTRY_SLIPPAGE_PCT = 0.30  # Maximum slippage for low liquidity
USE_OPENING_PRICE_FOR_ENTRY = True  # Use next day's open instead of current close
TRAIL_STOP_EXECUTION_SLIPPAGE_PCT = 0.20  # Slippage when hitting trailing stops