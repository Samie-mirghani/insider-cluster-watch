#!/bin/bash
if [ -f ~/.env ]; then
    export $(cat ~/.env | xargs)
fi
cd /home/samie_mirghani/insider-cluster-watch
source venv/bin/activate
exec python3 -m automated_trading.execute_trades morning
