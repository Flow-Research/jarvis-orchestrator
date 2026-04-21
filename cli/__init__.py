#!/usr/bin/env python3
"""
Jarvis-Miner CLI

Entry point that disables bittensor automatic CLI.
"""

# Disable bittensor's automatic CLI before importing anything else
import os

os.environ["BT_CLI_NO_AUTO"] = "1"

from cli.main import cli

if __name__ == "__main__":
    import sys

    sys.exit(cli())
