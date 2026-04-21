#!/usr/bin/env python3
"""
SN13 Dynamic Desirability layer.

This module turns upstream-style Gravity desirability jobs into a local lookup
Jarvis can use when planning operator work and classifying data value.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import DataEntity, DataSource, ensure_utc, normalize_label, time_bucket_from_datetime
from .policy import DesirableJobWindow, ScorableDecision, SN13Policy


PLATFORM_TO_SOURCE = {
    "x": DataSource.X,
    "reddit": DataSource.REDDIT,
    "youtube": DataSource.YOUTUBE,
}


class DesirabilityJob(BaseModel):
    """Normalized local representation of one Gravity desirability job."""

    model_config = {"frozen": True}

    job_id: str = Field(..., min_length=1, max_length=80)
    source: DataSource
    weight: float = Field(..., gt=0.0)
    label: Optional[str] = Field(default=None, max_length=140)
    keyword: Optional[str] = Field(default=None, max_length=140)
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        return normalize_label(value)

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, value: str | None) -> str | None:
        return value.strip().casefold() if value else None

    @field_validator("start_datetime", "end_datetime")
    @classmethod
    def validate_datetime_fields(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value)

    @model_validator(mode="after")
    def validate_job(self) -> "DesirabilityJob":
        if self.label is None and self.keyword is None:
            raise ValueError("desirability job requires at least one of label or keyword")
        if self.start_datetime and self.end_datetime and self.start_datetime >= self.end_datetime:
            raise ValueError("start_datetime must be before end_datetime")
        return self

    @classmethod
    def from_upstream_record(cls, record: dict[str, Any]) -> "DesirabilityJob":
        params = record.get("params") or {}
        platform = str(params.get("platform", "")).casefold()
        if platform not in PLATFORM_TO_SOURCE:
            raise ValueError(f"Unsupported desirability platform: {platform}")

        return cls(
            job_id=str(record["id"]),
            source=PLATFORM_TO_SOURCE[platform],
            weight=float(record["weight"]),
            label=params.get("label"),
            keyword=params.get("keyword"),
            start_datetime=_parse_optional_datetime(params.get("post_start_datetime")),
            end_datetime=_parse_optional_datetime(params.get("post_end_datetime")),
        )

    @property
    def start_time_bucket(self) -> int | None:
        return time_bucket_from_datetime(self.start_datetime) if self.start_datetime else None

    @property
    def end_time_bucket(self) -> int | None:
        return time_bucket_from_datetime(self.end_datetime) if self.end_datetime else None

    @property
    def has_explicit_range(self) -> bool:
        return self.start_datetime is not None or self.end_datetime is not None

    def matches_bucket(
        self,
        *,
        source: DataSource,
        label: Optional[str],
        time_bucket: int,
        keyword: Optional[str] = None,
    ) -> bool:
        if self.source != source:
            return False
        if self.label is not None and self.label != normalize_label(label):
            return False
        if self.keyword is not None:
            normalized_keyword = keyword.strip().casefold() if keyword else ""
            if self.keyword != normalized_keyword:
                return False
        if self.has_explicit_range and not self.contains_time_bucket(time_bucket):
            return False
        return True

    def contains_time_bucket(self, time_bucket: int) -> bool:
        start_bucket = self.start_time_bucket
        end_bucket = self.end_time_bucket
        if start_bucket is not None and time_bucket < start_bucket:
            return False
        if end_bucket is not None and time_bucket > end_bucket:
            return False
        return True

    def to_policy_window(self) -> DesirableJobWindow | None:
        if self.label is None:
            return None
        return DesirableJobWindow(
            source=self.source,
            label=self.label,
            scale_factor=self.weight,
            start_time_bucket=self.start_time_bucket,
            end_time_bucket=self.end_time_bucket,
        )


class DesirabilityMatch(BaseModel):
    """Lookup result for a bucket or entity."""

    model_config = {"frozen": True}

    matched: bool
    source: DataSource
    label: Optional[str]
    time_bucket: int
    job: Optional[DesirabilityJob] = None
    reason: str

    @property
    def weight(self) -> float:
        return self.job.weight if self.job else 0.0


class DesirabilitySnapshot(BaseModel):
    """A cached desirability lookup snapshot."""

    model_config = {"frozen": True}

    jobs: list[DesirabilityJob] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_ref: Optional[str] = None

    @field_validator("retrieved_at")
    @classmethod
    def validate_retrieved_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @classmethod
    def from_upstream_records(
        cls,
        records: list[dict[str, Any]],
        *,
        source_ref: Optional[str] = None,
        retrieved_at: Optional[datetime] = None,
    ) -> "DesirabilitySnapshot":
        return cls(
            jobs=[DesirabilityJob.from_upstream_record(record) for record in records],
            source_ref=source_ref,
            retrieved_at=ensure_utc(retrieved_at or datetime.now(timezone.utc)),
        )

    @classmethod
    def from_json_file(cls, path: Path) -> "DesirabilitySnapshot":
        return cls.from_upstream_records(
            json.loads(path.read_text()),
            source_ref=str(path),
        )

    def find_best_match(
        self,
        *,
        source: DataSource,
        label: Optional[str],
        time_bucket: int,
        keyword: Optional[str] = None,
    ) -> DesirabilityMatch:
        candidates = [
            job
            for job in self.jobs
            if job.matches_bucket(
                source=source,
                label=label,
                time_bucket=time_bucket,
                keyword=keyword,
            )
        ]
        if not candidates:
            return DesirabilityMatch(
                matched=False,
                source=source,
                label=normalize_label(label),
                time_bucket=time_bucket,
                reason="no_desirability_match",
            )

        best = sorted(candidates, key=lambda job: job.weight, reverse=True)[0]
        return DesirabilityMatch(
            matched=True,
            source=source,
            label=normalize_label(label),
            time_bucket=time_bucket,
            job=best,
            reason="matched_desirability_job",
        )

    def find_for_entity(self, entity: DataEntity, *, keyword: Optional[str] = None) -> DesirabilityMatch:
        return self.find_best_match(
            source=entity.source,
            label=entity.label,
            time_bucket=entity.time_bucket,
            keyword=keyword,
        )

    def classify_entity(
        self,
        entity: DataEntity,
        *,
        policy: Optional[SN13Policy] = None,
        now: Optional[datetime] = None,
        keyword: Optional[str] = None,
    ) -> tuple[DesirabilityMatch, ScorableDecision]:
        active_policy = policy or SN13Policy()
        match = self.find_for_entity(entity, keyword=keyword)
        policy_window = match.job.to_policy_window() if match.job else None
        return match, active_policy.classify_entity(entity, now=now, desirable_job=policy_window)


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
