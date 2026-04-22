#!/usr/bin/env python3
"""
SN13 closed-loop local simulator.

This module proves the local Jarvis loop without a live validator:
Gravity/DD snapshot -> planner -> operator tasks -> operator submissions ->
quality gate -> SQLite -> protocol adapter -> local export.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .desirability import DesirabilitySnapshot
from .export import ExportResult, SN13ExportJob, SN13ParquetExporter
from .gravity import load_gravity_cache
from .intake import OperatorSubmission, SubmissionProvenance
from .listener.protocol_adapter import (
    bind_get_contents_by_buckets_response,
    bind_get_data_entity_bucket_response,
    bind_get_miner_index_response,
    bucket_id_to_upstream_dict,
)
from .models import DataSource, datetime_from_time_bucket, ensure_utc
from .planner import OperatorDemand, PlannerConfig, SN13Planner
from .quality import SubmissionQualityChecker
from .storage import SQLiteStorage
from .tasks import OperatorTask, SN13OperatorRuntime

DEFAULT_GRAVITY_RECORDS: list[dict[str, Any]] = [
    {
        "id": "jarvis_default_x_bittensor",
        "weight": 4.0,
        "params": {
            "keyword": None,
            "platform": "x",
            "label": "#bittensor",
            "post_start_datetime": None,
            "post_end_datetime": None,
        },
    },
    {
        "id": "jarvis_default_reddit_bittensor",
        "weight": 3.0,
        "params": {
            "keyword": None,
            "platform": "reddit",
            "label": "r/Bittensor_",
            "post_start_datetime": None,
            "post_end_datetime": None,
        },
    },
]


class ClosedLoopSimulationConfig(BaseModel):
    """Tunable config for the local end-to-end simulator."""

    model_config = {"frozen": True}

    operator_ids: tuple[str, ...] = ("sim_operator_1", "sim_operator_2")
    target_items_per_bucket: int = Field(default=5, ge=1)
    default_recent_buckets: int = Field(default=1, ge=1)
    max_tasks: int = Field(default=4, ge=1)
    export: bool = True
    miner_hotkey: str = "jarvis_simulated_hotkey"

    @field_validator("operator_ids")
    @classmethod
    def validate_operator_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(operator.strip() for operator in value if operator.strip())
        if not cleaned:
            raise ValueError("at least one operator_id is required")
        return cleaned


class ClosedLoopSimulationReport(BaseModel):
    """Summary of one closed-loop SN13 simulation run."""

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    started_at: datetime
    desirability_jobs: int
    planned_tasks: int
    accepted_submissions: int
    rejected_submissions: int
    index_source_groups: int
    validator_bucket_entities: int
    validator_content_buckets: int
    export_results: tuple[ExportResult, ...] = Field(default_factory=tuple)
    first_task: OperatorTask | None = None

    @property
    def exported_rows(self) -> int:
        return sum(result.row_count for result in self.export_results if not result.skipped)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "desirability_jobs": self.desirability_jobs,
            "planned_tasks": self.planned_tasks,
            "accepted_submissions": self.accepted_submissions,
            "rejected_submissions": self.rejected_submissions,
            "index_source_groups": self.index_source_groups,
            "validator_bucket_entities": self.validator_bucket_entities,
            "validator_content_buckets": self.validator_content_buckets,
            "exported_rows": self.exported_rows,
            "first_task_id": self.first_task.task_id if self.first_task else None,
        }


def load_snapshot(
    path: Path | None = None,
    *,
    cache_dir: Path | None = None,
    use_sample: bool = False,
) -> DesirabilitySnapshot:
    """Load a Gravity/DD snapshot from file or real cache.

    Sample records are intentionally opt-in so operational commands do not
    silently plan work from fake demand.
    """
    if path is not None:
        return DesirabilitySnapshot.from_json_file(path)
    if use_sample:
        return DesirabilitySnapshot.from_upstream_records(
            DEFAULT_GRAVITY_RECORDS,
            source_ref="built-in simulator sample",
        )
    return load_gravity_cache(cache_dir=cache_dir).snapshot


def plan_demands(
    *,
    storage: SQLiteStorage,
    snapshot: DesirabilitySnapshot,
    config: ClosedLoopSimulationConfig | None = None,
    now: datetime | None = None,
) -> list[OperatorDemand]:
    """Plan operator demand from current coverage and DD snapshot."""
    active_config = config or ClosedLoopSimulationConfig()
    planner = SN13Planner(
        config=PlannerConfig(
            target_items_per_bucket=active_config.target_items_per_bucket,
            default_recent_buckets=active_config.default_recent_buckets,
            max_tasks=active_config.max_tasks,
        )
    )
    return planner.plan(
        index=storage.get_index(active_config.miner_hotkey),
        desirability=snapshot,
        now=now,
    )


def create_tasks_from_demands(
    *,
    storage: SQLiteStorage,
    demands: list[OperatorDemand],
    config: ClosedLoopSimulationConfig | None = None,
) -> list[OperatorTask]:
    """Create open workstream tasks from planned demand."""
    runtime = SN13OperatorRuntime(storage=storage)
    return runtime.create_tasks(demands)


def run_closed_loop_simulation(
    *,
    storage: SQLiteStorage,
    snapshot: DesirabilitySnapshot,
    output_root: Path,
    config: ClosedLoopSimulationConfig | None = None,
    now: datetime | None = None,
) -> ClosedLoopSimulationReport:
    """Run a local Gravity-to-validator SN13 lifecycle."""
    active_config = config or ClosedLoopSimulationConfig()
    current_time = ensure_utc(now or datetime.now(timezone.utc).replace(microsecond=0))
    demands = plan_demands(
        storage=storage,
        snapshot=snapshot,
        config=active_config,
        now=current_time,
    )
    tasks = create_tasks_from_demands(storage=storage, demands=demands, config=active_config)
    runtime = SN13OperatorRuntime(
        storage=storage,
        quality_checker=SubmissionQualityChecker(desirability_snapshot=snapshot),
    )

    accepted = 0
    rejected = 0
    for task_index, task in enumerate(tasks):
        operator_id = active_config.operator_ids[task_index % len(active_config.operator_ids)]
        for submission in submissions_for_task(
            task,
            now=current_time,
            operator_id=operator_id,
        ):
            result = runtime.ingest_submission(submission, now=current_time)
            accepted += 1 if result.stored else 0
            rejected += 0 if result.stored else 1

    index_synapse = SimpleNamespace()
    index_payload = bind_get_miner_index_response(
        index_synapse,
        storage=storage,
        miner_hotkey=active_config.miner_hotkey,
    )

    first_task = tasks[0] if tasks else None
    bucket_entities = 0
    content_buckets = 0
    if first_task is not None:
        bucket_id = _bucket_for_task(first_task)
        bucket_synapse = SimpleNamespace(data_entity_bucket_id=bucket_id)
        bucket_entities = len(
            bind_get_data_entity_bucket_response(
                bucket_synapse,
                storage=storage,
                limit=active_config.target_items_per_bucket,
            )
        )
        contents_synapse = SimpleNamespace(data_entity_bucket_ids=[bucket_id])
        content_buckets = len(
            bind_get_contents_by_buckets_response(
                contents_synapse,
                storage=storage,
                per_bucket_limit=active_config.target_items_per_bucket,
            )
        )

    export_results: tuple[ExportResult, ...] = ()
    if active_config.export:
        exporter = SN13ParquetExporter(
            storage=storage,
            output_root=output_root,
            miner_hotkey=active_config.miner_hotkey,
        )
        export_results = tuple(
            exporter.export_job(
                SN13ExportJob.from_desirability_job(
                    job,
                    max_rows=active_config.target_items_per_bucket,
                ),
                now=current_time,
            )
            for job in snapshot.jobs
        )

    return ClosedLoopSimulationReport(
        started_at=current_time,
        desirability_jobs=len(snapshot.jobs),
        planned_tasks=len(tasks),
        accepted_submissions=accepted,
        rejected_submissions=rejected,
        index_source_groups=len(index_payload.get("sources", {})),
        validator_bucket_entities=bucket_entities,
        validator_content_buckets=content_buckets,
        export_results=export_results,
        first_task=first_task,
    )


def submissions_for_task(
    task: OperatorTask,
    *,
    now: datetime,
    operator_id: str = "sim_operator",
) -> list[OperatorSubmission]:
    """Create deterministic source-valid submissions for a simulated operator task."""
    quantity = task.quantity_target
    source = DataSource(task.source)
    bucket_start = datetime_from_time_bucket(task.time_bucket)
    submissions: list[OperatorSubmission] = []
    for index in range(quantity):
        created_at = bucket_start + timedelta(seconds=index)
        uri = simulated_uri(source, task.label, index, created_at)
        submissions.append(
            OperatorSubmission(
                operator_id=operator_id,
                source=source,
                label=task.label,
                uri=uri,
                source_created_at=created_at,
                scraped_at=now,
                content=simulated_content(source, task.label, index, created_at, uri),
                provenance=SubmissionProvenance(
                    scraper_id="jarvis.closed_loop_simulator",
                    query_type="gravity_planned_task",
                    query_value=task.label or task.keyword,
                    job_id=task.demand_id,
                ),
            )
        )
    return submissions


def simulated_uri(source: DataSource, label: str | None, index: int, created_at: datetime) -> str:
    safe_label = (label or "unlabeled").strip("#$/ ").replace("/", "_").replace(" ", "-").lower()
    stamp = int(created_at.timestamp())
    if source == DataSource.REDDIT:
        return f"https://www.reddit.com/r/{safe_label}/comments/jarvis{stamp}{index}"
    return f"https://x.com/jarvis_sim/status/{stamp}{index}"


def simulated_content(
    source: DataSource,
    label: str | None,
    index: int,
    created_at: datetime,
    uri: str,
) -> dict[str, Any]:
    timestamp = created_at.isoformat()
    if source == DataSource.REDDIT:
        community = label or "r/Bittensor_"
        return {
            "id": f"jarvis_reddit_{int(created_at.timestamp())}_{index}",
            "username": "jarvis_sim_operator",
            "communityName": community,
            "url": uri,
            "createdAt": timestamp,
            "dataType": "post",
            "title": f"Jarvis simulated Reddit item {index} for {community}",
            "body": f"Simulated Reddit body for {community}",
            "scrapedAt": ensure_utc(datetime.now(timezone.utc)).isoformat(),
        }

    hashtag = label or "#bittensor"
    return {
        "tweet_id": f"jarvis_x_{int(created_at.timestamp())}_{index}",
        "username": "jarvis_sim_operator",
        "text": f"Jarvis simulated X item {index} for {hashtag}",
        "tweet_hashtags": [hashtag] if hashtag.startswith("#") else [],
        "url": uri,
        "timestamp": timestamp,
        "scraped_at": ensure_utc(datetime.now(timezone.utc)).isoformat(),
    }


def _bucket_for_task(task: OperatorTask) -> dict[str, Any]:
    from .models import DataEntityBucketId

    return bucket_id_to_upstream_dict(
        DataEntityBucketId(
            time_bucket=task.time_bucket,
            source=DataSource(task.source),
            label=task.label,
        )
    )
