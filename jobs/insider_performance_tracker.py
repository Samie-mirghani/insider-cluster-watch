"""
Insider Performance Tracker - Follow-the-Smart-Money Scoring

Tracks individual insider trading performance over time to identify which insiders
have the best track record of timing their purchases. This allows us to weight
current signals based on historical insider performance.

Core Concept:
- Track every insider purchase going back 2-3 years
- Calculate outcomes: stock performance at 30/90/180 day marks
- Build insider profiles with win rates, average returns, Sharpe ratios
- Score current signals based on the insider's historical track record
"""

import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import yfinance as yf
import time
from pathlib import Path
import re
from difflib import SequenceMatcher

# Data paths
DATA_DIR = Path(__file__).parent.parent / 'data'
INSIDER_PROFILES_PATH = DATA_DIR / 'insider_profiles.json'
INSIDER_TRADES_HISTORY_PATH = DATA_DIR / 'insider_trades_history.csv'


class InsiderPerformanceTracker:
    """
    Tracks and analyzes individual insider trading performance over time.
    """

    def __init__(self, lookback_years: int = 3, min_trades_for_score: int = 3, verbose: bool = False):
        """
        Initialize the tracker.

        Args:
            lookback_years: How many years of history to analyze (default: 3)
            min_trades_for_score: Minimum trades needed to calculate a reliable score (default: 3)
            verbose: Enable verbose logging (default: False)
        """
        self.lookback_years = lookback_years
        self.min_trades_for_score = min_trades_for_score
        self.verbose = verbose
        self.name_mapping = self._load_name_mapping()  # Maps raw names to canonical names
        self.profiles = self._load_profiles()
        self.trades_history = self._load_trades_history()

    def _load_profiles(self) -> Dict:
        """Load insider profiles from JSON file."""
        if INSIDER_PROFILES_PATH.exists():
            try:
                with open(INSIDER_PROFILES_PATH, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {INSIDER_PROFILES_PATH}, starting fresh")
                return {}
        return {}

    def _save_profiles(self):
        """Save insider profiles to JSON file."""
        INSIDER_PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(INSIDER_PROFILES_PATH, 'w') as f:
            json.dump(self.profiles, f, indent=2, default=str)

    def _load_name_mapping(self) -> Dict:
        """Load insider name mapping from JSON file."""
        name_mapping_path = DATA_DIR / 'insider_name_mapping.json'
        if name_mapping_path.exists():
            try:
                with open(name_mapping_path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {name_mapping_path}, starting fresh")
                return {}
        return {}

    def _save_name_mapping(self):
        """Save insider name mapping to JSON file."""
        name_mapping_path = DATA_DIR / 'insider_name_mapping.json'
        name_mapping_path.parent.mkdir(parents=True, exist_ok=True)
        with open(name_mapping_path, 'w') as f:
            json.dump(self.name_mapping, f, indent=2)

    def _normalize_insider_name(self, name: str, company: str = None) -> str:
        """
        Normalize insider name to canonical format with fuzzy matching.

        Handles common variations:
        - "Last, First Middle" → "First Middle Last"
        - Removes punctuation and titles
        - Fuzzy matches against existing names (>85% similarity)
        - Uses company ticker to disambiguate common names

        Args:
            name: Raw insider name from Form 4
            company: Company ticker (helps disambiguate common names)

        Returns:
            Canonical name format

        Examples:
            "Cook, Timothy D." → "Timothy D Cook"
            "Tim Cook" → "Timothy D Cook" (fuzzy matched)
            "T.D. Cook" → "Timothy D Cook" (fuzzy matched)
        """
        if not name or not isinstance(name, str):
            return "UNKNOWN"

        # Step 1: Clean the name
        cleaned = name.strip()

        # Step 2: Handle "Last, First" format
        if ',' in cleaned:
            parts = cleaned.split(',', 1)  # Only split on first comma
            if len(parts) == 2:
                last, first = parts
                cleaned = f"{first.strip()} {last.strip()}"

        # Step 3: Remove common titles and suffixes
        titles_suffixes = [
            r'\bMr\.?\b', r'\bMrs\.?\b', r'\bMs\.?\b', r'\bDr\.?\b',
            r'\bJr\.?\b', r'\bSr\.?\b', r'\bIII\b', r'\bII\b', r'\bIV\b'
        ]
        for pattern in titles_suffixes:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        # Step 4: Normalize spaces and punctuation
        cleaned = re.sub(r'[^\w\s]', '', cleaned)  # Remove punctuation
        cleaned = re.sub(r'\s+', ' ', cleaned)      # Normalize spaces
        cleaned = cleaned.strip().lower()

        # Step 5: Create lookup key (with company if provided)
        lookup_key = f"{cleaned}|{company}" if company else cleaned

        # Step 6: Check if we've seen this exact name before
        if lookup_key in self.name_mapping:
            return self.name_mapping[lookup_key]

        # Step 7: Fuzzy match against existing names
        best_match = None
        best_ratio = 0

        for existing_key, canonical_name in self.name_mapping.items():
            # Only compare same-company insiders if company specified
            if company and '|' in existing_key:
                existing_name, existing_company = existing_key.split('|', 1)
                if existing_company != company:
                    continue
            else:
                existing_name = existing_key.split('|')[0] if '|' in existing_key else existing_key

            # Calculate similarity ratio
            ratio = SequenceMatcher(None, cleaned.split('|')[0], existing_name).ratio()

            # If very similar (>85% match), consider it the same person
            if ratio > 0.85 and ratio > best_ratio:
                best_ratio = ratio
                best_match = canonical_name

        # If found good match, use it
        if best_match and best_ratio > 0.85:
            self.name_mapping[lookup_key] = best_match
            self._save_name_mapping()
            # print(f"   Matched '{name}' → '{best_match}' (similarity: {best_ratio:.1%})")
            return best_match

        # Otherwise, this is a new unique person - create canonical name
        canonical = self._format_canonical_name(cleaned.split('|')[0])
        self.name_mapping[lookup_key] = canonical
        self._save_name_mapping()
        return canonical

    def _format_canonical_name(self, normalized_name: str) -> str:
        """
        Format normalized name to Title Case canonical format.

        Args:
            normalized_name: Lowercase normalized name

        Returns:
            Title case formatted name

        Example:
            "timothy d cook" → "Timothy D Cook"
        """
        return ' '.join(word.capitalize() for word in normalized_name.split())

    def _load_trades_history(self) -> pd.DataFrame:
        """Load historical trades from CSV file."""
        if INSIDER_TRADES_HISTORY_PATH.exists():
            try:
                df = pd.read_csv(INSIDER_TRADES_HISTORY_PATH, parse_dates=['trade_date'])
                return df
            except Exception as e:
                print(f"Warning: Could not load {INSIDER_TRADES_HISTORY_PATH}: {e}")
                return self._create_empty_trades_df()
        return self._create_empty_trades_df()

    def _create_empty_trades_df(self) -> pd.DataFrame:
        """Create an empty trades history DataFrame with the correct schema."""
        return pd.DataFrame(columns=[
            'trade_date', 'ticker', 'insider_name', 'insider_name_raw', 'title', 'qty', 'price',
            'value', 'entry_price', 'outcome_30d', 'outcome_60d', 'outcome_90d', 'outcome_180d',
            'return_30d', 'return_60d', 'return_90d', 'return_180d', 'last_updated'
        ])

    def _save_trades_history(self):
        """Save trades history to CSV file."""
        INSIDER_TRADES_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.trades_history.to_csv(INSIDER_TRADES_HISTORY_PATH, index=False)

    def add_trades(self, trades_df: pd.DataFrame):
        """
        Add new trades to the tracking system.

        Args:
            trades_df: DataFrame with columns: trade_date, ticker, insider, title, qty, price, value
        """
        if trades_df.empty:
            return

        # Normalize column names
        trades_df = trades_df.copy()
        if 'insider' in trades_df.columns and 'insider_name' not in trades_df.columns:
            trades_df['insider_name'] = trades_df['insider']

        # Prepare new trades for insertion
        new_trades = []
        for _, row in trades_df.iterrows():
            # Skip if already in history (deduplication)
            if not self.trades_history.empty:
                existing = self.trades_history[
                    (self.trades_history['ticker'] == row['ticker']) &
                    (self.trades_history['insider_name'] == row.get('insider_name', row.get('insider'))) &
                    (self.trades_history['trade_date'] == pd.to_datetime(row['trade_date']))
                ]
                if not existing.empty:
                    continue

            # Normalize insider name to handle variations
            raw_name = row.get('insider_name', row.get('insider', 'UNKNOWN'))
            ticker = row['ticker']
            normalized_name = self._normalize_insider_name(raw_name, ticker)

            new_trade = {
                'trade_date': pd.to_datetime(row['trade_date']),
                'ticker': ticker,
                'insider_name': normalized_name,  # Use normalized name
                'insider_name_raw': raw_name,      # Keep original for reference
                'title': row.get('title', ''),
                'qty': row.get('qty', 0),
                'price': row.get('price', 0),
                'value': row.get('value', 0),
                'entry_price': row.get('price', 0),  # Use purchase price as entry
                'outcome_30d': None,
                'outcome_60d': None,  # BUG FIX: Added missing 60d field
                'outcome_90d': None,
                'outcome_180d': None,
                'return_30d': None,
                'return_60d': None,   # BUG FIX: Added missing 60d field
                'return_90d': None,
                'return_180d': None,
                'last_updated': datetime.now().isoformat()
            }
            new_trades.append(new_trade)

        if new_trades:
            new_df = pd.DataFrame(new_trades)
            # Fix for pandas FutureWarning: handle empty DataFrame properly
            if self.trades_history.empty:
                self.trades_history = new_df
            else:
                self.trades_history = pd.concat([self.trades_history, new_df], ignore_index=True)

            # Only print summary when adding multiple trades or in verbose mode
            if self.verbose or len(new_trades) > 5:
                print(f"Added {len(new_trades)} new insider trades to tracking system")

            # CRITICAL BUG FIX: Save to disk to persist changes
            self._save_trades_history()

    def update_outcomes(self, batch_size: int = 50, rate_limit_delay: float = 0.3):
        """
        Update outcomes for trades that don't have complete outcome data.

        Args:
            batch_size: Maximum number of trades to update per run (to avoid API rate limits)
            rate_limit_delay: Delay between API calls in seconds
        """
        if self.trades_history.empty:
            return

        # Find trades that need outcome updates
        today = datetime.now()
        needs_update = self.trades_history.copy()

        # Filter for trades old enough to have outcomes
        needs_update = needs_update[
            pd.to_datetime(needs_update['trade_date']) < (today - timedelta(days=30))
        ]

        # Prioritize trades with missing outcomes
        missing_outcomes = needs_update[
            needs_update['outcome_30d'].isna() |
            needs_update['outcome_60d'].isna() |  # BUG FIX: Check 60d outcomes
            needs_update['outcome_90d'].isna() |
            needs_update['outcome_180d'].isna()
        ]

        if missing_outcomes.empty:
            print("All tracked trades have complete outcome data")
            return

        # Process in batches
        to_process = missing_outcomes.head(batch_size)
        print(f"Updating outcomes for {len(to_process)} trades (batch size: {batch_size})")

        updated_count = 0
        for idx, row in to_process.iterrows():
            try:
                outcomes = self._calculate_trade_outcomes(
                    row['ticker'],
                    row['trade_date'],
                    row['entry_price']
                )

                if outcomes:
                    # Update the dataframe
                    self.trades_history.loc[idx, 'outcome_30d'] = outcomes.get('price_30d')
                    self.trades_history.loc[idx, 'outcome_60d'] = outcomes.get('price_60d')  # BUG FIX: Update 60d
                    self.trades_history.loc[idx, 'outcome_90d'] = outcomes.get('price_90d')
                    self.trades_history.loc[idx, 'outcome_180d'] = outcomes.get('price_180d')
                    self.trades_history.loc[idx, 'return_30d'] = outcomes.get('return_30d')
                    self.trades_history.loc[idx, 'return_60d'] = outcomes.get('return_60d')  # BUG FIX: Update 60d
                    self.trades_history.loc[idx, 'return_90d'] = outcomes.get('return_90d')
                    self.trades_history.loc[idx, 'return_180d'] = outcomes.get('return_180d')
                    self.trades_history.loc[idx, 'last_updated'] = datetime.now().isoformat()
                    updated_count += 1

                # Rate limiting
                time.sleep(rate_limit_delay)

            except Exception as e:
                print(f"Error updating outcomes for {row['ticker']} ({row['insider_name']}): {e}")
                continue

        print(f"Successfully updated outcomes for {updated_count}/{len(to_process)} trades")

        # Save updated history
        if updated_count > 0:
            self._save_trades_history()

    def _calculate_trade_outcomes(self, ticker: str, trade_date: datetime,
                                  entry_price: float, max_retries: int = 3) -> Optional[Dict]:
        """
        Calculate outcomes for a single trade at 30/90/180 day marks with retry logic.

        Args:
            ticker: Stock ticker symbol
            trade_date: Date of the trade
            entry_price: Purchase price
            max_retries: Maximum number of retry attempts (default: 3)

        Returns:
            Dict with price and return outcomes, or None if data unavailable
        """
        delay = 1.0  # Initial delay in seconds

        for attempt in range(max_retries):
            try:
                # Convert to datetime if needed
                if isinstance(trade_date, str):
                    trade_date = pd.to_datetime(trade_date)

                # Fetch historical data
                # Start a few days before trade date to ensure we have data
                start_date = trade_date - timedelta(days=5)
                end_date = trade_date + timedelta(days=200)  # Give buffer beyond 180 days

                stock = yf.Ticker(ticker)
                hist = stock.history(start=start_date, end=end_date)

                if hist.empty:
                    return None

                # Find the actual trade date or closest after
                hist = hist.reset_index()
                hist['Date'] = pd.to_datetime(hist['Date']).dt.tz_localize(None)  # Remove timezone for comparison

                # Normalize trade_date to timezone-naive for comparison
                trade_date_normalized = pd.to_datetime(trade_date)
                if trade_date_normalized.tz is not None:
                    trade_date_normalized = trade_date_normalized.tz_localize(None)

                trade_idx = hist[hist['Date'] >= trade_date_normalized].head(1)

                if trade_idx.empty:
                    return None

                trade_position = trade_idx.index[0]

                outcomes = {}

                # Calculate outcomes at different time horizons
                # BUG FIX: Added 60d to match schema
                for days, key in [(30, '30d'), (60, '60d'), (90, '90d'), (180, '180d')]:
                    target_date = trade_date_normalized + timedelta(days=days)

                    # Find price closest to target date (but after trade date)
                    future_data = hist[hist['Date'] >= target_date]

                    if not future_data.empty:
                        # Use the first available price on or after target date
                        outcome_price = future_data.iloc[0]['Close']
                        outcomes[f'price_{key}'] = outcome_price
                        outcomes[f'return_{key}'] = ((outcome_price - entry_price) / entry_price) * 100
                    else:
                        outcomes[f'price_{key}'] = None
                        outcomes[f'return_{key}'] = None

                return outcomes

            except Exception as e:
                if attempt < max_retries - 1:
                    # Retry with exponential backoff
                    print(f"   Attempt {attempt + 1} failed for {ticker}: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                    continue
                else:
                    # Final attempt failed
                    print(f"   Error calculating outcomes for {ticker} after {max_retries} attempts: {e}")
                    return None

        return None

    def calculate_insider_profiles(self):
        """
        Calculate performance profiles for all insiders based on their trade history.

        Updates self.profiles with comprehensive statistics for each insider.
        """
        if self.trades_history.empty:
            print("No trade history available to calculate profiles")
            return

        # Filter for trades with outcome data
        trades_with_outcomes = self.trades_history[
            self.trades_history['return_30d'].notna() |
            self.trades_history['return_90d'].notna() |
            self.trades_history['return_180d'].notna()
        ].copy()

        if trades_with_outcomes.empty:
            print("No trades with outcome data available")
            return

        # Group by insider
        for insider_name in trades_with_outcomes['insider_name'].unique():
            insider_trades = trades_with_outcomes[
                trades_with_outcomes['insider_name'] == insider_name
            ].copy()

            if len(insider_trades) < self.min_trades_for_score:
                continue  # Not enough trades for reliable statistics

            profile = {
                'name': insider_name,
                'total_trades': len(insider_trades),
                'most_recent_trade': insider_trades['trade_date'].max().isoformat(),
                'oldest_trade': insider_trades['trade_date'].min().isoformat(),
                'companies_traded': insider_trades['ticker'].nunique(),
                'tickers': insider_trades['ticker'].unique().tolist(),
            }

            # Calculate performance metrics for each time horizon
            for horizon in ['30d', '90d', '180d']:
                returns_col = f'return_{horizon}'
                valid_returns = insider_trades[insider_trades[returns_col].notna()][returns_col]

                if len(valid_returns) > 0:
                    # Win rate (% of profitable trades)
                    win_rate = (valid_returns > 0).sum() / len(valid_returns) * 100

                    # Average return
                    avg_return = valid_returns.mean()

                    # Median return (more robust to outliers)
                    median_return = valid_returns.median()

                    # Best and worst returns
                    best_return = valid_returns.max()
                    worst_return = valid_returns.min()

                    # Standard deviation (for Sharpe calculation)
                    std_return = valid_returns.std()

                    # Sharpe ratio (assuming 0% risk-free rate, annualized)
                    # Sharpe = (Average Return - Risk Free Rate) / Std Dev
                    if std_return > 0:
                        sharpe = (avg_return / std_return)
                    else:
                        sharpe = 0

                    profile[f'win_rate_{horizon}'] = round(win_rate, 2)
                    profile[f'avg_return_{horizon}'] = round(avg_return, 2)
                    profile[f'median_return_{horizon}'] = round(median_return, 2)
                    profile[f'best_return_{horizon}'] = round(best_return, 2)
                    profile[f'worst_return_{horizon}'] = round(worst_return, 2)
                    profile[f'sharpe_{horizon}'] = round(sharpe, 2)
                    profile[f'sample_size_{horizon}'] = len(valid_returns)
                else:
                    profile[f'win_rate_{horizon}'] = None
                    profile[f'avg_return_{horizon}'] = None
                    profile[f'median_return_{horizon}'] = None
                    profile[f'best_return_{horizon}'] = None
                    profile[f'worst_return_{horizon}'] = None
                    profile[f'sharpe_{horizon}'] = None
                    profile[f'sample_size_{horizon}'] = 0

            # Calculate recency-weighted performance (last 12 months weighted 2x)
            recent_cutoff = datetime.now() - timedelta(days=365)
            recent_trades = insider_trades[
                pd.to_datetime(insider_trades['trade_date']) >= recent_cutoff
            ]

            if not recent_trades.empty and recent_trades['return_90d'].notna().any():
                recent_avg_return = recent_trades['return_90d'].mean()
                profile['recent_avg_return_90d'] = round(recent_avg_return, 2)
                profile['recent_trade_count'] = len(recent_trades)
            else:
                profile['recent_avg_return_90d'] = None
                profile['recent_trade_count'] = 0

            # Calculate overall score (0-100 scale)
            # Based on: 90-day performance (primary), win rate, Sharpe ratio, recency
            score_components = []

            # Component 1: 90-day average return (weighted 40%)
            if profile['avg_return_90d'] is not None:
                # Normalize: 0% = 50, +20% = 100, -20% = 0
                return_score = 50 + (profile['avg_return_90d'] * 2.5)
                return_score = max(0, min(100, return_score))
                score_components.append(return_score * 0.40)

            # Component 2: 90-day win rate (weighted 30%)
            if profile['win_rate_90d'] is not None:
                score_components.append(profile['win_rate_90d'] * 0.30)

            # Component 3: Sharpe ratio (weighted 20%)
            if profile['sharpe_90d'] is not None:
                # Normalize: 0 = 50, 2.0 = 100, -2.0 = 0
                sharpe_score = 50 + (profile['sharpe_90d'] * 25)
                sharpe_score = max(0, min(100, sharpe_score))
                score_components.append(sharpe_score * 0.20)

            # Component 4: Recent performance bonus (weighted 10%)
            if profile['recent_avg_return_90d'] is not None:
                recent_score = 50 + (profile['recent_avg_return_90d'] * 2.5)
                recent_score = max(0, min(100, recent_score))
                score_components.append(recent_score * 0.10)

            if score_components:
                overall_score = sum(score_components)
                profile['overall_score'] = round(overall_score, 2)
                profile['score_percentile'] = None  # Will calculate after all profiles done
            else:
                profile['overall_score'] = 50  # Neutral score if no data
                profile['score_percentile'] = None

            # Store profile
            self.profiles[insider_name] = profile

        # Calculate percentiles
        if self.profiles:
            scores = [p['overall_score'] for p in self.profiles.values() if p['overall_score'] is not None]
            if scores:
                for insider_name, profile in self.profiles.items():
                    if profile['overall_score'] is not None:
                        percentile = (sum(s <= profile['overall_score'] for s in scores) / len(scores)) * 100
                        profile['score_percentile'] = round(percentile, 1)

        print(f"Calculated profiles for {len(self.profiles)} insiders")

        # Save profiles
        self._save_profiles()

    def get_insider_score(self, insider_name: str, company: str = None) -> Dict:
        """
        Get the performance score for a specific insider.

        Args:
            insider_name: Name of the insider (will be normalized)
            company: Company ticker (optional, helps with name disambiguation)

        Returns:
            Dict with score and profile info, or default score if insider not tracked
        """
        # Normalize the name to match against profiles
        normalized_name = self._normalize_insider_name(insider_name, company)

        if normalized_name in self.profiles:
            return self.profiles[normalized_name]
        else:
            # Return neutral score for unknown insiders
            return {
                'name': normalized_name,
                'overall_score': 50,  # Neutral
                'score_percentile': 50,
                'total_trades': 0,
                'note': 'Insufficient historical data'
            }

    def get_signal_multiplier(self, insider_name: str, base_conviction: float) -> float:
        """
        Calculate a multiplier for the conviction score based on insider's track record.

        Args:
            insider_name: Name of the insider
            base_conviction: Original conviction score

        Returns:
            Multiplier to apply to conviction (0.5x to 2.0x range)
        """
        profile = self.get_insider_score(insider_name)
        overall_score = profile.get('overall_score', 50)

        # Convert 0-100 score to 0.5x - 2.0x multiplier
        # Score 50 (neutral) = 1.0x
        # Score 100 (excellent) = 2.0x
        # Score 0 (poor) = 0.5x
        multiplier = 0.5 + (overall_score / 100) * 1.5

        return round(multiplier, 2)

    def get_top_performers(self, n: int = 20, min_trades: int = 5) -> pd.DataFrame:
        """
        Get the top performing insiders.

        Args:
            n: Number of top performers to return
            min_trades: Minimum number of trades required

        Returns:
            DataFrame with top performers ranked by overall score
        """
        if not self.profiles:
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame.from_dict(self.profiles, orient='index')

        # Filter by minimum trades
        df = df[df['total_trades'] >= min_trades]

        if df.empty:
            return df

        # Sort by overall score
        df = df.sort_values('overall_score', ascending=False)

        # Select key columns
        cols = [
            'name', 'overall_score', 'score_percentile', 'total_trades',
            'win_rate_90d', 'avg_return_90d', 'sharpe_90d',
            'recent_avg_return_90d', 'companies_traded'
        ]
        available_cols = [c for c in cols if c in df.columns]

        return df[available_cols].head(n)

    def get_worst_performers(self, n: int = 20, min_trades: int = 5) -> pd.DataFrame:
        """
        Get the worst performing insiders (to potentially fade their signals).

        Args:
            n: Number of worst performers to return
            min_trades: Minimum number of trades required

        Returns:
            DataFrame with worst performers ranked by overall score
        """
        df = self.get_top_performers(n=1000, min_trades=min_trades)  # Get all
        if df.empty:
            return df
        return df.tail(n).sort_values('overall_score', ascending=True)

    def get_insider_report(self, insider_name: str) -> str:
        """
        Generate a detailed text report for a specific insider.

        Args:
            insider_name: Name of the insider

        Returns:
            Formatted text report
        """
        profile = self.get_insider_score(insider_name)

        if profile.get('total_trades', 0) == 0:
            return f"No historical data available for {insider_name}"

        report = []
        report.append(f"\n{'='*70}")
        report.append(f"INSIDER PERFORMANCE REPORT: {insider_name}")
        report.append(f"{'='*70}")
        report.append(f"Overall Score: {profile['overall_score']}/100 (Percentile: {profile.get('score_percentile', 'N/A')})")
        report.append(f"Total Trades Tracked: {profile['total_trades']}")
        report.append(f"Companies Traded: {profile['companies_traded']}")
        report.append(f"Date Range: {profile['oldest_trade'][:10]} to {profile['most_recent_trade'][:10]}")
        report.append("")

        report.append("PERFORMANCE BY TIME HORIZON:")
        report.append("-" * 70)

        for horizon, days in [('30d', 30), ('90d', 90), ('180d', 180)]:
            report.append(f"\n{days}-Day Performance:")
            sample_size = profile.get(f'sample_size_{horizon}', 0)
            if sample_size > 0:
                report.append(f"  Sample Size: {sample_size} trades")
                report.append(f"  Win Rate: {profile[f'win_rate_{horizon}']}%")
                report.append(f"  Avg Return: {profile[f'avg_return_{horizon}']}%")
                report.append(f"  Median Return: {profile[f'median_return_{horizon}']}%")
                report.append(f"  Best Trade: +{profile[f'best_return_{horizon}']}%")
                report.append(f"  Worst Trade: {profile[f'worst_return_{horizon}']}%")
                report.append(f"  Sharpe Ratio: {profile[f'sharpe_{horizon}']}")
            else:
                report.append(f"  No data available")

        report.append("")
        report.append("RECENT ACTIVITY (Last 12 Months):")
        report.append("-" * 70)
        recent_count = profile.get('recent_trade_count', 0)
        if recent_count > 0:
            report.append(f"  Trades: {recent_count}")
            report.append(f"  Avg 90-day Return: {profile['recent_avg_return_90d']}%")
        else:
            report.append("  No recent activity")

        report.append("")
        report.append(f"{'='*70}\n")

        return "\n".join(report)

    def check_data_freshness(self) -> Dict:
        """
        Check if performance data is fresh and up-to-date.

        Returns:
            Dict with freshness status:
            {
                'is_fresh': bool,
                'last_updated': datetime or None,
                'age_days': float or None,
                'status': 'OK' | 'WARNING' | 'STALE' | 'EMPTY' | 'UNKNOWN',
                'message': str
            }
        """
        if not self.profiles:
            return {
                'is_fresh': False,
                'last_updated': None,
                'age_days': None,
                'status': 'EMPTY',
                'message': '❌ No insider profiles loaded. Run bootstrap to populate data.'
            }

        # Find most recent update across all profiles and trades
        most_recent_profile = None
        most_recent_trade = None

        # Check profiles for last update
        for profile in self.profiles.values():
            if profile.get('most_recent_trade'):
                trade_date = pd.to_datetime(profile['most_recent_trade'])
                if most_recent_profile is None or trade_date > most_recent_profile:
                    most_recent_profile = trade_date

        # Check trades history for last update
        if not self.trades_history.empty and 'last_updated' in self.trades_history.columns:
            updates = self.trades_history['last_updated'].dropna()
            if not updates.empty:
                most_recent_trade = pd.to_datetime(updates.max())

        # Use the most recent timestamp
        most_recent = most_recent_profile or most_recent_trade

        if most_recent is None:
            return {
                'is_fresh': False,
                'last_updated': None,
                'age_days': None,
                'status': 'UNKNOWN',
                'message': '⚠️  Cannot determine data age - no timestamps found'
            }

        # Calculate age in days
        now = datetime.now()
        if most_recent.tzinfo is not None:
            # Make timezone-aware for comparison
            now = pd.Timestamp.now(tz=most_recent.tzinfo)

        age_seconds = (now - most_recent).total_seconds()
        age_days = age_seconds / 86400

        # Determine freshness status
        if age_days < 7:
            status = 'OK'
            is_fresh = True
            message = f'✅ Data is fresh (last updated {age_days:.1f} days ago)'
        elif age_days < 14:
            status = 'WARNING'
            is_fresh = True
            message = f'⚠️  Data is aging (last updated {age_days:.1f} days ago). Consider updating soon.'
        else:
            status = 'STALE'
            is_fresh = False
            message = f'❌ Data is STALE (last updated {age_days:.1f} days ago). Update NOW!'

        return {
            'is_fresh': is_fresh,
            'last_updated': most_recent,
            'age_days': age_days,
            'status': status,
            'message': message
        }

    def log_freshness_check(self):
        """
        Log data freshness status with formatted output.
        Call this at the start of your daily pipeline.

        Returns:
            Dict with alert info: {'alert': bool, 'message': str}
        """
        freshness = self.check_data_freshness()

        print(f"\n{'='*70}")
        print(f"INSIDER PERFORMANCE DATA FRESHNESS CHECK")
        print(f"{'='*70}")
        print(freshness['message'])

        if freshness['last_updated']:
            print(f"Last updated: {freshness['last_updated'].strftime('%Y-%m-%d %H:%M')}")

        if freshness['status'] != 'EMPTY':
            print(f"Total profiles: {len(self.profiles):,}")
            print(f"Total trades: {len(self.trades_history):,}")

        print(f"{'='*70}\n")

        # Return alert if data is stale or empty
        if freshness['status'] in ['STALE', 'EMPTY']:
            return {
                'alert': True,
                'status': freshness['status'],
                'message': freshness['message']
            }

        return {
            'alert': False,
            'status': freshness['status']
        }


def create_tracker(lookback_years: int = 3, min_trades: int = 3, verbose: bool = False) -> InsiderPerformanceTracker:
    """
    Convenience function to create a tracker instance.

    Args:
        lookback_years: Years of history to analyze
        min_trades: Minimum trades for scoring
        verbose: Enable verbose logging

    Returns:
        InsiderPerformanceTracker instance
    """
    return InsiderPerformanceTracker(lookback_years, min_trades, verbose)


if __name__ == '__main__':
    # Test/demo code
    print("Insider Performance Tracker - Test Mode")
    print("=" * 70)

    tracker = create_tracker()
    print(f"Loaded {len(tracker.profiles)} existing profiles")
    print(f"Historical trades: {len(tracker.trades_history)}")

    if not tracker.profiles:
        print("\nNo profiles yet. Run update_outcomes() and calculate_insider_profiles() to build them.")
    else:
        print("\nTop 10 Performers:")
        top = tracker.get_top_performers(n=10)
        if not top.empty:
            print(top.to_string())
