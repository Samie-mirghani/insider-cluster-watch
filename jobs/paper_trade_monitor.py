# jobs/paper_trade_monitor.py
"""
Paper Trading Health Monitor

Monitors portfolio health and generates alerts when risk thresholds are breached.
"""

from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class PaperTradingMonitor:
    """Monitor paper trading health and send alerts"""
    
    def __init__(self, 
                 max_daily_loss_pct=5.0,
                 max_drawdown_alert=10.0,
                 min_win_rate_alert=35.0,
                 max_exposure_alert=30.0):
        self.max_daily_loss = max_daily_loss_pct
        self.max_drawdown_alert = max_drawdown_alert
        self.min_win_rate = min_win_rate_alert
        self.max_exposure = max_exposure_alert
        
        self.start_of_day_value = None
        self.alerts = []
    
    def set_start_of_day_value(self, value):
        """Set the portfolio value at start of day"""
        self.start_of_day_value = value
    
    def check_portfolio_health(self, portfolio):
        """
        Run comprehensive health checks on portfolio
        
        Returns: (status, alerts_list)
        """
        self.alerts = []
        stats = portfolio.get_performance_summary()
        current_value = stats['current_value']
        
        # Check 1: Daily loss limit
        if self.start_of_day_value:
            daily_pnl_pct = ((current_value - self.start_of_day_value) / self.start_of_day_value) * 100
            
            if daily_pnl_pct <= -self.max_daily_loss:
                self.alerts.append({
                    'level': 'CRITICAL',
                    'type': 'DAILY_LOSS',
                    'message': f"Daily loss limit breached: {daily_pnl_pct:.2f}% (limit: -{self.max_daily_loss}%)",
                    'action': 'Consider halting new positions for today'
                })
        
        # Check 2: Maximum drawdown
        if stats['max_drawdown'] <= -self.max_drawdown_alert:
            self.alerts.append({
                'level': 'WARNING',
                'type': 'MAX_DRAWDOWN',
                'message': f"Maximum drawdown alert: {stats['max_drawdown']:.2f}% (alert: -{self.max_drawdown_alert}%)",
                'action': 'Review strategy and position sizing'
            })
        
        # Check 3: Win rate (only if enough trades)
        if stats['total_trades'] >= 10:
            if stats['win_rate'] < self.min_win_rate:
                self.alerts.append({
                    'level': 'WARNING',
                    'type': 'LOW_WIN_RATE',
                    'message': f"Win rate below threshold: {stats['win_rate']:.1f}% (min: {self.min_win_rate}%)",
                    'action': 'Strategy may need adjustment'
                })
        
        # Check 4: Position concentration
        if stats['exposure_pct'] > self.max_exposure:
            self.alerts.append({
                'level': 'WARNING',
                'type': 'HIGH_EXPOSURE',
                'message': f"Total exposure too high: {stats['exposure_pct']:.1f}% (max: {self.max_exposure}%)",
                'action': 'Reduce position sizes or close some positions'
            })
        
        # Check 5: Single position too large
        if portfolio.positions:
            for ticker, pos in portfolio.positions.items():
                current_price = portfolio._get_current_price(ticker, pos['entry_price'])
                position_value = pos['shares'] * current_price
                position_pct = (position_value / current_value) * 100
                
                if position_pct > 10:
                    self.alerts.append({
                        'level': 'WARNING',
                        'type': 'POSITION_CONCENTRATION',
                        'message': f"{ticker} position is {position_pct:.1f}% of portfolio (max recommended: 10%)",
                        'action': f'Consider trimming {ticker} position'
                    })
        
        # Check 6: Stale positions (>21 days)
        if portfolio.positions:
            for ticker, pos in portfolio.positions.items():
                days_held = (datetime.now() - pos['entry_date']).days
                if days_held > 21:
                    self.alerts.append({
                        'level': 'INFO',
                        'type': 'STALE_POSITION',
                        'message': f"{ticker} held for {days_held} days (time stop should trigger soon)",
                        'action': 'Monitor for time-based exit'
                    })
        
        # Check 7: Negative total return
        if stats['total_trades'] >= 5 and stats['total_return_pct'] < -5:
            self.alerts.append({
                'level': 'CRITICAL',
                'type': 'NEGATIVE_RETURN',
                'message': f"Total return is negative: {stats['total_return_pct']:.2f}%",
                'action': 'Consider pausing strategy and reviewing parameters'
            })
        
        # Determine overall status
        if any(alert['level'] == 'CRITICAL' for alert in self.alerts):
            status = 'CRITICAL'
        elif any(alert['level'] == 'WARNING' for alert in self.alerts):
            status = 'WARNING'
        else:
            status = 'HEALTHY'
        
        return status, self.alerts
    
    def format_alerts_report(self, status, alerts):
        """Format alerts into a readable report"""
        if not alerts:
            return "✅ Portfolio Health: HEALTHY\n   No alerts detected.\n"
        
        status_emoji = {
            'HEALTHY': '✅',
            'WARNING': '⚠️',
            'CRITICAL': '🚨'
        }
        
        report = f"\n{status_emoji[status]} Portfolio Health: {status}\n"
        report += f"{'='*70}\n"
        
        # Group by level
        critical = [a for a in alerts if a['level'] == 'CRITICAL']
        warning = [a for a in alerts if a['level'] == 'WARNING']
        info = [a for a in alerts if a['level'] == 'INFO']
        
        if critical:
            report += f"\n🚨 CRITICAL ALERTS ({len(critical)}):\n"
            for alert in critical:
                report += f"  • {alert['message']}\n"
                report += f"    Action: {alert['action']}\n\n"
        
        if warning:
            report += f"\n⚠️  WARNING ALERTS ({len(warning)}):\n"
            for alert in warning:
                report += f"  • {alert['message']}\n"
                report += f"    Action: {alert['action']}\n\n"
        
        if info:
            report += f"\nℹ️  INFO ({len(info)}):\n"
            for alert in info:
                report += f"  • {alert['message']}\n\n"
        
        report += f"{'='*70}\n"
        
        return report
    
    def log_alerts(self, status, alerts):
        """Log alerts to logger"""
        if not alerts:
            logger.info("✅ Portfolio health check: HEALTHY")
            return
        
        for alert in alerts:
            level = alert['level']
            message = f"[{alert['type']}] {alert['message']}"
            
            if level == 'CRITICAL':
                logger.critical(message)
            elif level == 'WARNING':
                logger.warning(message)
            else:
                logger.info(message)


if __name__ == "__main__":
    # Test monitor
    from paper_trade import PaperTradingPortfolio
    
    portfolio = PaperTradingPortfolio.load()
    monitor = PaperTradingMonitor()
    
    # Set start of day value (for testing, use current - 2%)
    monitor.set_start_of_day_value(portfolio.get_portfolio_value() * 1.02)
    
    status, alerts = monitor.check_portfolio_health(portfolio)
    print(monitor.format_alerts_report(status, alerts))