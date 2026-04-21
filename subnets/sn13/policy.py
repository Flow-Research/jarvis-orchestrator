#!/usr/bin/env python3
"""
SN13 policy core.

This module defines the local policy rules Jarvis uses to reason about what
data is scorable, which hard protocol limits apply, and how desirability
windows can override the default freshness logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .models import (
    DataEntity,
    DataEntityBucket,
    DataSource,
    MinerIndex,
    TimeBucket,
    ensure_utc,
    time_bucket_from_datetime,
)

MB = 1024 * 1024


class CredibilityPolicy(BaseModel):
    """Parameters that affect score scaling from validator credibility."""

    model_config = {"frozen": True}

    starting_credibility: float = Field(default=0.0, ge=0.0, le=1.0)
    alpha: float = Field(default=0.15, gt=0.0, le=1.0)
    exponent: float = Field(default=2.5, gt=0.0)


class DesirableJobWindow(BaseModel):
    """
    Desirable job override window.

    If a desirable job specifies a time range, data inside that range should be
    considered scorable even if it is outside the default 30-day freshness
    window. Data outside the desirable range should be treated as non-scorable
    for that job path.
    """

    model_config = {"frozen": True}

    source: DataSource
    label: str = Field(..., min_length=1, max_length=140)
    scale_factor: float = Field(default=1.0, gt=0.0)
    start_time_bucket: Optional[int] = Field(default=None, ge=0)
    end_time_bucket: Optional[int] = Field(default=None, ge=0)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        return value.strip().casefold()

    def contains_bucket(self, bucket_id: int) -> bool:
        if self.start_time_bucket is not None and bucket_id < self.start_time_bucket:
            return False
        if self.end_time_bucket is not None and bucket_id > self.end_time_bucket:
            return False
        return True

    @property
    def has_explicit_range(self) -> bool:
        return self.start_time_bucket is not None or self.end_time_bucket is not None


class ScorableDecision(BaseModel):
    """Result of classifying an entity under local SN13 policy."""

    model_config = {"frozen": True}

    is_scorable: bool
    reason: str
    source_weight: float
    hours_old: int = Field(..., ge=0)
    time_bucket: int = Field(..., ge=0)
    desirable_scale_factor: Optional[float] = Field(default=None, gt=0.0)
    desirable_window_applied: bool = False


class SN13Policy(BaseModel):
    """Top-level policy object for SN13 reasoning inside Jarvis."""

    model_config = {"frozen": True}

    default_freshness_days: int = Field(default=30, ge=1)
    bucket_size_limit_bytes: int = Field(default=128 * MB, ge=1)
    miner_index_bucket_limit: int = Field(default=350_000, ge=1)
    source_weights: dict[DataSource, float] = Field(
        default_factory=lambda: {
            DataSource.REDDIT: 0.55,
            DataSource.X: 0.35,
            DataSource.YOUTUBE: 0.10,
        }
    )
    credibility: CredibilityPolicy = Field(default_factory=CredibilityPolicy)

    def current_time_bucket(self, now: Optional[datetime] = None) -> int:
        return time_bucket_from_datetime(ensure_utc(now or datetime.now(timezone.utc)))

    def max_freshness_hours(self) -> int:
        return self.default_freshness_days * 24

    def get_source_weight(self, source: DataSource) -> float:
        return self.source_weights.get(source, 0.0)

    def bucket_is_within_limit(self, bucket: DataEntityBucket) -> bool:
        return bucket.total_bytes <= self.bucket_size_limit_bytes

    def index_is_within_limit(self, index: MinerIndex) -> bool:
        return len(index.blocks) <= self.miner_index_bucket_limit

    def classify_entity(
        self,
        entity: DataEntity,
        *,
        now: Optional[datetime] = None,
        desirable_job: Optional[DesirableJobWindow] = None,
    ) -> ScorableDecision:
        current_bucket = self.current_time_bucket(now)
        entity_bucket = entity.time_bucket
        hours_old = max(0, current_bucket - entity_bucket)
        source_weight = self.get_source_weight(entity.source)

        if source_weight <= 0:
            return ScorableDecision(
                is_scorable=False,
                reason="unsupported_source_weight",
                source_weight=source_weight,
                hours_old=hours_old,
                time_bucket=entity_bucket,
            )

        if desirable_job is not None:
            if desirable_job.source != entity.source or desirable_job.label != (entity.label or ""):
                return ScorableDecision(
                    is_scorable=False,
                    reason="desirable_job_mismatch",
                    source_weight=source_weight,
                    hours_old=hours_old,
                    time_bucket=entity_bucket,
                )

            if desirable_job.has_explicit_range:
                if desirable_job.contains_bucket(entity_bucket):
                    return ScorableDecision(
                        is_scorable=True,
                        reason="scorable_within_desirable_window",
                        source_weight=source_weight,
                        hours_old=hours_old,
                        time_bucket=entity_bucket,
                        desirable_scale_factor=desirable_job.scale_factor,
                        desirable_window_applied=True,
                    )
                return ScorableDecision(
                    is_scorable=False,
                    reason="outside_desirable_window",
                    source_weight=source_weight,
                    hours_old=hours_old,
                    time_bucket=entity_bucket,
                    desirable_scale_factor=desirable_job.scale_factor,
                    desirable_window_applied=True,
                )

        if hours_old > self.max_freshness_hours():
            return ScorableDecision(
                is_scorable=False,
                reason="stale_beyond_default_freshness",
                source_weight=source_weight,
                hours_old=hours_old,
                time_bucket=entity_bucket,
                desirable_scale_factor=desirable_job.scale_factor if desirable_job else None,
            )

        return ScorableDecision(
            is_scorable=True,
            reason="scorable_within_default_freshness",
            source_weight=source_weight,
            hours_old=hours_old,
            time_bucket=entity_bucket,
            desirable_scale_factor=desirable_job.scale_factor if desirable_job else None,
        )

    def classify_time_bucket(
        self,
        source: DataSource,
        label: Optional[str],
        time_bucket: TimeBucket,
        *,
        now: Optional[datetime] = None,
        desirable_job: Optional[DesirableJobWindow] = None,
    ) -> ScorableDecision:
        entity = DataEntity(
            uri=f"policy://{source.value.casefold()}/{time_bucket}/{label or 'unlabeled'}",
            datetime=datetime.fromtimestamp(time_bucket * 3600, tz=timezone.utc),
            source=source,
            label=label,
            content=b"policy-probe",
        )
        return self.classify_entity(entity, now=now, desirable_job=desirable_job)
