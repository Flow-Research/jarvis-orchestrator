#!/bin/bash
#
# Stop SN13 Listener

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$PROJECT_DIR/listener.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "Stopped listener PID $PID"
    fi
    rm "$PID_FILE"
else
    echo "No listener running"
fi