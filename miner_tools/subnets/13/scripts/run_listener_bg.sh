#!/bin/bash
#
# SN13 Listener - Background Launch Script
#
# Usage: cd subnet13 && ./scripts/run_listener_bg.sh [wallet_name]
# Default: sn13miner
#
# Runs listener in background, logs to files
# Output: subnet13/listener.log
# PID saved to: subnet13/listener.pid

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

WALLET_NAME="${1:-sn13miner}"
LOG_FILE="$PROJECT_DIR/listener.log"
PID_FILE="$PROJECT_DIR/listener.pid"

# Activate venv relative to project root
if [ -d "$PROJECT_DIR/.venv" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
fi

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Listener already running with PID $OLD_PID"
        exit 1
    fi
    rm "$PID_FILE"
fi

cd "$PROJECT_DIR"

nohup "$PROJECT_DIR/.venv/bin/python" subnet13/listener/listener.py --wallet "$WALLET_NAME" > "$LOG_FILE" 2>&1 &
PID=$!

echo "$PID" > "$PID_FILE"

echo "Started listener with PID $PID"
echo "Log file: $LOG_FILE"