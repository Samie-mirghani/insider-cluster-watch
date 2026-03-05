# jobs/signal_filters.py
"""
Centralized signal filters for shell company, M&A, and stale ticker detection.

Used by:
- process_signals.py (batch filtering pipeline)
- paper_trade.py (per-signal validation)
- execute_trades.py (per-signal validation via automated_trading)

All filter functions are stateless and side-effect free (except logging).
Cache I/O for M&A status is handled by the caller.
"""

import logging
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)


def check_shell_company(
    ticker: str,
    sector: str,
    industry: str,
    company_name: str,
    blocked_sectors: list,
    name_patterns: list,
) -> Tuple[bool, str]:
    """
    Check if a signal is a shell company or SPAC.

    Returns:
        (is_shell, reason) — True means REJECT this signal.
    """
    sector = sector or ''
    industry = industry or ''
    company_name = company_name or ''

    # Check 1: Blocked sector
    if sector in blocked_sectors or industry in blocked_sectors:
        return True, f"sector '{sector or industry}' is a shell company/SPAC"

    # Check 2: Company name matches SPAC/acquisition vehicle patterns
    name_upper = company_name.upper()
    for pattern in name_patterns:
        if pattern.upper() in name_upper:
            return True, f"company name '{company_name}' matches SPAC pattern '{pattern}'"

    return False, ''


def check_stale_ticker(
    ticker: str,
    current_price: Optional[float],
    market_cap: Optional[float],
    max_stale_days: int = 5,
    price_history: Optional[pd.DataFrame] = None,
) -> Tuple[bool, str]:
    """
    Check if a ticker is stale/delisted.

    Args:
        ticker: Stock ticker symbol.
        current_price: Current price (may be None/NaN/0 for delisted).
        market_cap: Market cap (may be None/NaN/0 for delisted).
        max_stale_days: Maximum days since last trade before rejection.
        price_history: Optional pre-fetched yfinance DataFrame to avoid redundant calls.

    Returns:
        (is_stale, reason) — True means REJECT this signal.
    """
    price_missing = current_price is None or (isinstance(current_price, float) and pd.isna(current_price)) or current_price <= 0
    cap_missing = market_cap is None or (isinstance(market_cap, float) and pd.isna(market_cap)) or market_cap <= 0

    # If both price and market cap are missing, the ticker is likely delisted
    if price_missing and cap_missing:
        return True, "no price or market cap data (likely delisted or non-trading)"

    # Verify ticker has recent trading activity
    hist = price_history
    if hist is None:
        try:
            hist = yf.download(ticker, period=f'{max_stale_days + 5}d', progress=False)
        except Exception as e:
            logger.debug(f"Stale ticker check failed for {ticker}: {e}")
            return False, ''  # Fail open

    if hist is None or hist.empty or len(hist) == 0:
        return True, f"no trading history in last {max_stale_days} days (likely delisted)"

    try:
        last_trade_date = hist.index[-1]
        if hasattr(last_trade_date, 'tz_localize'):
            last_trade_date = last_trade_date.tz_localize(None) if last_trade_date.tzinfo else last_trade_date
        days_since_trade = (datetime.now() - pd.Timestamp(last_trade_date).to_pydatetime()).days
        if days_since_trade > max_stale_days:
            return True, f"last traded {days_since_trade} days ago (>{max_stale_days}d limit, likely delisted)"
    except Exception as e:
        logger.debug(f"Stale ticker date check failed for {ticker}: {e}")

    return False, ''


def check_ma_target(
    ticker: str,
    company_name: str,
    ma_cache: Optional[Dict] = None,
    ma_cache_ttl_days: int = 7,
    search_fn=None,
    profile_fn=None,
    enable_heuristic: bool = True,
    atr_threshold_pct: float = 0.3,
    heuristic_lookback_days: int = 10,
    min_market_cap_for_heuristic: float = 500_000_000,
    market_cap: Optional[float] = None,
    price_history: Optional[pd.DataFrame] = None,
) -> Tuple[bool, str, Optional[Dict]]:
    """
    Check if a ticker is an M&A/acquisition target.

    Uses a two-tier approach:
      A) FMP M&A search API (primary)
      B) Price-action ATR heuristic (fallback, only for mid+ cap stocks)

    Args:
        ticker: Stock ticker symbol.
        company_name: Company name for FMP search.
        ma_cache: Dict of cached M&A results (keyed by ticker).
        ma_cache_ttl_days: Cache TTL in days.
        search_fn: Callable for FMP M&A search (accepts company name string).
        profile_fn: Callable for FMP profile lookup (accepts ticker string).
        enable_heuristic: Whether to run ATR fallback.
        atr_threshold_pct: ATR percentage threshold for heuristic.
        heuristic_lookback_days: Days of history for ATR calculation.
        min_market_cap_for_heuristic: Skip heuristic for stocks below this cap
            (avoids false positives on low-vol micro/small caps and preferred shares).
        market_cap: Current market cap of the stock.
        price_history: Optional pre-fetched yfinance DataFrame.

    Returns:
        (is_target, reason, cache_entry) — cache_entry is the dict to store in cache.
    """
    company_name = company_name or ''

    # If company name is empty or just the ticker, try FMP profile
    if (not company_name or company_name == ticker) and profile_fn:
        try:
            profile = profile_fn(ticker)
            if profile:
                company_name = profile.get('companyName', '') or ''
        except Exception:
            pass

    # Check cache first
    if ma_cache:
        cached = ma_cache.get(ticker)
        if cached:
            try:
                cache_age = (datetime.now() - datetime.fromisoformat(cached.get('checked', '2000-01-01'))).days
                if cache_age < ma_cache_ttl_days:
                    return cached.get('is_target', False), cached.get('details', ''), None
            except Exception:
                pass

    # Option A: FMP M&A API search
    is_ma_target = False
    ma_details = ''

    if company_name and search_fn:
        try:
            ma_results = search_fn(company_name)
            if ma_results:
                for deal in ma_results:
                    target_symbol = (deal.get('targetedSymbol') or '').upper()
                    # Use ticker match as primary (exact)
                    if target_symbol == ticker.upper():
                        is_ma_target = True
                        acquirer = deal.get('companyName', 'Unknown acquirer')
                        tx_date = deal.get('transactionDate', 'Unknown date')
                        ma_details = f"target of {acquirer} (filed {tx_date})"
                        break

                    # Fallback: name match — but require the target name to contain
                    # our FULL company name AND our company name is long enough to
                    # avoid false substring matches (e.g. "US" matching "Citrus")
                    if not is_ma_target:
                        target_name = (deal.get('targetedCompanyName') or '').upper()
                        if company_name and len(company_name) >= 6 and company_name.upper() in target_name:
                            is_ma_target = True
                            acquirer = deal.get('companyName', 'Unknown acquirer')
                            tx_date = deal.get('transactionDate', 'Unknown date')
                            ma_details = f"target of {acquirer} (filed {tx_date})"
                            break
        except Exception as e:
            logger.debug(f"M&A search failed for {ticker}: {e}")

    # Option B: Price-action ATR heuristic (only if API found nothing)
    # Guard: skip for small caps and missing market cap to avoid false positives
    # on preferred shares, units, and low-vol micro-caps.
    if not is_ma_target and enable_heuristic:
        if market_cap and market_cap >= min_market_cap_for_heuristic:
            try:
                hist = price_history
                if hist is None:
                    hist = yf.download(ticker, period=f'{heuristic_lookback_days + 5}d', progress=False)

                if hist is not None and not hist.empty and len(hist) >= heuristic_lookback_days:
                    high_col = hist['High']
                    low_col = hist['Low']
                    close_col = hist['Close']

                    # Handle multi-level columns from newer yfinance
                    if isinstance(high_col, pd.DataFrame):
                        high_col = high_col.squeeze()
                    if isinstance(low_col, pd.DataFrame):
                        low_col = low_col.squeeze()
                    if isinstance(close_col, pd.DataFrame):
                        close_col = close_col.squeeze()

                    # True Range = max(H-L, |H-PrevClose|, |L-PrevClose|)
                    h = high_col.tail(heuristic_lookback_days)
                    l = low_col.tail(heuristic_lookback_days)
                    prev_c = close_col.shift(1).tail(heuristic_lookback_days)

                    tr1 = h - l
                    tr2 = (h - prev_c).abs()
                    tr3 = (l - prev_c).abs()
                    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

                    atr = float(true_range.mean())
                    avg_price = float(close_col.tail(heuristic_lookback_days).mean())
                    if avg_price > 0:
                        atr_pct = (atr / avg_price) * 100
                        if atr_pct < atr_threshold_pct:
                            is_ma_target = True
                            ma_details = (
                                f"abnormally low volatility "
                                f"(ATR {atr_pct:.2f}% < {atr_threshold_pct}% threshold, "
                                f"likely acquisition-pinned)"
                            )
            except Exception as e:
                logger.debug(f"Acquisition heuristic failed for {ticker}: {e}")

    # Build cache entry
    cache_entry = {
        'is_target': is_ma_target,
        'details': ma_details,
        'checked': datetime.now().isoformat()
    }

    return is_ma_target, ma_details, cache_entry


def prefetch_price_history(tickers: list, period: str = '20d') -> Dict[str, pd.DataFrame]:
    """
    Batch-fetch price history for multiple tickers to avoid per-signal yfinance calls.

    Returns:
        Dict mapping ticker → DataFrame of price history.
    """
    results = {}
    if not tickers:
        return results

    try:
        # yfinance supports batch download
        data = yf.download(tickers, period=period, progress=False, group_by='ticker')
        if data.empty:
            return results

        if len(tickers) == 1:
            # Single ticker — data is not grouped
            results[tickers[0]] = data
        else:
            # Multiple tickers — data is grouped by ticker
            for t in tickers:
                try:
                    ticker_data = data[t].dropna(how='all')
                    if not ticker_data.empty:
                        results[t] = ticker_data
                except (KeyError, Exception):
                    pass
    except Exception as e:
        logger.debug(f"Batch price history fetch failed: {e}")

    return results
