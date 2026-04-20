#!/bin/bash
#
# SN13 Listener - Production Launch Script
# 
# Usage: ./scripts/run_listener.sh [wallet_name]
# Default wallet: default
#
# This runs the listener which:
# - Connects to SN13 testnet
# - Listens for validator queries
# - Logs every query to files
#
# Query logs saved to: listener/captures/

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Get wallet name (default: sn13miner)
WALLET_NAME="${1:-sn13miner}"

echo -e "${GREEN}==============================================${NC}"
echo -e "${GREEN}  SN13 Listener - Production Runner${NC}"
echo -e "${GREEN}==============================================${NC}"
echo ""
echo -e "Wallet: ${YELLOW}$WALLET_NAME${NC}"
echo -e "Network: ${YELLOW}test (testnet)${NC}"
echo -e "Subnet: ${YELLOW}13${NC}"
echo ""

# Activate virtual environment
cd "$PROJECT_DIR"
if [ -d "$PROJECT_DIR/.venv" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
else
    echo -e "${RED}Error: .venv not found${NC}"
    exit 1
fi

# Check wallet exists
echo -e "${GREEN}Checking wallet...${NC}"
python -c "import bittensor as bt; w = bt.Wallet(name='$WALLET_NAME'); print(f'Wallet: {w.name}'); print(f'Hotkey: {w.hotkey_str}')"

# Run the listener
echo ""
echo -e "${GREEN}Starting listener...${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
echo ""

exec python subnet13/listener/listener.py --wallet "$WALLET_NAME"