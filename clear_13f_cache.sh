#!/bin/bash
# Clear 13F cache to force fresh data pull
# Run this script manually when you want to force refresh 13F data

echo "🗑️  Clearing 13F cache..."

if [ -d "data/13f_cache" ]; then
    rm -rf data/13f_cache/*.json
    echo "✅ 13F cache cleared successfully"
    echo "ℹ️  Next run will fetch fresh 13F data from SEC EDGAR"
else
    echo "ℹ️  No 13F cache directory found - nothing to clear"
fi

echo ""
echo "To force a fresh run now:"
echo "  python jobs/main.py"
