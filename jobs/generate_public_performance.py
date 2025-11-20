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

# Paths
DATA_DIR = Path(__file__).parent.parent / 'data'
OUTPUT_FILE = Path(__file__).parent.parent / 'public_performance.json'
PAPER_PORTFOLIO_FILE = DATA_DIR / 'paper_portfolio.json'
PAPER_TRADES_CSV = DATA_DIR / 'paper_trades.csv'


def load_portfolio():
    """Load current portfolio state"""
    if not PAPER_PORTFOLIO_FILE.exists():
        return None

    with open(PAPER_PORTFOLIO_FILE, 'r') as f:
        return json.load(f)


def load_trades():
    """Load trade history"""
    if not PAPER_TRADES_CSV.exists():
        return pd.DataFrame()

    return pd.read_csv(PAPER_TRADES_CSV, parse_dates=['entry_date', 'exit_date'])


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
    public_data = {
        "last_updated": datetime.now().strftime("%B %d, %Y at %I:%M %p ET"),
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
        starting_capital = portfolio.get('starting_capital', 10000)
        cash = portfolio.get('cash', starting_capital)
        positions = portfolio.get('positions', {})

        # Calculate total return
        current_value = cash
        for ticker, pos in positions.items():
            # For public display, we'll just show the positions without calculating current value
            current_value += pos.get('cost_basis', 0)

        total_return_pct = ((current_value - starting_capital) / starting_capital) * 100
        public_data['total_return_pct'] = round(total_return_pct, 2)
        public_data['active_trades'] = len(positions)

        # Open positions for display
        for ticker, pos in positions.items():
            entry_date = pos.get('entry_date', '')
            if isinstance(entry_date, str):
                entry_dt = pd.to_datetime(entry_date)
            else:
                entry_dt = entry_date

            days_held = (datetime.now() - entry_dt).days

            # Calculate unrealized return (from cost basis)
            entry_price = pos.get('entry_price', 0)
            shares = pos.get('shares', 0)
            cost_basis = pos.get('cost_basis', 0)

            # Simple unrealized calc - in reality would fetch current price
            # For public display, we use stored data
            unrealized_pct = 0.0  # Placeholder

            conviction = get_conviction_level(pos.get('signal_score', 5))

            public_data['open_positions'].append({
                "ticker": ticker,
                "entry_date": entry_dt.strftime("%b %d, %Y"),
                "days_held": days_held,
                "unrealized_return": unrealized_pct,
                "conviction": conviction
            })

    # Calculate metrics from completed trades
    if not trades_df.empty:
        completed_trades = len(trades_df)
        public_data['completed_trades'] = completed_trades

        # Win rate
        winning_trades = len(trades_df[trades_df['pnl_pct'] > 0])
        public_data['win_rate'] = round((winning_trades / completed_trades) * 100, 1) if completed_trades > 0 else 0.0

        # Average return per trade
        public_data['avg_return_per_trade'] = round(trades_df['pnl_pct'].mean(), 2)

        # Sharpe ratio
        if len(trades_df) >= 2:
            public_data['sharpe_ratio'] = calculate_sharpe_ratio(trades_df['pnl_pct'].values / 100)

        # Average hold days
        if 'entry_date' in trades_df.columns and 'exit_date' in trades_df.columns:
            trades_df['hold_days'] = (trades_df['exit_date'] - trades_df['entry_date']).dt.days
            public_data['avg_hold_days'] = int(trades_df['hold_days'].mean())

        # Best and worst trades
        public_data['best_trade_pct'] = round(trades_df['pnl_pct'].max(), 2)
        public_data['worst_trade_pct'] = round(trades_df['pnl_pct'].min(), 2)

        # Recent trades (last 20)
        recent = trades_df.sort_values('exit_date', ascending=False).head(20)

        for _, trade in recent.iterrows():
            conviction = get_conviction_level(trade.get('signal_score', 5))

            # Determine exit reason
            exit_reason = "Unknown"
            if trade.get('pnl_pct', 0) >= 8:
                exit_reason = "Take Profit"
            elif trade.get('pnl_pct', 0) <= -5:
                exit_reason = "Stop Loss"
            elif trade.get('hold_days', 0) >= 21:
                exit_reason = "Time Stop"
            else:
                exit_reason = "Trailing Stop"

            public_data['recent_trades'].append({
                "ticker": trade['ticker'],
                "entry_date": trade['entry_date'].strftime("%b %d, %Y") if pd.notna(trade['entry_date']) else "N/A",
                "exit_date": trade['exit_date'].strftime("%b %d, %Y") if pd.notna(trade['exit_date']) else "N/A",
                "hold_days": int(trade.get('hold_days', 0)),
                "return_pct": round(trade['pnl_pct'], 2),
                "conviction": conviction,
                "exit_reason": exit_reason
            })

    # Write to file
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(public_data, f, indent=2)

    print(f"✅ Generated public_performance.json")
    print(f"   Total Return: {public_data['total_return_pct']}%")
    print(f"   Win Rate: {public_data['win_rate']}%")
    print(f"   Completed Trades: {public_data['completed_trades']}")
    print(f"   Active Positions: {public_data['active_trades']}")
    print(f"   Sharpe Ratio: {public_data['sharpe_ratio']}")

    return public_data


if __name__ == '__main__':
    generate_public_performance()
