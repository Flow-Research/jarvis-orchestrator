#!/usr/bin/env python3
"""
SN13 axon runtime backed by canonical SQLite.

This runtime serves the confirmed SN13 query surface through local protocol
classes and the proven response adapter. It does not invent any validator-task
decomposition logic.
"""

import logging
import signal
import time
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any

import bittensor as bt

from miner_tools.fetcher import get_wallet_hotkey_ss58

from ..storage import SQLiteStorage
from .protocol import GetContentsByBuckets, GetDataEntityBucket, GetMinerIndex
from .protocol_adapter import (
    bind_get_contents_by_buckets_response,
    bind_get_data_entity_bucket_response,
    bind_get_miner_index_response,
)
from .protocol_observer import ProtocolObserver

logger = logging.getLogger(__name__)
NETUID = 13


class SN13ListenerRuntime:
    """Axon-backed SN13 listener using canonical SQLite."""

    def __init__(
        self,
        *,
        db_path: Path,
        capture_dir: Path,
        wallet_name: str,
        wallet_hotkey: str = "default",
        wallet_path: str = "~/.bittensor/wallets",
        network: str = "finney",
        endpoint: str | None = None,
        offline: bool = False,
        miner_hotkey: str | None = None,
    ) -> None:
        self.db_path = db_path
        self.capture_dir = capture_dir
        self.wallet_name = wallet_name
        self.wallet_hotkey = wallet_hotkey
        self.wallet_path = wallet_path
        self.network = network
        self.endpoint = endpoint
        self.offline = offline
        self.storage = SQLiteStorage(db_path)
        self.observer = ProtocolObserver(capture_dir=capture_dir)
        self._stop_requested = False
        self._axon: bt.Axon | None = None
        self._subtensor: bt.Subtensor | None = None
        self._miner_hotkey = miner_hotkey or self._resolve_miner_hotkey()

    @property
    def miner_hotkey(self) -> str:
        """Hotkey used to build the miner index."""
        return self._miner_hotkey

    def _resolve_miner_hotkey(self) -> str:
        try:
            return get_wallet_hotkey_ss58(
                SimpleNamespace(
                    name=self.wallet_name,
                    hotkey=self.wallet_hotkey,
                    path=self.wallet_path,
                )
            )
        except Exception:
            fallback = f"{self.wallet_name}/{self.wallet_hotkey}"
            logger.warning("Falling back to synthetic miner hotkey label: %s", fallback)
            return fallback

    def _record_success(
        self,
        *,
        synapse: Any,
        response_payload: dict[str, Any],
        started_at: float,
    ) -> None:
        self.observer.record(
            query_type=type(synapse).__name__,
            synapse=synapse,
            response_payload=response_payload,
            latency_ms=(perf_counter() - started_at) * 1000,
        )

    def _record_error(self, *, synapse: Any, started_at: float, error: Exception) -> None:
        self.observer.record(
            query_type=type(synapse).__name__,
            synapse=synapse,
            response_payload={},
            latency_ms=(perf_counter() - started_at) * 1000,
            error=f"{type(error).__name__}: {error}",
        )

    def handle_get_miner_index(self, synapse: GetMinerIndex) -> GetMinerIndex:
        """Serve `GetMinerIndex` from canonical SQLite."""
        started_at = perf_counter()
        try:
            payload = bind_get_miner_index_response(
                synapse,
                storage=self.storage,
                miner_hotkey=self.miner_hotkey,
            )
            self._record_success(
                synapse=synapse,
                response_payload={"compressed_index": payload},
                started_at=started_at,
            )
            return synapse
        except Exception as exc:
            self._record_error(synapse=synapse, started_at=started_at, error=exc)
            raise

    def handle_get_data_entity_bucket(self, synapse: GetDataEntityBucket) -> GetDataEntityBucket:
        """Serve `GetDataEntityBucket` from canonical SQLite."""
        started_at = perf_counter()
        try:
            payload = bind_get_data_entity_bucket_response(synapse, storage=self.storage)
            self._record_success(
                synapse=synapse,
                response_payload={"data_entities": payload},
                started_at=started_at,
            )
            return synapse
        except Exception as exc:
            self._record_error(synapse=synapse, started_at=started_at, error=exc)
            raise

    def handle_get_contents_by_buckets(
        self,
        synapse: GetContentsByBuckets,
    ) -> GetContentsByBuckets:
        """Serve `GetContentsByBuckets` from canonical SQLite."""
        started_at = perf_counter()
        try:
            payload = bind_get_contents_by_buckets_response(synapse, storage=self.storage)
            safe_payload = {
                "bucket_ids_to_contents": [
                    {
                        "bucket": bucket_id,
                        "content_count": len(contents),
                    }
                    for bucket_id, contents in payload
                ]
            }
            self._record_success(
                synapse=synapse,
                response_payload=safe_payload,
                started_at=started_at,
            )
            return synapse
        except Exception as exc:
            self._record_error(synapse=synapse, started_at=started_at, error=exc)
            raise

    def build_axon(
        self,
        *,
        port: int,
        ip: str = "0.0.0.0",
        external_ip: str | None = None,
        external_port: int | None = None,
        max_workers: int | None = None,
    ) -> bt.Axon:
        """Create and bind the axon routes for the SN13 protocol surface."""
        wallet = bt.Wallet(
            name=self.wallet_name,
            hotkey=self.wallet_hotkey,
            path=self.wallet_path,
        )
        axon = bt.Axon(
            wallet=wallet,
            port=port,
            ip=ip,
            external_ip=external_ip,
            external_port=external_port,
            max_workers=max_workers,
        )
        axon.attach(self.handle_get_miner_index)
        axon.attach(self.handle_get_data_entity_bucket)
        axon.attach(self.handle_get_contents_by_buckets)

        @axon.app.get("/health")
        def health() -> dict[str, Any]:
            return {
                "ok": self.storage.health_check(),
                "netuid": NETUID,
                "offline": self.offline,
                "db_path": str(self.db_path),
                "capture_dir": str(self.capture_dir),
                "miner_hotkey": self.miner_hotkey,
            }

        self._axon = axon
        return axon

    def _build_subtensor(self) -> bt.Subtensor:
        network_value = self.endpoint or self.network
        return bt.Subtensor(network=network_value)

    def start(
        self,
        *,
        port: int,
        ip: str = "0.0.0.0",
        external_ip: str | None = None,
        external_port: int | None = None,
        max_workers: int | None = None,
    ) -> None:
        """Start the runtime and block until terminated."""
        if not self.storage.health_check():
            raise RuntimeError(f"Canonical SQLite health check failed: {self.db_path}")

        axon = self.build_axon(
            port=port,
            ip=ip,
            external_ip=external_ip,
            external_port=external_port,
            max_workers=max_workers,
        )

        if not self.offline:
            self._subtensor = self._build_subtensor()
            logger.info("Serving SN13 axon on chain via network=%s", self.endpoint or self.network)
            axon.serve(netuid=NETUID, subtensor=self._subtensor)
        else:
            logger.info("Starting SN13 listener in offline mode")

        axon.start()
        logger.info(
            "SN13 listener started | port=%s | db=%s | capture_dir=%s | miner_hotkey=%s",
            port,
            self.db_path,
            self.capture_dir,
            self.miner_hotkey,
        )

        def _request_stop(signum, _frame) -> None:
            logger.info("Received signal %s; stopping listener", signum)
            self._stop_requested = True

        signal.signal(signal.SIGTERM, _request_stop)
        signal.signal(signal.SIGINT, _request_stop)

        try:
            while not self._stop_requested:
                time.sleep(1)
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the axon runtime."""
        if self._axon is not None:
            self._axon.stop()
            self._axon = None
        if self._subtensor is not None and hasattr(self._subtensor, "close"):
            self._subtensor.close()
        self._subtensor = None
