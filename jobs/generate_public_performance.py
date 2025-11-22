#!/usr/bin/env python3
"""
Generate public_performance.json for GitHub Pages dashboard

This script creates a public-facing performance summary without sensitive data.
Shows percentages and statistics, but NOT dollar amounts.
"""

import json
import os
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import yfinance as yf
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent / 'data'
OUTPUT_FILE = Path(__file__).parent.parent / 'public_performance.json'
PAPER_PORTFOLIO_FILE = DATA_DIR / 'paper_portfolio.json'
PAPER_TRADES_CSV = DATA_DIR / 'paper_trades.csv'


def load_portfolio():
    """Load current portfolio state"""
    if not PAPER_PORTFOLIO_FILE.exists():
        return None

    try:
        with open(PAPER_PORTFOLIO_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading portfolio: {e}")
        return None


def load_trades():
    """
    Load trade history

    Handles both old format (date, action, ticker...) and new format (entry_date, exit_date, pnl_pct...)
    """
    if not PAPER_TRADES_CSV.exists():
        return pd.DataFrame()

    try:
        # Read without parsing dates first to detect schema
        df = pd.read_csv(PAPER_TRADES_CSV)

        # Check which format we have
        if 'entry_date' in df.columns and 'exit_date' in df.columns:
            # New format - parse dates
            df = pd.read_csv(PAPER_TRADES_CSV, parse_dates=['entry_date', 'exit_date'])
        elif 'date' in df.columns:
            # Old format - parse date column
            df = pd.read_csv(PAPER_TRADES_CSV, parse_dates=['date'])

        return df
    except Exception as e:
        logger.error(f"Error loading trades CSV: {e}")
        return pd.DataFrame()


def get_current_price(ticker, fallback_price):
    """
    Fetch current price for a ticker using yfinance

    Args:
        ticker: Stock ticker symbol
        fallback_price: Fallback price if fetch fails

    Returns:
        Current price or fallback
    """
    try:
        logger.info(f"  Fetching current price for {ticker}...")
        ticker_obj = yf.Ticker(ticker)

        # Try multiple price sources in order of preference
        price = None

        # Method 1: currentPrice from info
        try:
            info = ticker_obj.info
            if info and isinstance(info, dict):
                if 'currentPrice' in info:
                    price = info.get('currentPrice')

                # Method 2: regularMarketPrice from info
                if not price or price <= 0:
                    price = info.get('regularMarketPrice')
        except Exception as e:
            logger.warning(f"    ⚠ Error accessing info for {ticker}: {e}")

        # Method 3: Get latest from history
        if not price or price <= 0:
            try:
                hist = ticker_obj.history(period='1d')
                if not hist.empty and 'Close' in hist.columns:
                    price = hist['Close'].iloc[-1]
            except Exception as e:
                logger.warning(f"    ⚠ Error accessing history for {ticker}: {e}")

        if price and price > 0:
            logger.info(f"    ✓ {ticker}: ${price:.2f}")
            return float(price)
        else:
            logger.warning(f"    ⚠ {ticker}: Using fallback ${fallback_price:.2f}")
            return fallback_price

    except Exception as e:
        logger.warning(f"    ⚠ Error fetching {ticker}: {str(e)}, using fallback ${fallback_price:.2f}")
        return fallback_price


def get_sp500_return(start_date, end_date=None):
    """
    Calculate S&P 500 return for comparison (Alpha calculation)

    Args:
        start_date: Start date for calculation
        end_date: End date (defaults to today)

    Returns:
        S&P 500 return percentage, or 0.0 if unable to fetch
    """
    try:
        logger.info("  Fetching S&P 500 data for Alpha calculation...")

        if end_date is None:
            end_date = datetime.utcnow()

        # Ensure dates are datetime objects
        if isinstance(start_date, str):
            start_date = pd.to_datetime(start_date)
        if isinstance(end_date, str):
            end_date = pd.to_datetime(end_date)

        # Fetch SPY data
        spy = yf.Ticker("SPY")
        hist = spy.history(start=start_date, end=end_date)

        if hist.empty or len(hist) < 2:
            logger.warning("    ⚠ Insufficient S&P 500 data")
            return 0.0

        start_price = hist['Close'].iloc[0]
        end_price = hist['Close'].iloc[-1]

        if start_price <= 0:
            return 0.0

        sp500_return = ((end_price - start_price) / start_price) * 100
        logger.info(f"    ✓ S&P 500 Return: {sp500_return:+.2f}%")

        return round(sp500_return, 2)

    except Exception as e:
        logger.warning(f"    ⚠ Error fetching S&P 500 data: {e}")
        return 0.0


def calculate_sharpe_ratio(returns, risk_free_rate=0.0):
    """Calculate Sharpe ratio from returns"""
    if len(returns) < 2:
        return 0.0

    excess_returns = returns - risk_free_rate
    if excess_returns.std() == 0:
        return 0.0

    # Annualized Sharpe ratio
    sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)  # 252 trading days
    return round(sharpe, 2)


def get_conviction_level(score):
    """Convert numeric score to conviction level"""
    if score >= 15:
        return "VERY HIGH"
    elif score >= 10:
        return "HIGH"
    elif score >= 7:
        return "MEDIUM"
    elif score >= 5:
        return "LOW"
    else:
        return "WATCH"


def generate_public_performance():
    """Generate public performance data"""

    portfolio = load_portfolio()
    trades_df = load_trades()

    # Initialize default data
    # Note: GitHub Actions runs in UTC, so we display UTC time
    now = datetime.utcnow()
    public_data = {
        "last_updated": now.strftime("%B %d, %Y at %H:%M UTC"),
        "total_return_pct": 0.0,
        "win_rate": 0.0,
        "completed_trades": 0,
        "active_trades": 0,
        "avg_return_per_trade": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "avg_hold_days": 0,
        "best_trade_pct": 0.0,
        "worst_trade_pct": 0.0,

        # NEW: Advanced metrics
        "alpha_vs_sp500": 0.0,
        "avg_winner": 0.0,
        "avg_loser": 0.0,
        "win_loss_ratio": 0.0,
        "profit_factor": 0.0,
        "last_30_days_return": 0.0,
        "last_10_trades_win_rate": 0.0,
        "current_streak": 0,
        "current_streak_type": "none",  # "wins", "losses", or "none"

        # NEW: Performance breakdowns
        "conviction_performance": [],  # Performance by conviction level
        "monthly_returns": [],  # For heatmap

        # Existing
        "recent_trades": [],
        "open_positions": []
    }

    # Track portfolio start date for Alpha calculation
    portfolio_start_date = None

    # Calculate metrics from portfolio
    if portfolio:
        logger.info("📊 Calculating portfolio metrics...")
        starting_capital = portfolio.get('starting_capital', 10000)
        cash = portfolio.get('cash', starting_capital)
        positions = portfolio.get('positions', {})

        # Get max_drawdown from portfolio data
        max_drawdown = portfolio.get('max_drawdown', 0.0)
        public_data['max_drawdown'] = round(max_drawdown, 2)

        # Calculate total return with REAL current prices
        logger.info(f"  Cash: ${cash:,.2f}")
        logger.info(f"  Fetching current prices for {len(positions)} positions...")

        # Cache prices to avoid duplicate fetches
        price_cache = {}
        positions_value = 0.0

        for ticker, pos in positions.items():
            entry_price = pos.get('entry_price', 0)
            shares = pos.get('shares', 0)

            # Fetch price once and cache it
            current_price = get_current_price(ticker, entry_price)
            price_cache[ticker] = current_price

            position_value = shares * current_price
            positions_value += position_value

            # Track earliest entry date for Alpha calculation
            entry_date = pos.get('entry_date')
            if entry_date:
                try:
                    entry_dt = pd.to_datetime(entry_date)
                    if portfolio_start_date is None or entry_dt < portfolio_start_date:
                        portfolio_start_date = entry_dt
                except:
                    pass

        current_value = cash + positions_value

        logger.info(f"  Total positions value: ${positions_value:,.2f}")
        logger.info(f"  Total portfolio value: ${current_value:,.2f}")

        # Protect against division by zero
        if starting_capital > 0:
            total_return_pct = ((current_value - starting_capital) / starting_capital) * 100
        else:
            total_return_pct = 0.0

        public_data['total_return_pct'] = round(total_return_pct, 2)
        public_data['active_trades'] = len(positions)

        logger.info(f"  Total return: {total_return_pct:.2f}%")

        # Open positions for display with REAL unrealized returns
        logger.info("  Calculating unrealized returns for open positions...")
        for ticker, pos in positions.items():
            entry_date = pos.get('entry_date', '')

            # Use naive datetime consistently
            if isinstance(entry_date, str):
                try:
                    entry_dt = pd.to_datetime(entry_date)
                    # Strip timezone if present to avoid mismatch
                    if entry_dt.tzinfo is not None:
                        entry_dt = entry_dt.replace(tzinfo=None)
                except:
                    entry_dt = datetime.utcnow()
            else:
                entry_dt = entry_date
                if hasattr(entry_dt, 'tzinfo') and entry_dt.tzinfo is not None:
                    entry_dt = entry_dt.replace(tzinfo=None)

            # Use naive datetime for comparison
            days_held = (datetime.utcnow() - entry_dt).days

            # Calculate REAL unrealized return
            entry_price = pos.get('entry_price', 0)

            # Use cached price
            current_price = price_cache.get(ticker, entry_price)

            # Protect against division by zero
            if entry_price > 0:
                unrealized_pct = ((current_price - entry_price) / entry_price) * 100
            else:
                unrealized_pct = 0.0

            conviction = get_conviction_level(pos.get('signal_score', 5))

            logger.info(f"    {ticker}: Entry ${entry_price:.2f} -> Current ${current_price:.2f} = {unrealized_pct:+.2f}%")

            public_data['open_positions'].append({
                "ticker": ticker,
                "entry_date": entry_dt.strftime("%b %d, %Y"),
                "days_held": days_held,
                "unrealized_return": round(unrealized_pct, 2),
                "conviction": conviction
            })

    # Calculate metrics from completed trades
    if not trades_df.empty:
        logger.info("📊 Processing trade history...")

        # Detect format and calculate metrics accordingly
        if 'pnl_pct' in trades_df.columns:
            # New format with pnl_pct column
            logger.info("  Detected new trade history format")

            # Filter for SELL actions only (completed trades)
            if 'action' in trades_df.columns:
                completed = trades_df[trades_df['action'] == 'SELL'].copy()
            else:
                completed = trades_df.copy()

            if not completed.empty:
                completed_trades = len(completed)
                public_data['completed_trades'] = completed_trades

                # Calculate wins and losses
                winners = completed[completed['pnl_pct'] > 0]
                losers = completed[completed['pnl_pct'] < 0]
                num_winners = len(winners)
                num_losers = len(losers)

                # Win rate
                public_data['win_rate'] = round((num_winners / completed_trades) * 100, 1) if completed_trades > 0 else 0.0

                # Average return per trade
                public_data['avg_return_per_trade'] = round(completed['pnl_pct'].mean(), 2)

                # NEW: Avg Winner and Avg Loser
                if not winners.empty:
                    public_data['avg_winner'] = round(winners['pnl_pct'].mean(), 2)
                else:
                    public_data['avg_winner'] = 0.0

                if not losers.empty:
                    public_data['avg_loser'] = round(losers['pnl_pct'].mean(), 2)
                else:
                    public_data['avg_loser'] = 0.0

                # NEW: Win/Loss Ratio
                if public_data['avg_loser'] != 0:
                    # Win/Loss ratio = Avg Win / Abs(Avg Loss)
                    public_data['win_loss_ratio'] = round(abs(public_data['avg_winner'] / public_data['avg_loser']), 2)
                else:
                    public_data['win_loss_ratio'] = 0.0

                # NEW: Profit Factor (Total Gains / Total Losses)
                total_gains = winners['pnl_pct'].sum() if not winners.empty else 0.0
                total_losses = abs(losers['pnl_pct'].sum()) if not losers.empty else 0.0

                if total_losses > 0:
                    public_data['profit_factor'] = round(total_gains / total_losses, 2)
                else:
                    public_data['profit_factor'] = 0.0

                # Sharpe ratio
                if len(completed) >= 2:
                    public_data['sharpe_ratio'] = calculate_sharpe_ratio(completed['pnl_pct'].values / 100)

                # Average hold days
                if 'hold_days' in completed.columns:
                    mean_days = completed['hold_days'].mean()
                    if pd.notna(mean_days):
                        public_data['avg_hold_days'] = int(mean_days)
                    else:
                        public_data['avg_hold_days'] = 0
                elif 'entry_date' in completed.columns and 'exit_date' in completed.columns:
                    completed['hold_days'] = (completed['exit_date'] - completed['entry_date']).dt.days
                    mean_days = completed['hold_days'].mean()
                    if pd.notna(mean_days):
                        public_data['avg_hold_days'] = int(mean_days)
                    else:
                        public_data['avg_hold_days'] = 0

                # Best and worst trades
                public_data['best_trade_pct'] = round(completed['pnl_pct'].max(), 2)
                public_data['worst_trade_pct'] = round(completed['pnl_pct'].min(), 2)

                # NEW: Last 10 Trades Win Rate
                if len(completed) >= 10:
                    if 'exit_date' in completed.columns:
                        last_10 = completed.sort_values('exit_date', ascending=False).head(10)
                    else:
                        last_10 = completed.tail(10)

                    last_10_winners = len(last_10[last_10['pnl_pct'] > 0])
                    public_data['last_10_trades_win_rate'] = round((last_10_winners / 10) * 100, 1)
                else:
                    public_data['last_10_trades_win_rate'] = public_data['win_rate']

                # NEW: Current Streak
                if 'exit_date' in completed.columns:
                    sorted_trades = completed.sort_values('exit_date', ascending=True)
                else:
                    sorted_trades = completed

                current_streak = 0
                streak_type = "none"

                if len(sorted_trades) > 0:
                    # Start from most recent trade and count backwards
                    last_result = None
                    for _, trade in sorted_trades.iloc[::-1].iterrows():
                        is_winner = trade['pnl_pct'] > 0

                        if last_result is None:
                            last_result = is_winner
                            current_streak = 1
                            streak_type = "wins" if is_winner else "losses"
                        elif is_winner == last_result:
                            current_streak += 1
                        else:
                            break

                public_data['current_streak'] = current_streak
                public_data['current_streak_type'] = streak_type

                # NEW: Last 30 Days Return
                if 'exit_date' in completed.columns:
                    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
                    recent_trades = completed[completed['exit_date'] >= thirty_days_ago]

                    if not recent_trades.empty:
                        # Calculate cumulative return for last 30 days
                        last_30_returns = recent_trades['pnl_pct'].values
                        # Assuming each trade is independent, sum the returns
                        public_data['last_30_days_return'] = round(last_30_returns.sum(), 2)
                    else:
                        public_data['last_30_days_return'] = 0.0
                else:
                    public_data['last_30_days_return'] = 0.0

                # NEW: Conviction Performance Breakdown
                logger.info("  Calculating conviction performance breakdown...")
                conviction_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'total_return': 0.0})

                for _, trade in completed.iterrows():
                    signal_score = trade.get('signal_score', 5)
                    conviction = get_conviction_level(signal_score)
                    pnl = trade['pnl_pct']

                    conviction_stats[conviction]['trades'] += 1
                    conviction_stats[conviction]['total_return'] += pnl
                    if pnl > 0:
                        conviction_stats[conviction]['wins'] += 1

                for conviction in ['VERY HIGH', 'HIGH', 'MEDIUM', 'LOW', 'WATCH']:
                    stats = conviction_stats[conviction]
                    if stats['trades'] > 0:
                        win_rate = (stats['wins'] / stats['trades']) * 100
                        avg_return = stats['total_return'] / stats['trades']

                        public_data['conviction_performance'].append({
                            'conviction': conviction,
                            'trades': stats['trades'],
                            'win_rate': round(win_rate, 1),
                            'avg_return': round(avg_return, 2)
                        })

                # NEW: Monthly Returns for Heatmap
                logger.info("  Calculating monthly returns...")
                if 'exit_date' in completed.columns:
                    # Group by year-month
                    completed['year_month'] = completed['exit_date'].dt.to_period('M')
                    monthly_groups = completed.groupby('year_month')['pnl_pct'].sum()

                    for period, total_return in monthly_groups.items():
                        public_data['monthly_returns'].append({
                            'month': str(period),  # Format: '2025-11'
                            'return': round(total_return, 2)
                        })

                # NEW: Alpha vs S&P 500
                logger.info("  Calculating Alpha vs S&P 500...")
                if portfolio_start_date:
                    sp500_return = get_sp500_return(portfolio_start_date)
                    alpha = public_data['total_return_pct'] - sp500_return
                    public_data['alpha_vs_sp500'] = round(alpha, 2)
                elif 'entry_date' in completed.columns and not completed.empty:
                    # Use first trade date as start
                    first_trade_date = completed['entry_date'].min()
                    sp500_return = get_sp500_return(first_trade_date)
                    alpha = public_data['total_return_pct'] - sp500_return
                    public_data['alpha_vs_sp500'] = round(alpha, 2)
                else:
                    public_data['alpha_vs_sp500'] = 0.0

                # Recent trades (last 20)
                if 'exit_date' in completed.columns:
                    recent = completed.sort_values('exit_date', ascending=False).head(20)
                else:
                    recent = completed.tail(20)

                for _, trade in recent.iterrows():
                    conviction = get_conviction_level(trade.get('signal_score', 5))

                    # Determine exit reason
                    exit_reason = "Unknown"
                    pnl = trade.get('pnl_pct', 0)
                    hold_days = trade.get('hold_days', 0)

                    if pnl >= 8:
                        exit_reason = "Take Profit"
                    elif pnl <= -5:
                        exit_reason = "Stop Loss"
                    elif hold_days >= 21:
                        exit_reason = "Time Stop"
                    else:
                        exit_reason = "Trailing Stop"

                    # Format dates safely
                    entry_date_str = "N/A"
                    exit_date_str = "N/A"

                    if 'entry_date' in trade.index and pd.notna(trade['entry_date']):
                        try:
                            entry_date_str = pd.to_datetime(trade['entry_date']).strftime("%b %d, %Y")
                        except:
                            entry_date_str = str(trade['entry_date'])[:10]

                    if 'exit_date' in trade.index and pd.notna(trade['exit_date']):
                        try:
                            exit_date_str = pd.to_datetime(trade['exit_date']).strftime("%b %d, %Y")
                        except:
                            exit_date_str = str(trade['exit_date'])[:10]

                    public_data['recent_trades'].append({
                        "ticker": trade['ticker'],
                        "entry_date": entry_date_str,
                        "exit_date": exit_date_str,
                        "hold_days": int(hold_days) if pd.notna(hold_days) else 0,
                        "return_pct": round(trade['pnl_pct'], 2),
                        "conviction": conviction,
                        "exit_reason": exit_reason
                    })
        else:
            # Old format - just log BUY/SELL actions, no completed trade data yet
            logger.info("  Detected old trade history format (no completed trades yet)")
            public_data['completed_trades'] = 0

    # Write to file
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(public_data, f, indent=2)

    logger.info("")
    logger.info("="*60)
    logger.info("✅ Generated public_performance.json")
    logger.info(f"   Last Updated: {public_data['last_updated']}")
    logger.info(f"   Total Return: {public_data['total_return_pct']:+.2f}%")
    logger.info(f"   Alpha vs S&P 500: {public_data['alpha_vs_sp500']:+.2f}%")
    logger.info(f"   Win Rate: {public_data['win_rate']:.1f}%")
    logger.info(f"   Completed Trades: {public_data['completed_trades']}")
    logger.info(f"   Active Positions: {public_data['active_trades']}")
    logger.info(f"   Sharpe Ratio: {public_data['sharpe_ratio']}")
    logger.info(f"   Profit Factor: {public_data['profit_factor']}")
    logger.info("="*60)

    return public_data


if __name__ == '__main__':
    generate_public_performance()
