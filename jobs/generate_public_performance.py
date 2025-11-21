#!/usr/bin/env python3
"""
Generate public_performance.json for GitHub Pages dashboard

This script creates a public-facing performance summary without sensitive data.
Shows percentages and statistics, but NOT dollar amounts.
"""

import json
import os
import pandas as pd
from datetime import datetime
from pathlib import Path
import numpy as np
import yfinance as yf
import logging

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
        "recent_trades": [],
        "open_positions": []
    }

    # Calculate metrics from portfolio
    if portfolio:
        logger.info("📊 Calculating portfolio metrics...")
        starting_capital = portfolio.get('starting_capital', 10000)
        cash = portfolio.get('cash', starting_capital)
        positions = portfolio.get('positions', {})

        # Calculate total return with REAL current prices
        logger.info(f"  Cash: ${cash:,.2f}")
        logger.info(f"  Fetching current prices for {len(positions)} positions...")

        # Cache prices to avoid duplicate fetches (Bug #7 fix)
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

        current_value = cash + positions_value

        logger.info(f"  Total positions value: ${positions_value:,.2f}")
        logger.info(f"  Total portfolio value: ${current_value:,.2f}")

        # Bug #3 fix: Protect against division by zero
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

            # Bug #5 fix: Use naive datetime consistently
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

            # Use cached price (Bug #7 fix)
            current_price = price_cache.get(ticker, entry_price)

            # Bug #3 fix: Protect against division by zero
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
    # Bug #4 fix: Handle both old and new CSV formats
    if not trades_df.empty:
        logger.info("📊 Processing trade history...")

        # Detect format and calculate metrics accordingly
        if 'pnl_pct' in trades_df.columns:
            # New format with pnl_pct column
            logger.info("  Detected new trade history format")

            # Filter for SELL actions only (completed trades)
            if 'action' in trades_df.columns:
                completed = trades_df[trades_df['action'] == 'SELL']
            else:
                completed = trades_df

            if not completed.empty:
                completed_trades = len(completed)
                public_data['completed_trades'] = completed_trades

                # Win rate
                winning_trades = len(completed[completed['pnl_pct'] > 0])
                public_data['win_rate'] = round((winning_trades / completed_trades) * 100, 1) if completed_trades > 0 else 0.0

                # Average return per trade
                public_data['avg_return_per_trade'] = round(completed['pnl_pct'].mean(), 2)

                # Sharpe ratio
                if len(completed) >= 2:
                    public_data['sharpe_ratio'] = calculate_sharpe_ratio(completed['pnl_pct'].values / 100)

                # Average hold days
                if 'hold_days' in completed.columns:
                    # Bug #6 fix: Handle NaN values
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
    logger.info(f"   Win Rate: {public_data['win_rate']:.1f}%")
    logger.info(f"   Completed Trades: {public_data['completed_trades']}")
    logger.info(f"   Active Positions: {public_data['active_trades']}")
    logger.info(f"   Sharpe Ratio: {public_data['sharpe_ratio']}")
    logger.info("="*60)

    return public_data


if __name__ == '__main__':
    generate_public_performance()
