"""FastAPI app exposing the Jarvis workstream HTTP boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from html import escape

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse

from workstream.models import (
    OperatorStats,
    OperatorSubmissionEnvelope,
    OperatorSubmissionReceipt,
    WorkstreamTask,
)
from workstream.ports import OperatorIntakePort, OperatorStatsPort, WorkstreamPort

from .auth import OperatorAuthError, OperatorIdentity

OperatorAuthenticator = Callable[[Request], Awaitable[OperatorIdentity]]


def _task_target_label(task: WorkstreamTask) -> str:
    contract = task.contract
    if not isinstance(contract, dict):
        return "-"
    for key in ("target", "label", "keyword"):
        value = contract.get(key)
        if value:
            return str(value)
    source_requirements = contract.get("source_requirements")
    if isinstance(source_requirements, dict):
        for key in ("label", "keyword", "subreddit"):
            value = source_requirements.get(key)
            if value:
                return str(value)
    return "-"


def _dashboard_tasks(workstream: WorkstreamPort, *, limit: int = 25) -> list[WorkstreamTask]:
    list_tasks = getattr(workstream, "list_tasks", None)
    if callable(list_tasks):
        return list_tasks(limit=limit)
    return workstream.list_available()[:limit]


def _dashboard_summary(workstream: WorkstreamPort, tasks: list[WorkstreamTask]) -> dict[str, int]:
    summary = getattr(workstream, "summary", None)
    if callable(summary):
        return summary()

    available_now = len(workstream.list_available())
    open_tasks = sum(1 for task in tasks if task.status.value == "open")
    completed_tasks = sum(1 for task in tasks if task.status.value == "completed")
    cancelled_tasks = sum(1 for task in tasks if task.status.value == "cancelled")
    return {
        "total_tasks": len(tasks),
        "open_tasks": open_tasks,
        "completed_tasks": completed_tasks,
        "cancelled_tasks": cancelled_tasks,
        "available_now": available_now,
    }


def _render_dashboard_html(
    *,
    summary: dict[str, int],
    tasks: list[WorkstreamTask],
    auth_enabled: bool,
) -> str:
    rows = []
    for task in tasks:
        rows.append(
            "".join(
                (
                    "<tr>",
                    f"<td>{escape(task.task_id)}</td>",
                    f"<td>{escape(task.subnet)}</td>",
                    f"<td>{escape(task.source)}</td>",
                    f"<td>{escape(_task_target_label(task))}</td>",
                    f"<td>{escape(task.status.value)}</td>",
                    f"<td>{task.accepted_count}/{task.acceptance_cap}</td>",
                    f"<td>{escape(task.created_at.isoformat())}</td>",
                    "</tr>",
                )
            )
        )
    if not rows:
        rows.append(
            "<tr><td colspan='7' class='empty'>No tasks published yet.</td></tr>"
        )

    auth_state = "required" if auth_enabled else "disabled"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Jarvis Workstream</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f3f0e8;
      --panel: #fffdf8;
      --ink: #1f2937;
      --muted: #5b6470;
      --line: #d9d2c2;
      --accent: #0f766e;
      --accent-soft: #d7f0eb;
      --warn: #92400e;
      --warn-soft: #fff1d6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.10), transparent 28%),
        linear-gradient(180deg, #f7f3ea 0%, var(--bg) 100%);
      color: var(--ink);
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }}
    .hero {{
      display: grid;
      gap: 12px;
      margin-bottom: 24px;
    }}
    .eyebrow {{
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--accent);
    }}
    h1 {{
      margin: 0;
      font-size: clamp(32px, 5vw, 56px);
      line-height: 0.95;
      letter-spacing: -0.04em;
    }}
    .sub {{
      max-width: 760px;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.55;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin: 24px 0 28px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 10px 24px rgba(31, 41, 55, 0.05);
    }}
    .label {{
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .value {{
      margin-top: 8px;
      font-size: 28px;
      font-weight: 700;
      letter-spacing: -0.04em;
    }}
    .note {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 13px;
    }}
    .bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 18px;
    }}
    .pill {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--panel);
      font-size: 14px;
    }}
    .pill strong {{ color: var(--ink); }}
    .hint {{
      background: var(--warn-soft);
      border: 1px solid #efd6a3;
      color: var(--warn);
      border-radius: 16px;
      padding: 14px 16px;
      margin-bottom: 20px;
      line-height: 1.5;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 10px 24px rgba(31, 41, 55, 0.05);
    }}
    th, td {{
      text-align: left;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
      background: #f8f4eb;
    }}
    tr:last-child td {{ border-bottom: none; }}
    .empty {{
      color: var(--muted);
      text-align: center;
      padding: 28px;
    }}
    .footer {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 14px;
    }}
    code {{
      font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
      font-size: 0.92em;
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="eyebrow">Jarvis Orchestrator</div>
      <h1>Workstream Runtime</h1>
      <div class="sub">
        Human-readable runtime view for the Jarvis workstream.
        Personal operators still use the signed HTTP API for task
        discovery and submission.
      </div>
    </section>

    <section class="summary">
      <article class="card">
        <div class="label">Total Tasks</div>
        <div class="value">{summary["total_tasks"]}</div>
        <div class="note">All durable workstream tasks</div>
      </article>
      <article class="card">
        <div class="label">Open Tasks</div>
        <div class="value">{summary["open_tasks"]}</div>
        <div class="note">Tasks still accepting valid submissions</div>
      </article>
      <article class="card">
        <div class="label">Available Now</div>
        <div class="value">{summary["available_now"]}</div>
        <div class="note">Open and not yet full or expired</div>
      </article>
      <article class="card">
        <div class="label">Completed</div>
        <div class="value">{summary["completed_tasks"]}</div>
        <div class="note">Tasks closed by cap or completion</div>
      </article>
      <article class="card">
        <div class="label">Cancelled</div>
        <div class="value">{summary["cancelled_tasks"]}</div>
        <div class="note">Tasks closed without completion</div>
      </article>
    </section>

    <section class="bar">
      <div class="pill"><strong>Health</strong> <code>/health</code></div>
      <div class="pill"><strong>Task API</strong> <code>/v1/tasks</code></div>
      <div class="pill"><strong>Submission API</strong> <code>/v1/submissions</code></div>
      <div class="pill"><strong>Auth</strong> {auth_state}</div>
    </section>

    <section class="hint">
      This page is read-only. It does not bypass the signed operator API
      and it does not accept submissions.
    </section>

    <table>
      <thead>
        <tr>
          <th>Task</th>
          <th>Subnet</th>
          <th>Source</th>
          <th>Target</th>
          <th>Status</th>
          <th>Accepted</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>

    <div class="footer">
      Use the signed API for operator work. This page is for human runtime inspection only.
    </div>
  </main>
</body>
</html>"""


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

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        tasks = _dashboard_tasks(workstream)
        return HTMLResponse(
            _render_dashboard_html(
                summary=_dashboard_summary(workstream, tasks),
                tasks=tasks,
                auth_enabled=authenticator is not None,
            )
        )

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
