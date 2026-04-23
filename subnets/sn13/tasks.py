#!/usr/bin/env python3
"""
SN13 operator task contract and intake runtime.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from .economics import PayoutBasis
from .intake import OperatorSubmission
from .models import DataSource, datetime_from_time_bucket
from .planner import OperatorDemand
from .quality import QualityResult, SubmissionQualityChecker, SubmissionStatus
from .storage import SQLiteStorage


class OperatorTaskStatus(str, Enum):
    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"


class OperatorTask(BaseModel):
    """Work item that a personal operator can pull and execute."""

    model_config = {"frozen": True}

    task_id: str
    demand_id: str
    source: str
    label: str | None = None
    keyword: str | None = None
    time_bucket: int = Field(..., ge=0)
    quantity_target: int = Field(..., ge=1)
    priority: float = Field(..., ge=0.0)
    desirability_job_id: str | None = None
    desirability_weight: float | None = Field(default=None, ge=0.0)
    expires_at: datetime
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
    ) -> OperatorTask:
        return cls(
            task_id=f"task_{demand.demand_id}",
            demand_id=demand.demand_id,
            source=demand.source.value,
            label=demand.label,
            keyword=demand.keyword,
            time_bucket=demand.time_bucket,
            quantity_target=demand.quantity_target,
            priority=demand.priority,
            desirability_job_id=demand.desirability_job_id,
            desirability_weight=demand.desirability_weight,
            expires_at=demand.expires_at,
        )

    @property
    def source_window_start(self) -> datetime:
        """Inclusive start of the source-created-at hour this task covers."""
        return datetime_from_time_bucket(self.time_bucket)

    @property
    def source_window_end(self) -> datetime:
        """Exclusive end of the source-created-at hour this task covers."""
        return self.source_window_start + timedelta(hours=1)

    def to_workstream_contract(self) -> OperatorTaskContract:
        """Return the explicit workstream contract operators must satisfy."""
        return OperatorTaskContract.from_task(self)


class OperatorSourceRequirement(BaseModel):
    """Source-specific submission requirements for a task."""

    model_config = {"frozen": True}

    required_content_fields: tuple[str, ...]
    any_of_content_fields: tuple[tuple[str, ...], ...] = ()
    accepted_access_paths: tuple[str, ...]
    provenance_query_type: str


class OperatorAcceptanceCriteria(BaseModel):
    """Acceptance gates Jarvis applies before submitted data becomes miner truth."""

    model_config = {"frozen": True}

    source_created_at_gte: datetime
    source_created_at_lt: datetime
    must_match_source_uri: bool = True
    must_match_requested_label_or_keyword: bool = True
    duplicate_uri_rejected: bool = True
    quality_gate_required: bool = True

    @field_validator("source_created_at_gte", "source_created_at_lt")
    @classmethod
    def validate_datetime_fields(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class OperatorDeliveryLimits(BaseModel):
    """Hard upload limits for a single workstream task."""

    model_config = {"frozen": True}

    max_records: int = Field(..., ge=1)
    max_content_bytes_per_record: int = Field(default=1_000_000, ge=1)
    max_total_content_bytes: int = Field(..., ge=1)
    uploads_over_limit_rejected: bool = True


class OperatorEconomicsDisclosure(BaseModel):
    """Economic facts the operator receives before deciding to execute a task."""

    model_config = {"frozen": True}

    payout_basis: PayoutBasis = PayoutBasis.ACCEPTED_SCORABLE_RECORD
    payable_records_cap: int = Field(..., ge=1)
    submitted_volume_not_payable: bool = True
    duplicate_records_not_payable: bool = True
    rejected_records_not_payable: bool = True
    validation_failure_can_zero_payable_records: bool = True
    operator_cost_estimate_required: bool = True
    operator_cost_estimate_currency: str = "USD"


class OperatorMinimumRequirement(BaseModel):
    """Requirement published with the task and enforced during Jarvis intake."""

    model_config = {"frozen": True}

    name: str
    required: bool = True
    enforcement: str = "intake_quality_gate"
    description: str


class OperatorTaskContract(BaseModel):
    """Workstream payload that tells a personal operator exactly what to scrape."""

    model_config = {"frozen": True}

    task_id: str
    demand_id: str
    source: str
    label: str | None = None
    keyword: str | None = None
    quantity_target: int = Field(..., ge=1)
    priority: float = Field(..., ge=0.0)
    expires_at: datetime
    desirability_job_id: str | None = None
    desirability_weight: float | None = Field(default=None, ge=0.0)
    source_requirements: OperatorSourceRequirement
    acceptance: OperatorAcceptanceCriteria
    delivery_limits: OperatorDeliveryLimits
    economics: OperatorEconomicsDisclosure
    minimum_requirements: tuple[OperatorMinimumRequirement, ...]
    submission_schema: str = "subnets.sn13.intake.OperatorSubmission"

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def from_task(cls, task: OperatorTask) -> OperatorTaskContract:
        return cls(
            task_id=task.task_id,
            demand_id=task.demand_id,
            source=task.source,
            label=task.label,
            keyword=task.keyword,
            quantity_target=task.quantity_target,
            priority=task.priority,
            expires_at=task.expires_at,
            desirability_job_id=task.desirability_job_id,
            desirability_weight=task.desirability_weight,
            source_requirements=requirements_for_source(DataSource(task.source)),
            acceptance=OperatorAcceptanceCriteria(
                source_created_at_gte=task.source_window_start,
                source_created_at_lt=task.source_window_end,
            ),
            delivery_limits=OperatorDeliveryLimits(
                max_records=task.quantity_target,
                max_total_content_bytes=task.quantity_target * 1_000_000,
            ),
            economics=OperatorEconomicsDisclosure(payable_records_cap=task.quantity_target),
            minimum_requirements=minimum_requirements_for_task(task),
        )


def requirements_for_source(source: DataSource) -> OperatorSourceRequirement:
    """Return source-specific content and access requirements."""
    if source == DataSource.REDDIT:
        return OperatorSourceRequirement(
            required_content_fields=("id", "username", "url", "createdAt"),
            any_of_content_fields=(("body", "title"),),
            accepted_access_paths=(
                "reddit_api_credentials",
                "jarvis_reddit_operator_provider",
            ),
            provenance_query_type="reddit_label_or_keyword_scrape",
        )

    if source == DataSource.X:
        return OperatorSourceRequirement(
            required_content_fields=("tweet_id", "username", "text", "url", "timestamp"),
            accepted_access_paths=(
                "apify_x_actor_token",
                "macrocosmos_x_api_key",
                "jarvis_x_operator_provider",
            ),
            provenance_query_type="x_label_or_keyword_scrape",
        )

    return OperatorSourceRequirement(
        required_content_fields=("id", "url", "timestamp"),
        accepted_access_paths=("jarvis_operator_provider",),
        provenance_query_type="source_label_or_keyword_scrape",
    )


def minimum_requirements_for_task(task: OperatorTask) -> tuple[OperatorMinimumRequirement, ...]:
    """Return task-level requirements Jarvis publishes and enforces at intake."""
    target = task.label or task.keyword or "requested target"
    return (
        OperatorMinimumRequirement(
            name="match_task_target",
            description=f"Submitted records must match {target}.",
        ),
        OperatorMinimumRequirement(
            name="match_source_time_window",
            description=(
                "Submitted source-created-at timestamps must be within "
                f"{task.source_window_start.isoformat()} and {task.source_window_end.isoformat()}."
            ),
        ),
        OperatorMinimumRequirement(
            name="source_payload_schema",
            description="Submitted content must include the source-specific required fields.",
        ),
        OperatorMinimumRequirement(
            name="unique_source_uri",
            description="Duplicate source URIs are rejected and not payable.",
        ),
        OperatorMinimumRequirement(
            name="operator_cost_estimate",
            description=(
                "Operator must estimate its own scrape/provider/proxy cost before execution; "
                "Jarvis pays only accepted quality under the published payout basis."
            ),
        ),
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
        quality_checker: SubmissionQualityChecker | None = None,
    ):
        self.storage = storage
        self.quality_checker = quality_checker or SubmissionQualityChecker()

    def create_tasks(
        self,
        demands: Iterable[OperatorDemand],
    ) -> list[OperatorTask]:
        return [OperatorTask.from_demand(demand) for demand in demands]

    def ingest_submission(
        self,
        submission: OperatorSubmission,
        *,
        now: datetime | None = None,
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
