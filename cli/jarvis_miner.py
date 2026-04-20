#!/usr/bin/env python3
"""
Jarvis-Miner — Entry point

Usage:
    jarvis-miner miner start --subnet 13 --network testnet
    jarvis-miner miner stop --subnet 13
    jarvis-miner wallet info
    jarvis-miner config show --network testnet
"""

from cli import cli

if __name__ == "__main__":
    cli()
