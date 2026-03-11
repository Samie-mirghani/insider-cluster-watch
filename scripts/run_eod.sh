#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "$HOME/.env" ]; then
    export $(cat "$HOME/.env" | xargs)
fi
cd "$PROJECT_DIR"
source venv/bin/activate
exec python3 -m automated_trading.execute_trades eod
