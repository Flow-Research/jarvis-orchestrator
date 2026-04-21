#!/usr/bin/env python3
"""
SN13 listener and protocol-observation runtime.

This module connects to a Bittensor subnet, attaches SN13-style request
handlers, captures validator query shape, and serves data from canonical
SQLite storage. Response fields are bound through `protocol_adapter.py` to
match Macrocosm SN13 synapse names. Live validator capture is still required
before treating this listener as production-ready.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field

try:
    from .protocol_observer import ProtocolObserver
    from .sn13_decomposition import (
        DEFAULT_TESTNET,
        SN13_NETUID,
        decompose_bucket_request,
        normalize_bucket_request,
    )
    from .protocol_adapter import (
        bind_get_contents_by_buckets_response,
        bind_get_data_entity_bucket_response,
        bind_get_miner_index_response,
    )
    from ..models import DataSource
    from ..storage import create_storage
except ImportError:
    # Fallback for direct script execution.
    _listener_dir = Path(__file__).parent
    _repo_root = _listener_dir.parent.parent.parent
    if str(_repo_root) not in sys.path:
        sys.path.insert(0, str(_repo_root))

    from subnets.sn13.listener.protocol_observer import ProtocolObserver
    from subnets.sn13.listener.sn13_decomposition import (
        DEFAULT_TESTNET,
        SN13_NETUID,
        decompose_bucket_request,
        normalize_bucket_request,
    )
    from subnets.sn13.listener.protocol_adapter import (
        bind_get_contents_by_buckets_response,
        bind_get_data_entity_bucket_response,
        bind_get_miner_index_response,
    )
    from subnets.sn13.models import DataSource
    from subnets.sn13.storage import create_storage


@dataclass
class QueryLog:
    """Record of a received query."""

    timestamp: str
    query_type: str
    validator: str
    payload: Dict[str, Any]
    response: Dict[str, Any]


def get_bittensor():
    """Lazy-load bittensor so this script owns its CLI arguments."""
    return __import__("bittensor")


class TaskListener:
    """SN13 listener backed by canonical SQLite storage."""

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

        # Initialize canonical SQLite storage.
        db_path = Path(__file__).resolve().parent.parent / "data" / "sn13.sqlite3"
        self.storage = create_storage(db_path)

    async def start(self):
        """Start the listener."""
        bt = get_bittensor()

        class GetMinerIndex(bt.Synapse):
            version: Optional[int] = None
            compressed_index_serialized: Optional[str] = None

        class GetDataEntityBucket(bt.Synapse):
            version: Optional[int] = None
            data_entity_bucket_id: Optional[Any] = None
            data_entities: List[Any] = Field(default_factory=list)

        class GetContentsByBuckets(bt.Synapse):
            version: Optional[int] = None
            data_entity_bucket_ids: Optional[List[Any]] = None
            bucket_ids_to_contents: List[Any] = Field(default_factory=list)

        async def get_index(synapse: GetMinerIndex) -> GetMinerIndex:
            return await self.handle_get_index(synapse)

        async def get_data_entity_bucket(
            synapse: GetDataEntityBucket,
        ) -> GetDataEntityBucket:
            return await self.handle_get_data_entity_bucket(synapse)

        async def get_contents_by_buckets(
            synapse: GetContentsByBuckets,
        ) -> GetContentsByBuckets:
            return await self.handle_get_contents(synapse)

        async def get_index_blacklist(synapse: GetMinerIndex) -> Tuple[bool, str]:
            return await self.default_blacklist(synapse)

        async def get_data_entity_bucket_blacklist(
            synapse: GetDataEntityBucket,
        ) -> Tuple[bool, str]:
            return await self.default_blacklist(synapse)

        async def get_contents_by_buckets_blacklist(
            synapse: GetContentsByBuckets,
        ) -> Tuple[bool, str]:
            return await self.default_blacklist(synapse)

        async def get_index_priority(synapse: GetMinerIndex) -> float:
            return await self.default_priority(synapse)

        async def get_data_entity_bucket_priority(synapse: GetDataEntityBucket) -> float:
            return await self.default_priority(synapse)

        async def get_contents_by_buckets_priority(synapse: GetContentsByBuckets) -> float:
            return await self.default_priority(synapse)

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
                # Note: For production, use proper key management
                # This requires interactive password input in production
                self.wallet.create_new_hotkey(n_words=12, use_password=False, suppress=True)
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
            forward_fn=get_index,
            blacklist_fn=get_index_blacklist,
            priority_fn=get_index_priority,
        )

        # Handler 2: GetDataEntityBucket
        self.axon.attach(
            forward_fn=get_data_entity_bucket,
            blacklist_fn=get_data_entity_bucket_blacklist,
            priority_fn=get_data_entity_bucket_priority,
        )

        # Handler 3: GetContentsByBuckets
        self.axon.attach(
            forward_fn=get_contents_by_buckets,
            blacklist_fn=get_contents_by_buckets_blacklist,
            priority_fn=get_contents_by_buckets_priority,
        )

        # Announce the axon on-chain so validators can discover and query it.
        try:
            self.axon.serve(netuid=self.netuid, subtensor=self.subtensor)
            print(f"Served axon to subnet {self.netuid} on {self.network}")
        except Exception as e:
            error_msg = str(e)
            if "Custom error: 10" in error_msg or "Invalid Transaction" in error_msg:
                print(f"[yellow]Not registered on subnet {self.netuid} (needs stake).[/]")
                print(f"[yellow]Running in observer mode (no serve).[/]")
            else:
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

    async def handle_get_index(self, synapse: Any) -> Any:
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

        # Bind exact upstream response fields.
        response = bind_get_miner_index_response(
            synapse,
            storage=self.storage,
            miner_hotkey=self._miner_hotkey(),
        )

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
                "Response bound to compressed_index_serialized.",
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

    async def handle_get_data_entity_bucket(self, synapse: Any) -> Any:
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

        source = DataSource(bucket_request.source)
        label = bucket_request.label
        time_bucket = bucket_request.time_bucket_id
        limit = bucket_request.expected_count or 100

        data_entities = bind_get_data_entity_bucket_response(
            synapse,
            storage=self.storage,
            limit=limit,
        )
        query_resp = self.storage.query_bucket(source, label, time_bucket, limit=limit)

        response = {
            "data_entities": [
                {
                    "uri": item["uri"],
                    "datetime": item["datetime"],
                    "source": item["source"],
                    "label": item["label"],
                    "content_size_bytes": item["content_size_bytes"],
                }
                for item in data_entities
            ],
            "total_count": query_resp.total_count,
            "has_more": query_resp.has_more,
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
                "Response bound to data_entities.",
            ],
            extra={
                "normalized_bucket_request": {
                    "source": bucket_request.source,
                    "time_bucket_id": bucket_request.time_bucket_id,
                    "label": bucket_request.label,
                    "expected_count": bucket_request.expected_count,
                },
                "resolved_storage_bucket": {
                    "bucket_id": query_resp.bucket_id,
                    "total_count": query_resp.total_count,
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

    async def handle_get_contents(self, synapse: Any) -> Any:
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

        bucket_ids_to_contents = bind_get_contents_by_buckets_response(
            synapse,
            storage=self.storage,
        )
        response = {
            "bucket_ids_to_contents": [
                {
                    "bucket_id": bucket_id,
                    "content_count": len(contents),
                }
                for bucket_id, contents in bucket_ids_to_contents
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
                "Response bound to bucket_ids_to_contents.",
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

    async def default_blacklist(self, synapse: Any) -> Tuple[bool, str]:
        """Allow all requests."""
        return (False, "Allow all")

    async def default_priority(self, synapse: Any) -> float:
        """Default priority."""
        return 1.0

    def _operator_pool_for_source(self, source: str) -> List[str]:
        if source == "REDDIT":
            return ["reddit_operator_1", "reddit_operator_2", "reddit_operator_3"]
        return ["x_operator_1", "x_operator_2", "x_operator_3"]

    def _miner_hotkey(self) -> str:
        hotkeypub = getattr(getattr(self, "wallet", None), "hotkeypub", None)
        return getattr(hotkeypub, "ss58_address", self.wallet_name)

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
