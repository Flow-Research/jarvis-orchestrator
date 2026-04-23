"""SN13 adapter for publishing operator tasks into the generic workstream."""

from __future__ import annotations

from workstream.models import WorkstreamTask
from workstream.ports import WorkstreamPort

from .tasks import OperatorTask


def workstream_task_from_sn13(task: OperatorTask) -> WorkstreamTask:
    """Convert an SN13 operator task into a generic workstream task."""
    contract = task.to_workstream_contract()
    return WorkstreamTask(
        task_id=task.task_id,
        route_key="sn13",
        source=task.source,
        contract=contract.model_dump(mode="json"),
        expires_at=contract.expires_at,
        acceptance_cap=task.quantity_target,
    )


def publish_sn13_tasks(
    tasks: list[OperatorTask],
    *,
    workstream: WorkstreamPort,
) -> list[WorkstreamTask]:
    """Publish SN13 tasks without exposing SN13 internals to the transport layer."""
    return [workstream.publish(workstream_task_from_sn13(task)) for task in tasks]
