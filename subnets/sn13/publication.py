#!/usr/bin/env python3
"""
SN13 task publication gates.

This module decides whether planned tasks are publishable before Jarvis writes
them into the operator workstream.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .economics import (
    CostBreakdown,
    PayoutBasis,
    S3StorageMode,
    TaskEconomicsInput,
    evaluate_task_economics,
)
from .models import DataSource
from .tasks import OperatorTask


class PublicationEconomicsConfig(BaseModel):
    """Economic assumptions required before Jarvis publishes operator work."""

    model_config = {"frozen": True}

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


class PublicationTaskAssessment(BaseModel):
    """Publication decision for one planned task."""

    model_config = {"frozen": True}

    task_id: str
    source: str
    target: str | None = None
    quantity_target: int = Field(..., ge=1)
    can_publish: bool
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    total_task_cost: float
    expected_margin: float | None


class PublicationBatchDecision(BaseModel):
    """Batch publication result for a planning cycle."""

    model_config = {"frozen": True}

    publishable_tasks: tuple[OperatorTask, ...]
    refused_tasks: tuple[PublicationTaskAssessment, ...]
    accepted_tasks: tuple[PublicationTaskAssessment, ...]


def evaluate_publication_batch(
    tasks: list[OperatorTask],
    *,
    economics: PublicationEconomicsConfig,
) -> PublicationBatchDecision:
    """Return which planned tasks Jarvis may safely publish."""
    publishable: list[OperatorTask] = []
    accepted: list[PublicationTaskAssessment] = []
    refused: list[PublicationTaskAssessment] = []

    for task in tasks:
        decision = evaluate_task_economics(_economics_input_for_task(task, economics))
        assessment = PublicationTaskAssessment(
            task_id=task.task_id,
            source=task.source,
            target=task.label or task.keyword,
            quantity_target=task.quantity_target,
            can_publish=decision.can_take_task,
            blockers=decision.blockers,
            warnings=decision.warnings,
            total_task_cost=decision.total_task_cost,
            expected_margin=decision.expected_margin,
        )
        if decision.can_take_task:
            publishable.append(task)
            accepted.append(assessment)
        else:
            refused.append(assessment)

    return PublicationBatchDecision(
        publishable_tasks=tuple(publishable),
        refused_tasks=tuple(refused),
        accepted_tasks=tuple(accepted),
    )


def _economics_input_for_task(
    task: OperatorTask,
    economics: PublicationEconomicsConfig,
) -> TaskEconomicsInput:
    return TaskEconomicsInput(
        source=DataSource(task.source),
        label=task.label,
        keyword=task.keyword,
        desirability_job_id=task.desirability_job_id,
        desirability_weight=task.desirability_weight,
        quantity_target=task.quantity_target,
        max_task_cost=economics.max_task_cost,
        expected_reward_value=economics.expected_reward_value,
        expected_submitted_records=economics.expected_submitted_records,
        expected_accepted_scorable_records=economics.expected_accepted_scorable_records,
        expected_duplicate_rate=economics.expected_duplicate_rate,
        expected_rejection_rate=economics.expected_rejection_rate,
        validation_pass_probability=economics.validation_pass_probability,
        payout_basis=economics.payout_basis,
        costs=economics.costs,
        s3_storage_mode=economics.s3_storage_mode,
        currency=economics.currency,
    )
