#!/usr/bin/env python3
"""
SN13-style Task Listener - Actual Working Version

This is a REAL working miner that:
1. Connects to SN13 on subtensor testnet
2. Listens for validator queries
3. Logs every query type with full details
4. Returns mock data (no real scraping)

Run this to see REAL queries come in from validators.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Tuple

import bittensor as bt
import sys
from pathlib import Path

# Add current dir to path for imports
_listener_dir = Path(__file__).parent
if str(_listener_dir) not in sys.path:
    sys.path.insert(0, str(_listener_dir))

from protocol_observer import ProtocolObserver
from sn13_decomposition import (
    DEFAULT_TESTNET,
    SN13_NETUID,
    decompose_bucket_request,
    normalize_bucket_request,
)


@dataclass
class QueryLog:
    """Record of a received query."""

    timestamp: str
    query_type: str
    validator: str
    payload: Dict[str, Any]
    response: Dict[str, Any]


class TaskListener:
    """A working miner that logs all validator queries."""

    def __init__(
        self,
        netuid: int = SN13_NETUID,
        wallet_name: str = "sn13miner",
        network: str = DEFAULT_TESTNET,
        capture_dir: str | Path = "listener/captures",
    ):
        self.netuid = netuid
        self.wallet_name = wallet_name
        self.network = network
        self.query_logs: List[QueryLog] = []
        self.running = True
        self.observer = ProtocolObserver(capture_dir=capture_dir)
        self.capture_dir = Path(capture_dir)

    async def start(self):
        """Start the listener."""
        print("\n" + "=" * 70)
        print("🚀 STARTING TASK LISTENER")
        print("=" * 70)

        # Setup wallet
        self.wallet = bt.Wallet(name=self.wallet_name)

        # Check if hotkey exists, if not create one
        try:
            hotkey_file = os.path.expanduser(
                f"~/.bittensor/wallets/{self.wallet_name}/hotkeys/default"
            )
            if not os.path.exists(hotkey_file):
                print(f"Creating new hotkey...")
                self.wallet.create_new_hotkey(
                    n_words=12, use_password=True, hotkey_password="testminer123", suppress=True
                )
        except Exception as e:
            print(f"Note: {e}")

        print(f"Wallet: {self.wallet.hotkeypub.ss58_address}")

        # Connect to the target subtensor network.
        try:
            self.subtensor = bt.Subtensor(network=self.network)
            print(f"Connected to subtensor network: {self.network}")
        except Exception as e:
            print(f"Failed to connect: {e}")
            return

        # Get metagraph
        try:
            self.metagraph = self.subtensor.metagraph(self.netuid)
            print(f"Subnet {self.netuid}: {len(self.metagraph.hotkeys)} miners")
        except Exception as e:
            print(f"Could not get metagraph: {e}")
            self.metagraph = None

        # Create axon for receiving queries
        self.axon = bt.Axon(wallet=self.wallet, port=8091, ip="127.0.0.1")

        # Attach handlers for different query types
        # These are the standard SN13 protocol handlers

        # Handler 1: GetMinerIndex
        self.axon.attach(
            forward_fn=self.handle_get_index,
            blacklist_fn=self.default_blacklist,
            priority_fn=self.default_priority,
        )

        # Handler 2: GetDataEntityBucket
        self.axon.attach(
            forward_fn=self.handle_get_data_entity_bucket,
            blacklist_fn=self.default_blacklist,
            priority_fn=self.default_priority,
        )

        # Handler 3: GetContentsByBuckets
        self.axon.attach(
            forward_fn=self.handle_get_contents,
            blacklist_fn=self.default_blacklist,
            priority_fn=self.default_priority,
        )

        # Announce the axon on-chain so validators can discover and query it.
        try:
            self.axon.serve(netuid=self.netuid, subtensor=self.subtensor)
            print(f"Served axon to subnet {self.netuid} on {self.network}")
        except Exception as e:
            print(f"Could not serve axon on subnet {self.netuid}: {e}")

        # Start the axon (begin listening)
        self.axon.start()

        print(f"\n" + "=" * 70)
        print("✅ LISTENER RUNNING")
        print("=" * 70)
        print(f"Listening on port: 8091")
        print(f"Subnet: {self.netuid}")
        print(f"Network: {self.network}")
        print(f"Wallet: {self.wallet.hotkeypub.ss58_address[:10]}...")
        print(f"Capture dir: {self.capture_dir}")
        print("\nWaiting for validator queries...")
        print("(Press Ctrl+C to stop)\n")

        # Print query stats periodically
        while self.running:
            await asyncio.sleep(10)
            self.print_stats()

    def print_stats(self):
        """Print query statistics."""
        if self.query_logs:
            print(f"\n📊 Received {len(self.query_logs)} queries so far...")
            # Group by type
            types = {}
            for log in self.query_logs:
                types[log.query_type] = types.get(log.query_type, 0) + 1
            for t, count in types.items():
                print(f"   {t}: {count}")
            print(f"   {self.observer.format_summary()}")

    async def handle_get_index(self, synapse: bt.Synapse) -> bt.Synapse:
        """
        Handle GetMinerIndex query.

        Validator asks: "What data do you have?"

        Response: List of all data buckets (source + time + label)
        """
        started = perf_counter()
        timestamp = datetime.now().isoformat()

        # Get validator info
        validator = "unknown"
        if hasattr(synapse, "dendrite") and synapse.dendrite:
            validator = getattr(synapse.dendrite, "hotkey", "unknown")

        # Build response (mock - no real data)
        response = {
            "compressed_index": {
                "buckets": [
                    {"source": "X", "time_bucket": 1845, "label": "$BTC", "count": 100},
                    {"source": "X", "time_bucket": 1845, "label": "$ETH", "count": 50},
                    {"source": "REDDIT", "time_bucket": 1845, "label": "bittensor", "count": 75},
                ],
                "total_bytes": 225000,
            }
        }

        # Log it
        log = QueryLog(
            timestamp=timestamp,
            query_type="GetMinerIndex",
            validator=str(validator)[:20],
            payload={},
            response=response,
        )
        self.query_logs.append(log)

        # Print it
        print("\n" + "=" * 60)
        print("📥 QUERY: GetMinerIndex")
        print("=" * 60)
        print(f"Timestamp: {timestamp}")
        print(f"Validator: {validator[:20]}...")
        print(f"Request: 'What data do you have?'")
        observation = self.observer.record(
            query_type="GetMinerIndex",
            synapse=synapse,
            response_payload=response,
            latency_ms=(perf_counter() - started) * 1000,
            notes=[
                "Index/discovery query observed.",
                "Likely should be served from local inventory, not workstream.",
            ],
        )
        print(f"Query ID: {observation.query_id}")
        print(f"Timeout: {observation.timeout_seconds}")
        print(f"Schema fields: {list(observation.payload_schema.get('fields', {}).keys())}")
        print(
            f"Captured to: {self.capture_dir / observation.timestamp[:10] / f'{observation.query_id}.json'}"
        )
        print(f"Response: {json.dumps(response, indent=2)[:200]}...")

        return synapse

    async def handle_get_data_entity_bucket(self, synapse: bt.Synapse) -> bt.Synapse:
        """
        Handle GetDataEntityBucket query.

        Validator asks: "Give me data from bucket X"

        Response: Actual data entities
        """
        started = perf_counter()
        timestamp = datetime.now().isoformat()

        # Get validator info
        validator = "unknown"
        if hasattr(synapse, "dendrite") and synapse.dendrite:
            validator = getattr(synapse.dendrite, "hotkey", "unknown")

        # Get bucket info from synapse
        bucket_id = {}
        if hasattr(synapse, "data_entity_bucket_id"):
            raw_bucket_id = synapse.data_entity_bucket_id
            if isinstance(raw_bucket_id, dict):
                bucket_id = raw_bucket_id
            elif hasattr(raw_bucket_id, "__dict__"):
                bucket_id = vars(raw_bucket_id)
            else:
                bucket_id = {"raw_bucket_id": str(raw_bucket_id)}

        bucket_request = normalize_bucket_request(bucket_id)
        operator_pool = self._operator_pool_for_source(bucket_request.source)
        decomposition_plan = decompose_bucket_request(
            bucket_request,
            operator_pool=operator_pool,
        )

        # Mock response
        response = {
            "data_entities": [
                {"content": "Mock post 1", "source": "X", "label": "$BTC"},
                {"content": "Mock post 2", "source": "X", "label": "$BTC"},
                {"content": "Mock post 3", "source": "X", "label": "$BTC"},
            ],
            "jarvis_plan": decomposition_plan.to_dict(),
        }

        # Log it
        log = QueryLog(
            timestamp=timestamp,
            query_type="GetDataEntityBucket",
            validator=str(validator)[:20],
            payload=bucket_id,
            response=response,
        )
        self.query_logs.append(log)

        # Print it
        print("\n" + "=" * 60)
        print("📥 QUERY: GetDataEntityBucket")
        print("=" * 60)
        print(f"Timestamp: {timestamp}")
        print(f"Validator: {validator[:20]}...")
        print(f"Bucket requested: {bucket_id}")
        print(
            f"Decomposition strategy: {decomposition_plan.strategy} "
            f"({len(decomposition_plan.tasks)} operator task(s))"
        )
        for task in decomposition_plan.tasks:
            print(
                "  "
                f"{task.operator_name} -> {task.operator_type} "
                f"offset={task.offset} limit={task.limit}"
            )
        observation = self.observer.record(
            query_type="GetDataEntityBucket",
            synapse=synapse,
            response_payload=response,
            latency_ms=(perf_counter() - started) * 1000,
            notes=[
                "Primary retrieval query.",
                "Candidate for pass-through versus decomposition decisioning.",
            ],
            extra={
                "normalized_bucket_request": {
                    "source": bucket_request.source,
                    "time_bucket_id": bucket_request.time_bucket_id,
                    "label": bucket_request.label,
                    "expected_count": bucket_request.expected_count,
                },
                "decomposition_plan": decomposition_plan.to_dict(),
            },
        )
        print(f"Query ID: {observation.query_id}")
        print(f"Timeout: {observation.timeout_seconds}")
        print(f"Payload schema fields: {list(observation.payload_schema.get('fields', {}).keys())}")
        print(
            "Captured to: "
            f"{self.capture_dir / observation.timestamp[:10] / f'{observation.query_id}.json'}"
        )
        print(f"Response: {json.dumps(response, indent=2)[:200]}...")

        return synapse

    async def handle_get_contents(self, synapse: bt.Synapse) -> bt.Synapse:
        """
        Handle GetContentsByBuckets query.

        Validator asks: "Verify this data is real"

        Response: Sample content for verification
        """
        started = perf_counter()
        timestamp = datetime.now().isoformat()

        # Get validator info
        validator = "unknown"
        if hasattr(synapse, "dendrite") and synapse.dendrite:
            validator = getattr(synapse.dendrite, "hotkey", "unknown")

        # Mock response
        response = {
            "contents": [
                {"content": "Sample 1", "verified": True},
                {"content": "Sample 2", "verified": True},
            ]
        }

        # Log it
        log = QueryLog(
            timestamp=timestamp,
            query_type="GetContentsByBuckets",
            validator=str(validator)[:20],
            payload={},
            response=response,
        )
        self.query_logs.append(log)

        # Print it
        print("\n" + "=" * 60)
        print("📥 QUERY: GetContentsByBuckets")
        print("=" * 60)
        print(f"Timestamp: {timestamp}")
        print(f"Validator: {validator[:20]}...")
        observation = self.observer.record(
            query_type="GetContentsByBuckets",
            synapse=synapse,
            response_payload=response,
            latency_ms=(perf_counter() - started) * 1000,
            notes=[
                "Verification query observed.",
                "Likely should be served from stored evidence, not fresh workstream execution.",
            ],
        )
        print(f"Request: 'Verify this data is real'")
        print(f"Query ID: {observation.query_id}")
        print(f"Timeout: {observation.timeout_seconds}")
        print(
            "Captured to: "
            f"{self.capture_dir / observation.timestamp[:10] / f'{observation.query_id}.json'}"
        )

        return synapse

    async def default_blacklist(self, synapse: bt.Synapse) -> Tuple[bool, str]:
        """Allow all requests."""
        return (False, "Allow all")

    async def default_priority(self, synapse: bt.Synapse) -> float:
        """Default priority."""
        return 1.0

    def _operator_pool_for_source(self, source: str) -> List[str]:
        if source == "REDDIT":
            return ["reddit_operator_1", "reddit_operator_2", "reddit_operator_3"]
        return ["x_operator_1", "x_operator_2", "x_operator_3"]

    def stop(self):
        """Stop the listener."""
        self.running = False
        print("\n\n🛑 Stopping listener...")
        if self.query_logs:
            print(f"\n📊 Final stats:")
            print(f"   Total queries: {len(self.query_logs)}")
            for log in self.query_logs:
                print(f"   - {log.query_type}: {log.timestamp}")


async def main():
    """Run the task listener."""
    import argparse

    parser = argparse.ArgumentParser(description="Task Listener")
    parser.add_argument("--netuid", type=int, default=SN13_NETUID, help="Subnet ID")
    parser.add_argument("--wallet", type=str, default="sn13miner", help="Wallet name")
    parser.add_argument("--network", type=str, default=DEFAULT_TESTNET, help="Subtensor network")
    parser.add_argument(
        "--capture-dir",
        type=str,
        default="listener/captures",
        help="Directory where protocol captures and summaries are written.",
    )
    args = parser.parse_args()

    listener = TaskListener(
        netuid=args.netuid,
        wallet_name=args.wallet,
        network=args.network,
        capture_dir=args.capture_dir,
    )

    try:
        await listener.start()
    except KeyboardInterrupt:
        listener.stop()


if __name__ == "__main__":
    asyncio.run(main())
