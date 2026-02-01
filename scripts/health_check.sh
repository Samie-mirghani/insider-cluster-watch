#!/bin/bash

# Navigate to project directory
cd ~/insider-cluster-watch

# Define paths and variables
LOG_DIR="$HOME/insider-cluster-watch/logs"
TODAY=$(date +%Y%m%d)
DAY_OF_WEEK=$(date +%u)  # 1=Monday, 7=Sunday
CURRENT_HOUR=$(date +%H | sed 's/^0*//;s/^$/0/')  # Remove leading zeros, handle 00 -> 0

# Health check log file
HEALTH_LOG="$LOG_DIR/health_$TODAY.log"

# Helper function to check log file freshness
check_log_freshness() {
    local logfile=$1
    local max_age_minutes=$2
    local job_name=$3

    if [ -f "$logfile" ]; then
        local file_time=$(stat -c %Y "$logfile" 2>/dev/null)
        local current_time=$(date +%s)
        local age_minutes=$(( (current_time - file_time) / 60 ))

        if [ $age_minutes -le $max_age_minutes ]; then
            echo "$(date): ✓ $job_name: Log updated $age_minutes min ago (OK)" | tee -a "$HEALTH_LOG"
            return 0
        else
            echo "$(date): ⚠ $job_name: Log is $age_minutes min old (expected < $max_age_minutes min)" | tee -a "$HEALTH_LOG"
            return 1
        fi
    else
        echo "$(date): ✗ $job_name: Log file not found" | tee -a "$HEALTH_LOG"
        return 1
    fi
}

# Start health check
echo "$(date): === TRADING SYSTEM HEALTH CHECK ===" | tee -a "$HEALTH_LOG"

# Check if it's a weekend (Saturday=6, Sunday=7)
if [ $DAY_OF_WEEK -ge 6 ]; then
    echo "$(date): Weekend - Trading jobs not scheduled" | tee -a "$HEALTH_LOG"
else
    # WEEKDAY - Check trading logs based on time

    # Morning execution check (if hour >= 15)
    if [ $CURRENT_HOUR -ge 15 ]; then
        check_log_freshness "$LOG_DIR/morning_$TODAY.log" 480 "Morning Execution"
    fi

    # Position monitoring check (if hour >= 14 AND hour <= 21)
    if [ $CURRENT_HOUR -ge 14 ] && [ $CURRENT_HOUR -le 21 ]; then
        check_log_freshness "$LOG_DIR/monitor_$TODAY.log" 10 "Position Monitoring"
    fi

    # EOD execution check (if hour >= 22)
    if [ $CURRENT_HOUR -ge 22 ]; then
        check_log_freshness "$LOG_DIR/eod_$TODAY.log" 180 "EOD Execution"
    fi

    # Git pull check (if hour >= 15)
    if [ $CURRENT_HOUR -ge 15 ]; then
        check_log_freshness "$LOG_DIR/git_pull.log" 480 "Git Pull"
    fi
fi

# ALWAYS CHECK - System health checks
# Disk usage check
DISK_USAGE=$(df -h ~ | awk 'NR==2 {print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 80 ]; then
    echo "$(date): ⚠ Disk usage: ${DISK_USAGE}% (Warning: > 80%)" | tee -a "$HEALTH_LOG"
else
    echo "$(date): ✓ Disk usage: ${DISK_USAGE}% (OK)" | tee -a "$HEALTH_LOG"
fi

# Log directory size check
LOG_SIZE_MB=$(du -sm "$LOG_DIR" 2>/dev/null | awk '{print $1}')
if [ $LOG_SIZE_MB -gt 500 ]; then
    echo "$(date): ⚠ Log directory size: ${LOG_SIZE_MB}MB (Warning: > 500MB)" | tee -a "$HEALTH_LOG"
else
    echo "$(date): ✓ Log directory size: ${LOG_SIZE_MB}MB (OK)" | tee -a "$HEALTH_LOG"
fi

# Virtual environment check
if [ -d "$HOME/insider-cluster-watch/venv" ]; then
    echo "$(date): ✓ Virtual environment exists" | tee -a "$HEALTH_LOG"
else
    echo "$(date): ✗ Virtual environment missing" | tee -a "$HEALTH_LOG"
fi

# .env file check
if [ -f "$HOME/insider-cluster-watch/automated_trading/.env" ]; then
    echo "$(date): ✓ .env configuration exists" | tee -a "$HEALTH_LOG"
else
    echo "$(date): ✗ .env configuration missing" | tee -a "$HEALTH_LOG"
fi

echo "$(date): === HEALTH CHECK COMPLETE ===" | tee -a "$HEALTH_LOG"
