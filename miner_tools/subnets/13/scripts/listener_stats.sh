#!/bin/bash
#
# SN13 Listener - View Logs & Stats
#
# Usage: cd subnet13 && ./scripts/listener_stats.sh

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAPTURES_DIR="$PROJECT_DIR/subnet13/captures"
LOG_FILE="$PROJECT_DIR/listener.log"

echo "=============================================="
echo "  SN13 Listener - Stats & Logs"
echo "=============================================="
echo ""

# Listener status
if pgrep -f "subnet13/listener/listener.py" > /dev/null; then
    echo "✅ Listener: RUNNING"
else
    echo "❌ Listener: NOT RUNNING"
fi
echo ""

# Log file
if [ -f "$LOG_FILE" ]; then
    echo "--- Recent Log (last 20 lines) ---"
    tail -20 "$LOG_FILE"
    echo ""
fi

# Captures
echo "--- Captures ---"
if [ -d "$CAPTURES_DIR" ] && [ "$(ls -A $CAPTURES_DIR 2>/dev/null)" ]; then
    TOTAL_QUERIES=$(find "$CAPTURES_DIR" -name "*.json" 2>/dev/null | wc -l)
    echo "Total queries captured: $TOTAL_QUERIES"
    echo ""
    
    # By date
    echo "By date:"
    for d in "$CAPTURES_DIR"/*/; do
        if [ -d "$d" ]; then
            DATE=$(basename "$d")
            COUNT=$(ls "$d"*.json 2>/dev/null | wc -l)
            echo "  $DATE: $COUNT queries"
        fi
    done
    
    # Query types
    echo ""
    echo "Query types:"
    find "$CAPTURES_DIR" -name "*.json" -exec jq -r '.query_type' 2>/dev/null {} \; | sort | uniq -c | sort -rn | head -10
else
    echo "No captures yet (waiting for validator queries)"
fi

echo ""
echo "=============================================="

# Wallet info
echo ""
echo "--- Wallet ---"
source "$PROJECT_DIR/.venv/bin/activate"
python -c "import bittensor as bt; w = bt.Wallet(name='sn13miner'); print(f'Wallet: {w.name}'); print(f'Hotkey: {w.hotkey_str}')"