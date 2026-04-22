"""Generic workstream models shared by the API and subnet adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    """Normalize datetimes crossing the API boundary."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class WorkstreamTaskStatus(str, Enum):
    """Generic task state independent of any subnet implementation."""

    OPEN = "open"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class WorkstreamTask(BaseModel):
    """Task visible to personal operators."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(..., min_length=1, max_length=160)
    subnet: str = Field(..., min_length=1, max_length=32)
    source: str = Field(..., min_length=1, max_length=64)
    contract: dict[str, Any] = Field(..., min_length=1)
    status: WorkstreamTaskStatus = WorkstreamTaskStatus.OPEN
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    acceptance_cap: int = Field(default=1, ge=1)
    accepted_count: int = Field(default=0, ge=0)

    @field_validator("created_at", "expires_at")
    @classmethod
    def validate_datetime(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    @property
    def is_available(self) -> bool:
        """Return whether the task can accept more valid submissions now."""
        now = utc_now()
        if self.status != WorkstreamTaskStatus.OPEN:
            return False
        if self.expires_at is not None and self.expires_at <= now:
            return False
        return self.accepted_count < self.acceptance_cap

    @property
    def remaining_capacity(self) -> int:
        """Return how many accepted records the task can still take."""
        return max(self.acceptance_cap - self.accepted_count, 0)

    @model_validator(mode="after")
    def validate_progress_and_contract(self) -> WorkstreamTask:
        if self.accepted_count > self.acceptance_cap:
            raise ValueError("accepted_count cannot exceed acceptance_cap")
        contract_task_id = self.contract.get("task_id")
        if contract_task_id is not None and str(contract_task_id) != self.task_id:
            raise ValueError("contract.task_id must match task_id")
        contract_source = self.contract.get("source")
        if contract_source is not None and str(contract_source) != self.source:
            raise ValueError("contract.source must match source")
        return self


class WorkstreamSubmissionRecord(BaseModel):
    """One source record submitted to the workstream API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    submission_id: str | None = Field(default=None, min_length=1, max_length=128)
    source: str | None = Field(default=None, min_length=1, max_length=64)
    label: str | None = Field(default=None, min_length=1, max_length=140)
    uri: str = Field(..., min_length=1, max_length=2048)
    source_created_at: datetime
    scraped_at: datetime | None = None
    content: dict[str, Any] = Field(..., min_length=1)
    provenance: dict[str, Any] | None = None

    @field_validator("source_created_at", "scraped_at")
    @classmethod
    def validate_datetime(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("uri must be non-empty")
        return normalized

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("label must be non-empty when provided")
        return normalized


class OperatorSubmissionEnvelope(BaseModel):
    """Generic operator upload envelope before subnet-specific validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    submission_id: str = Field(default_factory=lambda: f"opsub_{uuid4().hex}")
    task_id: str = Field(..., min_length=1)
    operator_id: str = Field(..., min_length=1, max_length=128)
    subnet: str = Field(..., min_length=1, max_length=32)
    records: list[WorkstreamSubmissionRecord] = Field(..., min_length=1)
    submitted_at: datetime = Field(default_factory=utc_now)

    @field_validator("submitted_at")
    @classmethod
    def validate_submitted_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class OperatorSubmissionReceipt(BaseModel):
    """Result returned to an operator after upload processing."""

    submission_id: str
    task_id: str
    operator_id: str
    accepted_count: int = Field(..., ge=0)
    rejected_count: int = Field(..., ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    status: str
    reasons: list[str] = Field(default_factory=list)


class OperatorStats(BaseModel):
    """Operator-facing accounting summary."""

    operator_id: str
    accepted_scorable: int = Field(default=0, ge=0)
    accepted_non_scorable: int = Field(default=0, ge=0)
    rejected: int = Field(default=0, ge=0)
    duplicate: int = Field(default=0, ge=0)
    estimated_reward_units: float = Field(default=0.0, ge=0.0)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)
