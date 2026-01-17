# automated_trading/__init__.py
"""
Alpaca Automated Trading System

Production-ready trading system using Alpaca API for executing insider cluster signals.
Designed for safety-first operation with comprehensive circuit breakers, reconciliation,
and audit logging.

Directory Structure:
    automated_trading/
    ├── __init__.py           # This file
    ├── config.py             # Configuration and circuit breakers
    ├── alpaca_client.py      # Alpaca API wrapper with error handling
    ├── order_manager.py      # Order state management with idempotency
    ├── signal_queue.py       # Signal queue for intraday redeployment
    ├── position_monitor.py   # Position monitoring and exits
    ├── reconciliation.py     # Broker state reconciliation
    ├── alerts.py             # Email alert system
    ├── execute_trades.py     # Daily execution engine
    ├── utils.py              # Utility functions
    └── data/
        ├── live_positions.json    # Current positions
        ├── pending_orders.json    # Orders awaiting fill
        ├── queued_signals.json    # Signals waiting for capital
        ├── daily_state.json       # Daily P&L and circuit breaker state
        └── audit_log.jsonl        # Immutable audit trail

Safety Features:
    - Daily loss circuit breaker (halts trading if exceeded)
    - Position reconciliation with Alpaca on every cycle
    - Idempotent order submission (prevents duplicates)
    - Comprehensive audit logging
    - Market hours validation
    - Graceful error handling with retry logic

Author: Automated Trading System
Version: 1.0.0
"""

__version__ = "1.0.0"
__author__ = "Insider Cluster Watch"
