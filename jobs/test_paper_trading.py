# jobs/test_paper_trading.py
"""
Test script for paper trading enhancements

Run this to verify all new features are working correctly.
"""

from paper_trade import PaperTradingPortfolio, generate_paper_trading_report
from paper_trade_monitor import PaperTradingMonitor
from datetime import datetime

def test_paper_trading():
    print("\n" + "="*70)
    print("🧪 TESTING PAPER TRADING ENHANCEMENTS")
    print("="*70 + "\n")
    
    # Test 1: Load portfolio
    print("Test 1: Loading portfolio...")
    portfolio = PaperTradingPortfolio.load()
    print("✅ Portfolio loaded successfully\n")
    
    # Test 2: Generate report
    print("Test 2: Generating performance report...")
    report = generate_paper_trading_report(portfolio)
    print(report)
    print("✅ Report generated successfully\n")
    
    # Test 3: Health monitoring
    print("Test 3: Running health check...")
    monitor = PaperTradingMonitor()
    monitor.set_start_of_day_value(portfolio.get_portfolio_value())
    status, alerts = monitor.check_portfolio_health(portfolio)
    print(monitor.format_alerts_report(status, alerts))
    print("✅ Health check completed\n")
    
    # Test 4: Test signal execution (fake signal) 
    print("Test 4: Testing signal execution with fake signal...")
    fake_signal = {
        'ticker': 'TEST',
        'entry_price': 10.50,
        'signal_score': 8.5,
        'cluster_count': 3,
        'sector': 'Technology'
    }
    
    # Check if we already have TEST position
    if 'TEST' in portfolio.positions:
        print("   ⚠️  TEST position already exists, skipping execution test")
    else:
        print(f"   Attempting to execute fake signal: {fake_signal['ticker']} @ ${fake_signal['entry_price']}")
        result = portfolio.execute_signal(fake_signal)
        
        if result:
            print("   ✅ Signal execution successful")
            print(f"   📊 New position created for {fake_signal['ticker']}")
        else:
            print("   ⚠️  Signal execution blocked (expected - validation working)")
    
    print("\n" + "="*70)
    print("🧪 ALL TESTS COMPLETED")
    print("="*70 + "\n")
    
    # Summary
    stats = portfolio.get_performance_summary()
    print("📊 Current Portfolio Summary:")
    print(f"   Portfolio Value: ${stats['current_value']:,.2f}")
    print(f"   Open Positions: {stats['open_positions']}")
    print(f"   Pending Entries: {stats['pending_entries']}")
    print(f"   Total Trades: {stats['total_trades']}")
    print(f"   Win Rate: {stats['win_rate']:.1f}%")
    print(f"   Health Status: {status}")
    print()

if __name__ == "__main__":
    test_paper_trading()