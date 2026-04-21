#!/usr/bin/env python3
"""
SN13 Monitor - Watch testnet activity

Usage:
    python monitor.py --watch    # Watch for queries
    python monitor.py --stats     # Show network stats
    python monitor.py --wallet # Show our wallet status
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import bittensor as bt
def watch_queries():
    """Watch for incoming queries."""
    import time

    capture_dir = Path(__file__).parent / "listener" / "captures"

    print("Watching for validator queries...")
    print("Press Ctrl+C to stop\n")

    while True:
        events_file = capture_dir / "queries.jsonl"
        if events_file.exists():
            with open(events_file) as f:
                lines = f.readlines()
            if lines:
                print(f"\n📩 {len(lines)} total queries captured")
                for line in lines[-5:]:
                    import json

                    try:
                        q = json.loads(line)
                        print(f"  - {q.get('query_type')}: {q.get('timestamp')}")
                    except:
                        pass
        else:
            print("No queries yet - waiting...")

        time.sleep(10)


def show_network_stats():
    """Show SN13 testnet statistics."""
    subtensor = bt.Subtensor(network="test")
    meta = subtensor.metagraph(13)

    print("=== SN13 Testnet Stats ===")
    print(f"Total miners: {len(meta.hotkeys)}")
    print(f"Max slots: {meta.n}")
    print(f"\nTop 5 validators by stake:")

    stakes = list(enumerate(meta.stake))
    stakes.sort(key=lambda x: float(x[1]), reverse=True)

    for uid, stake in stakes[:5]:
        print(f"  UID {uid}: {float(stake):.2f} TAO")


def show_wallet_status():
    """Show our wallet status on the network."""
    subtensor = bt.Subtensor(network="test")
    meta = subtensor.metagraph(13)
    wallet = bt.Wallet(name="sn13miner")
    hotkey = wallet.hotkeypub.ss58_address

    print("=== Our Wallet ===")
    print(f"Hotkey: {hotkey}")

    if hotkey in meta.hotkeys:
        uid = meta.hotkeys.index(hotkey)
        print(f"UID: {uid}")
        print(f"Stake: {float(meta.stake[uid]):.4f} TAO")
    else:
        print("Status: NOT REGISTERED")
        print(f"Miners: {len(meta.hotkeys)}/256")


def main():
    parser = argparse.ArgumentParser(description="SN13 Monitor")
    parser.add_argument("--watch", action="store_true", help="Watch for queries")
    parser.add_argument("--stats", action="store_true", help="Show network stats")
    parser.add_argument("--wallet", action="store_true", help="Show wallet status")

    args = parser.parse_args()

    if args.watch:
        watch_queries()
    elif args.stats:
        show_network_stats()
    elif args.wallet:
        show_wallet_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
