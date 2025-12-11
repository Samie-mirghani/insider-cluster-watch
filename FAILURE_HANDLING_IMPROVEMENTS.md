# Failure Handling Improvements

## Overview

This document describes improvements to how the insider performance tracker handles trade outcome fetch failures. The changes reduce log noise, categorize failures intelligently, and prevent wasteful retries of permanently failed trades.

## The Problem

**Before:**
- Many trades failing with generic "Failed to fetch outcomes after 3 retries" message
- Logs cluttered with 12+ individual failure messages per run
- No distinction between permanent failures (delisted stocks) vs temporary (network errors)
- Same failed trades retried every day forever
- Unclear impact on profile quality

## The Solution

### 1. Failure Categorization

Failures are now categorized into 4 types:

| Type | Description | Action |
|------|-------------|--------|
| `INVALID_TICKER` | Bad ticker format, mutual fund, placeholder (N.A.) | Mark as FAILED, never retry |
| `DELISTED` | No trading history available (possibly delisted) | Mark as FAILED, never retry |
| `RATE_LIMIT` | API rate limit hit (429 error) | Retry tomorrow |
| `NETWORK_ERROR` | Timeout, connection issues | Retry tomorrow |

### 2. Smart Retry Logic

**Permanent failures (INVALID_TICKER, DELISTED):**
- Status changed to `FAILED`
- Excluded from all future retry attempts
- Archived after 90 days to keep queue clean

**Temporary failures (RATE_LIMIT, NETWORK_ERROR):**
- Status remains `TRACKING`
- Will be retried in tomorrow's run
- No limit on retry count (may eventually succeed)

### 3. Reduced Log Noise

**Old logging (15+ lines per run):**
```
📊 GPUS - 90 days elapsed
⚠️  Failed to fetch outcomes after 3 retries
📊 GCV - 30 days elapsed
⚠️  Failed to fetch outcomes after 3 retries
[... 12 more failures ...]
```

**New logging (concise summary):**
```
UPDATE COMPLETE
======================================================================
  Updated: 5
  Matured: 2
  Failed: 15

  ⚠️  Permanent failures (will not retry): 7
     • INVALID_TICKER: 3
       Examples: XIVYX, PHXE., N.A.
     • DELISTED: 4
       Examples: GPUS, GCV, MTDR

  ⚠️  Temporary failures (will retry tomorrow): 8
     • NETWORK_ERROR: 8
```

### 4. Profile Quality Protection

**Impact on insider profiles:**
- Failed trades are **excluded entirely** from profile calculations
- Profiles use only trades with successful outcomes
- Minimum 3 successful trades required for profile (failed trades don't count)
- Conservative approach: better to exclude than to bias with bad data

**Example:**
```
Insider has 10 trades:
  - 8 successful outcomes → Used for profile calculation
  - 2 failed (no data)   → Excluded from profile

Profile metrics calculated from 8 trades only.
```

## Implementation Details

### New Track Record Fields

```python
{
  'status': 'FAILED',  # New status (was only TRACKING or MATURED)
  'failure_type': 'DELISTED',  # Categorization
  'failure_reason': 'No trading history available',  # Detailed reason
  'failure_count': 3,  # Number of failed attempts
  'last_updated': '2025-12-11T10:30:00'
}
```

### Invalid Ticker Detection

```python
def _is_invalid_ticker_format(ticker: str) -> bool:
    """
    Detects obviously invalid ticker formats:
    - N.A., N/A, NONE, NULL (placeholders)
    - Trailing periods (PHXE.)
    - Spaces in ticker
    - Too long (>10 chars)
    - Empty string
    """
```

### Failure Categorization in Fetch

```python
def _fetch_outcomes_with_retry(...) -> Dict:
    """
    Returns:
      {'outcomes': {...}}  # On success

      {'failure_type': 'DELISTED',      # On failure
       'failure_reason': '...'}
    """
```

## Statistics

Based on current tracking queue analysis:

- **Total TRACKING trades:** 4,992
- **True failures (missing expected outcomes):** 181 (3.6%)
- **Breakdown by horizon:**
  - 30d failures: 127
  - 60d failures: 61
  - 90d failures: 93
  - 180d failures: 6

**Top failing tickers:**
- XIVYX (11 trades) - Mutual fund ticker
- PHXE. (9 trades) - Invalid format (trailing period)
- MTDR (6 trades) - Possibly delisted
- N.A. (4 trades) - Placeholder value

## Testing

Run the demonstration script to see the improvements:

```bash
python3 test_failure_handling.py
```

This shows:
1. Old vs new logging output
2. Failure categorization examples
3. Profile calculation impact
4. Next-day behavior (skipping permanent failures)

## Benefits

✅ **Reduced log noise** - 15+ lines → 5 line summary
✅ **Intelligent retry** - Permanent failures never retried again
✅ **Better debugging** - Clear failure reasons and categories
✅ **Clean queue** - Old failures archived after 90 days
✅ **Protected profiles** - Failed trades don't degrade quality
✅ **Actionable data** - Easy to see which failures are fixable

## Future Improvements

Potential enhancements:
1. Retry backoff for temporary failures (longer delay after repeated failures)
2. Manual override to retry permanently failed trades
3. Dashboard showing failure analytics over time
4. Alert if failure rate exceeds threshold
5. Alternative data sources for delisted stocks

## Files Changed

- `insider_performance_auto_tracker.py` - Core failure handling logic
- `test_failure_handling.py` - Demonstration script (new)
- `FAILURE_HANDLING_IMPROVEMENTS.md` - This documentation (new)

## Backwards Compatibility

- Existing tracking queue works without modification
- New fields added only when failures occur
- Old MATURED/TRACKING records unchanged
- No migration needed
