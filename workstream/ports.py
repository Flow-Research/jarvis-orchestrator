"""Ports for workstream, intake, and operator accounting adapters."""

from __future__ import annotations

from typing import Protocol

from .models import (
    OperatorStats,
    OperatorSubmissionEnvelope,
    OperatorSubmissionReceipt,
    WorkstreamTask,
)


class WorkstreamPort(Protocol):
    """Task publication and progress boundary."""

    def publish(self, task: WorkstreamTask) -> WorkstreamTask:
        """Publish or replace a task."""

    def get(self, task_id: str) -> WorkstreamTask | None:
        """Return one task by ID."""

    def list_available(
        self,
        *,
        subnet: str | None = None,
        source: str | None = None,
    ) -> list[WorkstreamTask]:
        """Return tasks that can currently accept valid submissions."""

    def record_acceptance(self, task_id: str, *, accepted_count: int) -> WorkstreamTask:
        """Record accepted work against a task and close it at cap."""

    def complete(self, task_id: str) -> WorkstreamTask:
        """Mark a task complete."""


class OperatorIntakePort(Protocol):
    """Upload boundary enforced by subnet-specific intake adapters."""

    def submit(self, envelope: OperatorSubmissionEnvelope) -> OperatorSubmissionReceipt:
        """Validate and process an operator upload."""


class OperatorStatsPort(Protocol):
    """Operator accounting/read-model boundary."""

    def get_operator_stats(self, operator_id: str) -> OperatorStats:
        """Return operator-facing accounting stats."""
