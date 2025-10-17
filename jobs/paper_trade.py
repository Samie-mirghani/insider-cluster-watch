# jobs/paper_trade.py
"""
Paper Trading Simulator

Simulates real trading with virtual money to test strategy before risking real capital.

Features:
- Automatic position tracking
- Stop loss and take profit monitoring
- Daily P&L calculation
- Position size management
- Trade history logging
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
import json

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
PAPER_PORTFOLIO_FILE = os.path.join(DATA_DIR, 'paper_portfolio.json')
PAPER_TRADES_CSV = os.path.join(DATA_DIR, 'paper_trades.csv')

class PaperTradingPortfolio:
    """
    Simulates a trading portfolio with virtual money
    """
    
    def __init__(self, starting_capital=10000, max_position_pct=0.05, stop_loss_pct=0.05, take_profit_pct=0.08):
        self.starting_capital = starting_capital
        self.cash = starting_capital
        self.positions = {}  # {ticker: position_info}
        self.trade_history = []
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        
        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
    
    def get_portfolio_value(self):
        """Calculate total portfolio value (cash + positions)"""
        positions_value = 0.0
        
        for ticker, pos in self.positions.items():
            try:
                current_price = yf.Ticker(ticker).info.get('currentPrice', pos['entry_price'])
                positions_value += pos['shares'] * current_price
            except:
                positions_value += pos['shares'] * pos['entry_price']
        
        return self.cash + positions_value
    
    def execute_signal(self, signal):
        """
        Execute a buy signal
        
        Args:
            signal: dict or Series with keys: ticker, currentPrice, rank_score, etc.
        """
        ticker = signal.get('ticker') if isinstance(signal, dict) else signal['ticker']
        entry_price = signal.get('currentPrice') if isinstance(signal, dict) else signal['currentPrice']
        
        if not entry_price or entry_price <= 0:
            print(f"   ⚠️  Cannot execute {ticker}: Invalid price")
            return False
        
        # Check if already have position
        if ticker in self.positions:
            print(f"   ⚠️  Already have position in {ticker}")
            return False
        
        # Calculate position size
        portfolio_value = self.get_portfolio_value()
        position_size = portfolio_value * self.max_position_pct
        
        # Don't exceed available cash
        position_size = min(position_size, self.cash * 0.9)  # Keep 10% cash buffer
        
        if position_size < 100:
            print(f"   ⚠️  Position size too small for {ticker}: ${position_size:.2f}")
            return False
        
        shares = int(position_size / entry_price)
        
        if shares == 0:
            print(f"   ⚠️  Cannot afford shares of {ticker} at ${entry_price:.2f}")
            return False
        
        actual_cost = shares * entry_price
        
        # Execute trade
        self.positions[ticker] = {
            'entry_date': datetime.now(),
            'entry_price': entry_price,
            'shares': shares,
            'cost_basis': actual_cost,
            'stop_loss': entry_price * (1 - self.stop_loss_pct),
            'take_profit': entry_price * (1 + self.take_profit_pct),
            'signal_score': signal.get('rank_score') if isinstance(signal, dict) else signal.get('rank_score', 0),
            'sector': signal.get('sector') if isinstance(signal, dict) else signal.get('sector', 'Unknown')
        }
        
        self.cash -= actual_cost
        self.total_trades += 1
        
        # Log trade
        self.trade_history.append({
            'date': datetime.now(),
            'action': 'BUY',
            'ticker': ticker,
            'price': entry_price,
            'shares': shares,
            'cost': actual_cost,
            'reason': 'Signal',
            'cash_remaining': self.cash
        })
        
        print(f"   ✅ PAPER BUY: {shares} {ticker} @ ${entry_price:.2f} (${actual_cost:.2f})")
        print(f"      Stop: ${self.positions[ticker]['stop_loss']:.2f} | Target: ${self.positions[ticker]['take_profit']:.2f}")
        
        return True
    
    def check_exits(self):
        """
        Check all positions for stop loss or take profit hits
        Returns list of closed positions
        """
        closed_positions = []
        
        for ticker, pos in list(self.positions.items()):
            try:
                current_price = yf.Ticker(ticker).info.get('currentPrice')
                
                if not current_price:
                    continue
                
                # Check stop loss
                if current_price <= pos['stop_loss']:
                    reason = 'STOP_LOSS'
                    self._close_position(ticker, current_price, reason)
                    closed_positions.append((ticker, reason, current_price))
                
                # Check take profit
                elif current_price >= pos['take_profit']:
                    reason = 'TAKE_PROFIT'
                    self._close_position(ticker, current_price, reason)
                    closed_positions.append((ticker, reason, current_price))
                
                # Time-based exit (3 weeks)
                elif (datetime.now() - pos['entry_date']).days >= 21:
                    reason = 'TIME_STOP'
                    self._close_position(ticker, current_price, reason)
                    closed_positions.append((ticker, reason, current_price))
            
            except Exception as e:
                print(f"   ⚠️  Error checking {ticker}: {e}")
        
        return closed_positions
    
    def _close_position(self, ticker, exit_price, reason):
        """Close a position and update stats"""
        pos = self.positions[ticker]
        
        proceeds = pos['shares'] * exit_price
        profit = proceeds - pos['cost_basis']
        profit_pct = (profit / pos['cost_basis']) * 100
        
        self.cash += proceeds
        self.total_profit += profit
        
        if profit > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        
        # Log trade
        self.trade_history.append({
            'date': datetime.now(),
            'action': 'SELL',
            'ticker': ticker,
            'price': exit_price,
            'shares': pos['shares'],
            'proceeds': proceeds,
            'reason': reason,
            'profit': profit,
            'profit_pct': profit_pct,
            'days_held': (datetime.now() - pos['entry_date']).days,
            'cash_remaining': self.cash
        })
        
        print(f"   {'✅' if profit > 0 else '❌'} PAPER SELL: {pos['shares']} {ticker} @ ${exit_price:.2f}")
        print(f"      Reason: {reason} | P&L: ${profit:.2f} ({profit_pct:+.2f}%)")
        
        # Remove position
        del self.positions[ticker]
    
    def get_performance_summary(self):
        """Get portfolio performance statistics"""
        current_value = self.get_portfolio_value()
        total_return = current_value - self.starting_capital
        total_return_pct = (total_return / self.starting_capital) * 100
        
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        # Calculate average win and loss
        trades_df = pd.DataFrame(self.trade_history)
        if not trades_df.empty:
            sells = trades_df[trades_df['action'] == 'SELL']
            if not sells.empty:
                wins = sells[sells['profit'] > 0]
                losses = sells[sells['profit'] < 0]
                
                avg_win = wins['profit'].mean() if len(wins) > 0 else 0
                avg_loss = losses['profit'].mean() if len(losses) > 0 else 0
                avg_win_pct = wins['profit_pct'].mean() if len(wins) > 0 else 0
                avg_loss_pct = losses['profit_pct'].mean() if len(losses) > 0 else 0
            else:
                avg_win = avg_loss = avg_win_pct = avg_loss_pct = 0
        else:
            avg_win = avg_loss = avg_win_pct = avg_loss_pct = 0
        
        return {
            'starting_capital': self.starting_capital,
            'current_value': current_value,
            'cash': self.cash,
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'open_positions': len(self.positions),
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'avg_win_pct': avg_win_pct,
            'avg_loss_pct': avg_loss_pct
        }
    
    def save(self):
        """Save portfolio state to disk"""
        data = {
            'starting_capital': self.starting_capital,
            'cash': self.cash,
            'positions': {
                ticker: {
                    **pos,
                    'entry_date': pos['entry_date'].isoformat()
                }
                for ticker, pos in self.positions.items()
            },
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'total_profit': self.total_profit,
            'last_updated': datetime.now().isoformat()
        }
        
        with open(PAPER_PORTFOLIO_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Save trade history
        if self.trade_history:
            trades_df = pd.DataFrame(self.trade_history)
            trades_df.to_csv(PAPER_TRADES_CSV, index=False)
    
    @classmethod
    def load(cls):
        """Load portfolio state from disk"""
        if not os.path.exists(PAPER_PORTFOLIO_FILE):
            return cls()
        
        try:
            with open(PAPER_PORTFOLIO_FILE, 'r') as f:
                data = json.load(f)
            
            portfolio = cls(starting_capital=data['starting_capital'])
            portfolio.cash = data['cash']
            portfolio.total_trades = data.get('total_trades', 0)
            portfolio.winning_trades = data.get('winning_trades', 0)
            portfolio.losing_trades = data.get('losing_trades', 0)
            portfolio.total_profit = data.get('total_profit', 0.0)
            
            # Restore positions
            for ticker, pos in data['positions'].items():
                pos['entry_date'] = datetime.fromisoformat(pos['entry_date'])
                portfolio.positions[ticker] = pos
            
            # Load trade history
            if os.path.exists(PAPER_TRADES_CSV):
                portfolio.trade_history = pd.read_csv(PAPER_TRADES_CSV).to_dict('records')
            
            return portfolio
        
        except Exception as e:
            print(f"⚠️  Error loading portfolio: {e}")
            return cls()

def generate_paper_trading_report(portfolio):
    """Generate a formatted paper trading performance report"""
    stats = portfolio.get_performance_summary()
    
    report = f"""
{'='*60}
📊 PAPER TRADING PERFORMANCE REPORT
{'='*60}

Portfolio Value:
  Starting Capital: ${stats['starting_capital']:,.2f}
  Current Value:    ${stats['current_value']:,.2f}
  Cash Available:   ${stats['cash']:,.2f}
  
  Total Return:     ${stats['total_return']:,.2f} ({stats['total_return_pct']:+.2f}%)

Trading Statistics:
  Total Trades:     {stats['total_trades']}
  Winners:          {stats['winning_trades']} ({stats['win_rate']:.1f}%)
  Losers:           {stats['losing_trades']}
  
  Avg Win:          ${stats['avg_win']:.2f} ({stats['avg_win_pct']:+.2f}%)
  Avg Loss:         ${stats['avg_loss']:.2f} ({stats['avg_loss_pct']:+.2f}%)

Current Positions: {stats['open_positions']}
"""
    
    if portfolio.positions:
        report += "\nOpen Positions:\n"
        for ticker, pos in portfolio.positions.items():
            try:
                current_price = yf.Ticker(ticker).info.get('currentPrice', pos['entry_price'])
                current_value = pos['shares'] * current_price
                unrealized_pl = current_value - pos['cost_basis']
                unrealized_pct = (unrealized_pl / pos['cost_basis']) * 100
                days_held = (datetime.now() - pos['entry_date']).days
                
                report += f"\n  {ticker}:"
                report += f"\n    Shares: {pos['shares']} @ ${pos['entry_price']:.2f}"
                report += f"\n    Current: ${current_price:.2f}"
                report += f"\n    P&L: ${unrealized_pl:,.2f} ({unrealized_pct:+.2f}%)"
                report += f"\n    Days Held: {days_held}"
                report += f"\n    Stop: ${pos['stop_loss']:.2f} | Target: ${pos['take_profit']:.2f}"
            except:
                pass
    
    report += f"\n{'='*60}\n"
    
    return report

if __name__ == "__main__":
    # Test paper trading
    portfolio = PaperTradingPortfolio.load()
    print(generate_paper_trading_report(portfolio))