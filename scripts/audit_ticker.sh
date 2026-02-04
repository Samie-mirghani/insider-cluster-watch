#!/bin/bash

################################################################################
# INSIDER CLUSTER WATCH - INTERACTIVE AUDIT TOOL
#
# Purpose: Comprehensive audit of ticker trading history across all system layers
# Author: Claude (Insider Cluster Watch System)
# Created: 2025-02-03
################################################################################

set -e  # Exit on error
set -u  # Exit on undefined variable

################################################################################
# CONSTANTS AND CONFIGURATION
################################################################################

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_ROOT/data"
TRADING_DIR="$PROJECT_ROOT/automated_trading/data"
AUDIT_REPORTS_DIR="$PROJECT_ROOT/audit_reports"

# Color codes for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# File paths
SIGNALS_HISTORY="$DATA_DIR/signals_history.csv"
APPROVED_SIGNALS="$DATA_DIR/approved_signals.json"
PAPER_TRADES="$DATA_DIR/paper_trades.csv"
PAPER_PORTFOLIO="$DATA_DIR/paper_portfolio.json"
PAPER_TRADING_LOG="$DATA_DIR/paper_trading.log"
AUDIT_LOG="$TRADING_DIR/audit_log.jsonl"
LIVE_POSITIONS="$TRADING_DIR/live_positions.json"
PENDING_ORDERS="$TRADING_DIR/pending_orders.json"
QUEUED_SIGNALS="$TRADING_DIR/queued_signals.json"
EXECUTION_METRICS="$TRADING_DIR/execution_metrics.json"
ALPACA_LOG="$TRADING_DIR/alpaca_trading.log"

# Global variables for storing report content
REPORT_CONTENT=""
USE_COLOR=true

################################################################################
# UTILITY FUNCTIONS
################################################################################

# Print colored text to terminal only
print_color() {
    local color="$1"
    local text="$2"
    if [ "$USE_COLOR" = true ]; then
        echo -e "${color}${text}${NC}"
    else
        echo "$text"
    fi
}

# Add text to report (both terminal and file output)
add_to_report() {
    local text="$1"
    local color="${2:-$WHITE}"

    # Strip color codes for file output
    local plain_text=$(echo "$text" | sed 's/\x1b\[[0-9;]*m//g')
    REPORT_CONTENT+="$plain_text"$'\n'

    # Print with color to terminal if enabled
    if [ "$OUTPUT_FORMAT" = "terminal" ] || [ "$OUTPUT_FORMAT" = "both" ]; then
        if [ "$USE_COLOR" = true ]; then
            echo -e "${color}${text}${NC}"
        else
            echo "$text"
        fi
    fi
}

# Print section header
print_section() {
    local title="$1"
    local separator="============================================================"
    add_to_report ""
    add_to_report "$separator" "$CYAN"
    add_to_report "$title" "$CYAN"
    add_to_report "$separator" "$CYAN"
    add_to_report ""
}

# Print subsection header
print_subsection() {
    local title="$1"
    local separator="-------------------------------------------------------------"
    add_to_report ""
    add_to_report "$title" "$BLUE"
    add_to_report "$separator" "$BLUE"
}

# Check if file exists
file_exists() {
    local file="$1"
    if [ -f "$file" ]; then
        return 0
    else
        return 1
    fi
}

# Format date for display
format_date() {
    local date_str="$1"
    if [ -n "$date_str" ]; then
        date -d "$date_str" "+%Y-%m-%d %H:%M" 2>/dev/null || echo "$date_str"
    else
        echo "N/A"
    fi
}

# Format currency
format_currency() {
    local amount="$1"
    printf "\$%.2f" "$amount"
}

# Format percentage
format_percentage() {
    local value="$1"
    printf "%.2f%%" "$value"
}

# Calculate percentage change
calc_percentage() {
    local initial="$1"
    local final="$2"
    if [ "$initial" != "0" ] && [ -n "$initial" ]; then
        echo "scale=2; (($final - $initial) / $initial) * 100" | bc
    else
        echo "0"
    fi
}

################################################################################
# INTERACTIVE PROMPTS
################################################################################

prompt_ticker() {
    local ticker
    while true; do
        read -p "Enter ticker symbol to audit: " ticker
        ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]' | tr -d ' ')
        if [ -n "$ticker" ]; then
            TICKER="$ticker"
            break
        else
            echo "Error: Ticker symbol cannot be empty"
        fi
    done
}

prompt_scope() {
    read -p "Select audit scope [all/signals/paper/live/recent]: " scope
    scope=$(echo "$scope" | tr '[:upper:]' '[:lower:]')
    if [ -z "$scope" ] || [ "$scope" = "all" ]; then
        SCOPE="all"
    else
        case "$scope" in
            signals|paper|live|recent)
                SCOPE="$scope"
                ;;
            *)
                echo "Invalid scope, using 'all'"
                SCOPE="all"
                ;;
        esac
    fi
}

prompt_date_range() {
    read -p "Filter by date range? [y/N]: " use_range
    use_range=$(echo "$use_range" | tr '[:upper:]' '[:lower:]')

    if [ "$use_range" = "y" ] || [ "$use_range" = "yes" ]; then
        read -p "Start date (YYYY-MM-DD) [default: all]: " start_date
        read -p "End date (YYYY-MM-DD) [default: today]: " end_date

        START_DATE="${start_date:-}"
        END_DATE="${end_date:-$(date +%Y-%m-%d)}"
    else
        START_DATE=""
        END_DATE=""
    fi
}

prompt_output_format() {
    read -p "Output format [terminal/file/both]: " format
    format=$(echo "$format" | tr '[:upper:]' '[:lower:]')
    if [ -z "$format" ] || [ "$format" = "terminal" ]; then
        OUTPUT_FORMAT="terminal"
    else
        case "$format" in
            file|both)
                OUTPUT_FORMAT="$format"
                ;;
            *)
                echo "Invalid format, using 'terminal'"
                OUTPUT_FORMAT="terminal"
                ;;
        esac
    fi
}

prompt_detail_level() {
    read -p "Detail level [summary/standard/verbose]: " level
    level=$(echo "$level" | tr '[:upper:]' '[:lower:]')
    if [ -z "$level" ] || [ "$level" = "standard" ]; then
        DETAIL_LEVEL="standard"
    else
        case "$level" in
            summary|verbose)
                DETAIL_LEVEL="$level"
                ;;
            *)
                echo "Invalid level, using 'standard'"
                DETAIL_LEVEL="standard"
                ;;
        esac
    fi
}

################################################################################
# DATA COLLECTION FUNCTIONS
################################################################################

collect_signal_history() {
    local ticker="$1"

    if ! file_exists "$SIGNALS_HISTORY"; then
        echo "[]"
        return
    fi

    # Parse CSV and extract signals for this ticker
    # Format: date,ticker,rank_score,suggested_action,cluster_count,total_buy_value,sector,industry,...
    local result=$(awk -F',' -v ticker="$ticker" '
        NR > 1 && $2 == ticker {
            print $0
        }
    ' "$SIGNALS_HISTORY" | jq -R -s '
        split("\n") |
        map(select(length > 0) | split(",")) |
        map({
            date: .[0],
            ticker: .[1],
            rank_score: (.[2] // "0" | tonumber),
            suggested_action: .[3],
            cluster_count: (.[4] // "0" | tonumber),
            total_buy_value: (.[5] // "0" | tonumber),
            sector: .[6],
            industry: .[7]
        })
    ')

    echo "$result"
}

collect_approved_signals() {
    local ticker="$1"

    if ! file_exists "$APPROVED_SIGNALS"; then
        echo "null"
        return
    fi

    jq -r --arg ticker "$ticker" '.[$ticker] // null' "$APPROVED_SIGNALS" 2>/dev/null || echo "null"
}

collect_paper_trades() {
    local ticker="$1"

    if ! file_exists "$PAPER_TRADES"; then
        echo "[]"
        return
    fi

    # Parse CSV: date,ticker,action,shares,price,total_cost,reason
    local result=$(awk -F',' -v ticker="$ticker" '
        NR > 1 && $2 == ticker {
            print $0
        }
    ' "$PAPER_TRADES" | jq -R -s '
        split("\n") |
        map(select(length > 0) | split(",")) |
        map({
            date: .[0],
            ticker: .[1],
            action: .[2],
            shares: (.[3] // "0" | tonumber),
            price: (.[4] // "0" | tonumber),
            total_cost: (.[5] // "0" | tonumber),
            reason: (.[6] // "")
        })
    ')

    echo "$result"
}

collect_paper_portfolio() {
    local ticker="$1"

    if ! file_exists "$PAPER_PORTFOLIO"; then
        echo "null"
        return
    fi

    jq -r --arg ticker "$ticker" '.positions[$ticker] // null' "$PAPER_PORTFOLIO" 2>/dev/null || echo "null"
}

collect_live_audit_log() {
    local ticker="$1"

    if ! file_exists "$AUDIT_LOG"; then
        echo "[]"
        return
    fi

    # Parse JSONL file and filter by ticker
    grep -i "\"ticker\".*:.*\"$ticker\"" "$AUDIT_LOG" 2>/dev/null | jq -s '.' || echo "[]"
}

collect_live_positions() {
    local ticker="$1"

    if ! file_exists "$LIVE_POSITIONS"; then
        echo "null"
        return
    fi

    jq -r --arg ticker "$ticker" '.positions[$ticker] // null' "$LIVE_POSITIONS" 2>/dev/null || echo "null"
}

collect_pending_orders() {
    local ticker="$1"

    if ! file_exists "$PENDING_ORDERS"; then
        echo "[]"
        return
    fi

    jq -r --arg ticker "$ticker" '[.[] | select(.ticker == $ticker)]' "$PENDING_ORDERS" 2>/dev/null || echo "[]"
}

collect_queued_signals() {
    local ticker="$1"

    if ! file_exists "$QUEUED_SIGNALS"; then
        echo "null"
        return
    fi

    jq -r --arg ticker "$ticker" '.[$ticker] // null' "$QUEUED_SIGNALS" 2>/dev/null || echo "null"
}

collect_execution_metrics() {
    if ! file_exists "$EXECUTION_METRICS"; then
        echo "null"
        return
    fi

    cat "$EXECUTION_METRICS" 2>/dev/null || echo "null"
}

collect_price_data() {
    local ticker="$1"

    # Use Python with yfinance to get price data
    python3 -c "
import yfinance as yf
import json
from datetime import datetime, timedelta

try:
    ticker = yf.Ticker('$ticker')

    # Get current price
    hist_1d = ticker.history(period='1d')
    current_price = float(hist_1d['Close'].iloc[-1]) if not hist_1d.empty else None

    # Get 30-day data
    hist_30d = ticker.history(period='30d')

    if not hist_30d.empty:
        high_30d = float(hist_30d['High'].max())
        low_30d = float(hist_30d['Low'].min())
        avg_volume = float(hist_30d['Volume'].mean())

        # Calculate SMAs
        sma_5 = float(hist_30d['Close'].tail(5).mean())
        sma_20 = float(hist_30d['Close'].tail(20).mean()) if len(hist_30d) >= 20 else None
    else:
        high_30d = low_30d = avg_volume = sma_5 = sma_20 = None

    result = {
        'current_price': current_price,
        'high_30d': high_30d,
        'low_30d': low_30d,
        'avg_volume': avg_volume,
        'sma_5': sma_5,
        'sma_20': sma_20,
        'success': True
    }

    print(json.dumps(result))
except Exception as e:
    print(json.dumps({'success': False, 'error': str(e)}))
" 2>/dev/null || echo '{"success": false, "error": "Failed to fetch price data"}'
}

collect_logs() {
    local ticker="$1"
    local logs=""

    # Collect from paper trading log
    if file_exists "$PAPER_TRADING_LOG"; then
        local paper_logs=$(grep -i "$ticker" "$PAPER_TRADING_LOG" 2>/dev/null | tail -50 || echo "")
        if [ -n "$paper_logs" ]; then
            logs+="=== Paper Trading Log ===$\n$paper_logs\n\n"
        fi
    fi

    # Collect from Alpaca trading log
    if file_exists "$ALPACA_LOG"; then
        local alpaca_logs=$(grep -i "$ticker" "$ALPACA_LOG" 2>/dev/null | tail -50 || echo "")
        if [ -n "$alpaca_logs" ]; then
            logs+="=== Alpaca Trading Log ===$\n$alpaca_logs\n\n"
        fi
    fi

    echo -e "$logs"
}

################################################################################
# ANALYSIS FUNCTIONS
################################################################################

analyze_paper_positions() {
    local trades_json="$1"

    # Group trades into positions (match BUY with SELL)
    python3 -c "
import json
import sys
from datetime import datetime

trades = json.loads('$trades_json')

# Separate buys and sells
buys = [t for t in trades if t['action'] == 'BUY']
sells = [t for t in trades if t['action'] == 'SELL']

positions = []
buy_idx = 0

for sell in sells:
    if buy_idx < len(buys):
        buy = buys[buy_idx]

        # Calculate P&L
        cost = buy['total_cost']
        proceeds = sell['total_cost']
        pnl = proceeds - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0

        # Calculate hold duration
        try:
            buy_date = datetime.fromisoformat(buy['date'].replace('Z', '+00:00'))
            sell_date = datetime.fromisoformat(sell['date'].replace('Z', '+00:00'))
            hold_days = (sell_date - buy_date).days
        except:
            hold_days = 0

        positions.append({
            'entry_date': buy['date'],
            'entry_price': buy['price'],
            'entry_shares': buy['shares'],
            'entry_cost': buy['total_cost'],
            'exit_date': sell['date'],
            'exit_price': sell['price'],
            'exit_shares': sell['shares'],
            'exit_proceeds': sell['total_cost'],
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'hold_days': hold_days,
            'exit_reason': sell['reason']
        })

        buy_idx += 1

print(json.dumps(positions, indent=2))
" 2>/dev/null || echo "[]"
}

calculate_paper_summary() {
    local positions_json="$1"

    python3 -c "
import json

positions = json.loads('$positions_json')

if not positions:
    print(json.dumps({
        'total_positions': 0,
        'wins': 0,
        'losses': 0,
        'win_rate': 0,
        'total_pnl': 0,
        'total_pnl_pct': 0,
        'avg_hold_days': 0,
        'avg_win': 0,
        'avg_win_pct': 0,
        'avg_loss': 0,
        'avg_loss_pct': 0,
        'win_loss_ratio': 0
    }))
else:
    wins = [p for p in positions if p['pnl'] > 0]
    losses = [p for p in positions if p['pnl'] <= 0]

    total_positions = len(positions)
    num_wins = len(wins)
    num_losses = len(losses)
    win_rate = (num_wins / total_positions * 100) if total_positions > 0 else 0

    total_pnl = sum(p['pnl'] for p in positions)
    avg_cost = sum(p['entry_cost'] for p in positions) / total_positions
    total_pnl_pct = (total_pnl / avg_cost * 100) if avg_cost > 0 else 0

    avg_hold_days = sum(p['hold_days'] for p in positions) / total_positions

    avg_win = sum(p['pnl'] for p in wins) / num_wins if num_wins > 0 else 0
    avg_win_pct = sum(p['pnl_pct'] for p in wins) / num_wins if num_wins > 0 else 0

    avg_loss = sum(p['pnl'] for p in losses) / num_losses if num_losses > 0 else 0
    avg_loss_pct = sum(p['pnl_pct'] for p in losses) / num_losses if num_losses > 0 else 0

    win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    summary = {
        'total_positions': total_positions,
        'wins': num_wins,
        'losses': num_losses,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'total_pnl_pct': total_pnl_pct,
        'avg_hold_days': avg_hold_days,
        'avg_win': avg_win,
        'avg_win_pct': avg_win_pct,
        'avg_loss': avg_loss,
        'avg_loss_pct': avg_loss_pct,
        'win_loss_ratio': win_loss_ratio
    }

    print(json.dumps(summary, indent=2))
"
}

################################################################################
# REPORT GENERATION FUNCTIONS
################################################################################

generate_header() {
    local ticker="$1"
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")

    print_section "INSIDER CLUSTER WATCH - AUDIT TOOL"
    add_to_report "Generated: $timestamp"
    add_to_report "Ticker: $ticker"
    add_to_report "Scope: $SCOPE"

    if [ -n "$START_DATE" ]; then
        add_to_report "Date Range: $START_DATE to $END_DATE"
    else
        add_to_report "Date Range: All time"
    fi

    add_to_report "Detail Level: $DETAIL_LEVEL"
    add_to_report ""
}

generate_executive_summary() {
    local ticker="$1"
    local signal_count="$2"
    local paper_trades_json="$3"
    local paper_positions_json="$4"
    local paper_summary_json="$5"
    local live_events_json="$6"
    local live_position="$7"
    local current_paper_position="$8"

    print_section "SECTION 1: EXECUTIVE SUMMARY"

    add_to_report "Ticker: $ticker"
    add_to_report "Audit Date: $(date '+%Y-%m-%d %H:%M:%S')"
    add_to_report ""

    # Overall status
    add_to_report "Overall Status:" "$WHITE"
    add_to_report "  Signals Generated:       $signal_count times"

    local paper_traded="No"
    if [ "$(echo "$paper_trades_json" | jq 'length')" -gt 0 ]; then
        paper_traded="Yes ($(echo "$paper_positions_json" | jq 'length') positions)"
    fi
    add_to_report "  Paper Traded:            $paper_traded"

    local live_traded="No"
    if [ "$(echo "$live_events_json" | jq 'length')" -gt 0 ]; then
        local live_pos_count=$(echo "$live_events_json" | jq '[.[] | select(.event_type == "POSITION_OPENED")] | length')
        live_traded="Yes ($live_pos_count positions)"
    fi
    add_to_report "  Live Traded:             $live_traded"

    local current_paper_status="None"
    if [ "$current_paper_position" != "null" ]; then
        current_paper_status="Active"
    else
        current_paper_status="Closed"
    fi
    add_to_report "  Current Paper Position:  $current_paper_status"

    local current_live_status="None"
    if [ "$live_position" != "null" ]; then
        current_live_status="Active"
    else
        current_live_status="Closed"
    fi
    add_to_report "  Current Live Position:   $current_live_status"
    add_to_report ""

    # Performance summary
    if [ "$DETAIL_LEVEL" != "summary" ]; then
        add_to_report "Performance Summary:" "$WHITE"

        # Paper trading P&L
        local paper_pnl=$(echo "$paper_summary_json" | jq -r '.total_pnl // 0')
        local paper_pnl_pct=$(echo "$paper_summary_json" | jq -r '.total_pnl_pct // 0')
        local paper_pnl_formatted=$(format_currency "$paper_pnl")
        local paper_pnl_pct_formatted=$(format_percentage "$paper_pnl_pct")

        if (( $(echo "$paper_pnl > 0" | bc -l) )); then
            add_to_report "  Paper Trading P&L:       ${GREEN}+${paper_pnl_formatted} (+${paper_pnl_pct_formatted})${NC}" "$GREEN"
        elif (( $(echo "$paper_pnl < 0" | bc -l) )); then
            add_to_report "  Paper Trading P&L:       ${RED}${paper_pnl_formatted} (${paper_pnl_pct_formatted})${NC}" "$RED"
        else
            add_to_report "  Paper Trading P&L:       ${paper_pnl_formatted} (${paper_pnl_pct_formatted})"
        fi

        # Live trading P&L (simplified for now)
        add_to_report "  Live Trading P&L:        (See live trading section)"
        add_to_report ""

        # Win rate
        add_to_report "Win Rate:" "$WHITE"
        local paper_wins=$(echo "$paper_summary_json" | jq -r '.wins // 0')
        local paper_losses=$(echo "$paper_summary_json" | jq -r '.losses // 0')
        local paper_win_rate=$(echo "$paper_summary_json" | jq -r '.win_rate // 0')
        add_to_report "  Paper: ${paper_wins}W / ${paper_losses}L ($(format_percentage "$paper_win_rate"))"
        add_to_report "  Live:  (See live trading section)"
    fi
}

generate_signal_timeline() {
    local signals_json="$1"
    local approved_signal="$2"

    print_section "SECTION 2: SIGNAL DETECTION TIMELINE"

    local signal_count=$(echo "$signals_json" | jq 'length')

    if [ "$signal_count" -eq 0 ]; then
        add_to_report "No signals found for this ticker." "$YELLOW"
        return
    fi

    # Iterate through signals
    echo "$signals_json" | jq -c '.[]' | while read -r signal; do
        local date=$(echo "$signal" | jq -r '.date')
        local score=$(echo "$signal" | jq -r '.rank_score')
        local action=$(echo "$signal" | jq -r '.suggested_action')
        local cluster=$(echo "$signal" | jq -r '.cluster_count')
        local value=$(echo "$signal" | jq -r '.total_buy_value')
        local sector=$(echo "$signal" | jq -r '.sector // "N/A"')
        local industry=$(echo "$signal" | jq -r '.industry // "N/A"')

        add_to_report ""
        add_to_report "$(format_date "$date") | SIGNAL GENERATED" "$CYAN"
        add_to_report "  Score: $score | Action: $action"
        add_to_report "  Cluster: $cluster insiders | Value: \$$(printf "%.0f" "$value")"
        add_to_report "  Sector: $sector | Industry: $industry"

        # Check if approved
        if [ "$approved_signal" != "null" ]; then
            add_to_report "  ${GREEN}→ APPROVED for trading${NC}" "$GREEN"
        else
            if (( $(echo "$score < 7.0" | bc -l) )); then
                add_to_report "  ${RED}→ REJECTED: Score below threshold ($score < 7.0)${NC}" "$RED"
            fi
        fi
    done
}

generate_paper_trading_history() {
    local positions_json="$1"
    local summary_json="$2"
    local current_position="$3"

    print_section "SECTION 3: PAPER TRADING HISTORY"

    local pos_count=$(echo "$positions_json" | jq 'length')

    if [ "$pos_count" -eq 0 ]; then
        add_to_report "No paper trading history found for this ticker." "$YELLOW"
        return
    fi

    # Display each position
    local idx=1
    echo "$positions_json" | jq -c '.[]' | while read -r position; do
        local entry_date=$(echo "$position" | jq -r '.entry_date')
        local entry_price=$(echo "$position" | jq -r '.entry_price')
        local entry_shares=$(echo "$position" | jq -r '.entry_shares')
        local entry_cost=$(echo "$position" | jq -r '.entry_cost')

        local exit_date=$(echo "$position" | jq -r '.exit_date')
        local exit_price=$(echo "$position" | jq -r '.exit_price')
        local exit_shares=$(echo "$position" | jq -r '.exit_shares')
        local exit_proceeds=$(echo "$position" | jq -r '.exit_proceeds')

        local pnl=$(echo "$position" | jq -r '.pnl')
        local pnl_pct=$(echo "$position" | jq -r '.pnl_pct')
        local hold_days=$(echo "$position" | jq -r '.hold_days')
        local exit_reason=$(echo "$position" | jq -r '.exit_reason')

        add_to_report ""
        add_to_report "Position #$idx: $(format_date "$entry_date") to $(format_date "$exit_date")" "$WHITE"
        add_to_report "  Entry:  $(format_date "$entry_date") | $entry_shares shares @ $(format_currency "$entry_price") | Cost: $(format_currency "$entry_cost")"
        add_to_report "  Exit:   $(format_date "$exit_date") | $exit_shares shares @ $(format_currency "$exit_price") | Proceeds: $(format_currency "$exit_proceeds")"

        if (( $(echo "$pnl > 0" | bc -l) )); then
            add_to_report "  Result: ${GREEN}+$(format_currency "$pnl") (+$(format_percentage "$pnl_pct"))${NC}" "$GREEN"
        else
            add_to_report "  Result: ${RED}$(format_currency "$pnl") ($(format_percentage "$pnl_pct"))${NC}" "$RED"
        fi

        add_to_report "  Reason: $exit_reason"
        add_to_report "  Hold:   $hold_days days"

        idx=$((idx + 1))
    done

    # Display summary
    if [ "$DETAIL_LEVEL" != "summary" ]; then
        add_to_report ""
        print_subsection "Paper Trading Summary"

        local total_pos=$(echo "$summary_json" | jq -r '.total_positions')
        local wins=$(echo "$summary_json" | jq -r '.wins')
        local losses=$(echo "$summary_json" | jq -r '.losses')
        local win_rate=$(echo "$summary_json" | jq -r '.win_rate')
        local total_pnl=$(echo "$summary_json" | jq -r '.total_pnl')
        local total_pnl_pct=$(echo "$summary_json" | jq -r '.total_pnl_pct')
        local avg_hold=$(echo "$summary_json" | jq -r '.avg_hold_days')
        local avg_win=$(echo "$summary_json" | jq -r '.avg_win')
        local avg_win_pct=$(echo "$summary_json" | jq -r '.avg_win_pct')
        local avg_loss=$(echo "$summary_json" | jq -r '.avg_loss')
        local avg_loss_pct=$(echo "$summary_json" | jq -r '.avg_loss_pct')
        local wl_ratio=$(echo "$summary_json" | jq -r '.win_loss_ratio')

        add_to_report "  Total Positions:    $total_pos"
        add_to_report "  Wins:               $wins ($(format_percentage "$win_rate"))"
        add_to_report "  Losses:             $losses"

        if (( $(echo "$total_pnl > 0" | bc -l) )); then
            add_to_report "  Total P&L:          ${GREEN}+$(format_currency "$total_pnl") (+$(format_percentage "$total_pnl_pct"))${NC}" "$GREEN"
        else
            add_to_report "  Total P&L:          ${RED}$(format_currency "$total_pnl") ($(format_percentage "$total_pnl_pct"))${NC}" "$RED"
        fi

        add_to_report "  Avg Hold:           $(printf "%.1f" "$avg_hold") days"
        add_to_report "  Avg Win:            +$(format_currency "$avg_win") (+$(format_percentage "$avg_win_pct"))"
        add_to_report "  Avg Loss:           $(format_currency "$avg_loss") ($(format_percentage "$avg_loss_pct"))"
        add_to_report "  Win/Loss Ratio:     $(printf "%.2f" "$wl_ratio")"
    fi

    # Current position
    if [ "$current_position" != "null" ]; then
        add_to_report ""
        print_subsection "Current Paper Position"

        local shares=$(echo "$current_position" | jq -r '.shares')
        local entry_price=$(echo "$current_position" | jq -r '.entry_price')
        local entry_date=$(echo "$current_position" | jq -r '.entry_date')
        local stop_loss=$(echo "$current_position" | jq -r '.stop_loss // "N/A"')
        local take_profit=$(echo "$current_position" | jq -r '.take_profit // "N/A"')

        add_to_report "  Shares:         $shares"
        add_to_report "  Entry Price:    $(format_currency "$entry_price")"
        add_to_report "  Entry Date:     $(format_date "$entry_date")"
        add_to_report "  Stop Loss:      $(format_currency "$stop_loss")"
        add_to_report "  Take Profit:    $(format_currency "$take_profit")"
    fi
}

generate_live_trading_history() {
    local events_json="$1"
    local live_position="$2"
    local price_data="$3"

    print_section "SECTION 4: LIVE TRADING HISTORY"

    local event_count=$(echo "$events_json" | jq 'length')

    if [ "$event_count" -eq 0 ]; then
        add_to_report "No live trading history found for this ticker." "$YELLOW"
        return
    fi

    # Display events chronologically
    echo "$events_json" | jq -c 'sort_by(.timestamp) | .[]' | while read -r event; do
        local timestamp=$(echo "$event" | jq -r '.timestamp')
        local event_type=$(echo "$event" | jq -r '.event_type')
        local details=$(echo "$event" | jq -r '.details // {}')

        add_to_report ""
        add_to_report "$(format_date "$timestamp") | $event_type" "$CYAN"

        case "$event_type" in
            "SIGNAL_RECEIVED")
                local score=$(echo "$details" | jq -r '.signal_score // "N/A"')
                local entry_price=$(echo "$details" | jq -r '.entry_price // "N/A"')
                add_to_report "  Signal Score: $score"
                add_to_report "  Entry Price: $(format_currency "$entry_price")"
                ;;
            "ORDER_SUBMITTED")
                local order_id=$(echo "$details" | jq -r '.order_id // "N/A"')
                local order_type=$(echo "$details" | jq -r '.order_type // "N/A"')
                local quantity=$(echo "$details" | jq -r '.quantity // "N/A"')
                local limit_price=$(echo "$details" | jq -r '.limit_price // "N/A"')
                add_to_report "  Order ID: $order_id"
                add_to_report "  Type: $order_type"
                add_to_report "  Quantity: $quantity shares"
                add_to_report "  Limit Price: $(format_currency "$limit_price")"
                ;;
            "ORDER_FILLED")
                local fill_price=$(echo "$details" | jq -r '.fill_price // "N/A"')
                local fill_qty=$(echo "$details" | jq -r '.fill_quantity // "N/A"')
                local slippage=$(echo "$details" | jq -r '.slippage // "N/A"')
                local total_cost=$(echo "$details" | jq -r '.total_cost // "N/A"')
                add_to_report "  Fill Price: $(format_currency "$fill_price")"
                add_to_report "  Fill Quantity: $fill_qty shares"
                add_to_report "  Total Cost: $(format_currency "$total_cost")"
                if [ "$slippage" != "N/A" ]; then
                    add_to_report "  Slippage: $(format_currency "$slippage")"
                fi
                ;;
            "POSITION_OPENED")
                local entry_price=$(echo "$details" | jq -r '.entry_price // "N/A"')
                local shares=$(echo "$details" | jq -r '.shares // "N/A"')
                local stop_loss=$(echo "$details" | jq -r '.stop_loss // "N/A"')
                local take_profit=$(echo "$details" | jq -r '.take_profit // "N/A"')
                add_to_report "  Entry Price: $(format_currency "$entry_price")"
                add_to_report "  Shares: $shares"
                add_to_report "  Stop Loss: $(format_currency "$stop_loss")"
                add_to_report "  Take Profit: $(format_currency "$take_profit")"
                ;;
            "POSITION_CLOSED")
                local exit_price=$(echo "$details" | jq -r '.exit_price // "N/A"')
                local pnl=$(echo "$details" | jq -r '.pnl // "N/A"')
                local reason=$(echo "$details" | jq -r '.reason // "N/A"')
                add_to_report "  Exit Price: $(format_currency "$exit_price")"
                if (( $(echo "$pnl > 0" | bc -l) 2>/dev/null )); then
                    add_to_report "  P&L: ${GREEN}+$(format_currency "$pnl")${NC}" "$GREEN"
                else
                    add_to_report "  P&L: ${RED}$(format_currency "$pnl")${NC}" "$RED"
                fi
                add_to_report "  Reason: $reason"
                ;;
        esac
    done

    # Current position
    if [ "$live_position" != "null" ]; then
        add_to_report ""
        print_subsection "Current Live Position"

        local shares=$(echo "$live_position" | jq -r '.shares')
        local entry_price=$(echo "$live_position" | jq -r '.entry_price')
        local entry_date=$(echo "$live_position" | jq -r '.entry_date')
        local stop_loss=$(echo "$live_position" | jq -r '.stop_loss // "N/A"')
        local take_profit=$(echo "$live_position" | jq -r '.take_profit // "N/A"')
        local current_price=$(echo "$price_data" | jq -r '.current_price // 0')

        add_to_report "  Shares:         $shares"
        add_to_report "  Entry Price:    $(format_currency "$entry_price")"
        add_to_report "  Entry Date:     $(format_date "$entry_date")"
        add_to_report "  Current Price:  $(format_currency "$current_price")"

        # Calculate unrealized P&L
        if [ "$current_price" != "0" ] && [ "$current_price" != "null" ]; then
            local cost=$(echo "$shares * $entry_price" | bc)
            local value=$(echo "$shares * $current_price" | bc)
            local unrealized_pnl=$(echo "$value - $cost" | bc)
            local unrealized_pct=$(calc_percentage "$entry_price" "$current_price")

            if (( $(echo "$unrealized_pnl > 0" | bc -l) )); then
                add_to_report "  Unrealized P&L: ${GREEN}+$(format_currency "$unrealized_pnl") (+$(format_percentage "$unrealized_pct"))${NC}" "$GREEN"
            else
                add_to_report "  Unrealized P&L: ${RED}$(format_currency "$unrealized_pnl") ($(format_percentage "$unrealized_pct"))${NC}" "$RED"
            fi
        fi

        add_to_report "  Stop Loss:      $(format_currency "$stop_loss")"
        add_to_report "  Take Profit:    $(format_currency "$take_profit")"
    fi

    # Summary
    add_to_report ""
    print_subsection "Live Trading Summary"

    local positions_opened=$(echo "$events_json" | jq '[.[] | select(.event_type == "POSITION_OPENED")] | length')
    local positions_closed=$(echo "$events_json" | jq '[.[] | select(.event_type == "POSITION_CLOSED")] | length')
    local active_positions=$((positions_opened - positions_closed))

    add_to_report "  Positions Opened:   $positions_opened"
    add_to_report "  Positions Closed:   $positions_closed"
    add_to_report "  Active Positions:   $active_positions"
}

generate_price_analysis() {
    local ticker="$1"
    local price_data="$2"
    local signals_json="$3"

    print_section "SECTION 5: PRICE ANALYSIS"

    local success=$(echo "$price_data" | jq -r '.success')

    if [ "$success" != "true" ]; then
        add_to_report "Failed to fetch price data." "$RED"
        return
    fi

    local current_price=$(echo "$price_data" | jq -r '.current_price // 0')
    local high_30d=$(echo "$price_data" | jq -r '.high_30d // 0')
    local low_30d=$(echo "$price_data" | jq -r '.low_30d // 0')
    local avg_volume=$(echo "$price_data" | jq -r '.avg_volume // 0')
    local sma_5=$(echo "$price_data" | jq -r '.sma_5 // 0')
    local sma_20=$(echo "$price_data" | jq -r '.sma_20 // 0')

    print_subsection "Current Market Data (as of $(date '+%Y-%m-%d %H:%M'))"

    add_to_report "  Current Price:      $(format_currency "$current_price")"
    add_to_report ""

    add_to_report "30-Day Statistics:" "$WHITE"
    add_to_report "  High:               $(format_currency "$high_30d")"
    add_to_report "  Low:                $(format_currency "$low_30d")"
    add_to_report "  Avg Volume:         $(printf "%.0f" "$avg_volume") shares/day"
    add_to_report ""

    add_to_report "Technical Indicators:" "$WHITE"
    add_to_report "  5-day SMA:          $(format_currency "$sma_5")"
    if [ "$sma_20" != "0" ] && [ "$sma_20" != "null" ]; then
        add_to_report "  20-day SMA:         $(format_currency "$sma_20")"
    fi

    # Compare to SMAs
    if [ "$sma_5" != "0" ]; then
        local vs_sma5=$(calc_percentage "$sma_5" "$current_price")
        if (( $(echo "$current_price > $sma_5" | bc -l) )); then
            add_to_report "  vs 5-day SMA:       ${GREEN}+$(format_percentage "$vs_sma5") (above)${NC}" "$GREEN"
        else
            add_to_report "  vs 5-day SMA:       ${RED}$(format_percentage "$vs_sma5") (below)${NC}" "$RED"
        fi
    fi

    if [ "$sma_20" != "0" ] && [ "$sma_20" != "null" ]; then
        local vs_sma20=$(calc_percentage "$sma_20" "$current_price")
        if (( $(echo "$current_price > $sma_20" | bc -l) )); then
            add_to_report "  vs 20-day SMA:      ${GREEN}+$(format_percentage "$vs_sma20") (above)${NC}" "$GREEN"
        else
            add_to_report "  vs 20-day SMA:      ${RED}$(format_percentage "$vs_sma20") (below)${NC}" "$RED"
        fi
    fi

    # Entry vs Current Analysis
    if [ "$(echo "$signals_json" | jq 'length')" -gt 0 ]; then
        add_to_report ""
        print_subsection "Entry vs Current Analysis"

        local first_signal=$(echo "$signals_json" | jq -r '.[0]')
        local first_date=$(echo "$first_signal" | jq -r '.date')
        # Note: We don't have entry price in signal history, so we'll skip this for now
        add_to_report "  First Signal:       $first_date"
        add_to_report "  Current Price:      $(format_currency "$current_price")"
    fi
}

generate_recommendations() {
    local ticker="$1"
    local paper_summary_json="$2"
    local live_position="$3"
    local price_data="$4"

    print_section "SECTION 6: LESSONS & RECOMMENDATIONS"

    # Analyze what went right
    print_subsection "What Went Right"

    local wins=$(echo "$paper_summary_json" | jq -r '.wins // 0')
    if [ "$wins" -gt 0 ]; then
        add_to_report "  ${GREEN}✅ Signal detection identified trading opportunities${NC}" "$GREEN"
        add_to_report "  ${GREEN}✅ Paper trading captured profitable trades${NC}" "$GREEN"
    fi

    if [ "$live_position" != "null" ]; then
        add_to_report "  ${GREEN}✅ Live trading position successfully opened${NC}" "$GREEN"
    fi

    # Analyze what went wrong
    add_to_report ""
    print_subsection "What Went Wrong"

    local losses=$(echo "$paper_summary_json" | jq -r '.losses // 0')
    if [ "$losses" -gt 0 ]; then
        add_to_report "  ${RED}❌ Some positions resulted in losses${NC}" "$RED"
    fi

    local win_rate=$(echo "$paper_summary_json" | jq -r '.win_rate // 0')
    if (( $(echo "$win_rate < 50" | bc -l) )); then
        add_to_report "  ${RED}❌ Win rate below 50% ($(format_percentage "$win_rate"))${NC}" "$RED"
    fi

    # Recommendations
    add_to_report ""
    print_subsection "Recommendations"

    if [ "$live_position" != "null" ]; then
        add_to_report "  ${BLUE}💡 Monitor live position closely${NC}" "$BLUE"
        add_to_report "  ${BLUE}💡 Consider adjusting stops if position moves favorably${NC}" "$BLUE"
    fi

    if [ "$losses" -gt 0 ]; then
        add_to_report "  ${BLUE}💡 Review entry criteria to avoid unfavorable entries${NC}" "$BLUE"
        add_to_report "  ${BLUE}💡 Consider implementing cooldown period between trades${NC}" "$BLUE"
    fi

    # Risk flags
    add_to_report ""
    print_subsection "Risk Flags"

    local current_price=$(echo "$price_data" | jq -r '.current_price // 0')
    local sma_20=$(echo "$price_data" | jq -r '.sma_20 // 0')

    if [ "$current_price" != "0" ] && [ "$sma_20" != "0" ] && (( $(echo "$current_price < $sma_20" | bc -l) )); then
        add_to_report "  ${YELLOW}⚠️  Current price below 20-day SMA (potential weakness)${NC}" "$YELLOW"
    fi

    if [ "$win_rate" != "0" ] && (( $(echo "$win_rate < 50" | bc -l) )); then
        add_to_report "  ${YELLOW}⚠️  Win rate below 50% in paper trading${NC}" "$YELLOW"
    fi

    # Next steps
    add_to_report ""
    print_subsection "Next Steps"

    if [ "$live_position" != "null" ]; then
        local stop_loss=$(echo "$live_position" | jq -r '.stop_loss')
        add_to_report "  1. Monitor live position for stop loss trigger at $(format_currency "$stop_loss")"
        add_to_report "  2. Watch for additional insider activity"
        add_to_report "  3. Review position sizing if volatility increases"
    else
        add_to_report "  1. Wait for new signals to generate"
        add_to_report "  2. Monitor market conditions"
        add_to_report "  3. Review filter criteria if needed"
    fi
}

generate_raw_data() {
    local ticker="$1"

    print_section "SECTION 7: RAW DATA"

    add_to_report "Signal History:"
    if file_exists "$SIGNALS_HISTORY"; then
        local raw_signals=$(grep -i "$ticker" "$SIGNALS_HISTORY" 2>/dev/null || echo "")
        if [ -n "$raw_signals" ]; then
            add_to_report "$raw_signals"
        else
            add_to_report "  No data"
        fi
    else
        add_to_report "  File not found"
    fi

    add_to_report ""
    add_to_report "Paper Trades:"
    if file_exists "$PAPER_TRADES"; then
        local raw_trades=$(grep -i "$ticker" "$PAPER_TRADES" 2>/dev/null || echo "")
        if [ -n "$raw_trades" ]; then
            add_to_report "$raw_trades"
        else
            add_to_report "  No data"
        fi
    else
        add_to_report "  File not found"
    fi

    add_to_report ""
    add_to_report "Live Audit Log:"
    if file_exists "$AUDIT_LOG"; then
        local raw_audit=$(grep -i "$ticker" "$AUDIT_LOG" 2>/dev/null | head -20 || echo "")
        if [ -n "$raw_audit" ]; then
            add_to_report "$raw_audit"
        else
            add_to_report "  No data"
        fi
    else
        add_to_report "  File not found"
    fi
}

################################################################################
# OUTPUT HANDLING
################################################################################

save_report_to_file() {
    local ticker="$1"
    local timestamp=$(date "+%Y%m%d_%H%M%S")
    local filename="${AUDIT_REPORTS_DIR}/${ticker}_${timestamp}.txt"

    # Create directory if it doesn't exist
    mkdir -p "$AUDIT_REPORTS_DIR"

    # Write report content to file
    echo "$REPORT_CONTENT" > "$filename"

    echo ""
    print_color "$GREEN" "Report saved to: $filename"
}

################################################################################
# MAIN EXECUTION
################################################################################

main() {
    # Display header
    echo ""
    print_color "$CYAN" "========================================"
    print_color "$CYAN" "INSIDER CLUSTER WATCH - AUDIT TOOL"
    print_color "$CYAN" "========================================"
    echo ""

    # Interactive prompts
    prompt_ticker
    prompt_scope
    prompt_date_range
    prompt_output_format
    prompt_detail_level

    echo ""
    echo "Generating comprehensive audit for $TICKER..."
    if [ -n "$START_DATE" ]; then
        echo "Date range: $START_DATE to $END_DATE"
    fi
    if [ "$OUTPUT_FORMAT" = "file" ] || [ "$OUTPUT_FORMAT" = "both" ]; then
        echo "Output: Saving to audit_reports/${TICKER}_*.txt"
    fi
    echo ""

    # Disable color for file output
    if [ "$OUTPUT_FORMAT" = "file" ]; then
        USE_COLOR=false
    fi

    # Data collection
    echo "Collecting data..."

    local signals_json=$(collect_signal_history "$TICKER")
    local signal_count=$(echo "$signals_json" | jq 'length')

    local approved_signal=$(collect_approved_signals "$TICKER")

    local paper_trades_json=$(collect_paper_trades "$TICKER")
    local paper_positions_json=$(analyze_paper_positions "$paper_trades_json")
    local paper_summary_json=$(calculate_paper_summary "$paper_positions_json")

    local current_paper_position=$(collect_paper_portfolio "$TICKER")

    local live_events_json=$(collect_live_audit_log "$TICKER")
    local live_position=$(collect_live_positions "$TICKER")

    local pending_orders=$(collect_pending_orders "$TICKER")
    local queued_signals=$(collect_queued_signals "$TICKER")

    local price_data=$(collect_price_data "$TICKER")

    echo "Generating report..."

    # Generate report sections
    generate_header "$TICKER"

    if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "signals" ] || [ "$SCOPE" = "recent" ]; then
        generate_executive_summary "$TICKER" "$signal_count" "$paper_trades_json" "$paper_positions_json" "$paper_summary_json" "$live_events_json" "$live_position" "$current_paper_position"
    fi

    if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "signals" ] || [ "$SCOPE" = "recent" ]; then
        generate_signal_timeline "$signals_json" "$approved_signal"
    fi

    if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "paper" ] || [ "$SCOPE" = "recent" ]; then
        generate_paper_trading_history "$paper_positions_json" "$paper_summary_json" "$current_paper_position"
    fi

    if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "live" ] || [ "$SCOPE" = "recent" ]; then
        generate_live_trading_history "$live_events_json" "$live_position" "$price_data"
    fi

    if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "recent" ]; then
        generate_price_analysis "$TICKER" "$price_data" "$signals_json"
    fi

    if [ "$DETAIL_LEVEL" = "standard" ] || [ "$DETAIL_LEVEL" = "verbose" ]; then
        if [ "$SCOPE" = "all" ] || [ "$SCOPE" = "recent" ]; then
            generate_recommendations "$TICKER" "$paper_summary_json" "$live_position" "$price_data"
        fi
    fi

    if [ "$DETAIL_LEVEL" = "verbose" ]; then
        generate_raw_data "$TICKER"
    fi

    # Save to file if requested
    if [ "$OUTPUT_FORMAT" = "file" ] || [ "$OUTPUT_FORMAT" = "both" ]; then
        save_report_to_file "$TICKER"
    fi

    echo ""
    print_color "$GREEN" "Audit complete!"
    echo ""
}

# Run main function
main
