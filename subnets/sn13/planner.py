#!/usr/bin/env python3
"""
SN13 operator demand planner.

The planner converts policy, desirability, and current miner coverage into
ranked scrape demand that operators can execute.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .desirability import DesirabilityJob, DesirabilitySnapshot
from .models import DataEntityBucketId, DataSource, MinerIndex, ensure_utc, normalize_label
from .policy import SN13Policy


class PlannerConfig(BaseModel):
    """Tunable planner settings."""

    model_config = {"frozen": True}

    target_items_per_bucket: int = Field(default=250, ge=1)
    task_ttl_minutes: int = Field(default=60, ge=1)
    max_tasks: int = Field(default=50, ge=1)
    default_recent_buckets: int = Field(default=3, ge=1)


class OperatorDemand(BaseModel):
    """Concrete scrape demand emitted for operators."""

    model_config = {"frozen": True}

    demand_id: str
    source: DataSource
    label: Optional[str] = None
    keyword: Optional[str] = None
    time_bucket: int = Field(..., ge=0)
    priority: float = Field(..., ge=0.0)
    quantity_target: int = Field(..., ge=1)
    existing_items: int = Field(default=0, ge=0)
    expires_at: datetime
    reason: str
    desirability_job_id: Optional[str] = None
    desirability_weight: Optional[float] = None

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        return normalize_label(value)

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, value: str | None) -> str | None:
        return value.strip().casefold() if value else None

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class SN13Planner:
    """Plans what operators should scrape next."""

    def __init__(
        self,
        *,
        policy: Optional[SN13Policy] = None,
        config: Optional[PlannerConfig] = None,
    ):
        self.policy = policy or SN13Policy()
        self.config = config or PlannerConfig()

    def plan(
        self,
        *,
        index: MinerIndex,
        desirability: DesirabilitySnapshot,
        now: Optional[datetime] = None,
    ) -> list[OperatorDemand]:
        current_time = ensure_utc(now or datetime.now(timezone.utc))
        current_bucket = self.policy.current_time_bucket(current_time)
        coverage = self._coverage_by_bucket(index)
        demands: list[OperatorDemand] = []

        for job in desirability.jobs:
            for bucket in self._candidate_buckets(job, current_bucket):
                if not self._job_bucket_is_valid(job, bucket):
                    continue
                existing = coverage.get(
                    DataEntityBucketId(
                        time_bucket=bucket,
                        source=job.source,
                        label=job.label,
                    ).key,
                    0,
                )
                remaining = self.config.target_items_per_bucket - existing
                if remaining <= 0:
                    continue
                priority = self._priority(job, bucket, current_bucket)
                demands.append(
                    OperatorDemand(
                        demand_id=self._demand_id(job, bucket),
                        source=job.source,
                        label=job.label,
                        keyword=job.keyword,
                        time_bucket=bucket,
                        priority=priority,
                        quantity_target=remaining,
                        existing_items=existing,
                        expires_at=current_time + timedelta(minutes=self.config.task_ttl_minutes),
                        reason="desirability_coverage_gap",
                        desirability_job_id=job.job_id,
                        desirability_weight=job.weight,
                    )
                )

        return sorted(
            demands,
            key=lambda demand: (
                -demand.priority,
                demand.source.value,
                demand.label or "",
                -demand.time_bucket,
            ),
        )[: self.config.max_tasks]

    def _coverage_by_bucket(self, index: MinerIndex) -> dict[str, int]:
        return {block.bucket_id: block.item_count for block in index.blocks}

    def _candidate_buckets(self, job: DesirabilityJob, current_bucket: int) -> list[int]:
        if job.has_explicit_range:
            start = job.start_time_bucket if job.start_time_bucket is not None else current_bucket
            end = job.end_time_bucket if job.end_time_bucket is not None else current_bucket
            end = min(end, current_bucket)
            if end < start:
                return []
            return list(range(end, start - 1, -1))[: self.config.default_recent_buckets]

        return [
            current_bucket - offset
            for offset in range(self.config.default_recent_buckets)
            if current_bucket - offset >= 0
        ]

    def _job_bucket_is_valid(self, job: DesirabilityJob, bucket: int) -> bool:
        if not job.has_explicit_range:
            return True
        return job.contains_time_bucket(bucket)

    def _priority(self, job: DesirabilityJob, bucket: int, current_bucket: int) -> float:
        source_weight = self.policy.get_source_weight(job.source)
        freshness_bonus = 1 / (1 + max(0, current_bucket - bucket))
        return source_weight * job.weight + freshness_bonus

    def _demand_id(self, job: DesirabilityJob, bucket: int) -> str:
        raw = f"{job.job_id}:{job.source.value}:{job.label}:{job.keyword}:{bucket}"
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return f"sn13_{digest}"
