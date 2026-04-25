"""Simple in-memory workstream adapter for tests and local development."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .models import WorkstreamTask, WorkstreamTaskStatus, ensure_utc, utc_now


class WorkstreamError(Exception):
    """Base workstream error."""


class TaskNotFoundError(WorkstreamError):
    """Raised when a task ID does not exist."""


class TaskUnavailableError(WorkstreamError):
    """Raised when a task cannot accept more work or transition."""


@dataclass
class InMemoryWorkstream:
    """Deterministic workstream implementation used until persistent transport lands."""

    _tasks: dict[str, WorkstreamTask] = field(default_factory=dict)

    def publish(self, task: WorkstreamTask) -> WorkstreamTask:
        self.expire_open_tasks()
        existing = self._tasks.get(task.task_id)
        terminal_statuses = {WorkstreamTaskStatus.COMPLETED, WorkstreamTaskStatus.CANCELLED}
        if task.status in terminal_statuses:
            self._tasks[task.task_id] = task
            return task
        if existing is not None and existing.status in {
            WorkstreamTaskStatus.COMPLETED,
            WorkstreamTaskStatus.CANCELLED,
        }:
            return existing

        accepted_count = existing.accepted_count if existing is not None else task.accepted_count
        status = (
            WorkstreamTaskStatus.COMPLETED
            if accepted_count >= task.acceptance_cap
            else WorkstreamTaskStatus.OPEN
        )
        updated = task.model_copy(update={"accepted_count": accepted_count, "status": status})
        self._tasks[task.task_id] = updated
        return updated

    def get(self, task_id: str) -> WorkstreamTask | None:
        self.expire_open_tasks()
        return self._tasks.get(task_id)

    def list_available(
        self,
        *,
        route_key: str | None = None,
        source: str | None = None,
    ) -> list[WorkstreamTask]:
        self.expire_open_tasks()
        tasks = [task for task in self._tasks.values() if task.is_available]
        if route_key is not None:
            tasks = [task for task in tasks if task.route_key == route_key]
        if source is not None:
            tasks = [task for task in tasks if task.source == source]
        return sorted(tasks, key=lambda task: (task.created_at, task.task_id))

    def list_tasks(
        self,
        *,
        status: WorkstreamTaskStatus | None = None,
        route_key: str | None = None,
        source: str | None = None,
        limit: int | None = None,
    ) -> list[WorkstreamTask]:
        self.expire_open_tasks()
        tasks = list(self._tasks.values())
        if status is not None:
            tasks = [task for task in tasks if task.status == status]
        if route_key is not None:
            tasks = [task for task in tasks if task.route_key == route_key]
        if source is not None:
            tasks = [task for task in tasks if task.source == source]
        ordered = sorted(tasks, key=lambda task: (task.created_at, task.task_id))
        return ordered[:limit] if limit is not None else ordered

    def summary(
        self,
        *,
        route_key: str | None = None,
        source: str | None = None,
    ) -> dict[str, int]:
        self.expire_open_tasks()
        tasks = self.list_tasks(route_key=route_key, source=source)
        return {
            "total_tasks": len(tasks),
            "open_tasks": sum(1 for task in tasks if task.status == WorkstreamTaskStatus.OPEN),
            "completed_tasks": sum(
                1 for task in tasks if task.status == WorkstreamTaskStatus.COMPLETED
            ),
            "cancelled_tasks": sum(
                1 for task in tasks if task.status == WorkstreamTaskStatus.CANCELLED
            ),
            "expired_tasks": sum(
                1 for task in tasks if task.status == WorkstreamTaskStatus.EXPIRED
            ),
            "available_now": len(self.list_available(route_key=route_key, source=source)),
        }

    def expire_open_tasks(self, *, now: datetime | None = None) -> int:
        current_time = ensure_utc(now or utc_now())
        expired = 0
        for task_id, task in tuple(self._tasks.items()):
            if task.status == WorkstreamTaskStatus.OPEN and task.is_expired(current_time):
                self._tasks[task_id] = task.model_copy(
                    update={"status": WorkstreamTaskStatus.EXPIRED}
                )
                expired += 1
        return expired

    def record_acceptance(self, task_id: str, *, accepted_count: int) -> WorkstreamTask:
        self.expire_open_tasks()
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        if accepted_count < 1 or not task.is_available:
            raise TaskUnavailableError(task_id)
        new_accepted_count = min(task.acceptance_cap, task.accepted_count + accepted_count)
        updated = task.model_copy(
            update={
                "accepted_count": new_accepted_count,
                "status": (
                    WorkstreamTaskStatus.COMPLETED
                    if new_accepted_count >= task.acceptance_cap
                    else task.status
                ),
            }
        )
        self._tasks[task_id] = updated
        return updated

    def complete(self, task_id: str) -> WorkstreamTask:
        self.expire_open_tasks()
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        if task.status not in {WorkstreamTaskStatus.OPEN, WorkstreamTaskStatus.COMPLETED}:
            raise TaskUnavailableError(task_id)

        completed = task.model_copy(update={"status": WorkstreamTaskStatus.COMPLETED})
        self._tasks[task_id] = completed
        return completed
