#!/bin/bash
#
# SN13 Listener - Daily Query Log
#
# Reads captures and creates human-readable daily summary
# Output: logs/queries_YYYY-MM-DD.txt

CAPTURES_DIR="listener/captures"
LOG_DIR="logs"

mkdir -p "$LOG_DIR"

TODAY=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/queries_$TODAY.txt"

echo "SN13 Query Log - $TODAY" > "$LOG_FILE"
echo "======================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Check each capture
if [ -d "$CAPTURES_DIR" ]; then
    for date_dir in "$CAPTURES_DIR"/*/; do
        [ -d "$date_dir" ] || continue
        DIR_DATE=$(basename "$date_dir")
        
        for file in "$date_dir"*.json; do
            [ -f "$file" ] || continue
            
            # Read JSON and format
            TIMESTAMP=$(jq -r '.timestamp' "$file" 2>/dev/null)
            QUERY_TYPE=$(jq -r '.query_type' "$file" 2>/dev/null)
            VALIDATOR=$(jq -r '.validator_hotkey[:20]' "$file" 2>/dev/null)
            
            echo "[$TIMESTAMP] $QUERY_TYPE (validator: $VALIDATOR...)" >> "$LOG_FILE"
        done
    done
fi

# Show result
if [ -f "$LOG_FILE" ]; then
    LINES=$(wc -l < "$LOG_FILE")
    if [ "$LINES" -gt 3 ]; then
        cat "$LOG_FILE"
    else
        echo "No queries logged yet"
    fi
else
    echo "No queries logged yet"
fi