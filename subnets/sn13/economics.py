#!/usr/bin/env python3
"""
SN13 economic gates and unit-cost calculations.

This module is intentionally pure. It does not fetch prices, query wallets, or
call providers. Callers pass observed or configured numbers in, and the module
returns a deterministic take/refuse decision with the exact blockers.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from .models import DataSource, normalize_label

SN13_DUPLICATE_RATE_BLOCKER = 0.10
MIN_VALIDATION_PASS_PROBABILITY = 0.80


class S3StorageMode(str, Enum):
    """Where validator-facing or archive objects are stored."""

    UPSTREAM_PRESIGNED = "upstream_presigned"
    JARVIS_ARCHIVE = "jarvis_archive"
    UPSTREAM_AND_JARVIS_ARCHIVE = "upstream_and_jarvis_archive"


class PayoutBasis(str, Enum):
    """How an operator payout is calculated."""

    ACCEPTED_SCORABLE_RECORD = "accepted_scorable_record"
    ACCEPTED_RECORD = "accepted_record"
    FLAT_TASK = "flat_task"
    NONE = "none"


class CostBreakdown(BaseModel):
    """Cost surfaces for one planned SN13 task, all in the same currency."""

    model_config = {"frozen": True}

    operator_payout: float = Field(default=0.0, ge=0.0)
    scraper_provider_cost: float = Field(default=0.0, ge=0.0)
    proxy_cost: float = Field(default=0.0, ge=0.0)
    compute_cost: float = Field(default=0.0, ge=0.0)
    local_storage_cost: float = Field(default=0.0, ge=0.0)
    export_staging_cost: float = Field(default=0.0, ge=0.0)
    upload_bandwidth_cost: float = Field(default=0.0, ge=0.0)
    retry_cost: float = Field(default=0.0, ge=0.0)
    risk_reserve: float = Field(default=0.0, ge=0.0)
    jarvis_archive_bucket_cost: float = Field(default=0.0, ge=0.0)

    @computed_field
    @property
    def total(self) -> float:
        """Total estimated task spend."""
        return round(
            self.operator_payout
            + self.scraper_provider_cost
            + self.proxy_cost
            + self.compute_cost
            + self.local_storage_cost
            + self.export_staging_cost
            + self.upload_bandwidth_cost
            + self.retry_cost
            + self.risk_reserve
            + self.jarvis_archive_bucket_cost,
            8,
        )


class S3ArchiveCostInput(BaseModel):
    """Region-specific S3 archive usage and unit prices for Jarvis-owned archive buckets."""

    model_config = {"frozen": True}

    storage_gb_month: float = Field(default=0.0, ge=0.0)
    storage_usd_per_gb_month: float = Field(default=0.0, ge=0.0)
    put_requests: int = Field(default=0, ge=0)
    put_usd_per_1000: float = Field(default=0.0, ge=0.0)
    get_requests: int = Field(default=0, ge=0)
    get_usd_per_1000: float = Field(default=0.0, ge=0.0)
    retrieval_gb: float = Field(default=0.0, ge=0.0)
    retrieval_usd_per_gb: float = Field(default=0.0, ge=0.0)
    transfer_out_gb: float = Field(default=0.0, ge=0.0)
    transfer_out_usd_per_gb: float = Field(default=0.0, ge=0.0)
    lifecycle_transition_requests: int = Field(default=0, ge=0)
    lifecycle_transition_usd_per_1000: float = Field(default=0.0, ge=0.0)
    monitoring_object_count: int = Field(default=0, ge=0)
    monitoring_usd_per_1000_objects: float = Field(default=0.0, ge=0.0)


class S3ArchiveCostEstimate(BaseModel):
    """Cost estimate for one Jarvis-owned archive bucket period."""

    model_config = {"frozen": True}

    storage_cost: float
    put_request_cost: float
    get_request_cost: float
    retrieval_cost: float
    transfer_out_cost: float
    lifecycle_transition_cost: float
    monitoring_cost: float

    @computed_field
    @property
    def total(self) -> float:
        """Total estimated archive cost."""
        return round(
            self.storage_cost
            + self.put_request_cost
            + self.get_request_cost
            + self.retrieval_cost
            + self.transfer_out_cost
            + self.lifecycle_transition_cost
            + self.monitoring_cost,
            8,
        )


class TaskEconomicsInput(BaseModel):
    """Inputs required before Jarvis publishes paid or rate-limited SN13 work."""

    model_config = {"frozen": True}

    source: DataSource
    label: str | None = None
    keyword: str | None = None
    desirability_job_id: str | None = None
    desirability_weight: float | None = Field(default=None, ge=0.0)
    quantity_target: int | None = Field(default=None, ge=1)
    max_task_cost: float | None = Field(default=None, ge=0.0)
    expected_reward_value: float | None = Field(default=None, ge=0.0)
    expected_submitted_records: int | None = Field(default=None, ge=0)
    expected_accepted_scorable_records: int | None = Field(default=None, ge=0)
    expected_duplicate_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    expected_rejection_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    validation_pass_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    payout_basis: PayoutBasis | None = None
    costs: CostBreakdown = Field(default_factory=CostBreakdown)
    s3_storage_mode: S3StorageMode = S3StorageMode.UPSTREAM_PRESIGNED
    currency: str = "USD"

    @field_validator("label")
    @classmethod
    def validate_label(cls, value: str | None) -> str | None:
        return normalize_label(value)

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, value: str | None) -> str | None:
        return value.strip().casefold() if value else None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("currency is required")
        return value

    @model_validator(mode="after")
    def validate_task_target(self) -> TaskEconomicsInput:
        if not self.label and not self.keyword:
            raise ValueError("label or keyword is required")
        return self


class TaskEconomicsDecision(BaseModel):
    """Deterministic economic decision for one planned task."""

    model_config = {"frozen": True}

    can_take_task: bool
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    total_task_cost: float
    accepted_scorable_unit_cost: float | None
    quality_adjusted_unit_cost: float | None
    expected_margin: float | None
    s3_storage_cost_owner: str
    currency: str


def evaluate_task_economics(task: TaskEconomicsInput) -> TaskEconomicsDecision:
    """Return whether a task has enough economic proof to be published."""
    blockers = list(_missing_required_inputs(task))
    warnings: list[str] = []

    total_cost = task.costs.total
    accepted = task.expected_accepted_scorable_records
    validation_probability = task.validation_pass_probability

    if task.max_task_cost is not None and total_cost > task.max_task_cost:
        blockers.append("total_task_cost_exceeds_max_task_cost")

    if accepted is not None and accepted <= 0:
        blockers.append("expected_accepted_scorable_records_must_be_positive")

    if (
        task.expected_duplicate_rate is not None
        and task.expected_duplicate_rate > SN13_DUPLICATE_RATE_BLOCKER
    ):
        blockers.append("expected_duplicate_rate_exceeds_sn13_threshold")

    if (
        validation_probability is not None
        and validation_probability < MIN_VALIDATION_PASS_PROBABILITY
    ):
        blockers.append("validation_pass_probability_below_floor")

    if task.expected_rejection_rate is not None and task.expected_rejection_rate > 0.25:
        warnings.append("expected_rejection_rate_above_25_percent")

    margin = None
    if task.expected_reward_value is not None:
        margin = round(task.expected_reward_value - total_cost, 8)
        if margin < 0:
            blockers.append("expected_margin_negative")

    unit_cost = None
    quality_adjusted_unit_cost = None
    if accepted and accepted > 0:
        unit_cost = round(total_cost / accepted, 8)
        if validation_probability and validation_probability > 0:
            quality_adjusted_unit_cost = round(total_cost / (accepted * validation_probability), 8)

    return TaskEconomicsDecision(
        can_take_task=not blockers,
        blockers=tuple(dict.fromkeys(blockers)),
        warnings=tuple(warnings),
        total_task_cost=total_cost,
        accepted_scorable_unit_cost=unit_cost,
        quality_adjusted_unit_cost=quality_adjusted_unit_cost,
        expected_margin=margin,
        s3_storage_cost_owner=_s3_storage_cost_owner(task.s3_storage_mode),
        currency=task.currency,
    )


def calculate_payable_records(
    *,
    accepted_scorable_records: int,
    duplicate_records: int = 0,
    rejected_records: int = 0,
    validation_failed: bool = False,
) -> int:
    """Calculate operator-payable records after quality penalties."""
    if validation_failed:
        return 0
    payable = accepted_scorable_records - duplicate_records - rejected_records
    return max(payable, 0)


def calculate_s3_archive_cost(usage: S3ArchiveCostInput) -> S3ArchiveCostEstimate:
    """Calculate Jarvis-owned S3 archive cost from explicit usage and unit prices."""
    return S3ArchiveCostEstimate(
        storage_cost=round(usage.storage_gb_month * usage.storage_usd_per_gb_month, 8),
        put_request_cost=round((usage.put_requests / 1000) * usage.put_usd_per_1000, 8),
        get_request_cost=round((usage.get_requests / 1000) * usage.get_usd_per_1000, 8),
        retrieval_cost=round(usage.retrieval_gb * usage.retrieval_usd_per_gb, 8),
        transfer_out_cost=round(usage.transfer_out_gb * usage.transfer_out_usd_per_gb, 8),
        lifecycle_transition_cost=round(
            (usage.lifecycle_transition_requests / 1000)
            * usage.lifecycle_transition_usd_per_1000,
            8,
        ),
        monitoring_cost=round(
            (usage.monitoring_object_count / 1000) * usage.monitoring_usd_per_1000_objects,
            8,
        ),
    )


def _missing_required_inputs(task: TaskEconomicsInput) -> tuple[str, ...]:
    required = {
        "desirability_job_id": task.desirability_job_id,
        "desirability_weight": task.desirability_weight,
        "quantity_target": task.quantity_target,
        "max_task_cost": task.max_task_cost,
        "expected_reward_value": task.expected_reward_value,
        "expected_submitted_records": task.expected_submitted_records,
        "expected_accepted_scorable_records": task.expected_accepted_scorable_records,
        "expected_duplicate_rate": task.expected_duplicate_rate,
        "expected_rejection_rate": task.expected_rejection_rate,
        "validation_pass_probability": task.validation_pass_probability,
        "payout_basis": task.payout_basis,
    }
    return tuple(f"missing_{name}" for name, value in required.items() if value is None)


def _s3_storage_cost_owner(mode: S3StorageMode) -> str:
    if mode == S3StorageMode.UPSTREAM_PRESIGNED:
        return "upstream_destination_not_jarvis_bucket"
    if mode == S3StorageMode.UPSTREAM_AND_JARVIS_ARCHIVE:
        return "upstream_presigned_destination_plus_jarvis_owned_archive_bucket"
    return "jarvis_owned_archive_bucket"
