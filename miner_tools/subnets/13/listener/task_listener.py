"""
Task Listener Miner - Tests receiving queries from validators.

This is a SIMPLE miner that:
1. Registers on a subnet
2. Listens for validator queries
3. Logs what tasks come in (for analysis)
4. Returns mock data (no actual scraping)

Use this to understand what validators send to miners.
"""

import asyncio
import copy
import time
import bittensor as bt
from typing import Dict, Any

try:
    from listener.sn13_decomposition import DEFAULT_TESTNET, SN13_NETUID
except ModuleNotFoundError:
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from listener.sn13_decomposition import DEFAULT_TESTNET, SN13_NETUID


class TaskListenerMiner:
    """A simple miner that logs all incoming validator queries."""

    def __init__(
        self,
        netuid: int = SN13_NETUID,
        wallet_name: str = "sn13miner",
        network: str = DEFAULT_TESTNET,
    ):
        self.netuid = netuid
        self.wallet_name = wallet_name
        self.network = network

    async def start(self):
        """Start the miner and listen for queries."""

        # Setup wallet
        self.wallet = bt.Wallet(name=self.wallet_name)
        print(f"Wallet: {self.wallet.hotkeypub.ss58_address}")

        # Connect to subtensor
        self.subtensor = bt.Subtensor(network=self.network)
        print(f"Connected to subtensor network: {self.network}")

        # Check if registered, if not register
        metagraph = self.subtensor.metagraph(self.netuid)

        if self.wallet.hotkeypub.ss58_address not in metagraph.hotkeys:
            print(f"Not registered on subnet {self.netuid}, registering...")
            # Register would need TAO - for now we'll run in offline/mock mode
            print("Cannot register - need TAO. Running in MOCK mode.")
            self.uid = 999  # Mock UID
        else:
            self.uid = metagraph.hotkeys.index(self.wallet.hotkeypub.ss58_address)
            print(f"Registered with UID: {self.uid}")

        # Setup axon (this handles incoming validator requests)
        self.axon = bt.Axon(wallet=self.wallet, port=8091, ip="127.0.0.1")

        # Attach our handler functions
        print("\n=== Registering Query Handlers ===")

        # This is a simplified version - the actual miner has these 3 endpoints:
        # 1. get_index - "What data do you have?"
        # 2. get_data_entity_bucket - "Give me specific data"
        # 3. get_contents_by_buckets - "Verify data"

        self.axon.attach(
            forward_fn=self.handle_get_index,
            blacklist_fn=self.handle_blacklist,
            priority_fn=self.handle_priority,
        )
        self.axon.attach(
            forward_fn=self.handle_get_data_entity_bucket,
            blacklist_fn=self.handle_blacklist,
            priority_fn=self.handle_priority,
        )
        self.axon.attach(
            forward_fn=self.handle_get_contents,
            blacklist_fn=self.handle_blacklist,
            priority_fn=self.handle_priority,
        )

        try:
            self.axon.serve(netuid=self.netuid, subtensor=self.subtensor)
            print(f"Served axon to subnet {self.netuid} on {self.network}")
        except Exception as e:
            print(f"Could not serve axon on subnet {self.netuid}: {e}")

        # Start serving
        self.axon.start()
        print(f"\n=== Miner listening on port 8091 ===")
        print(f"NetUID: {self.netuid}")
        print(f"Network: {self.network}")
        print(f"Waiting for validator queries...\n")

        # Keep running
        while True:
            await asyncio.sleep(10)

    async def handle_get_index(self, synapse: bt.Synapse) -> bt.Synapse:
        """
        Validator asks: "What data do you have?"

        This is the FIRST query validators make to understand
        what data each miner has available.
        """
        print("\n" + "=" * 60)
        print("📥 QUERY TYPE: GetMinerIndex")
        print("=" * 60)
        print("Validator asks: 'What data do you have?'")
        print(f"  From: {synapse.dendrite.hotkey if hasattr(synapse, 'dendrite') else 'unknown'}")
        print(f"  Dendrite: {synapse.dendrite if hasattr(synapse, 'dendrite') else 'N/A'}")

        # Log full synapse structure
        print(f"\n  Synapse attributes:")
        for attr in dir(synapse):
            if not attr.startswith("_"):
                try:
                    val = getattr(synapse, attr)
                    if not callable(val):
                        print(f"    {attr}: {val}")
                except:
                    pass

        print("=" * 60 + "\n")

        # Return empty/minimal response for mock
        return synapse

    async def handle_get_data_entity_bucket(self, synapse: bt.Synapse) -> bt.Synapse:
        """
        Validator asks: "Give me data from bucket X"

        This is the SECOND query - validator wants specific data.
        The bucket_id tells us what data they want.
        """
        print("\n" + "=" * 60)
        print("📥 QUERY TYPE: GetDataEntityBucket")
        print("=" * 60)
        print("Validator asks: 'Give me specific data'")

        # Extract bucket info
        if hasattr(synapse, "data_entity_bucket_id"):
            bucket_id = synapse.data_entity_bucket_id
            print(f"  Bucket ID: {bucket_id}")

            # For SN13, bucket_id is (source, time_bucket, label)
            # Example: (DataSource.X, 1845, "$BTC")

        print("=" * 60 + "\n")
        return synapse

    async def handle_get_contents(self, synapse: bt.Synapse) -> bt.Synapse:
        """
        Validator asks: "Verify this data is real"

        This is the THIRD query - validator checks data quality.
        """
        print("\n" + "=" * 60)
        print("📥 QUERY TYPE: GetContentsByBuckets")
        print("=" * 60)
        print("Validator asks: 'Verify this data is real'")
        print("=" * 60 + "\n")
        return synapse

    async def handle_blacklist(self, synapse: bt.Synapse):
        """Check if validator should be allowed."""
        # Allow all validators
        return (False, "Allow all")

    async def handle_priority(self, synapse: bt.Synapse) -> float:
        """Priority score for this request."""
        return 1.0


async def main():
    """Run the task listener."""
    import argparse

    parser = argparse.ArgumentParser(description="Task Listener Miner")
    parser.add_argument("--netuid", type=int, default=SN13_NETUID, help="Subnet ID")
    parser.add_argument("--wallet", type=str, default="sn13miner", help="Wallet name")
    parser.add_argument("--network", type=str, default=DEFAULT_TESTNET, help="Subtensor network")
    args = parser.parse_args()

    miner = TaskListenerMiner(
        netuid=args.netuid,
        wallet_name=args.wallet,
        network=args.network,
    )
    await miner.start()


if __name__ == "__main__":
    asyncio.run(main())
