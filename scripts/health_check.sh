#!/bin/bash
cd ~/insider-cluster-watch
source venv/bin/activate

# Check if Python process is hanging
if pgrep -f "automated_trading" > /dev/null; then
    echo "$(date): Trading processes running OK" >> logs/health_$(date +\%Y\%m\%d).log
else
    echo "$(date): No trading processes found" >> logs/health_$(date +\%Y\%m\%d).log
fi
