"""Utilities for decomposing SN13 validator bucket requests into operator tasks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil
from typing import Any, Iterable, Sequence


SN13_NETUID = 13
DEFAULT_TESTNET = "test"
DEFAULT_BUCKET_CHUNK_SIZE = 500
DEFAULT_VALIDATOR_TIMEOUT_SECONDS = 30
SMALL_BUCKET_THRESHOLD = 500


@dataclass(frozen=True)
class BucketRequest:
    """Normalized validator request for an SN13 bucket."""

    source: str
    time_bucket_id: int
    label: str
    expected_count: int = 0


@dataclass(frozen=True)
class OperatorTask:
    """A unit of work assigned to a personal operator agent."""

    task_id: str
    subnet_id: int
    query_type: str
    operator_type: str
    operator_name: str
    source: str
    label: str
    time_bucket_id: int
    offset: int
    limit: int
    priority: int
    deadline_seconds: int


@dataclass(frozen=True)
class DecompositionPlan:
    """Planner output for a validator bucket request."""

    subnet_id: int
    strategy: str
    reason: str
    estimated_total_count: int
    chunk_size: int
    tasks: tuple[OperatorTask, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view for logs or debugging."""
        return {
            "subnet_id": self.subnet_id,
            "strategy": self.strategy,
            "reason": self.reason,
            "estimated_total_count": self.estimated_total_count,
            "chunk_size": self.chunk_size,
            "tasks": [asdict(task) for task in self.tasks],
        }


def normalize_bucket_request(bucket_id: dict[str, Any] | Any) -> BucketRequest:
    """Convert a synapse bucket identifier into the planner input model."""
    if not isinstance(bucket_id, dict):
        bucket_id = _object_to_dict(bucket_id)

    source = str(bucket_id.get("source", "X")).upper()
    if source == "TWITTER":
        source = "X"

    time_bucket_id = int(bucket_id.get("time_bucket_id", bucket_id.get("time_bucket", 0)))
    label = str(bucket_id.get("label", "unknown"))

    raw_count = (
        bucket_id.get("expected_count")
        or bucket_id.get("count")
        or bucket_id.get("estimated_count")
        or 0
    )
    expected_count = int(raw_count) if raw_count else 0

    return BucketRequest(
        source=source,
        time_bucket_id=time_bucket_id,
        label=label,
        expected_count=expected_count,
    )


def decompose_bucket_request(
    bucket: BucketRequest,
    operator_pool: Sequence[str] | None = None,
    *,
    chunk_size: int = DEFAULT_BUCKET_CHUNK_SIZE,
    validator_timeout_seconds: int = DEFAULT_VALIDATOR_TIMEOUT_SECONDS,
) -> DecompositionPlan:
    """Split an SN13 bucket request into operator-sized units of work."""
    estimated_total_count = max(bucket.expected_count, 0)
    operator_type = _operator_type_for_source(bucket.source)
    operator_pool = tuple(operator_pool or _default_operator_pool(operator_type))

    if estimated_total_count <= SMALL_BUCKET_THRESHOLD:
        size = estimated_total_count or chunk_size
        task = OperatorTask(
            task_id=_task_id(bucket, 0, size),
            subnet_id=SN13_NETUID,
            query_type="GetDataEntityBucket",
            operator_type=operator_type,
            operator_name=operator_pool[0],
            source=bucket.source,
            label=bucket.label,
            time_bucket_id=bucket.time_bucket_id,
            offset=0,
            limit=size,
            priority=1,
            deadline_seconds=validator_timeout_seconds,
        )
        return DecompositionPlan(
            subnet_id=SN13_NETUID,
            strategy="single_operator",
            reason="bucket is small enough for one operator within validator timeout",
            estimated_total_count=estimated_total_count,
            chunk_size=size,
            tasks=(task,),
        )

    tasks = []
    total_chunks = ceil(estimated_total_count / chunk_size)
    for index in range(total_chunks):
        offset = index * chunk_size
        limit = min(chunk_size, estimated_total_count - offset)
        tasks.append(
            OperatorTask(
                task_id=_task_id(bucket, offset, limit),
                subnet_id=SN13_NETUID,
                query_type="GetDataEntityBucket",
                operator_type=operator_type,
                operator_name=operator_pool[index % len(operator_pool)],
                source=bucket.source,
                label=bucket.label,
                time_bucket_id=bucket.time_bucket_id,
                offset=offset,
                limit=limit,
                priority=1,
                deadline_seconds=validator_timeout_seconds,
            )
        )

    return DecompositionPlan(
        subnet_id=SN13_NETUID,
        strategy="chunk_by_offset",
        reason=f"bucket exceeds {SMALL_BUCKET_THRESHOLD} items; split for parallel operator execution",
        estimated_total_count=estimated_total_count,
        chunk_size=chunk_size,
        tasks=tuple(tasks),
    )


def aggregate_operator_results(result_batches: Iterable[Iterable[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Merge operator results while removing duplicates by stable content identity."""
    unique_results: dict[tuple[Any, ...], dict[str, Any]] = {}

    for batch in result_batches:
        for item in batch:
            if not isinstance(item, dict):
                continue
            key = (
                item.get("uri"),
                item.get("source"),
                item.get("label"),
                item.get("created_at"),
                item.get("content"),
            )
            unique_results.setdefault(key, item)

    return list(unique_results.values())


def _operator_type_for_source(source: str) -> str:
    normalized = source.upper()
    if normalized == "X":
        return "x_scraper"
    if normalized == "REDDIT":
        return "reddit_scraper"
    return "data_operator"


def _default_operator_pool(operator_type: str) -> tuple[str, ...]:
    return tuple(f"{operator_type}_{index}" for index in range(1, 4))


def _task_id(bucket: BucketRequest, offset: int, limit: int) -> str:
    return (
        f"sn13:{bucket.source}:{bucket.time_bucket_id}:{bucket.label}:"
        f"{offset}:{limit}"
    )


def _object_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {}
