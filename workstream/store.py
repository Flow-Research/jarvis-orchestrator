"""Simple in-memory workstream adapter for tests and local development."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import WorkstreamTask, WorkstreamTaskStatus


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
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> WorkstreamTask | None:
        return self._tasks.get(task_id)

    def list_available(
        self,
        *,
        route_key: str | None = None,
        source: str | None = None,
    ) -> list[WorkstreamTask]:
        tasks = [task for task in self._tasks.values() if task.is_available]
        if route_key is not None:
            tasks = [task for task in tasks if task.route_key == route_key]
        if source is not None:
            tasks = [task for task in tasks if task.source == source]
        return sorted(tasks, key=lambda task: (task.created_at, task.task_id))

    def record_acceptance(self, task_id: str, *, accepted_count: int) -> WorkstreamTask:
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
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        if task.status not in {WorkstreamTaskStatus.OPEN, WorkstreamTaskStatus.COMPLETED}:
            raise TaskUnavailableError(task_id)

        completed = task.model_copy(update={"status": WorkstreamTaskStatus.COMPLETED})
        self._tasks[task_id] = completed
        return completed
