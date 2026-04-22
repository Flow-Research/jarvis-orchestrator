#!/usr/bin/env python3
"""
SN13 upstream protocol response adapter.

Macrocosm SN13 expects miners to mutate inbound synapses with specific response
fields. This module keeps that wire-facing binding separate from Jarvis'
internal models so tests can prove compatibility without a live validator.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from ..models import (
    DataEntity,
    DataEntityBucketId,
    DataSource,
    MinerIndex,
    normalize_label,
)
from ..storage import StorageBackend

PROTOCOL_VERSION = 4
BULK_BUCKETS_COUNT_LIMIT = 100
UPSTREAM_SOURCE_IDS = {
    DataSource.REDDIT: 1,
    DataSource.X: 2,
}


class ProtocolAdapterError(Exception):
    """Base error for protocol adapter failures."""


class UnsupportedProtocolSourceError(ProtocolAdapterError):
    """Raised when local source has no confirmed upstream source ID."""


def bind_get_miner_index_response(
    synapse: Any,
    *,
    storage: StorageBackend,
    miner_hotkey: str,
) -> dict[str, Any]:
    """Bind upstream `GetMinerIndex` response fields on the synapse."""
    index = storage.get_index(miner_hotkey)
    compressed_index = miner_index_to_upstream_compressed(index)
    synapse.compressed_index_serialized = json.dumps(compressed_index, separators=(",", ":"))
    synapse.version = PROTOCOL_VERSION
    return compressed_index


def bind_get_data_entity_bucket_response(
    synapse: Any,
    *,
    storage: StorageBackend,
    limit: int = 100_000,
) -> list[dict[str, Any]]:
    """Bind upstream `GetDataEntityBucket.data_entities` on the synapse."""
    bucket = bucket_id_from_synapse(getattr(synapse, "data_entity_bucket_id", None))
    response = storage.query_bucket(bucket.source, bucket.label, bucket.time_bucket, limit=limit)
    data_entities = [data_entity_to_upstream_dict(entity) for entity in response.entities]
    synapse.data_entities = data_entities
    synapse.version = PROTOCOL_VERSION
    return data_entities


def bind_get_contents_by_buckets_response(
    synapse: Any,
    *,
    storage: StorageBackend,
    bucket_limit: int = BULK_BUCKETS_COUNT_LIMIT,
    per_bucket_limit: int = 100_000,
) -> list[tuple[dict[str, Any], list[bytes]]]:
    """Bind upstream `GetContentsByBuckets.bucket_ids_to_contents` on the synapse."""
    raw_bucket_ids = getattr(synapse, "data_entity_bucket_ids", None) or []
    if len(raw_bucket_ids) > bucket_limit:
        return []

    bucket_ids = [bucket_id_from_synapse(raw) for raw in raw_bucket_ids]
    bucket_ids_to_contents: list[tuple[dict[str, Any], list[bytes]]] = []
    for bucket in bucket_ids:
        response = storage.query_bucket(
            bucket.source,
            bucket.label,
            bucket.time_bucket,
            limit=per_bucket_limit,
        )
        bucket_ids_to_contents.append(
            (
                bucket_id_to_upstream_dict(bucket),
                [entity.content for entity in response.entities],
            )
        )

    synapse.bucket_ids_to_contents = bucket_ids_to_contents
    synapse.version = PROTOCOL_VERSION
    return bucket_ids_to_contents


def miner_index_to_upstream_compressed(index: MinerIndex) -> dict[str, Any]:
    """
    Convert local MinerIndex into upstream `CompressedMinerIndex` JSON shape.

    Upstream shape:
    `{ "sources": { source_id: [{ label, time_bucket_ids, sizes_bytes }] } }`
    """
    grouped: dict[int, dict[str | None, list[tuple[int, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for block in index.blocks:
        source_id = upstream_source_id(block.source)
        grouped[source_id][block.label].append((block.time_bucket, block.size_bytes))

    sources: dict[str, list[dict[str, Any]]] = {}
    for source_id, labels in sorted(grouped.items()):
        compressed_buckets = []
        for label, bucket_rows in sorted(labels.items(), key=lambda item: item[0] or ""):
            sorted_rows = sorted(bucket_rows, key=lambda item: item[0])
            compressed_buckets.append(
                {
                    "label": label,
                    "time_bucket_ids": [bucket_id for bucket_id, _ in sorted_rows],
                    "sizes_bytes": [size_bytes for _, size_bytes in sorted_rows],
                }
            )
        sources[str(source_id)] = compressed_buckets

    return {"sources": sources}


def data_entity_to_upstream_dict(entity: DataEntity) -> dict[str, Any]:
    """Convert local DataEntity to the upstream `DataEntity` JSON-compatible shape."""
    return {
        "uri": entity.uri,
        "datetime": entity.datetime.isoformat(),
        "source": upstream_source_id(entity.source),
        "label": {"value": entity.label} if entity.label is not None else None,
        "content": entity.content,
        "content_size_bytes": entity.content_size_bytes,
    }


def bucket_id_to_upstream_dict(bucket: DataEntityBucketId) -> dict[str, Any]:
    """Convert local bucket ID to upstream `DataEntityBucketId` JSON-compatible shape."""
    return {
        "time_bucket": {"id": bucket.time_bucket},
        "source": upstream_source_id(bucket.source),
        "label": {"value": bucket.label} if bucket.label is not None else None,
    }


def bucket_id_from_synapse(value: Any) -> DataEntityBucketId:
    """Parse upstream-style, local-style, or object-style bucket IDs."""
    raw = _object_to_dict(value)
    time_bucket_raw = raw.get("time_bucket", raw.get("time_bucket_id", 0))
    if isinstance(time_bucket_raw, dict):
        time_bucket = int(time_bucket_raw.get("id", 0))
    elif hasattr(time_bucket_raw, "id"):
        time_bucket = int(time_bucket_raw.id)
    else:
        time_bucket = int(time_bucket_raw)

    label_raw = raw.get("label")
    if isinstance(label_raw, dict):
        label = label_raw.get("value")
    elif hasattr(label_raw, "value"):
        label = label_raw.value
    else:
        label = label_raw

    return DataEntityBucketId(
        time_bucket=time_bucket,
        source=source_from_upstream(raw.get("source", DataSource.X.value)),
        label=normalize_label(label),
    )


def source_from_upstream(value: Any) -> DataSource:
    """Normalize upstream source IDs/names into local DataSource."""
    if isinstance(value, DataSource):
        return value
    if value == 1 or str(value).upper() == "REDDIT":
        return DataSource.REDDIT
    if value == 2 or str(value).upper() in {"X", "TWITTER"}:
        return DataSource.X
    if str(value).upper() == "YOUTUBE":
        return DataSource.YOUTUBE
    raise UnsupportedProtocolSourceError(f"Unsupported upstream source: {value}")


def upstream_source_id(source: DataSource) -> int:
    """Return confirmed upstream numeric source ID for a local source."""
    if source not in UPSTREAM_SOURCE_IDS:
        raise UnsupportedProtocolSourceError(
            f"No confirmed upstream protocol source ID for {source.value}"
        )
    return UPSTREAM_SOURCE_IDS[source]


def _object_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "dict"):
        dumped = value.dict()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {}
