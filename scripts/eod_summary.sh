#!/bin/bash
if [ -f ~/.env ]; then
    export $(cat ~/.env | xargs)
fi
cd ~/insider-cluster-watch
source venv/bin/activate
python3 -m automated_trading.execute_trades eod >> logs/eod_$(date +\%Y\%m\%d).log 2>&1
