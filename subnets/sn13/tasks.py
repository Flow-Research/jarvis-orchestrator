#!/usr/bin/env python3
"""
SN13 operator task contract and intake runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Optional

from pydantic import BaseModel, Field, field_validator

from .intake import OperatorSubmission
from .planner import OperatorDemand
from .quality import QualityResult, SubmissionQualityChecker, SubmissionStatus
from .storage import SQLiteStorage


class OperatorTaskStatus(str, Enum):
    QUEUED = "queued"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    FAILED = "failed"


class OperatorTask(BaseModel):
    """Work item that a personal operator can pull and execute."""

    model_config = {"frozen": True}

    task_id: str
    demand_id: str
    source: str
    label: Optional[str] = None
    keyword: Optional[str] = None
    time_bucket: int = Field(..., ge=0)
    quantity_target: int = Field(..., ge=1)
    priority: float = Field(..., ge=0.0)
    expires_at: datetime
    assigned_operator_id: Optional[str] = None
    status: OperatorTaskStatus = OperatorTaskStatus.QUEUED

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def from_demand(
        cls,
        demand: OperatorDemand,
        *,
        assigned_operator_id: Optional[str] = None,
    ) -> "OperatorTask":
        status = OperatorTaskStatus.ASSIGNED if assigned_operator_id else OperatorTaskStatus.QUEUED
        return cls(
            task_id=f"task_{demand.demand_id}",
            demand_id=demand.demand_id,
            source=demand.source.value,
            label=demand.label,
            keyword=demand.keyword,
            time_bucket=demand.time_bucket,
            quantity_target=demand.quantity_target,
            priority=demand.priority,
            expires_at=demand.expires_at,
            assigned_operator_id=assigned_operator_id,
            status=status,
        )


class IngestionResult(BaseModel):
    """Result of ingesting one operator submission."""

    model_config = {"frozen": True}

    quality: QualityResult
    stored: bool
    duplicate_recorded: bool = False
    rejection_recorded: bool = False


class SN13OperatorRuntime:
    """
    Bridges planned operator demand to storage-backed submissions.

    This is still local/in-process. Later phases can wrap this with an API,
    queue, or workstream transport without changing the task/submission contract.
    """

    def __init__(
        self,
        *,
        storage: SQLiteStorage,
        quality_checker: Optional[SubmissionQualityChecker] = None,
    ):
        self.storage = storage
        self.quality_checker = quality_checker or SubmissionQualityChecker()

    def create_tasks(
        self,
        demands: Iterable[OperatorDemand],
        *,
        operator_ids: Optional[list[str]] = None,
    ) -> list[OperatorTask]:
        operators = operator_ids or []
        tasks: list[OperatorTask] = []
        for idx, demand in enumerate(demands):
            assigned = operators[idx % len(operators)] if operators else None
            tasks.append(OperatorTask.from_demand(demand, assigned_operator_id=assigned))
        return tasks

    def ingest_submission(
        self,
        submission: OperatorSubmission,
        *,
        now: Optional[datetime] = None,
    ) -> IngestionResult:
        duplicate = self.storage.uri_exists(submission.uri)
        quality = self.quality_checker.assess(
            submission,
            duplicate=duplicate,
            now=now,
        )

        duplicate_recorded = False
        rejection_recorded = False

        if quality.status == SubmissionStatus.REJECTED:
            if duplicate:
                self.storage.record_duplicate(submission, submission.uri)
                duplicate_recorded = True
            self.storage.record_rejection(submission, quality.reasons)
            rejection_recorded = True
            return IngestionResult(
                quality=quality,
                stored=False,
                duplicate_recorded=duplicate_recorded,
                rejection_recorded=rejection_recorded,
            )

        self.storage.store_submission(submission, status=quality.status.value)
        return IngestionResult(quality=quality, stored=True)
