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
from ticker_validator import get_failed_ticker_cache

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
    
    def get_portfolio_value(self, verbose=False):
        """
        Calculate total portfolio value (cash + positions)

        Args:
            verbose: If True, log detailed breakdown of calculation

        Returns:
            float: Total portfolio value
        """
        positions_value = 0.0
        position_details = []
        failed_ticker_cache = get_failed_ticker_cache()

        for ticker, pos in self.positions.items():
            try:
                current_price = yf.Ticker(ticker).info.get('currentPrice', pos['entry_price'])
                if not current_price or current_price <= 0:
                    current_price = pos['entry_price']
                position_value = pos['shares'] * current_price
                positions_value += position_value

                if verbose:
                    position_details.append({
                        'ticker': ticker,
                        'shares': pos['shares'],
                        'price': current_price,
                        'value': position_value
                    })
            except Exception as e:
                # Better error handling - log and cache failures
                error_msg = str(e)
                position_value = pos['shares'] * pos['entry_price']
                positions_value += position_value

                # Record failure for paper trading price fetch
                if '404' in error_msg or 'not found' in error_msg.lower():
                    failed_ticker_cache.record_failure(
                        ticker,
                        f"Paper trading price fetch: {error_msg[:80]}",
                        failure_type='PERMANENT'
                    )
                    logger.debug(f"Paper trading: {ticker} price fetch failed (404)")

                if verbose:
                    position_details.append({
                        'ticker': ticker,
                        'shares': pos['shares'],
                        'price': pos['entry_price'],
                        'value': position_value
                    })

        portfolio_value = self.cash + positions_value

        # VALIDATION: Log detailed breakdown if verbose mode enabled
        if verbose:
            logger.info(f"\n{'='*60}")
            logger.info(f"📊 PORTFOLIO VALUE BREAKDOWN")
            logger.info(f"{'='*60}")
            logger.info(f"   Cash: ${self.cash:,.2f}")
            logger.info(f"   Open Positions ({len(self.positions)}):")
            for detail in position_details:
                logger.info(f"      {detail['ticker']}: {detail['shares']} × ${detail['price']:.2f} = ${detail['value']:,.2f}")
            logger.info(f"   Total Positions Value: ${positions_value:,.2f}")
            logger.info(f"   ─────────────────────")
            logger.info(f"   Portfolio Value: ${portfolio_value:,.2f}")
            logger.info(f"   (Cash ${self.cash:,.2f} + Positions ${positions_value:,.2f})")
            logger.info(f"{'='*60}\n")

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
        except Exception as e:
            # Log price fetch failures at debug level
            error_msg = str(e)
            if '404' in error_msg or 'not found' in error_msg.lower():
                logger.debug(f"Paper trading: Failed to fetch price for {ticker}: {error_msg[:50]}")
            return fallback_price

    def get_sector_concentration(self):
        """
        Calculate current sector concentration across all positions.

        Returns:
            dict: Sector breakdown with counts, values, and percentages
        """
        if not self.positions:
            return {
                'total_positions': 0,
                'total_value': 0,
                'sectors': {},
                'warnings': []
            }

        portfolio_value = self.get_portfolio_value()
        sector_data = {}

        # Calculate value per sector
        for ticker, pos in self.positions.items():
            sector = pos.get('sector', 'Unknown')
            current_price = self._get_current_price(ticker, pos['entry_price'])
            position_value = pos['shares'] * current_price

            if sector not in sector_data:
                sector_data[sector] = {
                    'count': 0,
                    'value': 0,
                    'tickers': []
                }

            sector_data[sector]['count'] += 1
            sector_data[sector]['value'] += position_value
            sector_data[sector]['tickers'].append(ticker)

        # Calculate percentages and check for warnings
        total_positions_value = sum(s['value'] for s in sector_data.values())
        warnings = []

        for sector, data in sector_data.items():
            if sector == 'Unknown':
                continue

            pct = data['value'] / portfolio_value if portfolio_value > 0 else 0
            data['percentage'] = pct

            # Check concentration thresholds
            try:
                from config import SECTOR_HIGH_CONCENTRATION_THRESHOLD, SECTOR_WARNING_CONCENTRATION_THRESHOLD
                high_threshold = SECTOR_HIGH_CONCENTRATION_THRESHOLD
                warning_threshold = SECTOR_WARNING_CONCENTRATION_THRESHOLD
            except ImportError:
                high_threshold = 0.40
                warning_threshold = 0.30

            if pct >= high_threshold:
                warnings.append({
                    'level': 'HIGH',
                    'sector': sector,
                    'percentage': pct,
                    'message': f"⚠️ HIGH CONCENTRATION: {sector} ({data['count']} positions, "
                              f"{pct*100:.1f}%) - Consider diversifying"
                })
            elif pct >= warning_threshold:
                warnings.append({
                    'level': 'ELEVATED',
                    'sector': sector,
                    'percentage': pct,
                    'message': f"⚡ ELEVATED CONCENTRATION: {sector} ({data['count']} positions, "
                              f"{pct*100:.1f}%) - Monitor diversification"
                })

        return {
            'total_positions': len(self.positions),
            'total_value': total_positions_value,
            'sectors': sector_data,
            'warnings': warnings
        }

    def check_sector_concentration_limit(self, sector, new_position_value):
        """
        Check if adding a position would violate sector concentration limits.

        Args:
            sector: Sector name
            new_position_value: Value of the new position

        Returns:
            tuple: (is_ok, warning_message)
        """
        if not sector or sector == 'Unknown':
            return True, None

        concentration = self.get_sector_concentration()
        portfolio_value = self.get_portfolio_value()

        # Calculate what the concentration would be with the new position
        current_sector_value = concentration['sectors'].get(sector, {}).get('value', 0)
        new_sector_value = current_sector_value + new_position_value
        new_sector_pct = new_sector_value / portfolio_value if portfolio_value > 0 else 0

        try:
            from config import SECTOR_HIGH_CONCENTRATION_THRESHOLD
            high_threshold = SECTOR_HIGH_CONCENTRATION_THRESHOLD
        except ImportError:
            high_threshold = 0.40

        if new_sector_pct >= high_threshold:
            return False, (
                f"Would create HIGH concentration in {sector} "
                f"({new_sector_pct*100:.1f}%). Consider diversifying."
            )

        return True, None

    def log_sector_concentration(self):
        """
        Log current sector concentration to console.
        Useful for monitoring portfolio balance.
        """
        concentration = self.get_sector_concentration()

        if concentration['total_positions'] == 0:
            logger.info("   📊 No active positions")
            return

        logger.info(f"\n{'='*60}")
        logger.info("📊 SECTOR CONCENTRATION ANALYSIS")
        logger.info(f"{'='*60}")
        logger.info(f"Total Positions: {concentration['total_positions']}")
        logger.info(f"Total Value: ${concentration['total_value']:,.2f}")
        logger.info("\nSector Breakdown:")

        # Sort by value descending
        sorted_sectors = sorted(
            concentration['sectors'].items(),
            key=lambda x: x[1]['value'],
            reverse=True
        )

        for sector, data in sorted_sectors:
            pct = data.get('percentage', 0) * 100
            logger.info(
                f"  {sector:25s}: {data['count']} positions | "
                f"${data['value']:>10,.2f} | {pct:>5.1f}%"
            )

        # Log warnings
        if concentration['warnings']:
            logger.info("\n⚠️  CONCENTRATION WARNINGS:")
            for warning in concentration['warnings']:
                logger.info(f"  {warning['message']}")
        else:
            logger.info("\n✅ Sector diversification looks good")

        logger.info(f"{'='*60}\n")

    def calculate_position_size(self, signal):
        """
        Calculate appropriate position size based on portfolio value and risk params
        Enhanced with:
        - Multi-signal tier support
        - Score-weighted position sizing (higher scores = larger positions)

        Returns: (full_position_size, initial_size, second_tranche_size)
        """
        portfolio_value = self.get_portfolio_value()
        entry_price = signal.get('entry_price')
        ticker = signal.get('ticker', 'UNKNOWN')
        signal_score = signal.get('signal_score', 0)

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

        # Score-Weighted Position Sizing
        # Position size scales with signal score: higher scores = larger positions
        if ENABLE_SCORE_WEIGHTED_SIZING:
            # Validate score
            if signal_score is None or pd.isna(signal_score) or signal_score <= 0:
                logger.warning(f"   ⚠️  {ticker}: Invalid score ({signal_score}), using default position sizing")
                base_position_pct = self.max_position_pct
            else:
                # Linear scaling: score 6.0 → 5% position, score 20.0 → 15% position
                # Formula: position_pct = MIN + (normalized_score * (MAX - MIN))
                score_range = SCORE_WEIGHT_MAX_SCORE - SCORE_WEIGHT_MIN_SCORE

                # Handle edge case: if score range is 0 or negative
                if score_range <= 0:
                    logger.warning(f"   ⚠️  Invalid score range config, using default sizing")
                    base_position_pct = self.max_position_pct
                else:
                    # Clamp score to valid range
                    clamped_score = max(SCORE_WEIGHT_MIN_SCORE, min(signal_score, SCORE_WEIGHT_MAX_SCORE))

                    # Calculate normalized score (0.0 to 1.0)
                    normalized_score = (clamped_score - SCORE_WEIGHT_MIN_SCORE) / score_range

                    # Calculate position percentage
                    base_position_pct = SCORE_WEIGHT_MIN_POSITION_PCT + (
                        normalized_score * (SCORE_WEIGHT_MAX_POSITION_PCT - SCORE_WEIGHT_MIN_POSITION_PCT)
                    )

                    # Log the calculation
                    logger.info(f"   📈 Score-Weighted Sizing for {ticker}:")
                    logger.info(f"      Signal Score: {signal_score:.2f} (clamped: {clamped_score:.2f})")
                    logger.info(f"      Normalized Score: {normalized_score:.2%}")
                    logger.info(f"      Position %: {base_position_pct:.2%} (range: {SCORE_WEIGHT_MIN_POSITION_PCT:.2%}-{SCORE_WEIGHT_MAX_POSITION_PCT:.2%})")

            base_position_size = portfolio_value * base_position_pct
        else:
            # Traditional fixed-percentage sizing
            base_position_size = portfolio_value * self.max_position_pct

        # Apply tier multiplier for multi-signal trades
        full_position_size = base_position_size * tier_multiplier

        # Don't exceed 90% of available cash (keep buffer)
        full_position_size = min(full_position_size, self.cash * 0.9)

        # Calculate dollar amount and percentage of available cash
        cash_pct = (full_position_size / self.cash * 100) if self.cash > 0 else 0
        logger.info(f"   💰 Position Size: ${full_position_size:,.2f} ({cash_pct:.1f}% of available cash)")

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

        # Validation 1: Valid price
        if not entry_price or entry_price <= 0:
            logger.warning(f"   ❌ REJECTED: Invalid price (value: {entry_price})")
            return False

        # Validation 2: Signal score threshold (defensive check)
        # Note: Signals should already be filtered in main.py, but we check again here
        # in case execute_signal is called directly from other code paths
        if signal_score is None or pd.isna(signal_score):
            logger.warning(f"   ❌ REJECTED: Missing or invalid signal score")
            return False

        if signal_score < MIN_SIGNAL_SCORE_THRESHOLD:
            logger.warning(f"   ❌ REJECTED: Score {signal_score:.2f} below threshold {MIN_SIGNAL_SCORE_THRESHOLD}")
            return False

        # Log validated values
        logger.info(f"   Entry Price: ${entry_price:.2f}")
        logger.info(f"   Signal Score: {signal_score:.2f}")

        # Validation 3: No duplicate position
        if ticker in self.positions:
            logger.warning(f"   ⏭️  SKIPPED: Already have position in {ticker}")
            return False

        # Validation 4: Daily trade limit (reset counter if new day)
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

        # Validation 4: Check sector concentration
        sector = signal.get('sector') if isinstance(signal, dict) else signal.get('sector', 'Unknown')
        is_sector_ok, sector_warning = self.check_sector_concentration_limit(sector, actual_cost)
        if not is_sector_ok:
            logger.warning(f"   ⚠️  SECTOR WARNING: {sector_warning}")
            logger.warning(f"   💡 Consider signals from underrepresented sectors for better diversification")
            # Don't reject, just warn - allow trade to proceed but user is informed

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
        """Update trailing stops for profitable positions with dynamic tightening"""
        # Import dynamic stop config
        try:
            from config import (ENABLE_DYNAMIC_STOPS, BIG_WINNER_THRESHOLD, BIG_WINNER_STOP_PCT,
                              HUGE_WINNER_THRESHOLD, HUGE_WINNER_STOP_PCT, MODEST_GAIN_THRESHOLD,
                              OLD_POSITION_DAYS, OLD_POSITION_STOP_PCT)
            dynamic_stops_enabled = ENABLE_DYNAMIC_STOPS
        except ImportError:
            dynamic_stops_enabled = False

        for ticker, pos in self.positions.items():
            try:
                current_price = self._get_current_price(ticker, pos['entry_price'])
                unrealized_pnl_pct = ((current_price - pos['entry_price']) / pos['entry_price']) * 100
                days_held = (datetime.now() - pos['entry_date']).days

                # Track highest price
                if current_price > pos['highest_price']:
                    pos['highest_price'] = current_price

                    # Enable trailing stop after +3% gain
                    if not pos['trailing_enabled']:
                        if unrealized_pnl_pct >= 3.0:
                            pos['trailing_enabled'] = True
                            logger.info(f"   📈 {ticker}: Trailing stop ENABLED at +{unrealized_pnl_pct:.1f}%")

                # === HYBRID: Dynamic Stop Tightening for Winners ===
                if dynamic_stops_enabled and pos['trailing_enabled']:
                    trailing_pct = self.trailing_stop_pct  # Default 5%
                    stop_reason = "standard trailing"

                    # 1. Huge winner: +30% → 7% trailing stop
                    if unrealized_pnl_pct > HUGE_WINNER_THRESHOLD:
                        trailing_pct = HUGE_WINNER_STOP_PCT
                        stop_reason = f"HUGE WINNER (+{unrealized_pnl_pct:.1f}%) → 7% stop"

                    # 2. Big winner: +20% → 10% trailing stop
                    elif unrealized_pnl_pct > BIG_WINNER_THRESHOLD:
                        trailing_pct = BIG_WINNER_STOP_PCT
                        stop_reason = f"BIG WINNER (+{unrealized_pnl_pct:.1f}%) → 10% stop"

                    # 3. Old position with modest gain: tighten from high
                    elif days_held > OLD_POSITION_DAYS and 0 < unrealized_pnl_pct < MODEST_GAIN_THRESHOLD:
                        # Use 10% from highest price instead of current price
                        new_stop = pos['highest_price'] * (1 - OLD_POSITION_STOP_PCT)
                        if new_stop > pos['stop_loss']:
                            old_stop = pos['stop_loss']
                            pos['stop_loss'] = new_stop
                            logger.info(f"   🔼 {ticker}: OLD+MODEST ({days_held}d, +{unrealized_pnl_pct:.1f}%) → stop ${old_stop:.2f} → ${new_stop:.2f}")
                        continue  # Skip standard trailing update

                    # Update trailing stop with dynamic percentage
                    new_stop = current_price * (1 - trailing_pct)

                    # Only raise the stop, never lower it
                    if new_stop > pos['stop_loss']:
                        old_stop = pos['stop_loss']
                        pos['stop_loss'] = new_stop
                        if stop_reason != "standard trailing":
                            logger.info(f"   🔼 {ticker}: {stop_reason} → ${old_stop:.2f} → ${new_stop:.2f}")
                        else:
                            logger.info(f"   🔼 {ticker}: Stop raised ${old_stop:.2f} → ${new_stop:.2f} (trailing)")

                # Standard trailing stop (if dynamic stops disabled)
                elif pos['trailing_enabled']:
                    new_stop = current_price * (1 - self.trailing_stop_pct)
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

                # Performance-Based Max Hold (HYBRID: time-based + dynamic stops)
                elif PERFORMANCE_BASED_MAX_HOLD:
                    # Exit condition 1: Held 21 days and negative
                    if days_held >= MAX_HOLD_LOSS_DAYS and unrealized_pnl < 0:
                        exit_reason = 'MAX_HOLD_LOSS'
                        logger.info(f"   ⏰ MAX HOLD - LOSS ({days_held} days, {unrealized_pnl:.2f}%)")

                    # Exit condition 2: Held 30 days and barely positive (not moving)
                    elif days_held >= MAX_HOLD_STAGNANT_DAYS and unrealized_pnl < MAX_HOLD_STAGNANT_THRESHOLD:
                        exit_reason = 'MAX_HOLD_STAGNANT'
                        logger.info(f"   ⏰ MAX HOLD - STAGNANT ({days_held} days, only {unrealized_pnl:.2f}%)")

                    # Exit condition 3: Held 45 days - with exception for big winners (HYBRID)
                    elif days_held >= MAX_HOLD_EXTREME_DAYS:
                        try:
                            from config import MAX_HOLD_EXTREME_EXCEPTION
                            exception_threshold = MAX_HOLD_EXTREME_EXCEPTION
                        except ImportError:
                            exception_threshold = 15.0

                        # Exception: Keep if gaining >15% at 45 days (let winners run!)
                        if unrealized_pnl < exception_threshold:
                            exit_reason = 'MAX_HOLD_EXTREME'
                            logger.info(f"   ⏰ MAX HOLD - EXTREME ({days_held} days, {unrealized_pnl:.2f}%)")
                        else:
                            logger.info(f"   🚀 {ticker}: {days_held} days BUT +{unrealized_pnl:.1f}% → HOLDING (exception for big winners)")

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
        # CRITICAL FIX: Store position data and remove from positions dict BEFORE
        # any portfolio value calculations to prevent double-counting
        pos = self.positions[ticker].copy()  # Make a copy of position data

        proceeds = pos['shares'] * exit_price
        profit = proceeds - pos['cost_basis']
        profit_pct = (profit / pos['cost_basis']) * 100
        days_held = (datetime.now() - pos['entry_date']).days

        # Update cash and stats
        self.cash += proceeds
        self.total_profit += profit

        if profit > 0:
            self.winning_trades += 1
            emoji = "✅"
        else:
            self.losing_trades += 1
            emoji = "❌"

        # CRITICAL FIX: Remove position from dict BEFORE calculating portfolio value
        # This prevents double-counting (cash includes proceeds + position still counted)
        del self.positions[ticker]

        # Remove any pending entries for this ticker
        if ticker in self.pending_entries:
            del self.pending_entries[ticker]

        # Now log with CORRECT portfolio value (position already removed)
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

        # Get portfolio value with detailed breakdown for validation
        current_portfolio_value = self.get_portfolio_value(verbose=True)

        # CRITICAL VALIDATION: Verify portfolio state is consistent
        # This catches bugs where cash/position count don't match expectations
        logger.info(f"🔍 POST-CLOSE VALIDATION:")
        logger.info(f"   Position '{ticker}' removed from portfolio: {ticker not in self.positions}")
        logger.info(f"   Cash balance: ${self.cash:,.2f}")
        logger.info(f"   Open position count: {len(self.positions)}")
        logger.info(f"   Portfolio value: ${current_portfolio_value:,.2f}")

        # Store these values for later comparison
        expected_cash = self.cash
        expected_position_count = len(self.positions)
        expected_portfolio_value = current_portfolio_value

        logger.info(f"{'='*60}\n")

        # Log trade in NEW format expected by generate_public_performance.py
        # Portfolio value is now CORRECT (position already removed, no double-counting)
        self.trade_history.append({
            'entry_date': pos['entry_date'],        # Entry date from position
            'exit_date': datetime.now(),             # Exit date (now)
            'action': 'SELL',
            'ticker': ticker,
            'entry_price': pos['entry_price'],       # Entry price
            'exit_price': exit_price,                # Exit price
            'shares': pos['shares'],
            'proceeds': proceeds,
            'exit_reason': reason,                   # Renamed from 'reason' for clarity
            'profit': profit,
            'pnl_pct': profit_pct,                   # Renamed from 'profit_pct' to match expected format
            'hold_days': days_held,                  # Renamed from 'days_held' to match expected format
            'signal_score': pos.get('signal_score', 0),
            'cash_remaining': self.cash,
            'portfolio_value': self.get_portfolio_value(),  # Now CORRECT - no double counting
            # Store expected values for validation
            '_expected_cash': expected_cash,
            '_expected_positions': expected_position_count,
            '_expected_portfolio_value': expected_portfolio_value
        })
    
    def get_performance_summary(self, validate=True):
        """
        Get comprehensive portfolio performance statistics

        Args:
            validate: If True, perform internal consistency checks and log warnings

        Returns:
            dict: Performance statistics including current_value, cash, positions, etc.
        """
        # CRITICAL: Always recalculate portfolio value fresh
        current_value = self.get_portfolio_value()
        total_return = current_value - self.starting_capital
        total_return_pct = (total_return / self.starting_capital) * 100

        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

        # VALIDATION: Check for consistency issues
        if validate:
            # Verify that portfolio value matches cash + positions
            positions_value = sum(
                p['shares'] * self._get_current_price(t, p['entry_price'])
                for t, p in self.positions.items()
            )
            calculated_value = self.cash + positions_value

            # Allow for small floating point differences (< $0.10)
            value_diff = abs(current_value - calculated_value)
            if value_diff > 0.10:
                logger.warning(f"⚠️  PORTFOLIO VALUE MISMATCH!")
                logger.warning(f"   get_portfolio_value() returned: ${current_value:,.2f}")
                logger.warning(f"   Cash + Positions = ${calculated_value:,.2f}")
                logger.warning(f"   Difference: ${value_diff:,.2f}")
                logger.warning(f"   Cash: ${self.cash:,.2f}")
                logger.warning(f"   Positions value: ${positions_value:,.2f}")
                logger.warning(f"   Position count: {len(self.positions)}")

            # Check if we have recent trade history with expected values
            if self.trade_history:
                recent_sells = [t for t in self.trade_history if t.get('action') == 'SELL']
                if recent_sells:
                    last_sell = recent_sells[-1]
                    if '_expected_cash' in last_sell:
                        expected_cash = last_sell['_expected_cash']
                        expected_positions = last_sell['_expected_positions']

                        # Check if current state matches what was expected after last close
                        if abs(self.cash - expected_cash) > 0.01:
                            logger.warning(f"⚠️  CASH DISCREPANCY DETECTED!")
                            logger.warning(f"   Expected cash after last close: ${expected_cash:,.2f}")
                            logger.warning(f"   Current cash: ${self.cash:,.2f}")
                            logger.warning(f"   Difference: ${self.cash - expected_cash:,.2f}")

                        if len(self.positions) != expected_positions:
                            logger.warning(f"⚠️  POSITION COUNT DISCREPANCY DETECTED!")
                            logger.warning(f"   Expected positions after last close: {expected_positions}")
                            logger.warning(f"   Current positions: {len(self.positions)}")
                            logger.warning(f"   Difference: {len(self.positions) - expected_positions}")
        
        # Calculate average win and loss
        trades_df = pd.DataFrame(self.trade_history)
        if not trades_df.empty:
            sells = trades_df[trades_df['action'].isin(['SELL'])]
            if not sells.empty:
                wins = sells[sells['profit'] > 0]
                losses = sells[sells['profit'] < 0]

                avg_win = wins['profit'].mean() if len(wins) > 0 else 0
                avg_loss = losses['profit'].mean() if len(losses) > 0 else 0
                # Handle both old and new field names for backwards compatibility
                pct_field = 'pnl_pct' if 'pnl_pct' in sells.columns else 'profit_pct'
                hold_field = 'hold_days' if 'hold_days' in sells.columns else 'days_held'
                avg_win_pct = wins[pct_field].mean() if len(wins) > 0 else 0
                avg_loss_pct = losses[pct_field].mean() if len(losses) > 0 else 0
                avg_hold_days = sells[hold_field].mean() if len(sells) > 0 else 0
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

        # Build stats dictionary
        stats = {
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

        # ENHANCED LOGGING: Log summary generation for debugging
        if validate:
            logger.debug(f"📊 get_performance_summary() returning:")
            logger.debug(f"   Portfolio Value: ${stats['current_value']:,.2f}")
            logger.debug(f"   Cash: ${stats['cash']:,.2f}")
            logger.debug(f"   Open Positions: {stats['open_positions']}")
            logger.debug(f"   Source: self.cash=${self.cash:,.2f}, len(self.positions)={len(self.positions)}")

        return stats
    
    def save(self):
        """Save portfolio state to disk with validation"""
        # Store pre-save state for validation
        pre_save_cash = self.cash
        pre_save_position_count = len(self.positions)
        pre_save_position_tickers = list(self.positions.keys())

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

        # VALIDATION: Log what was saved for debugging
        logger.info(f"💾 Portfolio saved to disk")
        logger.debug(f"   Saved cash: ${pre_save_cash:,.2f}")
        logger.debug(f"   Saved positions: {pre_save_position_count} ({', '.join(pre_save_position_tickers) if pre_save_position_tickers else 'none'})")

        # CRITICAL VALIDATION: Verify in-memory state didn't change during save
        if self.cash != pre_save_cash:
            logger.error(f"🚨 CRITICAL: Cash changed during save! Before: ${pre_save_cash:,.2f}, After: ${self.cash:,.2f}")
        if len(self.positions) != pre_save_position_count:
            logger.error(f"🚨 CRITICAL: Position count changed during save! Before: {pre_save_position_count}, After: {len(self.positions)}")
        if list(self.positions.keys()) != pre_save_position_tickers:
            logger.error(f"🚨 CRITICAL: Position tickers changed during save!")
    
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
            logger.info(f"   Cash: ${portfolio.cash:,.2f}")
            logger.info(f"   Positions: {len(portfolio.positions)} ({', '.join(portfolio.positions.keys()) if portfolio.positions else 'none'})")
            logger.info(f"   Pending Entries: {len(portfolio.pending_entries)}")
            logger.info(f"   Total Trades: {portfolio.total_trades}")

            # VALIDATION: Calculate and log portfolio value after load
            loaded_value = portfolio.get_portfolio_value()
            logger.debug(f"   Portfolio Value after load: ${loaded_value:,.2f}")

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