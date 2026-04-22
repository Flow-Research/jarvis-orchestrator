"""FastAPI app exposing the Jarvis workstream HTTP boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status

from workstream.models import (
    OperatorStats,
    OperatorSubmissionEnvelope,
    OperatorSubmissionReceipt,
    WorkstreamTask,
)
from workstream.ports import OperatorIntakePort, OperatorStatsPort, WorkstreamPort

from .auth import OperatorAuthError, OperatorIdentity

OperatorAuthenticator = Callable[[Request], Awaitable[OperatorIdentity]]


def create_workstream_app(
    *,
    workstream: WorkstreamPort,
    intake: OperatorIntakePort,
    stats: OperatorStatsPort,
    authenticator: OperatorAuthenticator | None = None,
) -> FastAPI:
    """Create the workstream API without coupling it to a subnet implementation."""
    app = FastAPI(
        title="Jarvis Workstream API",
        version="1.0.0",
        description=(
            "Personal operators use this API to discover open workstream tasks, "
            "submit candidate records, and read operator quality stats."
        ),
    )

    async def authenticate(request: Request) -> OperatorIdentity | None:
        if authenticator is None:
            return None
        try:
            return await authenticator(request)
        except OperatorAuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc

    def enforce_operator(identity: OperatorIdentity | None, operator_id: str) -> None:
        if identity is not None and identity.operator_id != operator_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="authenticated operator does not match request operator",
            )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/tasks", response_model=list[WorkstreamTask])
    def list_tasks(
        subnet: str | None = Query(default=None, min_length=1),
        source: str | None = Query(default=None, min_length=1),
        _identity: OperatorIdentity | None = Depends(authenticate),
    ) -> list[WorkstreamTask]:
        return workstream.list_available(
            subnet=subnet,
            source=source,
        )

    @app.get("/v1/tasks/{task_id}", response_model=WorkstreamTask)
    def get_task(
        task_id: str,
        _identity: OperatorIdentity | None = Depends(authenticate),
    ) -> WorkstreamTask:
        task = workstream.get(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
        return task

    @app.post("/v1/submissions", response_model=OperatorSubmissionReceipt)
    def submit_records(
        envelope: OperatorSubmissionEnvelope,
        identity: OperatorIdentity | None = Depends(authenticate),
    ) -> OperatorSubmissionReceipt:
        enforce_operator(identity, envelope.operator_id)
        return intake.submit(envelope)

    @app.get("/v1/operators/{operator_id}/stats", response_model=OperatorStats)
    def get_operator_stats(
        operator_id: str,
        identity: OperatorIdentity | None = Depends(authenticate),
    ) -> OperatorStats:
        enforce_operator(identity, operator_id)
        return stats.get_operator_stats(operator_id)

    return app
