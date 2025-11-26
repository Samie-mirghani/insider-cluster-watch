# jobs/paper_trade.py
"""
Enhanced Paper Trading Simulator
Simulates real trading with virtual money to test strategy before risking real capital.
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
import json
import logging
from config import *

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
PAPER_PORTFOLIO_FILE = os.path.join(DATA_DIR, 'paper_portfolio.json')
PAPER_TRADES_CSV = os.path.join(DATA_DIR, 'paper_trades.csv')
PAPER_LOG_FILE = os.path.join(DATA_DIR, 'paper_trading.log')

# Set up enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(PAPER_LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PaperTradingPortfolio:
    """
    Enhanced simulated trading portfolio with advanced risk management
    """
    
    def __init__(
        self, 
        starting_capital=STARTING_CAPITAL, 
        max_position_pct=MAX_POSITION_PCT,
        stop_loss_pct=STOP_LOSS_PCT,
        take_profit_pct=TAKE_PROFIT_PCT,
        trailing_stop_pct=TRAILING_STOP_PCT,
        max_total_exposure=MAX_TOTAL_EXPOSURE,
        max_positions=MAX_POSITIONS,
        enable_scaling=ENABLE_SCALING,
        scaling_trigger_pct=SCALING_TRIGGER_PCT
    ):
        self.starting_capital = starting_capital
        self.cash = starting_capital
        self.positions = {}  # {ticker: position_info}
        self.pending_entries = {}  # {ticker: pending_second_tranche}
        self.trade_history = []
        
        # Risk parameters
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.max_total_exposure = max_total_exposure
        self.max_positions = max_positions
        
        # Scaling parameters
        self.enable_scaling = enable_scaling
        self.scaling_trigger_pct = scaling_trigger_pct
        
        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
        self.max_portfolio_value = starting_capital
        self.max_drawdown = 0.0
        
        # Daily tracking for monitoring
        self.daily_trades_count = 0
        self.last_trade_date = None
        
        logger.info(f"📊 Paper Trading Portfolio Initialized")
        logger.info(f"   Starting Capital: ${starting_capital:,.2f}")
        logger.info(f"   Max Position Size: {max_position_pct*100}%")
        logger.info(f"   Scaling Enabled: {enable_scaling}")
    
    def get_portfolio_value(self):
        """Calculate total portfolio value (cash + positions)"""
        positions_value = 0.0
        
        for ticker, pos in self.positions.items():
            try:
                current_price = yf.Ticker(ticker).info.get('currentPrice', pos['entry_price'])
                if not current_price or current_price <= 0:
                    current_price = pos['entry_price']
                positions_value += pos['shares'] * current_price
            except:
                positions_value += pos['shares'] * pos['entry_price']
        
        portfolio_value = self.cash + positions_value
        
        # Track max value for drawdown calculation
        if portfolio_value > self.max_portfolio_value:
            self.max_portfolio_value = portfolio_value
        
        # Calculate current drawdown
        current_drawdown = ((portfolio_value - self.max_portfolio_value) / self.max_portfolio_value) * 100
        if current_drawdown < self.max_drawdown:
            self.max_drawdown = current_drawdown
        
        return portfolio_value
    
    def validate_position_size(self, ticker, shares, price):
        """
        Validate position doesn't exceed risk limits
        
        Returns: (is_valid, reason)
        """
        position_value = shares * price
        portfolio_value = self.get_portfolio_value()
        
        # Check 1: Max position size per ticker
        position_pct = (position_value / portfolio_value) * 100
        if position_value > portfolio_value * self.max_position_pct:
            return False, f"Exceeds max position size ({self.max_position_pct*100}%): {position_pct:.2f}%"
        
        # Check 2: Max number of positions
        if len(self.positions) >= self.max_positions:
            return False, f"Already at max positions limit ({self.max_positions})"
        
        # Check 3: Max total exposure
        total_exposure = sum(
            p['shares'] * self._get_current_price(t, p['entry_price']) 
            for t, p in self.positions.items()
        )
        total_exposure += position_value
        
        exposure_pct = (total_exposure / portfolio_value)
        if exposure_pct > self.max_total_exposure:
            return False, f"Exceeds max total exposure ({self.max_total_exposure*100}%): {exposure_pct*100:.1f}%"
        
        # Check 4: Sufficient cash
        if position_value > self.cash:
            return False, f"Insufficient cash: need ${position_value:.2f}, have ${self.cash:.2f}"
        
        return True, "VALID"
    
    def _get_current_price(self, ticker, fallback_price):
        """Safely get current price with fallback"""
        try:
            price = yf.Ticker(ticker).info.get('currentPrice', fallback_price)
            return price if price and price > 0 else fallback_price
        except:
            return fallback_price
    
    def calculate_position_size(self, signal):
        """
        Calculate appropriate position size based on portfolio value and risk params
        Enhanced with multi-signal tier support

        Returns: (full_position_size, initial_size, second_tranche_size)
        """
        portfolio_value = self.get_portfolio_value()
        entry_price = signal.get('entry_price')

        # Import multi-signal config if available
        try:
            from config import MULTI_SIGNAL_POSITION_SIZES
            multi_signal_available = True
        except ImportError:
            multi_signal_available = False

        # Check if this is a multi-signal trade
        multi_signal_tier = signal.get('multi_signal_tier', 'none')
        tier_multiplier = 1.0

        if multi_signal_available and multi_signal_tier in MULTI_SIGNAL_POSITION_SIZES:
            tier_multiplier = MULTI_SIGNAL_POSITION_SIZES[multi_signal_tier]
            logger.info(f"   📊 Multi-Signal Tier: {multi_signal_tier.upper()} (multiplier: {tier_multiplier}x)")

        # Calculate base position size
        base_position_size = portfolio_value * self.max_position_pct

        # Apply tier multiplier for multi-signal trades
        full_position_size = base_position_size * tier_multiplier

        # Don't exceed 90% of available cash (keep buffer)
        full_position_size = min(full_position_size, self.cash * 0.9)

        if self.enable_scaling:
            # Split into 2 tranches: 60% initial, 40% on pullback
            initial_size = full_position_size * 0.6
            second_tranche_size = full_position_size * 0.4
        else:
            # No scaling - use full size
            initial_size = full_position_size
            second_tranche_size = 0

        return full_position_size, initial_size, second_tranche_size
    
    def execute_signal(self, signal):
        """
        Execute a buy signal with enhanced risk management
        
        Args:
            signal: dict or Series with keys: ticker, entry_price, signal_score, etc.
        """
        ticker = signal.get('ticker') if isinstance(signal, dict) else signal['ticker']
        entry_price = signal.get('entry_price') if isinstance(signal, dict) else signal['entry_price']
        signal_score = signal.get('signal_score') if isinstance(signal, dict) else signal.get('signal_score', 0)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 SIGNAL EVALUATION: {ticker}")
        logger.info(f"   Entry Price: ${entry_price:.2f}")
        logger.info(f"   Signal Score: {signal_score:.2f}")
        
        # Validation 1: Valid price
        if not entry_price or entry_price <= 0:
            logger.warning(f"   ❌ REJECTED: Invalid price")
            return False
        
        # Validation 2: No duplicate position
        if ticker in self.positions:
            logger.warning(f"   ⏭️  SKIPPED: Already have position in {ticker}")
            return False
        
        # Validation 3: Daily trade limit (reset counter if new day)
        today = datetime.now().date()
        if self.last_trade_date != today:
            self.daily_trades_count = 0
            self.last_trade_date = today
        
        if self.daily_trades_count >= 3:
            logger.warning(f"   ⚠️  REJECTED: Daily trade limit reached (3)")
            return False
        
        # Calculate position sizing
        full_size, initial_size, second_tranche_size = self.calculate_position_size(signal)
        initial_shares = int(initial_size / entry_price)
        
        if initial_shares == 0:
            logger.warning(f"   ❌ REJECTED: Cannot afford shares at ${entry_price:.2f}")
            return False
        
        # Validate position size
        is_valid, reason = self.validate_position_size(ticker, initial_shares, entry_price)
        if not is_valid:
            logger.warning(f"   ❌ REJECTED: {reason}")
            return False
        
        # Calculate actual cost
        actual_cost = initial_shares * entry_price

        # Get tier-specific stop loss if multi-signal
        try:
            from config import MULTI_SIGNAL_STOP_LOSS
            multi_signal_tier = signal.get('multi_signal_tier', 'none')
            if multi_signal_tier in MULTI_SIGNAL_STOP_LOSS:
                stop_loss_pct = MULTI_SIGNAL_STOP_LOSS[multi_signal_tier]
                logger.info(f"   🎯 Using {multi_signal_tier.upper()} stop loss: {stop_loss_pct*100:.0f}%")
            else:
                stop_loss_pct = self.stop_loss_pct
        except ImportError:
            stop_loss_pct = self.stop_loss_pct

        # Execute first tranche
        logger.info(f"   ✅ VALIDATION PASSED")
        logger.info(f"   📈 EXECUTING BUY ORDER")
        logger.info(f"   Shares: {initial_shares} @ ${entry_price:.2f}")
        logger.info(f"   Cost: ${actual_cost:.2f}")
        logger.info(f"   Position Size: {(actual_cost/self.get_portfolio_value())*100:.2f}%")

        # Log multi-signal info if applicable
        if signal.get('multi_signal_tier', 'none') != 'none':
            logger.info(f"   🔥 Multi-Signal Trade: {signal.get('multi_signal_tier', '').upper()}")
        if signal.get('has_politician_signal'):
            logger.info(f"   🏛️ Politician Activity Detected")

        # Create position
        self.positions[ticker] = {
            'entry_date': datetime.now(),
            'entry_price': entry_price,
            'shares': initial_shares,
            'cost_basis': actual_cost,
            'initial_stop_loss': entry_price * (1 - stop_loss_pct),
            'stop_loss': entry_price * (1 - stop_loss_pct),
            'take_profit': entry_price * (1 + self.take_profit_pct),
            'highest_price': entry_price,  # For trailing stop
            'trailing_enabled': False,  # Enable after +3%
            'signal_score': signal_score,
            'sector': signal.get('sector') if isinstance(signal, dict) else signal.get('sector', 'Unknown'),
            'multi_signal_tier': signal.get('multi_signal_tier', 'none'),
            'has_politician_signal': signal.get('has_politician_signal', False),
            'tranches': [{'shares': initial_shares, 'price': entry_price, 'date': datetime.now()}]
        }
        
        self.cash -= actual_cost
        self.total_trades += 1
        self.daily_trades_count += 1
        
        # Log trade
        self.trade_history.append({
            'date': datetime.now(),
            'action': 'BUY',
            'ticker': ticker,
            'price': entry_price,
            'shares': initial_shares,
            'cost': actual_cost,
            'reason': 'Signal',
            'signal_score': signal_score,
            'cash_remaining': self.cash,
            'portfolio_value': self.get_portfolio_value()
        })
        
        logger.info(f"   💰 Cash Remaining: ${self.cash:,.2f}")
        logger.info(f"   🎯 Stop Loss: ${self.positions[ticker]['stop_loss']:.2f} (-{self.stop_loss_pct*100}%)")
        logger.info(f"   🎯 Take Profit: ${self.positions[ticker]['take_profit']:.2f} (+{self.take_profit_pct*100}%)")
        
        # Set up second tranche if scaling enabled
        if self.enable_scaling and second_tranche_size > 0:
            second_shares = int(second_tranche_size / entry_price)
            if second_shares > 0:
                trigger_price = entry_price * (1 - self.scaling_trigger_pct)
                self.pending_entries[ticker] = {
                    'shares': second_shares,
                    'trigger_price': trigger_price,
                    'original_entry': entry_price,
                    'expires': datetime.now() + timedelta(days=5),
                    'signal_score': signal_score
                }
                logger.info(f"   📊 Scaling Enabled: {second_shares} shares pending")
                logger.info(f"   📍 Trigger Price: ${trigger_price:.2f} (-{self.scaling_trigger_pct*100}%)")
                logger.info(f"   ⏰ Expires: {self.pending_entries[ticker]['expires'].strftime('%Y-%m-%d')}")
        
        logger.info(f"{'='*60}\n")
        return True
    
    def check_pending_entries(self):
        """Check if any pending second tranches should be triggered"""
        if not self.pending_entries:
            return
        
        for ticker in list(self.pending_entries.keys()):
            pending = self.pending_entries[ticker]
            
            # Check if expired
            if datetime.now() > pending['expires']:
                logger.info(f"   ⏰ {ticker}: Second tranche expired (not triggered)")
                del self.pending_entries[ticker]
                continue
            
            # Check if position was closed
            if ticker not in self.positions:
                logger.info(f"   🚫 {ticker}: Position closed, canceling pending entry")
                del self.pending_entries[ticker]
                continue
            
            # Get current price
            try:
                current_price = self._get_current_price(ticker, pending['original_entry'])
                
                # Check if trigger hit
                if current_price <= pending['trigger_price']:
                    # Execute second tranche
                    shares = pending['shares']
                    cost = shares * current_price
                    
                    # Validate we still have cash
                    if cost <= self.cash:
                        logger.info(f"\n{'='*60}")
                        logger.info(f"📊 SCALING ENTRY TRIGGERED: {ticker}")
                        logger.info(f"   Second Tranche: {shares} shares @ ${current_price:.2f}")
                        logger.info(f"   Cost: ${cost:.2f}")
                        
                        # Update position
                        pos = self.positions[ticker]
                        old_shares = pos['shares']
                        old_cost = pos['cost_basis']
                        
                        pos['shares'] += shares
                        pos['cost_basis'] += cost
                        pos['entry_price'] = pos['cost_basis'] / pos['shares']  # New average
                        pos['tranches'].append({'shares': shares, 'price': current_price, 'date': datetime.now()})
                        
                        # Adjust stops to new average
                        pos['stop_loss'] = pos['entry_price'] * (1 - self.stop_loss_pct)
                        pos['take_profit'] = pos['entry_price'] * (1 + self.take_profit_pct)
                        
                        self.cash -= cost
                        
                        # Log trade
                        self.trade_history.append({
                            'date': datetime.now(),
                            'action': 'BUY_SCALE',
                            'ticker': ticker,
                            'price': current_price,
                            'shares': shares,
                            'cost': cost,
                            'reason': 'Scaling Entry',
                            'signal_score': pending['signal_score'],
                            'cash_remaining': self.cash,
                            'portfolio_value': self.get_portfolio_value()
                        })
                        
                        logger.info(f"   📈 New Position: {pos['shares']} shares @ ${pos['entry_price']:.2f} avg")
                        logger.info(f"   🎯 New Stop: ${pos['stop_loss']:.2f}")
                        logger.info(f"   🎯 New Target: ${pos['take_profit']:.2f}")
                        logger.info(f"{'='*60}\n")
                        
                        # Remove from pending
                        del self.pending_entries[ticker]
                    else:
                        logger.warning(f"   ⚠️  {ticker}: Insufficient cash for second tranche, canceling")
                        del self.pending_entries[ticker]
                        
            except Exception as e:
                logger.error(f"   ❌ Error checking {ticker} pending entry: {e}")
    
    def update_trailing_stops(self):
        """Update trailing stops for profitable positions"""
        for ticker, pos in self.positions.items():
            try:
                current_price = self._get_current_price(ticker, pos['entry_price'])
                
                # Track highest price
                if current_price > pos['highest_price']:
                    pos['highest_price'] = current_price
                    
                    # Enable trailing stop after +3% gain
                    if not pos['trailing_enabled']:
                        gain_pct = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
                        if gain_pct >= 3.0:
                            pos['trailing_enabled'] = True
                            logger.info(f"   📈 {ticker}: Trailing stop ENABLED at +{gain_pct:.1f}%")
                    
                    # Update trailing stop if enabled
                    if pos['trailing_enabled']:
                        new_stop = current_price * (1 - self.trailing_stop_pct)
                        
                        # Only raise the stop, never lower it
                        if new_stop > pos['stop_loss']:
                            old_stop = pos['stop_loss']
                            pos['stop_loss'] = new_stop
                            logger.info(f"   🔼 {ticker}: Stop raised ${old_stop:.2f} → ${new_stop:.2f} (trailing)")
                            
            except Exception as e:
                logger.error(f"   ❌ Error updating {ticker} trailing stop: {e}")
    
    def check_exits(self):
        """
        Check all positions for stop loss, take profit, or time-based exits
        Returns list of closed positions
        """
        closed_positions = []
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 CHECKING EXITS FOR {len(self.positions)} POSITION(S)")
        logger.info(f"{'='*60}")
        
        # First, check pending entries
        if self.pending_entries:
            logger.info(f"\n📊 Checking {len(self.pending_entries)} pending entries...")
            self.check_pending_entries()
        
        # Update trailing stops
        if self.positions:
            logger.info(f"\n📊 Updating trailing stops...")
            self.update_trailing_stops()
        
        # Check exits
        for ticker, pos in list(self.positions.items()):
            try:
                current_price = self._get_current_price(ticker, pos['entry_price'])
                
                unrealized_pnl = (current_price - pos['entry_price']) / pos['entry_price'] * 100
                days_held = (datetime.now() - pos['entry_date']).days
                
                logger.info(f"\n📊 {ticker}:")
                logger.info(f"   Entry: ${pos['entry_price']:.2f} | Current: ${current_price:.2f}")
                logger.info(f"   P&L: {unrealized_pnl:+.2f}% | Days: {days_held}")
                logger.info(f"   Stop: ${pos['stop_loss']:.2f} | Target: ${pos['take_profit']:.2f}")
                
                exit_reason = None
                
                # Check stop loss
                if current_price <= pos['stop_loss']:
                    exit_reason = 'STOP_LOSS'
                    trailing_indicator = " (TRAILING)" if pos.get('trailing_enabled') else ""
                    logger.info(f"   🛑 STOP LOSS HIT{trailing_indicator}")
                
                # Check take profit
                elif current_price >= pos['take_profit']:
                    exit_reason = 'TAKE_PROFIT'
                    logger.info(f"   🎯 TAKE PROFIT HIT")

                # Performance-Based Max Hold (more sophisticated time-based exits)
                elif PERFORMANCE_BASED_MAX_HOLD:
                    # Exit condition 1: Held 21 days and negative
                    if days_held >= MAX_HOLD_LOSS_DAYS and unrealized_pnl < 0:
                        exit_reason = 'MAX_HOLD_LOSS'
                        logger.info(f"   ⏰ MAX HOLD - LOSS ({days_held} days, {unrealized_pnl:.2f}%)")

                    # Exit condition 2: Held 30 days and barely positive (not moving)
                    elif days_held >= MAX_HOLD_STAGNANT_DAYS and unrealized_pnl < MAX_HOLD_STAGNANT_THRESHOLD:
                        exit_reason = 'MAX_HOLD_STAGNANT'
                        logger.info(f"   ⏰ MAX HOLD - STAGNANT ({days_held} days, only {unrealized_pnl:.2f}%)")

                    # Exit condition 3: Held 45 days regardless (extreme case)
                    elif days_held >= MAX_HOLD_EXTREME_DAYS:
                        exit_reason = 'MAX_HOLD_EXTREME'
                        logger.info(f"   ⏰ MAX HOLD - EXTREME ({days_held} days, {unrealized_pnl:.2f}%)")

                # Fallback: Old simple time stop (if PERFORMANCE_BASED_MAX_HOLD is disabled)
                elif days_held >= TIME_STOP_DAYS:
                    exit_reason = 'TIME_STOP'
                    logger.info(f"   ⏰ TIME STOP ({days_held} days)")
                
                # Execute exit if triggered
                if exit_reason:
                    self._close_position(ticker, current_price, exit_reason)
                    closed_positions.append((ticker, exit_reason, current_price))
                else:
                    logger.info(f"   ✅ Position OK - holding")
            
            except Exception as e:
                logger.error(f"   ❌ Error checking {ticker}: {e}")
        
        logger.info(f"\n{'='*60}")
        if closed_positions:
            logger.info(f"📊 CLOSED {len(closed_positions)} POSITION(S)")
        else:
            logger.info(f"📊 NO EXITS - ALL POSITIONS HOLDING")
        logger.info(f"{'='*60}\n")
        
        return closed_positions
    
    def _close_position(self, ticker, exit_price, reason):
        """Close a position and update stats"""
        pos = self.positions[ticker]
        
        proceeds = pos['shares'] * exit_price
        profit = proceeds - pos['cost_basis']
        profit_pct = (profit / pos['cost_basis']) * 100
        days_held = (datetime.now() - pos['entry_date']).days
        
        self.cash += proceeds
        self.total_profit += profit
        
        if profit > 0:
            self.winning_trades += 1
            emoji = "✅"
        else:
            self.losing_trades += 1
            emoji = "❌"
        
        logger.info(f"\n{'='*60}")
        logger.info(f"{emoji} POSITION CLOSED: {ticker}")
        logger.info(f"{'='*60}")
        logger.info(f"   Reason: {reason}")
        logger.info(f"   Entry: ${pos['entry_price']:.2f} | Exit: ${exit_price:.2f}")
        logger.info(f"   Shares: {pos['shares']}")
        logger.info(f"   Cost: ${pos['cost_basis']:.2f} | Proceeds: ${proceeds:.2f}")
        logger.info(f"   Profit: ${profit:.2f} ({profit_pct:+.2f}%)")
        logger.info(f"   Days Held: {days_held}")
        logger.info(f"   Cash After: ${self.cash:,.2f}")
        logger.info(f"   Portfolio: ${self.get_portfolio_value():,.2f}")
        logger.info(f"{'='*60}\n")
        
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
            'days_held': days_held,
            'signal_score': pos.get('signal_score', 0),
            'cash_remaining': self.cash,
            'portfolio_value': self.get_portfolio_value()
        })
        
        # Remove position
        del self.positions[ticker]
        
        # Remove any pending entries
        if ticker in self.pending_entries:
            del self.pending_entries[ticker]
    
    def get_performance_summary(self):
        """Get comprehensive portfolio performance statistics"""
        current_value = self.get_portfolio_value()
        total_return = current_value - self.starting_capital
        total_return_pct = (total_return / self.starting_capital) * 100
        
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        # Calculate average win and loss
        trades_df = pd.DataFrame(self.trade_history)
        if not trades_df.empty:
            sells = trades_df[trades_df['action'].isin(['SELL'])]
            if not sells.empty:
                wins = sells[sells['profit'] > 0]
                losses = sells[sells['profit'] < 0]
                
                avg_win = wins['profit'].mean() if len(wins) > 0 else 0
                avg_loss = losses['profit'].mean() if len(losses) > 0 else 0
                avg_win_pct = wins['profit_pct'].mean() if len(wins) > 0 else 0
                avg_loss_pct = losses['profit_pct'].mean() if len(losses) > 0 else 0
                avg_hold_days = sells['days_held'].mean() if len(sells) > 0 else 0
            else:
                avg_win = avg_loss = avg_win_pct = avg_loss_pct = avg_hold_days = 0
        else:
            avg_win = avg_loss = avg_win_pct = avg_loss_pct = avg_hold_days = 0
        
        # Calculate exposure
        total_exposure = sum(
            p['shares'] * self._get_current_price(t, p['entry_price']) 
            for t, p in self.positions.items()
        )
        exposure_pct = (total_exposure / current_value * 100) if current_value > 0 else 0
        
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
            'pending_entries': len(self.pending_entries),
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'avg_win_pct': avg_win_pct,
            'avg_loss_pct': avg_loss_pct,
            'avg_hold_days': avg_hold_days,
            'max_drawdown': self.max_drawdown,
            'current_exposure': total_exposure,
            'exposure_pct': exposure_pct,
            'realized_pnl': self.total_profit
        }
    
    def save(self):
        """Save portfolio state to disk"""
        data = {
            'starting_capital': self.starting_capital,
            'cash': self.cash,
            'positions': {
                ticker: {
                    **pos,
                    'entry_date': pos['entry_date'].isoformat(),
                    'tranches': [
                        {**t, 'date': t['date'].isoformat()} 
                        for t in pos.get('tranches', [])
                    ]
                }
                for ticker, pos in self.positions.items()
            },
            'pending_entries': {
                ticker: {
                    **pending,
                    'expires': pending['expires'].isoformat()
                }
                for ticker, pending in self.pending_entries.items()
            },
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'total_profit': self.total_profit,
            'max_portfolio_value': self.max_portfolio_value,
            'max_drawdown': self.max_drawdown,
            'last_updated': datetime.now().isoformat()
        }
        
        with open(PAPER_PORTFOLIO_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Save trade history
        if self.trade_history:
            trades_df = pd.DataFrame(self.trade_history)
            trades_df.to_csv(PAPER_TRADES_CSV, index=False)
        
        logger.info(f"💾 Portfolio saved to disk")
    
    @classmethod
    def load(cls):
        """Load portfolio state from disk"""
        if not os.path.exists(PAPER_PORTFOLIO_FILE):
            logger.info("📂 No existing portfolio found, creating new")
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
            portfolio.max_portfolio_value = data.get('max_portfolio_value', data['starting_capital'])
            portfolio.max_drawdown = data.get('max_drawdown', 0.0)
            
            # Restore positions
            for ticker, pos in data['positions'].items():
                pos['entry_date'] = datetime.fromisoformat(pos['entry_date'])
                if 'tranches' in pos:
                    pos['tranches'] = [
                        {**t, 'date': datetime.fromisoformat(t['date'])} 
                        for t in pos['tranches']
                    ]
                portfolio.positions[ticker] = pos
            
            # Restore pending entries
            for ticker, pending in data.get('pending_entries', {}).items():
                pending['expires'] = datetime.fromisoformat(pending['expires'])
                portfolio.pending_entries[ticker] = pending
            
            # Load trade history
            if os.path.exists(PAPER_TRADES_CSV):
                portfolio.trade_history = pd.read_csv(PAPER_TRADES_CSV).to_dict('records')
            
            logger.info(f"📂 Portfolio loaded from disk")
            logger.info(f"   Positions: {len(portfolio.positions)}")
            logger.info(f"   Pending Entries: {len(portfolio.pending_entries)}")
            logger.info(f"   Total Trades: {portfolio.total_trades}")
            
            return portfolio
        
        except Exception as e:
            logger.error(f"⚠️  Error loading portfolio: {e}")
            logger.info("   Creating new portfolio")
            return cls()


def generate_paper_trading_report(portfolio):
    """Generate a detailed formatted paper trading performance report"""
    stats = portfolio.get_performance_summary()
    report = f"""
        {'='*70}
        📊 PAPER TRADING PERFORMANCE REPORT
        {'='*70}

        Portfolio Summary:
        Starting Capital:  ${stats['starting_capital']:>12,.2f}
        Current Value:     ${stats['current_value']:>12,.2f}
        Cash Available:    ${stats['cash']:>12,.2f}
        
        Total Return:      ${stats['total_return']:>12,.2f} ({stats['total_return_pct']:+.2f}%)
        Realized P&L:      ${stats['realized_pnl']:>12,.2f}
        Max Drawdown:      {stats['max_drawdown']:>12.2f}%

        Position Metrics:
        Open Positions:    {stats['open_positions']:>12}
        Pending Entries:   {stats['pending_entries']:>12}
        Current Exposure:  ${stats['current_exposure']:>12,.2f} ({stats['exposure_pct']:.1f}%)

        Trading Statistics:
        Total Trades:      {stats['total_trades']:>12}
        Winners:           {stats['winning_trades']:>12} ({stats['win_rate']:.1f}%)
        Losers:            {stats['losing_trades']:>12}
        
        Avg Win:           ${stats['avg_win']:>12.2f} ({stats['avg_win_pct']:+.2f}%)
        Avg Loss:          ${stats['avg_loss']:>12.2f} ({stats['avg_loss_pct']:+.2f}%)
        Avg Hold Time:     {stats['avg_hold_days']:>12.1f} days

        """
    
    if portfolio.positions:
        report += f"\n{'='*70}\nOpen Positions:\n{'='*70}\n"
        for ticker, pos in portfolio.positions.items():
            try:
                current_price = portfolio._get_current_price(ticker, pos['entry_price'])
                current_value = pos['shares'] * current_price
                unrealized_pl = current_value - pos['cost_basis']
                unrealized_pct = (unrealized_pl / pos['cost_basis']) * 100
                days_held = (datetime.now() - pos['entry_date']).days
                
                trailing_status = "🔼 TRAILING" if pos.get('trailing_enabled') else "🔒 FIXED"
                
                report += f"\n  {ticker}:\n"
                report += f"    Entry Date:       {pos['entry_date'].strftime('%Y-%m-%d')}\n"
                report += f"    Shares:           {pos['shares']} @ ${pos['entry_price']:.2f}\n"
                report += f"    Current Price:    ${current_price:.2f}\n"
                report += f"    Cost Basis:       ${pos['cost_basis']:,.2f}\n"
                report += f"    Current Value:    ${current_value:,.2f}\n"
                report += f"    Unrealized P&L:   ${unrealized_pl:,.2f} ({unrealized_pct:+.2f}%)\n"
                report += f"    Days Held:        {days_held}\n"
                report += f"    Stop Loss:        ${pos['stop_loss']:.2f} {trailing_status}\n"
                report += f"    Take Profit:      ${pos['take_profit']:.2f}\n"
                report += f"    Highest Price:    ${pos['highest_price']:.2f}\n"
                
                if len(pos.get('tranches', [])) > 1:
                    report += f"    Tranches:         {len(pos['tranches'])} entries\n"
                    for i, tranche in enumerate(pos['tranches'], 1):
                        report += f"      #{i}: {tranche['shares']} @ ${tranche['price']:.2f} on {tranche['date'].strftime('%Y-%m-%d')}\n"
                
            except Exception as e:
                report += f"\n  {ticker}: Error calculating metrics\n"
    
    if portfolio.pending_entries:
        report += f"\n{'='*70}\nPending Entries (Scaling):\n{'='*70}\n"
        for ticker, pending in portfolio.pending_entries.items():
            report += f"\n  {ticker}:\n"
            report += f"    Pending Shares:   {pending['shares']}\n"
            report += f"    Trigger Price:    ${pending['trigger_price']:.2f}\n"
            report += f"    Original Entry:   ${pending['original_entry']:.2f}\n"
            report += f"    Expires:          {pending['expires'].strftime('%Y-%m-%d')}\n"
    
    report += f"\n{'='*70}\n"
    
    return report


if __name__ == "__main__":
    # Test paper trading
    portfolio = PaperTradingPortfolio.load()
    print(generate_paper_trading_report(portfolio))