# automated_trading/utils.py
"""
Utility Functions for Automated Trading System

Provides common utilities including:
- Audit logging
- Date/time helpers
- File operations
- Validation functions
- Client order ID generation
"""

import os
import json
import logging
import fcntl
import tempfile
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, Optional, List, Tuple
import hashlib
import pytz

from . import config

logger = logging.getLogger(__name__)

# Timezone for market hours
EASTERN = pytz.timezone('US/Eastern')

# Cache for trading calendar (populated from Alpaca API)
# Format: {'YYYY-MM-DD': True/False}
_trading_calendar_cache: Dict[str, bool] = {}
_calendar_cache_updated: Optional[datetime] = None


def _get_lock_file(filepath: str) -> str:
    """Get the lock file path for a given file."""
    return f"{filepath}.lock"


# =============================================================================
# AUDIT LOGGING
# =============================================================================

def log_audit_event(
    event_type: str,
    data: Dict[str, Any],
    outcome: str = 'SUCCESS'
) -> None:
    """
    Log an audit event to the permanent audit trail.

    Uses JSONL format (one JSON object per line) for append-only efficiency.
    Audit logs should NEVER be deleted or rotated for compliance.
    Uses file locking to prevent corruption from concurrent writes.

    Args:
        event_type: Type of event (ORDER_SUBMITTED, POSITION_CLOSED, etc.)
        data: Event data dictionary
        outcome: SUCCESS, FAILURE, or ERROR
    """
    # Ensure data directory exists
    os.makedirs(config.DATA_DIR, exist_ok=True)

    event = {
        'timestamp': datetime.now().isoformat(),
        'event_type': event_type,
        'outcome': outcome,
        'trading_mode': config.TRADING_MODE,
        'data': data
    }

    lock_file = _get_lock_file(config.AUDIT_LOG_FILE)

    try:
        with open(lock_file, 'w') as lf:
            # Acquire exclusive lock for appending
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                with open(config.AUDIT_LOG_FILE, 'a') as f:
                    f.write(json.dumps(event) + '\n')
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
        # Don't raise - audit failure shouldn't stop trading


def read_recent_audit_events(
    event_type: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Read recent audit events from the log.

    Args:
        event_type: Optional filter by event type
        limit: Maximum events to return

    Returns:
        List of event dictionaries (most recent first)
    """
    if not os.path.exists(config.AUDIT_LOG_FILE):
        return []

    events = []
    try:
        with open(config.AUDIT_LOG_FILE, 'r') as f:
            lines = f.readlines()

        # Read from end (most recent)
        for line in reversed(lines):
            if len(events) >= limit:
                break

            try:
                event = json.loads(line.strip())
                if event_type is None or event.get('event_type') == event_type:
                    events.append(event)
            except json.JSONDecodeError:
                continue

    except Exception as e:
        logger.error(f"Failed to read audit log: {e}")

    return events


# =============================================================================
# CLIENT ORDER ID GENERATION
# =============================================================================

def generate_client_order_id(
    ticker: str,
    action: str,
    timestamp: Optional[datetime] = None
) -> str:
    """
    Generate a unique, deterministic client order ID.

    Format: {TICKER}-{ACTION}-{YYYYMMDD}-{HHMMSS}-{HASH}

    The hash provides uniqueness even if multiple orders for the same
    ticker/action are submitted in the same second.

    Args:
        ticker: Stock ticker symbol
        action: BUY, SELL, STOP, etc.
        timestamp: Optional timestamp (defaults to now)

    Returns:
        Unique client order ID string
    """
    if timestamp is None:
        timestamp = datetime.now()

    base = f"{ticker}-{action}-{timestamp.strftime('%Y%m%d-%H%M%S')}"

    # Add a short hash for uniqueness
    hash_input = f"{base}-{timestamp.microsecond}"
    short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:6]

    return f"{base}-{short_hash}"


def extract_info_from_client_order_id(client_order_id: str) -> Dict[str, Any]:
    """
    Extract information from a client order ID.

    Args:
        client_order_id: The client order ID string

    Returns:
        Dictionary with ticker, action, date, time components
    """
    try:
        parts = client_order_id.split('-')
        if len(parts) >= 4:
            return {
                'ticker': parts[0],
                'action': parts[1],
                'date': parts[2],
                'time': parts[3],
                'hash': parts[4] if len(parts) > 4 else None
            }
    except Exception:
        pass

    return {'raw': client_order_id}


# =============================================================================
# DATE/TIME HELPERS
# =============================================================================

def get_eastern_now() -> datetime:
    """Get current time in US Eastern timezone."""
    return datetime.now(EASTERN)


def update_trading_calendar(alpaca_client) -> None:
    """
    Update the trading calendar cache from Alpaca API.

    This should be called once at startup when the alpaca_client is available.
    The calendar is cached for the current month to avoid repeated API calls.

    Args:
        alpaca_client: AlpacaTradingClient instance
    """
    global _trading_calendar_cache, _calendar_cache_updated

    try:
        # Get calendar for current month plus next month
        now = get_eastern_now()
        start_date = now.replace(day=1)
        # Get next month's end (handle year boundary for Nov/Dec)
        next_month_2 = now.month + 2
        if next_month_2 > 12:
            end_date = now.replace(year=now.year + 1, month=next_month_2 - 12, day=1) - timedelta(days=1)
        else:
            end_date = now.replace(month=next_month_2, day=1) - timedelta(days=1)

        calendar = alpaca_client.get_trading_calendar(start_date, end_date)

        # Clear and update cache
        _trading_calendar_cache = {}
        for day in calendar:
            _trading_calendar_cache[day['date']] = True

        _calendar_cache_updated = now
        logger.info(f"Trading calendar updated: {len(_trading_calendar_cache)} trading days cached")

    except Exception as e:
        logger.warning(f"Failed to update trading calendar: {e}. Using weekday fallback.")


def is_trading_day(check_date: Optional[date] = None) -> bool:
    """
    Check if a date is a trading day (accounts for market holidays).

    Uses cached Alpaca calendar if available, otherwise falls back to weekday check.
    Call update_trading_calendar() at startup to enable holiday detection.

    Args:
        check_date: Date to check (defaults to today)

    Returns:
        True if the market is open on that day
    """
    if check_date is None:
        check_date = get_eastern_now().date()

    date_str = check_date.strftime('%Y-%m-%d')

    # Check cache first (if populated)
    if _trading_calendar_cache:
        # If date is in cache, it's a trading day
        # If not in cache but within cached range, it's NOT a trading day (holiday)
        if date_str in _trading_calendar_cache:
            return True

        # Check if date is within our cached range
        if _calendar_cache_updated:
            cache_start = _calendar_cache_updated.replace(day=1).date()
            # Handle year boundary for Nov/Dec
            next_month_2 = _calendar_cache_updated.month + 2
            if next_month_2 > 12:
                cache_end = _calendar_cache_updated.replace(year=_calendar_cache_updated.year + 1, month=next_month_2 - 12, day=1).date() - timedelta(days=1)
            else:
                cache_end = _calendar_cache_updated.replace(month=next_month_2, day=1).date() - timedelta(days=1)

            if cache_start <= check_date <= cache_end:
                # Date is in range but not in cache - it's a holiday/weekend
                return False

    # Fallback to simple weekday check
    return check_date.weekday() < 5


def is_market_hours() -> bool:
    """
    Check if current time is within regular market hours.

    Accounts for:
    - Weekends (Saturday/Sunday)
    - Market holidays (if calendar cache is populated)
    - Regular market hours (9:30 AM - 4:00 PM ET)

    Returns:
        True if market is currently open
    """
    now = get_eastern_now()

    # Check if it's a trading day (includes holiday check)
    if not is_trading_day(now.date()):
        return False

    current_time = now.time()
    return config.MARKET_OPEN_TIME <= current_time <= config.MARKET_CLOSE_TIME


def is_trading_window() -> bool:
    """
    Check if current time is within our trading execution window.

    We don't trade in the first 5 minutes or last 30 minutes.
    Also checks for holidays via is_trading_day().

    Returns:
        True if within trading window
    """
    now = get_eastern_now()

    # Check if it's a trading day (includes holiday check)
    if not is_trading_day(now.date()):
        return False

    current_time = now.time()
    return config.EXECUTION_START_TIME <= current_time <= config.EXECUTION_END_TIME


def minutes_until_market_close() -> int:
    """
    Calculate minutes until market close.

    Returns:
        Minutes until close, or -1 if market is closed
    """
    if not is_market_hours():
        return -1

    now = get_eastern_now()
    close_dt = now.replace(
        hour=config.MARKET_CLOSE_TIME.hour,
        minute=config.MARKET_CLOSE_TIME.minute,
        second=0,
        microsecond=0
    )

    delta = close_dt - now
    return int(delta.total_seconds() / 60)


def format_datetime_for_display(dt: datetime) -> str:
    """Format datetime for display in logs/emails."""
    if dt.tzinfo is None:
        dt = EASTERN.localize(dt)
    return dt.strftime('%Y-%m-%d %I:%M %p ET')


def format_date_for_display(d: date) -> str:
    """Format date for display."""
    return d.strftime('%B %d, %Y')


# =============================================================================
# FILE OPERATIONS (with file locking for concurrent access safety)
# =============================================================================

def load_json_file(filepath: str, default: Any = None) -> Any:
    """
    Safely load a JSON file with file locking.

    Uses shared (read) lock to prevent reading while another process is writing.

    Args:
        filepath: Path to JSON file
        default: Default value if file doesn't exist or is invalid

    Returns:
        Parsed JSON data or default
    """
    if not os.path.exists(filepath):
        return default

    lock_file = _get_lock_file(filepath)

    try:
        # Create lock file if it doesn't exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(lock_file, 'w') as lf:
            # Acquire shared lock (allows multiple readers)
            fcntl.flock(lf.fileno(), fcntl.LOCK_SH)
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        return default
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        return default


def save_json_file(filepath: str, data: Any, indent: int = 2) -> bool:
    """
    Safely save data to a JSON file with file locking.

    Uses exclusive lock and atomic write (write to temp, then rename).
    Creates backup before overwriting for additional safety.

    Args:
        filepath: Path to JSON file
        data: Data to save
        indent: JSON indentation

    Returns:
        True if successful
    """
    # Ensure directory exists
    dir_path = os.path.dirname(filepath)
    os.makedirs(dir_path, exist_ok=True)

    lock_file = _get_lock_file(filepath)

    try:
        with open(lock_file, 'w') as lf:
            # Acquire exclusive lock (blocks other readers and writers)
            fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            try:
                # Create backup if file exists
                if os.path.exists(filepath):
                    backup_path = f"{filepath}.bak"
                    try:
                        with open(filepath, 'r') as f:
                            backup_data = f.read()
                        with open(backup_path, 'w') as f:
                            f.write(backup_data)
                    except Exception as e:
                        logger.warning(f"Failed to create backup of {filepath}: {e}")

                # Write to temp file first (atomic write pattern)
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=dir_path,
                    prefix='.tmp_',
                    suffix='.json'
                )
                try:
                    with os.fdopen(temp_fd, 'w') as f:
                        json.dump(data, f, indent=indent, default=str)

                    # Atomic rename (on same filesystem)
                    os.replace(temp_path, filepath)
                    return True

                except Exception:
                    # Clean up temp file on error
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    raise

            finally:
                fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

    except Exception as e:
        logger.error(f"Failed to save {filepath}: {e}")
        return False


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_ticker(ticker: str) -> Tuple[bool, str]:
    """
    Validate a ticker symbol.

    Args:
        ticker: Ticker symbol to validate

    Returns:
        Tuple of (is_valid, message)
    """
    if not ticker:
        return False, "Empty ticker"

    if not ticker.isalpha():
        return False, "Ticker contains non-alpha characters"

    if len(ticker) > 5:
        return False, "Ticker too long (max 5 characters)"

    return True, "Valid"


def validate_price(price: float, context: str = "price") -> Tuple[bool, str]:
    """
    Validate a price value.

    Args:
        price: Price to validate
        context: Description for error messages

    Returns:
        Tuple of (is_valid, message)
    """
    if price is None:
        return False, f"{context} is None"

    try:
        price = float(price)
    except (TypeError, ValueError):
        return False, f"{context} is not a number"

    if price <= 0:
        return False, f"{context} must be positive"

    if price > 100000:
        return False, f"{context} seems unreasonably high (${price})"

    return True, "Valid"


def validate_quantity(qty: int) -> Tuple[bool, str]:
    """
    Validate a share quantity.

    Args:
        qty: Quantity to validate

    Returns:
        Tuple of (is_valid, message)
    """
    if qty is None:
        return False, "Quantity is None"

    try:
        qty = int(qty)
    except (TypeError, ValueError):
        return False, "Quantity is not an integer"

    if qty <= 0:
        return False, "Quantity must be positive"

    if qty > 100000:
        return False, f"Quantity seems unreasonably high ({qty})"

    return True, "Valid"


# =============================================================================
# FORMATTING HELPERS
# =============================================================================

def format_currency(value: float) -> str:
    """Format a value as currency."""
    if value is None:
        return "$0.00"

    if abs(value) >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    elif abs(value) >= 1_000:
        return f"${value/1_000:.2f}K"
    else:
        return f"${value:,.2f}"


def format_percentage(value: float, include_sign: bool = True) -> str:
    """Format a value as percentage."""
    if value is None:
        return "0.00%"

    if include_sign and value > 0:
        return f"+{value:.2f}%"
    return f"{value:.2f}%"


def format_shares(qty: int) -> str:
    """Format share quantity."""
    if qty == 1:
        return "1 share"
    return f"{qty:,} shares"


# =============================================================================
# CALCULATION HELPERS
# =============================================================================

def calculate_position_pct(position_value: float, portfolio_value: float) -> float:
    """Calculate position as percentage of portfolio."""
    if portfolio_value <= 0:
        return 0.0
    return (position_value / portfolio_value) * 100


def calculate_pnl_pct(entry_price: float, exit_price: float) -> float:
    """Calculate P&L percentage."""
    if entry_price <= 0:
        return 0.0
    return ((exit_price - entry_price) / entry_price) * 100


def calculate_stop_price(entry_price: float, stop_pct: float) -> float:
    """Calculate stop loss price."""
    return entry_price * (1 - stop_pct)


def calculate_target_price(entry_price: float, target_pct: float) -> float:
    """Calculate take profit price."""
    return entry_price * (1 + target_pct)


# =============================================================================
# SAFETY CHECKS
# =============================================================================

def is_safe_to_trade() -> Tuple[bool, str]:
    """
    Check if it's safe to trade.

    Returns:
        Tuple of (is_safe, reason)
    """
    # Check trading enabled
    if not config.TRADING_ENABLED:
        return False, "Trading is disabled (TRADING_ENABLED=false)"

    # Check market hours
    if not is_market_hours():
        return False, "Market is closed"

    # Check trading window
    if not is_trading_window():
        mins_to_close = minutes_until_market_close()
        if mins_to_close >= 0 and mins_to_close < 30:
            return False, f"Too close to market close ({mins_to_close} minutes)"
        return False, "Outside trading window"

    return True, "Safe to trade"


if __name__ == '__main__':
    # Test utilities
    print(f"Eastern Time: {format_datetime_for_display(get_eastern_now())}")
    print(f"Market Hours: {is_market_hours()}")
    print(f"Trading Window: {is_trading_window()}")
    print(f"Minutes to Close: {minutes_until_market_close()}")

    test_id = generate_client_order_id('AAPL', 'BUY')
    print(f"Client Order ID: {test_id}")
    print(f"Extracted: {extract_info_from_client_order_id(test_id)}")
