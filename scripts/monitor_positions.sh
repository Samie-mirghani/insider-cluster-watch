#!/bin/bash
cd ~/insider-cluster-watch
source venv/bin/activate
python3 -m automated_trading.execute_trades monitor >> logs/monitor_$(date +\%Y\%m\%d).log 2>&1
