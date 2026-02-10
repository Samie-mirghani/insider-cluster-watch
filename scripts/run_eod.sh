#!/bin/bash
# Load environment variables from ~/.env (API keys, credentials)
# Create this file on the server: echo 'GROQ_API_KEY=your_key_here' > ~/.env && chmod 600 ~/.env
if [ -f ~/.env ]; then
    export $(cat ~/.env | xargs)
fi
cd /home/samie_mirghani/insider-cluster-watch
source venv/bin/activate
exec python3 -m automated_trading.execute_trades eod
