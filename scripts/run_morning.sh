#!/bin/bash
if [ -f ~/.env ]; then
    export $(cat ~/.env | xargs)
fi
cd ~/insider-cluster-watch
source venv/bin/activate
exec python3 -m automated_trading.execute_trades morning
