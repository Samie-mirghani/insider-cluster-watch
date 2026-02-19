#!/usr/bin/env python3
"""
Unit tests for insider performance profile filtering.

Covers:
- Penny stock filter boundary behavior ($1.00 threshold)
- Stale profile purge correctness (purge happens after min_trades gate)
- dtype safety on entry_price (non-numeric values don't crash)

These are unit-level tests that don't require external services.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
from types import ModuleType

# Mock yfinance before importing the tracker (yfinance may not be installed in CI)
yf_mock = ModuleType('yfinance')
yf_mock.Ticker = MagicMock()
sys.modules['yfinance'] = yf_mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / 'jobs'))

from insider_performance_tracker import (
    InsiderPerformanceTracker,
    MIN_ENTRY_PRICE_FOR_PROFILE,
)

PASS = 0
FAIL = 0


def report(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} — {detail}")


def make_trade_row(insider_name, ticker, entry_price, return_30d=None,
                   return_90d=None, return_180d=None, trade_date=None):
    """Helper: build a single trade row as a dict."""
    if trade_date is None:
        trade_date = datetime(2025, 6, 1)
    return {
        'trade_date': trade_date,
        'ticker': ticker,
        'insider_name': insider_name,
        'insider_name_raw': insider_name,
        'title': 'CEO',
        'qty': 1000,
        'price': entry_price,
        'value': entry_price * 1000 if isinstance(entry_price, (int, float)) else 0,
        'entry_price': entry_price,
        'outcome_30d': None,
        'outcome_60d': None,
        'outcome_90d': None,
        'outcome_180d': None,
        'return_30d': return_30d,
        'return_60d': None,
        'return_90d': return_90d,
        'return_180d': return_180d,
        'last_updated': datetime.now().isoformat(),
    }


def build_tracker_with_trades(trades, existing_profiles=None):
    """
    Build an InsiderPerformanceTracker with injected trade data,
    bypassing file I/O.
    """
    with patch.object(InsiderPerformanceTracker, '__init__', lambda self, **kw: None):
        tracker = InsiderPerformanceTracker()

    tracker.lookback_years = 3
    tracker.min_trades_for_score = 3
    tracker.verbose = False
    tracker.name_mapping = {}
    tracker.profiles = dict(existing_profiles) if existing_profiles else {}
    tracker.trades_history = pd.DataFrame(trades)

    # Mock _save_profiles so it doesn't write to disk
    tracker._save_profiles = MagicMock()

    # Mock _get_spy_return so it doesn't hit the network
    tracker._get_spy_return = MagicMock(return_value=5.0)

    return tracker


# ─── Test 1: Penny stock filter boundary — $0.50 is excluded ─────────────────

def test_penny_filter_excludes_below_threshold():
    """Trades with entry_price < $1.00 must be excluded from profiles."""
    trades = [
        make_trade_row('Penny Pete', 'PNNY', 0.50,
                       return_90d=500.0, trade_date=datetime(2025, 1, i+1))
        for i in range(5)
    ]
    tracker = build_tracker_with_trades(trades)
    tracker.calculate_insider_profiles()

    ok = 'Penny Pete' not in tracker.profiles
    report("Penny stock trades (all $0.50) excluded from profiles", ok,
           f"Expected no profile, got: "
           f"{tracker.profiles.get('Penny Pete', {}).get('total_trades', 'absent')}")


# ─── Test 2: Penny stock filter boundary — $1.00 exactly is included ─────────

def test_penny_filter_includes_at_threshold():
    """Trades with entry_price == $1.00 must NOT be filtered (boundary)."""
    trades = [
        make_trade_row('Dollar Dave', 'DLRR', 1.00,
                       return_90d=10.0, trade_date=datetime(2025, 1, i+1))
        for i in range(5)
    ]
    tracker = build_tracker_with_trades(trades)
    tracker.calculate_insider_profiles()

    ok = 'Dollar Dave' in tracker.profiles
    report("Trades at exactly $1.00 are included in profiles", ok,
           "Profile was not created for $1.00 entry price")


# ─── Test 3: Penny stock filter boundary — $0.99 excluded, $1.01 kept ────────

def test_penny_filter_boundary_precision():
    """$0.99 is excluded, $1.01 is kept — no off-by-one."""
    trades_099 = [
        make_trade_row('Borderline Bob', 'BORD', 0.99,
                       return_90d=20.0, trade_date=datetime(2025, 1, i+1))
        for i in range(5)
    ]
    trades_101 = [
        make_trade_row('Safe Sally', 'SAFE', 1.01,
                       return_90d=20.0, trade_date=datetime(2025, 1, i+1))
        for i in range(5)
    ]
    tracker = build_tracker_with_trades(trades_099 + trades_101)
    tracker.calculate_insider_profiles()

    ok_excluded = 'Borderline Bob' not in tracker.profiles
    ok_included = 'Safe Sally' in tracker.profiles
    report("$0.99 excluded from profiles", ok_excluded,
           "Borderline Bob ($0.99) should be excluded")
    report("$1.01 included in profiles", ok_included,
           "Safe Sally ($1.01) should be included")


# ─── Test 4: Mixed-price insider keeps qualifying trades ─────────────────────

def test_mixed_price_insider_keeps_qualifying_trades():
    """An insider with some penny trades and some good trades keeps the good ones."""
    penny_trades = [
        make_trade_row('Mixed Mike', 'MIXX', 0.05,
                       return_90d=9000.0, trade_date=datetime(2025, 1, i+1))
        for i in range(3)
    ]
    good_trades = [
        make_trade_row('Mixed Mike', 'MIXX', 5.00,
                       return_90d=15.0, trade_date=datetime(2025, 2, i+1))
        for i in range(4)
    ]
    tracker = build_tracker_with_trades(penny_trades + good_trades)
    tracker.calculate_insider_profiles()

    ok = 'Mixed Mike' in tracker.profiles
    total = tracker.profiles.get('Mixed Mike', {}).get('total_trades', 0)
    ok_count = total == 4  # Only the $5.00 trades
    report("Mixed-price insider gets a profile", ok,
           "Mixed Mike should have a profile from $5.00 trades")
    report("Mixed-price insider profile only counts non-penny trades", ok_count,
           f"Expected 4 trades, got {total}")


# ─── Test 5: Stale profile purge — penny-stock-only insider purged ───────────

def test_stale_purge_removes_penny_only_profiles():
    """A pre-existing profile for a penny-stock-only insider must be purged."""
    trades = [
        make_trade_row('Ghost Gary', 'GHST', 0.10,
                       return_90d=200.0, trade_date=datetime(2025, 1, i+1))
        for i in range(5)
    ]
    # Pre-existing profile from a previous run
    existing_profiles = {
        'Ghost Gary': {'overall_score': 95.0, 'total_trades': 5}
    }
    tracker = build_tracker_with_trades(trades, existing_profiles=existing_profiles)
    tracker.calculate_insider_profiles()

    ok = 'Ghost Gary' not in tracker.profiles
    report("Stale profile purged when all trades are penny stocks", ok,
           "Ghost Gary's stale profile should be removed")


# ─── Test 6: Stale profile purge — below min_trades after filter ─────────────

def test_stale_purge_removes_below_min_trades():
    """A pre-existing profile is purged if qualifying trades drop below min_trades_for_score."""
    trades = [
        # Only 2 qualifying trades (below default min_trades_for_score=3)
        make_trade_row('Fading Fred', 'FADE', 5.00,
                       return_90d=10.0, trade_date=datetime(2025, 1, i+1))
        for i in range(2)
    ]
    existing_profiles = {
        'Fading Fred': {'overall_score': 70.0, 'total_trades': 5}
    }
    tracker = build_tracker_with_trades(trades, existing_profiles=existing_profiles)
    tracker.calculate_insider_profiles()

    ok = 'Fading Fred' not in tracker.profiles
    report("Stale profile purged when trades drop below min_trades_for_score", ok,
           "Fading Fred's stale profile should be removed (only 2 trades left)")


# ─── Test 7: Stale purge doesn't remove active profiles ─────────────────────

def test_stale_purge_keeps_active_profiles():
    """Profiles for insiders who still qualify must NOT be purged."""
    trades = [
        make_trade_row('Active Alice', 'ACTV', 10.00,
                       return_90d=12.0, trade_date=datetime(2025, 1, i+1))
        for i in range(5)
    ]
    existing_profiles = {
        'Active Alice': {'overall_score': 80.0, 'total_trades': 5}
    }
    tracker = build_tracker_with_trades(trades, existing_profiles=existing_profiles)
    tracker.calculate_insider_profiles()

    ok = 'Active Alice' in tracker.profiles
    report("Active insider's profile is kept after recalculation", ok,
           "Active Alice should still have a profile")


# ─── Test 8: dtype safety — non-numeric entry_price doesn't crash ────────────

def test_dtype_safety_non_numeric_entry_price():
    """Non-numeric entry_price values should be coerced to NaN, not crash."""
    trades = [
        make_trade_row('Normal Nancy', 'NORM', 10.0,
                       return_90d=8.0, trade_date=datetime(2025, 1, i+1))
        for i in range(4)
    ]
    # Inject a corrupted row with string entry_price
    corrupted = make_trade_row('Normal Nancy', 'NORM', 'N/A',
                               return_90d=5.0, trade_date=datetime(2025, 2, 1))
    trades.append(corrupted)

    tracker = build_tracker_with_trades(trades)

    try:
        tracker.calculate_insider_profiles()
        ok = 'Normal Nancy' in tracker.profiles
        report("Non-numeric entry_price coerced without crash", ok,
               "Normal Nancy should have a profile (corrupted row treated as NaN)")
    except (TypeError, ValueError) as e:
        report("Non-numeric entry_price coerced without crash", False,
               f"Crashed with: {e}")


# ─── Test 9: All trades filtered yields no crash ─────────────────────────────

def test_all_trades_filtered_no_crash():
    """If every trade is a penny stock, the method should return gracefully."""
    trades = [
        make_trade_row('All Penny', 'APNY', 0.05,
                       return_90d=100.0, trade_date=datetime(2025, 1, i+1))
        for i in range(5)
    ]
    tracker = build_tracker_with_trades(trades)

    try:
        tracker.calculate_insider_profiles()
        ok = len(tracker.profiles) == 0
        report("All-penny-stock dataset produces no profiles without crash", ok,
               f"Expected 0 profiles, got {len(tracker.profiles)}")
    except Exception as e:
        report("All-penny-stock dataset produces no profiles without crash", False,
               f"Crashed with: {e}")


# ─── Run all tests ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*70)
    print("INSIDER PERFORMANCE PROFILE FILTER TESTS")
    print("="*70 + "\n")

    test_penny_filter_excludes_below_threshold()
    test_penny_filter_includes_at_threshold()
    test_penny_filter_boundary_precision()
    test_mixed_price_insider_keeps_qualifying_trades()
    test_stale_purge_removes_penny_only_profiles()
    test_stale_purge_removes_below_min_trades()
    test_stale_purge_keeps_active_profiles()
    test_dtype_safety_non_numeric_entry_price()
    test_all_trades_filtered_no_crash()

    print(f"\n{'='*70}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    print(f"{'='*70}\n")

    sys.exit(1 if FAIL > 0 else 0)
