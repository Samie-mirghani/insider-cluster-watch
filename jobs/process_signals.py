# jobs/process_signals.py
"""
Filter buys, compute cluster and conviction scores, determine suggested action and rationale,
and flag urgent signals according to thresholds.

NEW FEATURES:
- Sector analysis and tracking
- Enhanced quality filters
- Pattern detection (accelerating buys, CEO+CFO patterns, etc.)
"""

import pandas as pd
import math
import time
from datetime import timedelta, datetime
import yfinance as yf  # Fallback only
import config
from sector_analyzer import SectorAnalyzer
import logging
from fmp_api import (
    fetch_profiles_batch,
    get_analytics_summary,
    save_analytics
)
from ticker_validator import get_failed_ticker_cache

# Suppress yfinance error spam for delisted stocks
logging.getLogger('yfinance').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ============================================================================
# SIGNAL DETECTION ENHANCEMENT CONFIGURATION
# ============================================================================
# These thresholds control quality filters and can be tuned for different
# market conditions. Holiday mode automatically reduces these by 20%.

# Fix 1: Mega-Cluster Exception - Bypass volume filter for rare high-conviction clusters
MEGA_CLUSTER_MIN_INSIDERS = 3              # Minimum insiders for mega-cluster
MEGA_CLUSTER_MIN_TOTAL_VALUE = 1_000_000   # Minimum total $ for mega-cluster
MEGA_CLUSTER_MIN_AVG_PER_INSIDER = 300_000 # Minimum average per insider (conviction check)

# Fix 2: Dynamic $50k Threshold - Scale minimum purchase based on cluster size
DYNAMIC_THRESHOLD_BASE = 50_000            # Base threshold for small clusters (1-3 insiders)
DYNAMIC_THRESHOLD_MEDIUM = 40_000          # For medium clusters (4-6 insiders)
DYNAMIC_THRESHOLD_LARGE = 30_000           # For large clusters (7+ insiders)
DYNAMIC_THRESHOLD_MEDIUM_MIN_TOTAL = 150_000   # Minimum total for medium threshold
DYNAMIC_THRESHOLD_LARGE_MIN_TOTAL = 200_000    # Minimum total for large threshold

# Fix 3: Holiday Mode - Reduce thresholds during slow trading periods
HOLIDAY_THRESHOLD_REDUCTION = 0.20         # 20% reduction during holidays

# Holiday periods (month, day tuples)
HOLIDAY_PERIODS = [
    {'start': (12, 20), 'end': (1, 5), 'name': 'Year-End Holidays'},
    {'start': (11, 20), 'end': (11, 30), 'name': 'Thanksgiving Week'},
    {'start': (7, 1), 'end': (8, 15), 'name': 'Summer Slowdown'},
    {'start': (4, 1), 'end': (4, 20), 'name': 'Tax Season'},
]

# Quality filter thresholds (used in apply_quality_filters)
MIN_STOCK_PRICE = 2.0                      # No penny stocks
MIN_AVERAGE_VOLUME = 100_000               # Legacy: Liquidity requirement (shares/day) - deprecated
MAX_RECENT_DRAWDOWN = -0.40                # Don't buy falling knives (40% drop)

# Fix 4: Tiered Dollar Volume Thresholds - Fair liquidity assessment across price ranges
# Uses daily dollar volume (shares × price) instead of share volume for better normalization
DOLLAR_VOLUME_THRESHOLD_LARGE = 100_000    # 7+ insiders: $100k/day minimum
DOLLAR_VOLUME_THRESHOLD_MEDIUM = 150_000   # 4-6 insiders: $150k/day minimum
DOLLAR_VOLUME_THRESHOLD_SMALL = 200_000    # 1-3 insiders: $200k/day minimum

# ============================================================================

def is_holiday_period(check_date=None):
    """
    Check if the given date falls within any defined holiday period.

    Args:
        check_date: datetime object to check (defaults to today)

    Returns:
        tuple: (is_holiday, holiday_name, days_into_period)
    """
    if check_date is None:
        check_date = datetime.now()

    month = check_date.month
    day = check_date.day

    for period in HOLIDAY_PERIODS:
        start_month, start_day = period['start']
        end_month, end_day = period['end']

        # Handle year-boundary periods (e.g., Dec 20 - Jan 5)
        if start_month > end_month:
            # Period crosses year boundary
            if (month == start_month and day >= start_day) or \
               (month == end_month and day <= end_day) or \
               (month > start_month or month < end_month):
                # Calculate days into period
                if month == start_month:
                    days_into = day - start_day
                elif month == end_month:
                    # Days from start month + days in current month
                    days_in_start_month = 31 if start_month == 12 else 30
                    days_into = (days_in_start_month - start_day) + day
                else:
                    days_into = 0  # Middle of period

                return (True, period['name'], max(0, days_into))
        else:
            # Normal period within same year
            if month == start_month and month == end_month:
                if start_day <= day <= end_day:
                    return (True, period['name'], day - start_day)
            elif month == start_month and day >= start_day:
                return (True, period['name'], day - start_day)
            elif month == end_month and day <= end_day:
                return (True, period['name'], day - start_day)
            elif start_month < month < end_month:
                return (True, period['name'], 0)

    return (False, None, 0)

def apply_holiday_adjustment(value, reduction=HOLIDAY_THRESHOLD_REDUCTION):
    """
    Apply holiday mode reduction to a threshold value.

    Args:
        value: Original threshold value
        reduction: Reduction percentage (default 20%)

    Returns:
        Adjusted value (reduced by specified percentage)
    """
    return value * (1 - reduction)

def get_dynamic_min_per_insider(cluster_count, total_value, apply_holiday=True):
    """
    Calculate dynamic minimum per-insider threshold based on cluster size.

    Fix 2: Larger clusters (more insiders) get lower per-insider requirements,
    but must meet minimum total value thresholds for conviction.

    Args:
        cluster_count: Number of insiders in cluster
        total_value: Total $ value of cluster
        apply_holiday: Whether to apply holiday mode reduction

    Returns:
        Minimum per-insider threshold
    """
    # Base thresholds
    if cluster_count >= 7 and total_value >= DYNAMIC_THRESHOLD_LARGE_MIN_TOTAL:
        threshold = DYNAMIC_THRESHOLD_LARGE
    elif cluster_count >= 4 and total_value >= DYNAMIC_THRESHOLD_MEDIUM_MIN_TOTAL:
        threshold = DYNAMIC_THRESHOLD_MEDIUM
    else:
        threshold = DYNAMIC_THRESHOLD_BASE

    # Apply holiday mode if active
    if apply_holiday:
        is_holiday, holiday_name, days_into = is_holiday_period()
        if is_holiday:
            threshold = apply_holiday_adjustment(threshold)

    return threshold

def get_dollar_volume_threshold(cluster_count, total_value, apply_holiday=True):
    """
    Calculate tiered dollar volume threshold based on cluster size.

    Fix 4: Larger clusters (more diversified conviction) get lower liquidity requirements.
    Uses dollar volume (shares × price) for fair comparison across price ranges.

    Args:
        cluster_count: Number of insiders in cluster
        total_value: Total $ value of cluster (for validation)
        apply_holiday: Whether to apply holiday mode reduction

    Returns:
        Minimum daily dollar volume threshold
    """
    # Determine tier based on cluster size and total value
    if cluster_count >= 7 and total_value >= DYNAMIC_THRESHOLD_LARGE_MIN_TOTAL:
        threshold = DOLLAR_VOLUME_THRESHOLD_LARGE
    elif cluster_count >= 4 and total_value >= DYNAMIC_THRESHOLD_MEDIUM_MIN_TOTAL:
        threshold = DOLLAR_VOLUME_THRESHOLD_MEDIUM
    else:
        threshold = DOLLAR_VOLUME_THRESHOLD_SMALL

    # Apply holiday mode if active
    if apply_holiday:
        is_holiday, holiday_name, days_into = is_holiday_period()
        if is_holiday:
            threshold = apply_holiday_adjustment(threshold)

    return threshold

ROLE_WEIGHT = {
    'CEO': 3.0,
    'CFO': 2.5,
    'PRES': 2.0,
    'DIRECTOR': 1.5,
    'VP': 1.2,
    'OFFICER': 1.0,
}

# Title importance for sorting (higher = more important)
TITLE_PRIORITY = {
    'CEO': 100,
    'CFO': 90,
    'PRES': 80,
    'COO': 75,
    'CHAIRMAN': 70,
    'VICE CHAIRMAN': 65,
    'DIRECTOR': 50,
    'VP': 40,
    'SVP': 45,
    'EVP': 48,
    'OFFICER': 30,
    'TREASURER': 35,
    'SECRETARY': 32,
}

def _clean_title_artifacts(title):
    """
    Remove common artifacts from insider titles.

    Cleans:
    - Numeric suffixes: "Ceo(1)" -> "Ceo"
    - Multiple spaces
    - Leading/trailing whitespace
    - Parenthetical numbers indicating multiple roles
    """
    import re
    if not title or not isinstance(title, str):
        return ''

    # Remove numeric suffixes in parentheses: "Ceo(1)" -> "Ceo"
    title = re.sub(r'\(\d+\)\s*$', '', title)
    title = re.sub(r'\(\d+\)', '', title)  # Also remove from middle

    # Remove multiple spaces
    title = re.sub(r'\s+', ' ', title)

    # Clean up whitespace
    title = title.strip()

    return title

def normalize_title(title):
    """
    Normalize insider title to standard category.

    Handles special cases:
    - "10%" -> "10% Owner"
    - "Ceo(1)" -> "CEO"
    - Various title formats
    """
    if not title or not isinstance(title, str):
        return 'OFFICER'

    # Clean artifacts first
    title = _clean_title_artifacts(title)

    # Handle special case: "10%" or similar ownership percentages
    if title.strip() == '10%' or title.strip().startswith('10%'):
        return 'OFFICER'  # Categorize as officer for weighting

    t = title.upper()
    if 'CEO' in t: return 'CEO'
    if 'CFO' in t: return 'CFO'
    if 'PRES' in t or 'PRESIDENT' in t: return 'PRES'
    if 'DIRECT' in t: return 'DIRECTOR'
    if 'VP' in t and 'SVP' not in t: return 'VP'
    return 'OFFICER'

def expand_title(title):
    """
    Expand abbreviated titles to full readable forms.

    Examples:
        "Exec COB" -> "Executive Chairman of the Board"
        "Dir" -> "Director"
        "Pres, CEO" -> "President, CEO"
        "SVP & CFO" -> "Senior Vice President, CFO"
        "Ceo(1)" -> "CEO"
        "10%" -> "10% Owner"
    """
    if not title or not isinstance(title, str):
        return "Insider"

    # Clean artifacts first (removes "(1)" suffixes, etc.)
    title = _clean_title_artifacts(title)

    if not title:
        return "Insider"

    # Handle special case: "10%" or similar ownership percentages
    if title.strip() == '10%' or title.strip().startswith('10%'):
        return "10% Owner"

    # Handle "See Remarks" - a placeholder when actual title is in Form 4 remarks
    if "see remarks" in title.lower():
        return "Insider"

    # Common abbreviation mappings
    expansions = {
        r'\bExec\b': 'Executive',
        r'\bCOB\b': 'Chairman of the Board',
        r'\bDir\b': 'Director',
        r'\bPres\b': 'President',
        r'\bVP\b': 'Vice President',
        r'\bSVP\b': 'Senior Vice President',
        r'\bEVP\b': 'Executive Vice President',
        r'\bCEO\b': 'CEO',
        r'\bCFO\b': 'CFO',
        r'\bCOO\b': 'COO',
        r'\bCTO\b': 'CTO',
        r'\bCIO\b': 'CIO',
        r'\bChm\b': 'Chairman',
        r'\bChmn\b': 'Chairman',
        r'\bTreas\b': 'Treasurer',
        r'\bSec\b': 'Secretary',
        r'\bGen\b': 'General',
        r'\bMgr\b': 'Manager',
        r'\bOp\b': 'Operating',
        r'\bOps\b': 'Operations',
        r'\bFin\b': 'Financial',
        r'\bBus\b': 'Business',
        r'\bDev\b': 'Development',
    }

    import re
    expanded = title
    for abbrev, full in expansions.items():
        expanded = re.sub(abbrev, full, expanded, flags=re.IGNORECASE)

    # Clean up punctuation
    expanded = expanded.replace('&', ',').replace('  ', ' ').strip()

    # Capitalize properly
    words = expanded.split()
    capitalized = []
    for word in words:
        if word.upper() in ['CEO', 'CFO', 'COO', 'CTO', 'CIO', 'VP', 'SVP', 'EVP']:
            capitalized.append(word.upper())
        elif word in [',', '/', '-']:
            capitalized.append(word)
        else:
            capitalized.append(word.capitalize())

    return ' '.join(capitalized)

def normalize_name(name):
    """
    Normalize insider names from "Last First Middle" to "First Middle Last" format.

    Examples:
        "Brown Kyle Steven" -> "Kyle Steven Brown"
        "Estes Ronald E." -> "Ronald E. Estes"
        "Smith John" -> "John Smith"
    """
    if not name or not isinstance(name, str):
        return "Unknown"

    # Clean up the name
    name = name.strip()

    # Split by comma first (some names might be "Last, First")
    if ',' in name:
        parts = [p.strip() for p in name.split(',')]
        if len(parts) == 2:
            # "Last, First" -> "First Last"
            return f"{parts[1]} {parts[0]}"

    # Split by spaces
    parts = name.split()

    if len(parts) <= 1:
        return name

    # Heuristic: If last part looks like a last name (all caps or title case),
    # and first part looks like last name (all caps or starts with capital),
    # assume format is "Last First Middle..."

    # Common pattern: "BROWN Kyle Steven" or "Brown Kyle Steven"
    # We want: "Kyle Steven Brown"

    # If first word is all caps or title case, and there are at least 2 words,
    # assume it's "Last First [Middle]" format
    if len(parts) >= 2:
        first_word = parts[0]
        # Check if first word looks like a last name (capitalized)
        if first_word[0].isupper():
            # Rearrange: move first word to end
            return ' '.join(parts[1:] + [parts[0]])

    # Default: return as-is
    return name

def get_title_priority(title):
    """Get the priority score for a title for sorting purposes."""
    title_upper = title.upper()

    # Check for exact matches first
    for key, priority in TITLE_PRIORITY.items():
        if key in title_upper:
            return priority

    # Default priority
    return 0

def _extract_entity_base_name(name):
    """
    Extract the base entity name from variations like:
    - "LLC Series U of Um Partners" -> "Um Partners LLC"
    - "LLC Series R of Um Partners" -> "Um Partners LLC"
    - "John Doe Trust" -> "John Doe Trust"

    Returns: (base_name, series_info)
    """
    import re

    if not name or not isinstance(name, str):
        return name, None

    # Pattern: "LLC Series X of [Base Name]"
    # Pattern: "Series X LLC of [Base Name]"
    # Pattern: "[Base Name] LLC Series X"
    pattern_llc_series_of = re.compile(
        r'(?:LLC|LP|L\.P\.|L\.L\.C\.)?\s*(?:Series|Class)\s+([A-Z0-9]+)\s+(?:of|Of|OF)\s+(.+)',
        re.IGNORECASE
    )

    match = pattern_llc_series_of.search(name)
    if match:
        series = match.group(1)
        base = match.group(2).strip()

        # Normalize base name
        # Add LLC/LP suffix if not present
        if not re.search(r'\b(?:LLC|LP|L\.P\.|L\.L\.C\.|Trust|Partners)\b', base, re.IGNORECASE):
            # Check what type it was originally
            if 'LLC' in name.upper() or 'L.L.C' in name.upper():
                base = f"{base} LLC"
            elif 'LP' in name.upper() or 'L.P' in name.upper():
                base = f"{base} LP"
            elif 'PARTNERS' in name.upper():
                base = f"{base} Partners"

        return base, series

    # Pattern: "[Base Name] Series X LLC"
    pattern_base_series = re.compile(
        r'(.+?)\s+(?:Series|Class)\s+([A-Z0-9]+)\s*(?:LLC|LP|L\.P\.|L\.L\.C\.)?',
        re.IGNORECASE
    )

    match = pattern_base_series.search(name)
    if match:
        base = match.group(1).strip()
        series = match.group(2)

        # Add entity type suffix
        if not re.search(r'\b(?:LLC|LP|L\.P\.|L\.L\.C\.|Trust|Partners)\b', base, re.IGNORECASE):
            if 'LLC' in name.upper() or 'L.L.C' in name.upper():
                base = f"{base} LLC"
            elif 'LP' in name.upper() or 'L.P' in name.upper():
                base = f"{base} LP"

        return base, series

    # No series detected
    return name, None

def _should_group_entities(name1, name2):
    """
    Check if two insider names should be grouped together.

    Returns True if they appear to be the same entity with different series.
    """
    base1, series1 = _extract_entity_base_name(name1)
    base2, series2 = _extract_entity_base_name(name2)

    # If both have series info and same base name, they should be grouped
    if series1 and series2 and base1 and base2:
        # Normalize for comparison
        base1_norm = base1.lower().strip()
        base2_norm = base2.lower().strip()
        return base1_norm == base2_norm

    return False

def format_insiders_structured(window_df, limit=3):
    """
    Create a structured list of insiders with proper formatting.

    NEW: Groups related entities (e.g., multiple LLC series) together.

    Returns:
        - insiders_display: HTML-formatted string for email display
        - insiders_data: List of dicts with insider details
        - insiders_plain: Plain text comma-separated list (for backward compatibility)
    """
    if window_df.empty:
        return "", [], ""

    # First pass: Deduplicate by insider name and collect all titles
    insider_map = {}

    for _, row in window_df.iterrows():
        name = row.get('insider', 'Unknown')
        title = row.get('title', '')
        value = row.get('value_calc', 0)

        if name not in insider_map:
            insider_map[name] = {
                'name': name,
                'titles': set(),
                'total_value': 0,
                'max_priority': 0,
                'series': []  # Track series information
            }

        insider_map[name]['titles'].add(title)
        insider_map[name]['total_value'] += value
        insider_map[name]['max_priority'] = max(
            insider_map[name]['max_priority'],
            get_title_priority(title)
        )

    # Second pass: Group related entities (e.g., multiple LLC series)
    grouped_map = {}
    processed = set()

    for name1 in insider_map.keys():
        if name1 in processed:
            continue

        # Extract base name and series info
        base_name, series_info = _extract_entity_base_name(name1)

        # Find all related entities
        related = [name1]
        for name2 in insider_map.keys():
            if name1 != name2 and name2 not in processed:
                if _should_group_entities(name1, name2):
                    related.append(name2)
                    processed.add(name2)

        # Create grouped entry
        if len(related) > 1:
            # Multiple series - group them
            total_value = sum(insider_map[n]['total_value'] for n in related)
            all_titles = set()
            for n in related:
                all_titles.update(insider_map[n]['titles'])

            # Extract series info for display
            series_list = []
            for n in related:
                _, s = _extract_entity_base_name(n)
                if s:
                    series_list.append({
                        'series': s,
                        'value': insider_map[n]['total_value']
                    })

            grouped_map[base_name] = {
                'name': base_name,
                'titles': all_titles,
                'total_value': total_value,
                'max_priority': max(insider_map[n]['max_priority'] for n in related),
                'series': sorted(series_list, key=lambda x: x['value'], reverse=True),
                'is_grouped': True
            }
            processed.add(name1)
        else:
            # Single entity - use as-is
            grouped_map[name1] = insider_map[name1]
            grouped_map[name1]['is_grouped'] = False
            processed.add(name1)

    # Use grouped map for further processing
    insider_map = grouped_map

    # Convert to list and sort by title importance
    insiders_list = []
    for name, data in insider_map.items():
        # Normalize name (but preserve for grouped entities)
        if data.get('is_grouped'):
            # For grouped entities, use the base name as-is
            normalized_name = name
        else:
            # For individual insiders, normalize the name
            normalized_name = normalize_name(name)

        # Expand and combine titles
        expanded_titles = [expand_title(t) for t in data['titles']]
        # Remove duplicates while preserving order
        unique_titles = []
        seen = set()
        for title in expanded_titles:
            if title.lower() not in seen:
                unique_titles.append(title)
                seen.add(title.lower())

        combined_titles = ', '.join(unique_titles)

        insider_entry = {
            'name': normalized_name,
            'title': combined_titles,
            'value': data['total_value'],
            'priority': data['max_priority'],
            'is_grouped': data.get('is_grouped', False),
            'series': data.get('series', [])
        }

        insiders_list.append(insider_entry)

    # Sort by priority (highest first)
    insiders_list.sort(key=lambda x: x['priority'], reverse=True)

    # Limit to top N
    display_insiders = insiders_list[:limit]
    total_count = len(insiders_list)

    # Create display strings
    insiders_data = display_insiders

    # Plain text version (backward compatibility)
    plain_parts = []
    for i in display_insiders:
        if i.get('is_grouped') and i.get('series'):
            # Show grouped entity with series breakdown
            series_count = len(i['series'])
            plain_parts.append(f"{i['name']} ({i['title']}, {series_count} series)")
        else:
            plain_parts.append(f"{i['name']} ({i['title']})")

    if total_count > limit:
        plain_parts.append(f"...and {total_count - limit} more")
    insiders_plain = ", ".join(plain_parts)

    # HTML display version - will be used in template
    # We'll pass the structured data to the template and let it handle formatting
    insiders_display = ""  # Template will handle this

    return insiders_display, insiders_data, insiders_plain

def compute_conviction_score(value, role_weight):
    # log-scale dollar weight times role weight
    return math.log1p(max(value, 0)) * role_weight

def _is_valid_field(value):
    """
    Check if a field value is valid (not None, NaN, or string 'nan'/'null').

    Returns True if valid, False otherwise.
    """
    if value is None:
        return False
    if isinstance(value, str):
        value_lower = value.lower().strip()
        if value_lower in ['nan', 'null', 'none', '', 'n/a']:
            return False
    if pd.isna(value):
        return False
    return True

def enrich_with_market_data(cluster_df):
    """
    Uses FMP API (primary) for price, marketCap, volume, industry, sector.
    Uses yfinance (fallback) only for fields FMP doesn't provide.

    ENHANCED: Multi-field caching eliminates most yfinance calls
    ENHANCED: Smart analytics tracking without log flooding
    ENHANCED: 100% cache hit rate for S&P 500 (with cache warming)

    Fields from FMP:
    - industry, sector (classification)
    - price, marketCap, volume (market data)
    - sharesOutstanding (calculated from price/mktCap)
    - companyName, exchange (company info)

    Fields from yfinance (fallback):
    - fiftyTwoWeekLow, fiftyTwoWeekHigh (52-week range)
    - floatShares (float analysis)
    - averageVolume10days (short-term volume)
    """
    import warnings
    import logging

    # Suppress yfinance warnings and errors
    warnings.filterwarnings('ignore')
    logging.getLogger('yfinance').setLevel(logging.CRITICAL)

    tickers = cluster_df['ticker'].unique().tolist()
    info = {}

    print(f"   Fetching market data for {len(tickers)} tickers...")

    # STEP 1: Batch fetch complete profiles from FMP API (parallelized)
    print(f"   📊 FMP API: Batch fetching profiles...")
    fmp_profiles = fetch_profiles_batch(tickers)
    fmp_success_rate = (len(fmp_profiles)/len(tickers)*100) if len(tickers) > 0 else 0

    # STEP 2: Process FMP profiles
    fmp_used = 0
    yf_needed = []

    for t in tickers:
        if t in fmp_profiles:
            profile = fmp_profiles[t]
            ticker_info = {}

            # Extract fields from FMP profile
            if _is_valid_field(profile.get('price')):
                ticker_info['currentPrice'] = profile.get('price')
            if _is_valid_field(profile.get('marketCap')):
                ticker_info['marketCap'] = profile.get('marketCap')
            if _is_valid_field(profile.get('volume')):
                ticker_info['averageVolume'] = profile.get('volume')
            if _is_valid_field(profile.get('sharesOutstanding')):
                ticker_info['sharesOutstanding'] = profile.get('sharesOutstanding')

            # Company name
            company = profile.get('companyName')
            ticker_info['company'] = company if _is_valid_field(company) else t

            # Industry and sector
            industry = profile.get('industry')
            if industry and _is_valid_field(industry):
                ticker_info['industry'] = industry
                ticker_info['sector'] = industry  # Backward compatibility

            info[t] = ticker_info
            fmp_used += 1
        else:
            # FMP failed, need yfinance fallback
            yf_needed.append(t)

    # Log FMP results (smart, concise)
    print(f"   ✅ FMP: {fmp_used}/{len(tickers)} profiles ({fmp_success_rate:.1f}% success)")

    # STEP 3: Yfinance fallback for failed/missing tickers
    yf_successful = 0
    yf_failed = 0

    if yf_needed:
        print(f"   🔄 yfinance fallback: {len(yf_needed)} tickers...")

        failed_ticker_cache = get_failed_ticker_cache()

        for t in yf_needed:
            try:
                ticker_obj = yf.Ticker(t)
                q = ticker_obj.info

                if q and 'currentPrice' in q:
                    ticker_info = {}

                    # Price and market data
                    if _is_valid_field(q.get('currentPrice')):
                        ticker_info['currentPrice'] = q.get('currentPrice')
                    if _is_valid_field(q.get('marketCap')):
                        ticker_info['marketCap'] = q.get('marketCap')

                    # Company name
                    company = q.get('longName') or q.get('shortName')
                    ticker_info['company'] = company if _is_valid_field(company) else t

                    # Volume
                    avg_vol = q.get('averageVolume', 0)
                    ticker_info['averageVolume'] = avg_vol if _is_valid_field(avg_vol) else 0

                    # Shares outstanding
                    shares_out = q.get('sharesOutstanding')
                    if _is_valid_field(shares_out):
                        ticker_info['sharesOutstanding'] = shares_out

                    info[t] = ticker_info
                    yf_successful += 1

                    # Record success to remove from blacklist if present
                    failed_ticker_cache.record_success(t)
                else:
                    info[t] = {'company': t}
                    yf_failed += 1

                    # Record failure - no price data available
                    failed_ticker_cache.record_failure(
                        t,
                        "No price data from yfinance",
                        failure_type='TEMPORARY'
                    )

                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                error_msg = str(e)
                info[t] = {'company': t}
                yf_failed += 1

                # Improved error handling with specific logging
                failure_type = 'TEMPORARY'
                if '404' in error_msg or 'not found' in error_msg.lower():
                    failure_type = 'PERMANENT'
                    logger.debug(f"yfinance: {t} not found (404) - marking as permanent failure")
                elif 'delisted' in error_msg.lower():
                    failure_type = 'PERMANENT'
                    logger.debug(f"yfinance: {t} appears delisted - marking as permanent failure")
                else:
                    logger.debug(f"yfinance: {t} failed with error: {error_msg}")

                # Record the failure in cache
                failed_ticker_cache.record_failure(
                    t,
                    error_msg[:100],  # Truncate long error messages
                    failure_type=failure_type
                )

    # STEP 4: Fetch 52-week range and float from yfinance (for ALL tickers)
    # These fields are not available in FMP basic profile
    print(f"   📈 Fetching 52-week range & float data...")
    range_fetched = 0

    for t in tickers:
        if t not in info:
            continue

        try:
            ticker_obj = yf.Ticker(t)
            q = ticker_obj.info

            if q:
                # 52-week range
                if _is_valid_field(q.get('fiftyTwoWeekLow')):
                    info[t]['fiftyTwoWeekLow'] = q.get('fiftyTwoWeekLow')
                if _is_valid_field(q.get('fiftyTwoWeekHigh')):
                    info[t]['fiftyTwoWeekHigh'] = q.get('fiftyTwoWeekHigh')

                # Float shares
                float_shares = q.get('floatShares')
                if _is_valid_field(float_shares):
                    info[t]['floatShares'] = float_shares

                # 10-day volume
                avg_vol_10d = q.get('averageVolume10days', 0)
                if _is_valid_field(avg_vol_10d):
                    info[t]['averageVolume10days'] = avg_vol_10d

                range_fetched += 1

            time.sleep(0.3)  # Rate limiting

        except Exception as e:
            # Log 52-week data fetch failures at debug level (not critical)
            logger.debug(f"Failed to fetch 52-week data for {t}: {str(e)[:50]}")
            pass  # Continue without 52-week data

    # Smart logging summary (consolidated)
    successful = fmp_used + yf_successful
    failed = yf_failed

    print(f"   📊 Summary: {successful}/{len(tickers)} success ({successful/len(tickers)*100:.1f}%), {range_fetched} with 52-week data")

    # Analytics: Save analytics periodically
    analytics_summary = get_analytics_summary()
    print(f"   💾 Cache: {analytics_summary['cache_hit_rate_pct']}% hit rate, {analytics_summary['cache_size']} tickers cached")
    save_analytics()  # Persist analytics

    # CRITICAL: Validate all fields to prevent NaN from appearing in emails
    cluster_df['currentPrice'] = cluster_df['ticker'].map(
        lambda x: info.get(x, {}).get('currentPrice') if _is_valid_field(info.get(x, {}).get('currentPrice')) else None
    )
    cluster_df['marketCap'] = cluster_df['ticker'].map(
        lambda x: info.get(x, {}).get('marketCap') if _is_valid_field(info.get(x, {}).get('marketCap')) else None
    )
    cluster_df['fiftyTwoWeekLow'] = cluster_df['ticker'].map(
        lambda x: info.get(x, {}).get('fiftyTwoWeekLow') if _is_valid_field(info.get(x, {}).get('fiftyTwoWeekLow')) else None
    )
    cluster_df['fiftyTwoWeekHigh'] = cluster_df['ticker'].map(
        lambda x: info.get(x, {}).get('fiftyTwoWeekHigh') if _is_valid_field(info.get(x, {}).get('fiftyTwoWeekHigh')) else None
    )

    # Add company name
    cluster_df['company'] = cluster_df['ticker'].map(lambda x: info.get(x, {}).get('company', x))

    # NEW: Add sector and industry - only if valid (None if not available)
    # CRITICAL: Use _is_valid_field to prevent NaN from appearing in emails
    cluster_df['sector'] = cluster_df['ticker'].map(
        lambda x: info.get(x, {}).get('sector') if _is_valid_field(info.get(x, {}).get('sector')) else None
    )
    cluster_df['industry'] = cluster_df['ticker'].map(
        lambda x: info.get(x, {}).get('industry') if _is_valid_field(info.get(x, {}).get('industry')) else None
    )

    # NEW: Add volume data
    cluster_df['averageVolume'] = cluster_df['ticker'].map(lambda x: info.get(x, {}).get('averageVolume', 0))

    # NEW: Add float analysis data - validate to prevent NaN
    cluster_df['sharesOutstanding'] = cluster_df['ticker'].map(
        lambda x: info.get(x, {}).get('sharesOutstanding') if _is_valid_field(info.get(x, {}).get('sharesOutstanding')) else None
    )
    cluster_df['floatShares'] = cluster_df['ticker'].map(
        lambda x: info.get(x, {}).get('floatShares') if _is_valid_field(info.get(x, {}).get('floatShares')) else None
    )
    
    cluster_df['pct_from_52wk_low'] = None
    
    def pct_from_low(row):
        low = row.get('fiftyTwoWeekLow')
        cur = row.get('currentPrice')
        if low and cur:
            try:
                return (cur - low) / low * 100.0
            except Exception:
                return None
        return None
    
    cluster_df['pct_from_52wk_low'] = cluster_df.apply(pct_from_low, axis=1)

    # NEW: Calculate float impact - what % of float are insiders buying?
    def calculate_float_impact(row):
        """
        Calculate what % of tradeable shares insiders are purchasing.

        Returns: {
            'pct_of_float': Percentage of float being purchased,
            'pct_of_shares_outstanding': Percentage of total shares,
            'shares_purchased': Estimated number of shares purchased,
            'float_impact_score': Score from 0-10 based on significance
        }
        """
        result = {
            'pct_of_float': None,
            'pct_of_shares_outstanding': None,
            'shares_purchased': None,
            'float_impact_score': 0.0
        }

        # Need price, total value, and float data
        price = row.get('currentPrice')
        total_value = row.get('total_value', 0)
        float_shares = row.get('floatShares')
        shares_outstanding = row.get('sharesOutstanding')

        # Calculate shares purchased (estimate from dollar value)
        if price and price > 0 and total_value > 0:
            shares_purchased = total_value / price
            result['shares_purchased'] = shares_purchased

            # Calculate % of float
            if float_shares and float_shares > 0:
                pct_of_float = (shares_purchased / float_shares) * 100
                result['pct_of_float'] = pct_of_float

                # Calculate float impact score (0-10 scale)
                # 0.01% of float = score 1
                # 0.1% of float = score 5
                # 1% of float = score 10 (very significant)
                if pct_of_float >= 1.0:
                    result['float_impact_score'] = 10.0
                elif pct_of_float >= 0.5:
                    result['float_impact_score'] = 8.0
                elif pct_of_float >= 0.1:
                    result['float_impact_score'] = 5.0
                elif pct_of_float >= 0.05:
                    result['float_impact_score'] = 3.0
                elif pct_of_float >= 0.01:
                    result['float_impact_score'] = 1.0

            # Calculate % of shares outstanding
            if shares_outstanding and shares_outstanding > 0:
                pct_of_outstanding = (shares_purchased / shares_outstanding) * 100
                result['pct_of_shares_outstanding'] = pct_of_outstanding

        return pd.Series(result)

    # Apply float impact calculation
    float_impact_df = cluster_df.apply(calculate_float_impact, axis=1)
    cluster_df['pct_of_float'] = float_impact_df['pct_of_float']
    cluster_df['pct_of_shares_outstanding'] = float_impact_df['pct_of_shares_outstanding']
    cluster_df['shares_purchased'] = float_impact_df['shares_purchased']
    cluster_df['float_impact_score'] = float_impact_df['float_impact_score']

    # Re-enable warnings
    warnings.filterwarnings('default')

    return cluster_df

def apply_quality_filters(cluster_df):
    """
    ENHANCED: Quality filters with dynamic thresholds and tiered dollar volume

    Filters applied:
    1. Minimum price ($2.00) - no penny stocks
    2. DYNAMIC minimum purchase per insider (scales with cluster size)
    3. TIERED DOLLAR VOLUME liquidity (scales by cluster, fair across prices)
    4. Maximum recent drawdown (<40% drop in 30 days)

    NEW FEATURES:
    - Fix 1: Mega-cluster exception bypasses volume filter
    - Fix 2: Dynamic per-insider thresholds (lower for larger clusters)
    - Fix 3: Holiday mode automatically reduces all thresholds by 20%
    - Fix 4: Tiered dollar volume thresholds (7+ insiders: $100k, 4-6: $150k, 1-3: $200k daily)
    """
    if cluster_df.empty:
        return cluster_df

    original_count = len(cluster_df)
    filtered = cluster_df.copy()

    # Check for holiday mode
    is_holiday, holiday_name, days_into = is_holiday_period()
    if is_holiday:
        print(f"\n🎄 HOLIDAY MODE ACTIVE - {holiday_name} (Day {days_into + 1})")
        print(f"   All thresholds reduced by {int(HOLIDAY_THRESHOLD_REDUCTION * 100)}% to catch strategic holiday buys")

    print(f"\n🔍 Applying quality filters to {original_count} signals...")

    # Get adjusted thresholds for holiday mode
    min_price = apply_holiday_adjustment(MIN_STOCK_PRICE) if is_holiday else MIN_STOCK_PRICE
    min_volume = apply_holiday_adjustment(MIN_AVERAGE_VOLUME) if is_holiday else MIN_AVERAGE_VOLUME

    # Filter 1: No penny stocks (price > $2.00, or $1.60 in holiday mode)
    before = len(filtered)
    filtered = filtered[
        (filtered['currentPrice'].isna()) |
        (filtered['currentPrice'] > min_price)
    ]
    removed = before - len(filtered)
    if removed > 0:
        threshold_display = f"${min_price:.2f}"
        print(f"   ❌ Removed {removed} penny stocks (price < {threshold_display})")

    # Filter 2: DYNAMIC minimum purchase per insider
    # Fix 2: Scale threshold based on cluster size and total value
    before = len(filtered)

    # Safety check: Remove any clusters with invalid cluster_count
    filtered = filtered[filtered['cluster_count'] > 0]

    filtered['avg_purchase_per_insider'] = (
        filtered['total_value'] / filtered['cluster_count']
    )

    # Apply dynamic threshold with detailed logging
    def meets_dynamic_threshold(row):
        cluster_count = row['cluster_count']
        total_value = row['total_value']
        avg_per_insider = row['avg_purchase_per_insider']

        # Get dynamic threshold for this cluster
        threshold = get_dynamic_min_per_insider(cluster_count, total_value, apply_holiday=is_holiday)

        return avg_per_insider >= threshold

    # Track which signals use dynamic thresholds
    dynamic_threshold_applied = []
    for idx, row in filtered.iterrows():
        threshold = get_dynamic_min_per_insider(
            row['cluster_count'],
            row['total_value'],
            apply_holiday=is_holiday
        )
        if threshold != DYNAMIC_THRESHOLD_BASE:
            dynamic_threshold_applied.append({
                'ticker': row['ticker'],
                'cluster_count': row['cluster_count'],
                'threshold': threshold,
                'avg_per_insider': row['avg_purchase_per_insider']
            })

    filtered = filtered[filtered.apply(meets_dynamic_threshold, axis=1)]
    removed = before - len(filtered)

    if removed > 0:
        base_threshold = get_dynamic_min_per_insider(1, 0, apply_holiday=is_holiday)
        print(f"   ❌ Removed {removed} signals (below dynamic per-insider threshold)")
        if dynamic_threshold_applied:
            print(f"   ℹ️  Applied dynamic thresholds to {len(dynamic_threshold_applied)} signals")
            for dt in dynamic_threshold_applied[:3]:  # Show first 3 examples
                print(f"      • {dt['ticker']}: {dt['cluster_count']} insiders, ${dt['threshold']:,.0f} threshold (${dt['avg_per_insider']:,.0f} avg)")

    # Filter 3: Liquidity check using tiered dollar volume thresholds
    # Fix 1: MEGA-CLUSTER EXCEPTION - Bypass for rare high-conviction clusters
    # Fix 4: TIERED DOLLAR VOLUME - Scale requirements by cluster size, use $ volume not shares
    before = len(filtered)

    # Apply tiered dollar volume with mega-cluster exception
    def passes_volume_filter(row):
        # Check if missing data (volume or price) - don't filter
        if pd.isna(row.get('averageVolume')) or pd.isna(row.get('currentPrice')):
            return True

        volume_shares = row.get('averageVolume', 0)
        price = row.get('currentPrice', 0)
        cluster_count = row.get('cluster_count', 0)
        total_value = row.get('total_value', 0)
        avg_per_insider = row.get('avg_purchase_per_insider', 0)

        # Calculate dollar volume (shares × price)
        dollar_volume = volume_shares * price

        # Apply holiday adjustment to mega-cluster thresholds
        mega_cluster_min_insiders = MEGA_CLUSTER_MIN_INSIDERS  # No adjustment (count)
        mega_cluster_min_total = apply_holiday_adjustment(MEGA_CLUSTER_MIN_TOTAL_VALUE) if is_holiday else MEGA_CLUSTER_MIN_TOTAL_VALUE
        mega_cluster_min_avg = apply_holiday_adjustment(MEGA_CLUSTER_MIN_AVG_PER_INSIDER) if is_holiday else MEGA_CLUSTER_MIN_AVG_PER_INSIDER

        # MEGA-CLUSTER EXCEPTION: Bypass volume filter for high-conviction rare clusters
        is_mega_cluster = (
            cluster_count >= mega_cluster_min_insiders and
            total_value >= mega_cluster_min_total and
            avg_per_insider >= mega_cluster_min_avg
        )

        if is_mega_cluster:
            return True  # Bypass volume filter entirely

        # TIERED DOLLAR VOLUME FILTER: Scale threshold by cluster size
        threshold = get_dollar_volume_threshold(cluster_count, total_value, apply_holiday=is_holiday)
        return dollar_volume >= threshold

    # Track mega-cluster exceptions and tiered volume passes
    mega_cluster_exceptions = []
    tiered_volume_passes = []

    for idx, row in filtered.iterrows():
        volume_shares = row.get('averageVolume', 0)
        price = row.get('currentPrice', 0)
        cluster_count = row.get('cluster_count', 0)
        total_value = row.get('total_value', 0)
        avg_per_insider = row.get('avg_purchase_per_insider', 0)

        if pd.notna(volume_shares) and pd.notna(price):
            dollar_volume = volume_shares * price

            # Check if mega-cluster
            mega_cluster_min_total = apply_holiday_adjustment(MEGA_CLUSTER_MIN_TOTAL_VALUE) if is_holiday else MEGA_CLUSTER_MIN_TOTAL_VALUE
            mega_cluster_min_avg = apply_holiday_adjustment(MEGA_CLUSTER_MIN_AVG_PER_INSIDER) if is_holiday else MEGA_CLUSTER_MIN_AVG_PER_INSIDER

            is_mega = (
                cluster_count >= MEGA_CLUSTER_MIN_INSIDERS and
                total_value >= mega_cluster_min_total and
                avg_per_insider >= mega_cluster_min_avg
            )

            if is_mega:
                mega_cluster_exceptions.append({
                    'ticker': row['ticker'],
                    'cluster_count': cluster_count,
                    'total_value': total_value,
                    'avg_per_insider': avg_per_insider,
                    'volume_shares': volume_shares,
                    'dollar_volume': dollar_volume
                })
            else:
                # Check if using tiered threshold (not base threshold)
                threshold = get_dollar_volume_threshold(cluster_count, total_value, apply_holiday=is_holiday)
                base_threshold = DOLLAR_VOLUME_THRESHOLD_SMALL
                if is_holiday:
                    base_threshold = apply_holiday_adjustment(base_threshold)

                if threshold < base_threshold and dollar_volume >= threshold:
                    tiered_volume_passes.append({
                        'ticker': row['ticker'],
                        'cluster_count': cluster_count,
                        'threshold': threshold,
                        'dollar_volume': dollar_volume,
                        'volume_shares': volume_shares,
                        'price': price
                    })

    filtered = filtered[filtered.apply(passes_volume_filter, axis=1)]
    removed = before - len(filtered)

    if mega_cluster_exceptions:
        print(f"   🚀 MEGA-CLUSTER EXCEPTION: {len(mega_cluster_exceptions)} signals bypassed volume filter")
        for mc in mega_cluster_exceptions:
            print(f"      • {mc['ticker']}: {mc['cluster_count']} insiders × ${mc['avg_per_insider']:,.0f} = ${mc['total_value']:,.0f} total (${mc['dollar_volume']:,.0f}/day volume)")

    if tiered_volume_passes:
        print(f"   📊 TIERED VOLUME: {len(tiered_volume_passes)} signals passed via lower thresholds")
        for tv in tiered_volume_passes[:3]:  # Show first 3 examples
            print(f"      • {tv['ticker']}: {tv['cluster_count']} insiders, ${tv['threshold']:,.0f} threshold (${tv['dollar_volume']:,.0f}/day volume)")

    if removed > 0:
        print(f"   ❌ Removed {removed} illiquid stocks (below tiered dollar volume thresholds)")
    
    # Filter 4: Not down >40% in last 30 days (avoid falling knives)
    before = len(filtered)
    
    def check_recent_drawdown(row):
        """Check if stock is down >40% in last 30 days"""
        ticker = row['ticker']
        try:
            # Get 30 days of data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=35)
            hist = yf.download(ticker, start=start_date, end=end_date, progress=False)
            
            if hist.empty or len(hist) < 5:
                return True  # No data, don't filter
            
            high_30d = hist['High'].max()
            current = row.get('currentPrice')
            
            if not current or not high_30d:
                return True
            
            drawdown = (current - high_30d) / high_30d
            
            # Filter out if down more than 40%
            return drawdown > -0.40
            
        except Exception:
            return True  # Error, don't filter
    
    # Apply drawdown filter (this takes time, so we do it last after other filters)
    if len(filtered) <= 20:  # Only check if we have reasonable number of signals
        filtered = filtered[filtered.apply(check_recent_drawdown, axis=1)]
        removed = before - len(filtered)
        if removed > 0:
            print(f"   ❌ Removed {removed} stocks down >40% in 30 days")
    
    total_removed = original_count - len(filtered)
    print(f"   ✅ Quality filters: {len(filtered)} signals remaining ({total_removed} removed)")
    
    return filtered

def detect_patterns(buys_df, cluster_df):
    """
    NEW FEATURE: Detect meaningful insider buying patterns
    
    Patterns detected:
    1. Accelerating Buys - More buys recently than before
    2. CEO + CFO Together - Both top executives buying
    3. Breaking Silence - First buys after long quiet period
    4. Increasing Size - Each buy larger than previous
    """
    if buys_df.empty or cluster_df.empty:
        return cluster_df
    
    print(f"\n🔍 Detecting insider patterns...")
    
    # Add pattern columns
    cluster_df['patterns'] = ''
    cluster_df['pattern_score'] = 0.0
    
    for idx, row in cluster_df.iterrows():
        ticker = row['ticker']
        ticker_buys = buys_df[buys_df['ticker'] == ticker].sort_values('trade_date')
        
        if ticker_buys.empty:
            continue
        
        patterns = []
        pattern_score = 0.0
        
        # Pattern 1: Accelerating Buys
        if len(ticker_buys) >= 3:
            now = pd.Timestamp.now()
            recent_30d = ticker_buys[ticker_buys['trade_date'] >= (now - pd.Timedelta(days=30))]
            older_30d = ticker_buys[
                (ticker_buys['trade_date'] >= (now - pd.Timedelta(days=60))) &
                (ticker_buys['trade_date'] < (now - pd.Timedelta(days=30)))
            ]
            
            if len(recent_30d) > len(older_30d) * 1.5:
                patterns.append(f"🔥 Accelerating ({len(recent_30d)} recent vs {len(older_30d)} older)")
                pattern_score += 1.5
        
        # Pattern 2: CEO + CFO Together (within 5 days)
        ceo_buys = ticker_buys[ticker_buys['role'] == 'CEO']
        cfo_buys = ticker_buys[ticker_buys['role'] == 'CFO']
        
        if not ceo_buys.empty and not cfo_buys.empty:
            for _, ceo_buy in ceo_buys.iterrows():
                for _, cfo_buy in cfo_buys.iterrows():
                    days_apart = abs((ceo_buy['trade_date'] - cfo_buy['trade_date']).days)
                    if days_apart <= 5:
                        patterns.append("👔 CEO+CFO Coordination")
                        pattern_score += 2.0
                        break
        
        # Pattern 3: Breaking Silence (no buys for 90+ days, then cluster)
        if len(ticker_buys) >= 2:
            latest_date = ticker_buys['trade_date'].max()
            earlier_buys = ticker_buys[ticker_buys['trade_date'] < (latest_date - pd.Timedelta(days=90))]
            recent_buys = ticker_buys[ticker_buys['trade_date'] >= (latest_date - pd.Timedelta(days=30))]
            
            if earlier_buys.empty and len(recent_buys) >= 2:
                patterns.append("📅 Breaking Silence (90+ day gap)")
                pattern_score += 1.0
        
        # Pattern 4: Increasing Size
        if len(ticker_buys) >= 3:
            # Check if buy sizes are generally increasing
            recent_3 = ticker_buys.tail(3)
            values = recent_3['value_calc'].tolist()
            
            if len(values) == 3 and values[0] < values[1] < values[2]:
                patterns.append("📈 Increasing Size")
                pattern_score += 1.0
        
        # Update cluster_df
        if patterns:
            cluster_df.at[idx, 'patterns'] = " | ".join(patterns)
            cluster_df.at[idx, 'pattern_score'] = pattern_score
    
    # Count patterns found
    with_patterns = len(cluster_df[cluster_df['patterns'] != ''])
    if with_patterns > 0:
        print(f"   ✅ Found {with_patterns} signals with special patterns")
    
    return cluster_df

def apply_insider_scoring(buys_df, cluster_df, tracker=None):
    """
    Apply Follow-the-Smart-Money scoring to adjust conviction based on individual
    insider track records.

    Args:
        buys_df: DataFrame of all buy transactions
        cluster_df: DataFrame of clustered signals
        tracker: InsiderPerformanceTracker instance (optional)

    Returns:
        Updated cluster_df with insider_score columns
    """
    if not config.ENABLE_INSIDER_SCORING:
        # Add placeholder columns
        cluster_df['avg_insider_score'] = 50.0  # Neutral
        cluster_df['insider_multiplier'] = 1.0
        cluster_df['insiders_with_track_record'] = ''  # Empty - will use fallback in template
        return cluster_df

    if buys_df.empty or cluster_df.empty:
        cluster_df['avg_insider_score'] = 50.0
        cluster_df['insider_multiplier'] = 1.0
        cluster_df['insiders_with_track_record'] = ''
        return cluster_df

    if tracker is None:
        # Tracker not provided, use neutral scores
        cluster_df['avg_insider_score'] = 50.0
        cluster_df['insider_multiplier'] = 1.0
        cluster_df['insiders_with_track_record'] = ''
        return cluster_df

    print(f"\n📊 Applying Follow-the-Smart-Money scoring...")

    # For each cluster, calculate average insider score
    cluster_df['avg_insider_score'] = 50.0  # Default neutral
    cluster_df['insider_multiplier'] = 1.0
    cluster_df['top_insider_name'] = ''
    cluster_df['top_insider_score'] = 50.0
    cluster_df['insiders_with_track_record'] = ''  # Enhanced insider list with track records

    insiders_scored = 0

    for idx, row in cluster_df.iterrows():
        ticker = row['ticker']
        ticker_buys = buys_df[buys_df['ticker'] == ticker]

        if ticker_buys.empty:
            continue

        # Get scores for all insiders in this cluster
        insider_scores = []
        insider_names = []
        insider_details_map = {}  # Map name -> track record info

        for _, buy in ticker_buys.iterrows():
            insider_name = buy.get('insider', '')
            insider_title = buy.get('title', '')
            if insider_name:
                profile = tracker.get_insider_score(insider_name)
                score = profile.get('overall_score', 50.0)
                insider_scores.append(score)
                insider_names.append((insider_name, score))

                # Store track record for notable performers
                win_rate_90d = profile.get('win_rate_90d')
                avg_return_90d = profile.get('avg_return_90d')
                total_trades = profile.get('total_trades', 0)

                # Only show track record for notable performers with sufficient data
                if total_trades >= 3 and win_rate_90d is not None and avg_return_90d is not None:
                    # Store details if win rate is outside 45-60% range
                    track_data = {}

                    # High performers: >60% win rate
                    if win_rate_90d > 60:
                        track_data = {
                            'track_record': f"{win_rate_90d:.0f}% win rate, {avg_return_90d:+.1f}% avg return",
                            'win_rate_display': f"✓ {win_rate_90d:.0f}% Win Rate",
                            'win_rate_value': win_rate_90d,
                            'is_notable': True,
                            'is_high_performer': True
                        }
                    # Low performers: <45% win rate
                    elif win_rate_90d < 45:
                        track_data = {
                            'track_record': f"{win_rate_90d:.0f}% win rate, {avg_return_90d:+.1f}% avg return",
                            'win_rate_display': f"⚠️ {win_rate_90d:.0f}% Win Rate",
                            'win_rate_value': win_rate_90d,
                            'is_notable': True,
                            'is_high_performer': False
                        }

                    # Only add to map if outside neutral range
                    if track_data:
                        insider_details_map[insider_name] = track_data

        if insider_scores:
            # Calculate average score for this cluster
            avg_score = sum(insider_scores) / len(insider_scores)
            cluster_df.at[idx, 'avg_insider_score'] = round(avg_score, 2)

            # Calculate multiplier (0.5x to 2.0x based on score)
            # Score 50 (neutral) = 1.0x
            # Score 100 (excellent) = 2.0x
            # Score 0 (poor) = 0.5x
            multiplier = config.INSIDER_SCORE_MULTIPLIER_MIN + (
                (avg_score / 100) * (config.INSIDER_SCORE_MULTIPLIER_MAX - config.INSIDER_SCORE_MULTIPLIER_MIN)
            )
            cluster_df.at[idx, 'insider_multiplier'] = round(multiplier, 2)

            # Track top insider
            if insider_names:
                top_insider = max(insider_names, key=lambda x: x[1])
                cluster_df.at[idx, 'top_insider_name'] = top_insider[0]
                cluster_df.at[idx, 'top_insider_score'] = round(top_insider[1], 2)

            # Add track record data to insiders_data
            if 'insiders_data' in cluster_df.columns:
                insiders_data = cluster_df.at[idx, 'insiders_data']
                if insiders_data and isinstance(insiders_data, list):
                    for insider in insiders_data:
                        # Match by original name (before normalization)
                        # This is a best-effort match
                        for orig_name, track_data in insider_details_map.items():
                            if orig_name in insider['name'] or insider['name'] in orig_name:
                                insider['track_record'] = track_data['track_record']
                                insider['win_rate_display'] = track_data.get('win_rate_display')
                                insider['win_rate_value'] = track_data.get('win_rate_value')
                                insider['is_notable'] = track_data['is_notable']
                                insider['is_high_performer'] = track_data.get('is_high_performer')
                                break

            # Create legacy format for backward compatibility
            legacy_parts = []
            for _, buy in ticker_buys.drop_duplicates(subset=['insider']).iterrows():
                name = buy.get('insider', '')
                title = buy.get('title', '')
                if name in insider_details_map:
                    legacy_parts.append(f"{title} {name} (Track Record: {insider_details_map[name]['track_record']})")
                else:
                    legacy_parts.append(f"{title} {name}")

            cluster_df.at[idx, 'insiders_with_track_record'] = ", ".join(legacy_parts) if legacy_parts else ""

            insiders_scored += 1

    if insiders_scored > 0:
        print(f"   ✅ Applied insider scoring to {insiders_scored} signals")

        # Show some statistics
        high_performers = len(cluster_df[cluster_df['avg_insider_score'] >= 65])
        low_performers = len(cluster_df[cluster_df['avg_insider_score'] <= 35])

        if high_performers > 0:
            print(f"   🌟 {high_performers} signals from high-performing insiders (score ≥65)")
        if low_performers > 0:
            print(f"   ⚠️  {low_performers} signals from low-performing insiders (score ≤35)")

    return cluster_df

def cluster_and_score(df, window_days=5, top_n=config.MAX_SIGNALS_TO_ANALYZE, insider_tracker=None):
    """
    df: raw DataFrame from fetch_openinsider_recent
    returns: DataFrame with per-ticker aggregated cluster info and suggested action/rationale

    UPDATED: Now includes sector info, quality filters, and pattern detection
    FIXED: Changed default top_n from hardcoded 50 to config.MAX_SIGNALS_TO_ANALYZE (200)
    """
    # filter buys
    buys = df[df['trade_type'].str.upper().str.contains('BUY|PURCHASE|P -', na=False)].copy()
    if buys.empty:
        return pd.DataFrame()

    # Deduplicate transactions to prevent duplicate data from inflating cluster counts
    # This handles cases where the same transaction appears multiple times (e.g., amended Form 4 filings)
    initial_count = len(buys)
    buys = buys.drop_duplicates(subset=['ticker', 'insider', 'trade_date', 'trade_type', 'qty', 'price'], keep='first')
    if len(buys) < initial_count:
        print(f"   ℹ️  Removed {initial_count - len(buys)} duplicate transactions")

    buys['role'] = buys['title'].apply(normalize_title)
    buys['role_weight'] = buys['role'].map(ROLE_WEIGHT).fillna(1.0)
    # ensure value column - prefer explicit 'value' if present, else qty*price
    buys['value_calc'] = buys.apply(lambda r: r['value'] if (r.get('value',0) and r['value']>0) else (r.get('qty',0)*r.get('price',0)), axis=1)
    buys['conviction'] = buys.apply(lambda r: compute_conviction_score(r['value_calc'], r['role_weight']), axis=1)
    buys = buys.sort_values('trade_date')

    clusters = []
    tickers = buys['ticker'].unique()
    for t in tickers:
        tdf = buys[buys['ticker'] == t].copy().sort_values('trade_date')
        # compute cluster-level aggregates: last trade date, unique insiders in a sliding window
        max_cluster_count = 0
        max_total_value = 0
        last_trade = tdf['trade_date'].max()
        for idx,row in tdf.iterrows():
            start = row['trade_date'] - timedelta(days=window_days)
            end = row['trade_date'] + timedelta(days=window_days)
            window = tdf[(tdf['trade_date'] >= start) & (tdf['trade_date'] <= end)]
            cluster_count = window['insider'].nunique()
            total_value = window['value_calc'].sum()
            avg_conviction = window['conviction'].mean() if not window.empty else 0
            if cluster_count > max_cluster_count or (cluster_count == max_cluster_count and total_value > max_total_value):
                max_cluster_count = cluster_count
                max_total_value = total_value
                best_avg_conviction = avg_conviction
                best_window = window

        # Format insiders using new structured approach
        if max_cluster_count > 0:
            insiders_display, insiders_data, insiders_plain = format_insiders_structured(best_window, limit=3)
        else:
            insiders_display, insiders_data, insiders_plain = "", [], ""

        clusters.append({
            'ticker': t,
            'last_trade_date': last_trade,
            'cluster_count': int(max_cluster_count),
            'total_value': float(max_total_value),
            'avg_conviction': float(best_avg_conviction),
            'insiders': insiders_plain,  # Plain text for backward compatibility
            'insiders_data': insiders_data,  # Structured data for template
            'insiders_count': len(insiders_data) if insiders_data else 0,
            'insiders_total_count': max_cluster_count,
        })

    cluster_df = pd.DataFrame(clusters)
    if cluster_df.empty:
        return cluster_df

    # enrich market data (now includes sector info)
    cluster_df = enrich_with_market_data(cluster_df)

    # NEW: Apply quality filters
    cluster_df = apply_quality_filters(cluster_df)
    
    if cluster_df.empty:
        print("   ⚠️  All signals filtered out by quality checks")
        return cluster_df

    # NEW: Detect patterns
    cluster_df = detect_patterns(buys, cluster_df)

    # NEW: Apply insider performance scoring
    cluster_df = apply_insider_scoring(buys, cluster_df, insider_tracker)

    # NEW: Apply sector relative analysis
    if config.ENABLE_SECTOR_ANALYSIS:
        try:
            sector_analyzer = SectorAnalyzer(cache_hours=config.SECTOR_CACHE_HOURS)
            cluster_df = sector_analyzer.enhance_signals_with_sector_analysis(cluster_df)
            print(f"   ✅ Added sector analysis to {len(cluster_df)} signals")
        except Exception as e:
            print(f"   ⚠️  Sector analysis failed: {e}")
            # Add default values if sector analysis fails
            for col in ['sector_etf', 'relative_performance_30d', 'relative_performance_60d',
                       'relative_performance_90d', 'sector_signal', 'sector_context']:
                if col not in cluster_df.columns:
                    cluster_df[col] = None

    # rank score: simple combination (you can tune)
    # NEW: Include pattern score in ranking
    # NEW: Include float impact score in ranking (bonus for buying significant % of float)
    # NEW: Include insider performance multiplier in ranking
    # NEW: Optionally adjust for sector timing
    sector_adjustment = 0.0
    if config.ENABLE_SECTOR_ANALYSIS and config.ENABLE_SECTOR_CONVICTION_ADJUSTMENT:
        # Apply sector-based conviction adjustments
        cluster_df['sector_adjustment'] = cluster_df.apply(lambda r: calculate_sector_adjustment(r), axis=1)
        sector_adjustment = cluster_df['sector_adjustment']
    else:
        cluster_df['sector_adjustment'] = 0.0

    cluster_df['rank_score'] = (
        cluster_df['cluster_count'] * 2.0 +
        (cluster_df['avg_conviction'] * cluster_df['insider_multiplier']) / 10.0 +  # Apply insider multiplier
        cluster_df['pattern_score'] * 0.5 +  # Bonus for patterns
        cluster_df['float_impact_score'] * 0.3 +  # Bonus for float impact
        (cluster_df['avg_insider_score'] - 50.0) * config.INSIDER_SCORE_WEIGHT +  # Insider score bonus/penalty (neutral=50 gives 0 impact)
        cluster_df['sector_adjustment']  # Sector timing adjustment
    )
    # sanitize pattern_detected column
    if 'pattern_detected' in cluster_df.columns:
        cluster_df['pattern_detected'] = cluster_df['pattern_detected'].apply(sanitize_pattern_value)
    else:
        cluster_df['pattern_detected'] = None
    # suggested action and rationale
    cluster_df['suggested_action'] = cluster_df.apply(lambda r: suggest_action(r), axis=1)
    cluster_df['rationale'] = cluster_df.apply(lambda r: build_rationale(r), axis=1)

    # Sort by rank score and return top N
    result = cluster_df.sort_values('rank_score', ascending=False).head(top_n)

    # Filter out very low quality signals
    result = result[result['rank_score'] >= 3.0]

    # CRITICAL: Sanitize NaN values before returning to prevent "nan" from appearing in email templates
    result = sanitize_nan_values(result)

    return result

# Default urgent thresholds (feel free to tune)
URGENT_THRESHOLDS = {
    'cluster_count': 3,        # >= 3 insiders within window
    'total_value': 250000.0,   # total buy value across insiders (USD)
    'has_c_suite': True,       # at least one of CEO/CFO in insiders list
    'pct_from_52wk_low': 15.0, # within 15% of 52-week low (i.e., discounted)
}

def sanitize_pattern_value(value):
    """Convert None string or empty to actual None"""
    if value in ['None', '', 'none', None]:
        return None
    return str(value)

def calculate_sector_adjustment(r):
    """
    Calculate rank score adjustment based on sector timing.

    Contrarian setups (sector weak + insider buying) get a boost.
    Late momentum plays (sector strong + insider buying) get a slight reduction.
    """
    sector_signal = r.get('sector_signal')

    if sector_signal == 'STRONG_UPGRADE':
        return config.SECTOR_CONTRARIAN_BOOST * 1.5  # Extra boost for strong contrarian
    elif sector_signal == 'UPGRADE':
        return config.SECTOR_CONTRARIAN_BOOST
    elif sector_signal == 'CAUTION':
        return config.SECTOR_MOMENTUM_CAUTION  # Slight reduction for late momentum
    else:
        return 0.0  # Neutral or unknown

def is_urgent(r, thresholds=URGENT_THRESHOLDS):
    """
    DEPRECATED: Always returns False. All signals are now captured in daily report.

    The urgent email system has been removed to consolidate all signals into
    a single daily trading report. This function is kept for backward compatibility
    but will always return False.
    """
    return False

def suggest_action(r):
    """
    Determine suggested action based on signal strength.
    Now includes high-conviction single-insider buys.
    
    Rules:
      - Urgent: Multiple insiders + high conviction + near 52w low
      - Watchlist: 2+ insiders OR single high-conviction insider
      - Monitor: Everything else
    """
    # Check if urgent first
    if is_urgent(r):
        return "URGENT: Consider small entry at open / immediate review"
    
    # Multiple insiders (cluster of 2+)
    if r.get('cluster_count', 0) >= 2 and r.get('rank_score', 0) > 5:
        return "Watchlist - consider small entry after confirmation"
    
    # Single insider but HIGH conviction
    if r.get('cluster_count', 0) == 1:
        total_value = r.get('total_value', 0)
        conviction = r.get('avg_conviction', 0)
        
        # Very high conviction (CEO/CFO with large purchase)
        if conviction >= 12.0 and total_value >= 500000:
            return "Watchlist - strong single-insider signal"
        
        # High conviction with meaningful size
        elif conviction >= 10.0 and total_value >= 250000:
            return "Watchlist - notable insider purchase"
        
        # Large purchase (any insider buying $1M+)
        elif total_value >= 1000000:
            return "Watchlist - significant dollar amount"
        
        # Moderate conviction
        elif conviction >= 8.0 and total_value >= 100000:
            return "Monitor - single insider buying"
    
    # Default
    return "Monitor"

def sanitize_nan_values(df):
    """
    Replace all NaN, inf, and invalid values with None to prevent 'nan' from appearing in templates.

    This ensures that when DataFrames are converted to dicts and passed to Jinja2 templates,
    NaN values appear as None/null rather than the string 'nan'.

    CRITICAL FIX: Also converts string "nan", "null", "none", "N/A" to None.
    """
    if df.empty:
        return df

    # Define a safe NaN checker that handles both scalars and arrays
    def safe_nan_check(x):
        """Safely check for NaN in both scalars and arrays, including string 'nan'."""
        if isinstance(x, (list, tuple, dict)):
            # For arrays/lists/dicts, keep as-is (don't convert to None)
            return x

        # Check for string 'nan', 'null', 'none', etc.
        if isinstance(x, str):
            if x.lower().strip() in ['nan', 'null', 'none', 'n/a', '']:
                return None
            return x

        try:
            # For scalar NaN/inf, convert to None
            if pd.isna(x) or (isinstance(x, float) and (math.isinf(x))):
                return None
            else:
                return x
        except (ValueError, TypeError):
            # If pd.isna() fails (e.g., on complex objects), keep as-is
            return x

    # Clean all columns - this handles both scalar NaN and avoids errors on array columns
    for col in df.columns:
        # Check if column contains arrays/lists - if so, skip NaN conversion for this column
        # Arrays don't have NaN issues and checking them causes the ValueError
        has_arrays = False
        try:
            # Sample first non-null value to check type
            sample = df[col].dropna().iloc[0] if len(df[col].dropna()) > 0 else None
            if sample is not None and isinstance(sample, (list, tuple, dict)):
                has_arrays = True
        except:
            pass

        if not has_arrays:
            # For non-array columns, replace NaN with None using .where()
            # Convert to object dtype first to allow None values
            if pd.api.types.is_numeric_dtype(df[col]):
                # Use mask to replace NaN/inf with None
                mask = df[col].isna() | df[col].apply(lambda x: isinstance(x, float) and (math.isinf(x) if not pd.isna(x) else False))
                df[col] = df[col].astype('object').where(~mask, None)
            else:
                # For non-numeric columns (strings, etc.), also check for string "nan"
                df[col] = df[col].apply(safe_nan_check)

    return df

def build_rationale(r):
    parts = []
    parts.append(f"Cluster count: {int(r.get('cluster_count',0))}")
    parts.append(f"Total reported buys: ${int(r.get('total_value',0)):,}")
    if r.get('currentPrice') is not None:
        parts.append(f"Current Price: ${r.get('currentPrice')}")
    if r.get('pct_from_52wk_low') is not None:
        parts.append(f"{r.get('pct_from_52wk_low'):.1f}% above 52-week low")

    # NEW: Add sector info (only if valid)
    sector = r.get('sector')
    if sector and _is_valid_field(sector):
        parts.append(f"Sector: {sector}")

    # NEW: Add float impact if significant
    pct_of_float = r.get('pct_of_float')
    if pct_of_float is not None and pct_of_float > 0:
        if pct_of_float >= 1.0:
            parts.append(f"🔥 MAJOR: {pct_of_float:.2f}% of float")
        elif pct_of_float >= 0.1:
            parts.append(f"⚡ Significant: {pct_of_float:.3f}% of float")
        elif pct_of_float >= 0.01:
            parts.append(f"Float impact: {pct_of_float:.4f}%")

    parts.append(f"Rank Score: {r.get('rank_score'):.2f}")

    # NEW: Add pattern info if present
    if r.get('patterns'):
        parts.append(f"Patterns: {r.get('patterns')}")

    # NEW: Add insider performance score if available
    if config.ENABLE_INSIDER_SCORING and r.get('avg_insider_score') is not None:
        insider_score = r.get('avg_insider_score', 50.0)
        multiplier = r.get('insider_multiplier', 1.0)

        if insider_score >= 65:
            parts.append(f"🌟 Smart Money: {insider_score:.0f}/100 ({multiplier:.2f}x)")
        elif insider_score <= 35:
            parts.append(f"⚠️ Insider Score: {insider_score:.0f}/100 ({multiplier:.2f}x)")
        elif insider_score != 50.0:  # Not neutral
            parts.append(f"Insider Score: {insider_score:.0f}/100 ({multiplier:.2f}x)")

    return " | ".join(parts)

if __name__ == "__main__":
    # quick smoke test - requires fetch_openinsider.py
    import fetch_openinsider as fio
    df = fio.fetch_openinsider_recent()
    out = cluster_and_score(df)
    print(out.head())