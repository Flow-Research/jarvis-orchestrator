"""FastAPI app exposing the Jarvis workstream HTTP boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from html import escape

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse

from workstream.models import (
    OperatorStats,
    OperatorSubmissionReceipt,
    OperatorSubmissionRequest,
    OperatorTaskView,
    WorkstreamTask,
    WorkstreamTaskStatus,
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


def _dashboard_tasks(
    workstream: WorkstreamPort,
    *,
    limit: int = 25,
    offset: int = 0,
) -> list[WorkstreamTask]:
    list_tasks = getattr(workstream, "list_tasks", None)
    if callable(list_tasks):
        return list_tasks(status=WorkstreamTaskStatus.OPEN, limit=offset + limit)[
            offset : offset + limit
        ]
    return workstream.list_available()[offset : offset + limit]


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


def _status_tone(status: str) -> str:
    return {
        "open": "tone-open",
        "completed": "tone-complete",
        "cancelled": "tone-cancelled",
    }.get(status, "tone-neutral")


def _render_dashboard_task_card(task: WorkstreamTask) -> str:
    status = task.status.value
    target = _task_target_label(task)
    remaining = max(task.acceptance_cap - task.accepted_count, 0)
    progress = 0
    if task.acceptance_cap > 0:
        progress = min(int((task.accepted_count / task.acceptance_cap) * 100), 100)
    return "".join(
        (
            "<article class='task-card'>",
            "<div class='task-topline'>",
            f"<div class='task-source'>{escape(task.source)}</div>",
            (
                f"<div class='task-status {escape(_status_tone(status))}'>"
                f"{escape(status)}</div>"
            ),
            "</div>",
            f"<h3>{escape(target)}</h3>",
            "<div class='task-meta'>",
            f"<span><strong>ID</strong> <code>{escape(task.task_id)}</code></span>",
            f"<span><strong>Created</strong> {escape(task.created_at.isoformat())}</span>",
            "</div>",
            "<div class='progress-head'>",
            f"<span>{task.accepted_count}/{task.acceptance_cap} accepted</span>",
            f"<span>{remaining} remaining</span>",
            "</div>",
            (
                "<div class='progress-track'>"
                f"<div class='progress-fill' style='width: {progress}%;'></div>"
                "</div>"
            ),
            "</article>",
        )
    )


def _render_dashboard_task_cards(tasks: list[WorkstreamTask]) -> str:
    if not tasks:
        return "<div class='empty'>No tasks published yet.</div>"
    return "".join(_render_dashboard_task_card(task) for task in tasks)


def _render_dashboard_html(
    *,
    summary: dict[str, int],
    tasks: list[WorkstreamTask],
    auth_enabled: bool,
) -> str:
    auth_state = "required" if auth_enabled else "disabled"
    initial_count = len(tasks)
    active_total = summary["open_tasks"]
    has_more = "true" if initial_count < active_total else "false"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Jarvis Workstream</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5efe4;
      --bg-deep: #10323c;
      --panel: rgba(255, 251, 245, 0.88);
      --panel-strong: #fffaf2;
      --ink: #14222f;
      --muted: #5a6876;
      --line: rgba(20, 34, 47, 0.10);
      --accent: #d86d3f;
      --accent-2: #0f766e;
      --accent-3: #1c4e80;
      --open-bg: #dff7ef;
      --open-ink: #0f766e;
      --complete-bg: #dcecff;
      --complete-ink: #24518a;
      --cancel-bg: #f8e1d8;
      --cancel-ink: #9f4126;
      --neutral-bg: #ebe6dc;
      --neutral-ink: #6a5a46;
      --shadow: 0 18px 40px rgba(20, 34, 47, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(216, 109, 63, 0.22), transparent 26%),
        radial-gradient(circle at top right, rgba(15, 118, 110, 0.18), transparent 24%),
        linear-gradient(180deg, #f9f3e7 0%, var(--bg) 48%, #efe6d8 100%);
      color: var(--ink);
    }}
    main {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 28px 20px 56px;
    }}
    .hero-shell {{
      position: relative;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, 0.35);
      border-radius: 28px;
      padding: 28px;
      margin-bottom: 24px;
      background:
        linear-gradient(135deg, rgba(16, 50, 60, 0.96), rgba(28, 78, 128, 0.92));
      color: #f9f4eb;
      box-shadow: var(--shadow);
    }}
    .hero-shell::before {{
      content: "";
      position: absolute;
      inset: auto -80px -100px auto;
      width: 280px;
      height: 280px;
      border-radius: 50%;
      background: rgba(216, 109, 63, 0.22);
      filter: blur(4px);
    }}
    .hero {{
      position: relative;
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(280px, 0.95fr);
      gap: 24px;
    }}
    .eyebrow {{
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #ffc7aa;
    }}
    h1 {{
      margin: 6px 0 0;
      font-size: clamp(34px, 5vw, 68px);
      line-height: 0.9;
      letter-spacing: -0.04em;
    }}
    .sub {{
      max-width: 760px;
      color: rgba(249, 244, 235, 0.82);
      font-size: 16px;
      line-height: 1.6;
      margin-top: 12px;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin: 0;
    }}
    .card {{
      background: rgba(255, 251, 245, 0.10);
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: 18px;
      padding: 18px;
      backdrop-filter: blur(8px);
    }}
    .label {{
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: rgba(249, 244, 235, 0.68);
    }}
    .value {{
      margin-top: 8px;
      font-size: 34px;
      font-weight: 700;
      letter-spacing: -0.04em;
    }}
    .note {{
      margin-top: 6px;
      color: rgba(249, 244, 235, 0.72);
      font-size: 13px;
    }}
    .hero-rail {{
      display: grid;
      gap: 12px;
      align-content: start;
    }}
    .rail-card {{
      background: rgba(255, 251, 245, 0.12);
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: 18px;
      padding: 16px 18px;
      backdrop-filter: blur(8px);
    }}
    .rail-title {{
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: rgba(249, 244, 235, 0.62);
      margin-bottom: 10px;
    }}
    .rail-list {{
      display: grid;
      gap: 8px;
    }}
    .rail-item {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
      font-size: 14px;
    }}
    .rail-item strong,
    .rail-item code {{
      color: #fff8ef;
    }}
    .rail-copy {{
      color: rgba(249, 244, 235, 0.76);
      line-height: 1.55;
      font-size: 14px;
    }}
    .live-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      width: fit-content;
      margin-top: 14px;
      padding: 9px 12px;
      border-radius: 999px;
      background: rgba(255, 251, 245, 0.12);
      border: 1px solid rgba(255, 255, 255, 0.16);
      color: rgba(249, 244, 235, 0.84);
      font-size: 13px;
      font-weight: 700;
    }}
    .live-dot {{
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: #70f1bf;
      box-shadow: 0 0 0 6px rgba(112, 241, 191, 0.14);
    }}
    .surface {{
      display: grid;
      grid-template-columns: minmax(0, 1.7fr) minmax(260px, 0.85fr);
      gap: 18px;
      align-items: start;
    }}
    .tasks-panel,
    .side-panel {{
      background: var(--panel);
      border: 1px solid rgba(255, 255, 255, 0.45);
      border-radius: 26px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}
    .panel-head {{
      padding: 22px 24px 14px;
      border-bottom: 1px solid var(--line);
    }}
    .panel-title {{
      margin: 0;
      font-size: 24px;
      letter-spacing: -0.03em;
    }}
    .panel-copy {{
      margin-top: 8px;
      color: var(--muted);
      line-height: 1.55;
      font-size: 14px;
    }}
    .task-grid {{
      display: grid;
      gap: 14px;
      padding: 18px 20px 20px;
    }}
    .task-card {{
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 18px;
      box-shadow: 0 10px 24px rgba(20, 34, 47, 0.05);
    }}
    .task-topline {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 10px;
    }}
    .task-source {{
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--accent-3);
    }}
    .task-card h3 {{
      margin: 0 0 10px;
      font-size: 24px;
      letter-spacing: -0.03em;
      line-height: 1.05;
    }}
    .task-status {{
      display: inline-flex;
      align-items: center;
      padding: 7px 11px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .tone-open {{
      background: var(--open-bg);
      color: var(--open-ink);
    }}
    .tone-complete {{
      background: var(--complete-bg);
      color: var(--complete-ink);
    }}
    .tone-cancelled {{
      background: var(--cancel-bg);
      color: var(--cancel-ink);
    }}
    .tone-neutral {{
      background: var(--neutral-bg);
      color: var(--neutral-ink);
    }}
    .task-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px 18px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      margin-bottom: 14px;
    }}
    .task-meta strong {{
      color: var(--ink);
      font-weight: 600;
    }}
    .progress-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 8px;
    }}
    .progress-track {{
      position: relative;
      height: 10px;
      border-radius: 999px;
      background: #e7ddcc;
      overflow: hidden;
    }}
    .progress-fill {{
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
    }}
    .side-stack {{
      display: grid;
      gap: 14px;
      padding: 18px;
    }}
    .info-card {{
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
    }}
    .info-title {{
      margin: 0 0 10px;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent-3);
    }}
    .info-copy {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
    }}
    .endpoint-list {{
      display: grid;
      gap: 10px;
      margin-top: 12px;
    }}
    .endpoint {{
      display: grid;
      gap: 4px;
      padding: 12px;
      border-radius: 14px;
      background: #f5ecdf;
      border: 1px solid #eadcc7;
    }}
    .endpoint code {{
      color: var(--ink);
      font-weight: 600;
    }}
    .hint {{
      background: linear-gradient(135deg, #fff0dc, #f9dfcf);
      border: 1px solid #efc59f;
      color: #8d4e20;
      border-radius: 18px;
      padding: 16px;
      line-height: 1.5;
    }}
    .empty {{
      color: var(--muted);
      text-align: center;
      padding: 28px;
      background: var(--panel-strong);
      border: 1px dashed #d8cab2;
      border-radius: 18px;
    }}
    .load-more {{
      width: calc(100% - 40px);
      margin: 0 20px 22px;
      border: 0;
      border-radius: 18px;
      padding: 15px 18px;
      background: linear-gradient(135deg, var(--bg-deep), var(--accent-3));
      color: #fff8ef;
      font-weight: 800;
      letter-spacing: 0.02em;
      cursor: pointer;
      box-shadow: 0 12px 24px rgba(20, 34, 47, 0.12);
    }}
    .load-more[hidden] {{
      display: none;
    }}
    .load-more:disabled {{
      opacity: 0.62;
      cursor: wait;
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
    @media (max-width: 980px) {{
      .hero,
      .surface {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 720px) {{
      main {{
        padding: 18px 14px 36px;
      }}
      .hero-shell {{
        padding: 20px;
      }}
      .task-card h3 {{
        font-size: 20px;
      }}
      .task-topline,
      .progress-head {{
        flex-direction: column;
        align-items: flex-start;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero-shell">
      <section class="hero">
        <div>
          <div class="eyebrow">Jarvis Orchestrator</div>
          <h1>Workstream Runtime</h1>
          <div class="sub">
            Human-readable runtime view for the Jarvis workstream.
            Personal operators still use the signed HTTP API for task
            discovery and submission.
          </div>
          <div class="live-pill">
            <span class="live-dot"></span>
            Live view refreshes every 10 seconds
          </div>
        </div>
        <aside class="hero-rail">
          <section class="rail-card">
            <div class="rail-title">Live Surface</div>
            <div class="rail-list">
              <div class="rail-item"><span>Health</span> <code>/health</code></div>
              <div class="rail-item"><span>Tasks</span> <code>/v1/tasks</code></div>
              <div class="rail-item"><span>Submit</span> <code>/v1/submissions</code></div>
              <div class="rail-item"><span>Auth</span> <strong>{auth_state}</strong></div>
            </div>
          </section>
          <section class="rail-card">
            <div class="rail-title">Operating Rule</div>
            <div class="rail-copy">
              Jarvis publishes work. Operators compete on the same open tasks.
              Intake decides what becomes canonical miner truth.
            </div>
          </section>
        </aside>
      </section>
      <section class="summary">
        <article class="card">
          <div class="label">Active Tasks</div>
          <div class="value" data-summary-key="open_tasks">{summary["open_tasks"]}</div>
          <div class="note">Visible open workstream tasks</div>
        </article>
        <article class="card">
          <div class="label">Available Now</div>
          <div class="value" data-summary-key="available_now">{summary["available_now"]}</div>
          <div class="note">Open and not yet full or expired</div>
        </article>
        <article class="card">
          <div class="label">Completed</div>
          <div class="value" data-summary-key="completed_tasks">{summary["completed_tasks"]}</div>
          <div class="note">Tasks closed by cap or completion</div>
        </article>
        <article class="card">
          <div class="label">Expired</div>
          <div class="value" data-summary-key="expired_tasks">{summary["expired_tasks"]}</div>
          <div class="note">Publication windows closed</div>
        </article>
      </section>
    </section>

    <section class="surface">
      <section class="tasks-panel">
        <div class="panel-head">
          <h2 class="panel-title">Open Demand Surface</h2>
          <div class="panel-copy">
            The dashboard is read-only. It shows the runtime state humans
            need to inspect while operators continue to use the signed API.
          </div>
        </div>
        <div class="task-grid" data-task-grid>
          {_render_dashboard_task_cards(tasks)}
        </div>
        <button
          class="load-more"
          type="button"
          data-load-more
          {"hidden" if has_more == "false" else ""}
        >
          Load more tasks
        </button>
      </section>

      <aside class="side-panel">
        <div class="panel-head">
          <h2 class="panel-title">Runtime Notes</h2>
          <div class="panel-copy">
            This view is intentionally separate from the operator contract.
          </div>
        </div>
        <div class="side-stack">
          <section class="hint">
            This page does not accept uploads and it does not bypass signed
            operator requests.
          </section>
          <section class="info-card">
            <h3 class="info-title">Human Checks</h3>
            <div class="info-copy">
              Use this page to inspect current task pressure, accepted
              progress, runtime auth mode, and whether published work exists
              at all.
            </div>
          </section>
          <section class="info-card">
            <h3 class="info-title">Operator Surface</h3>
            <div class="endpoint-list">
              <div class="endpoint">
                <code>GET /v1/tasks</code>
                <div class="info-copy">List open tasks.</div>
              </div>
              <div class="endpoint">
                <code>GET /v1/tasks/&#123;task_id&#125;</code>
                <div class="info-copy">Inspect one task contract.</div>
              </div>
              <div class="endpoint">
                <code>POST /v1/submissions</code>
                <div class="info-copy">Submit candidate records.</div>
              </div>
              <div class="endpoint">
                <code>GET /v1/operators/&#123;operator_id&#125;/stats</code>
                <div class="info-copy">Read quality counters.</div>
              </div>
            </div>
          </section>
          <div class="footer">
            Use the signed API for operator work. This page is for human
            runtime inspection only.
          </div>
        </div>
      </aside>
    </section>
  </main>
  <script>
    (() => {{
      const state = {{
        loaded: {initial_count},
        pageSize: 25,
        hasMore: {has_more},
        loading: false,
      }};
      const grid = document.querySelector("[data-task-grid]");
      const loadMoreButton = document.querySelector("[data-load-more]");

      function updateSummary(summary) {{
        for (const [key, value] of Object.entries(summary)) {{
          const node = document.querySelector(`[data-summary-key="${{key}}"]`);
          if (node) node.textContent = value;
        }}
      }}

      function setLoadMoreState() {{
        if (!loadMoreButton) return;
        loadMoreButton.hidden = !state.hasMore;
        loadMoreButton.disabled = state.loading;
        loadMoreButton.textContent = state.loading ? "Loading..." : "Load more tasks";
      }}

      async function fetchTaskPage(offset, limit) {{
        const response = await fetch(`/dashboard/tasks?offset=${{offset}}&limit=${{limit}}`, {{
          headers: {{ "accept": "application/json" }},
          cache: "no-store",
        }});
        if (!response.ok) throw new Error(`dashboard task fetch failed: ${{response.status}}`);
        return response.json();
      }}

      async function refreshVisibleTasks() {{
        if (!grid || state.loading || state.loaded < 1) return;
        const payload = await fetchTaskPage(0, state.loaded);
        grid.innerHTML = payload.task_html;
        state.loaded = payload.loaded_count;
        state.hasMore = payload.has_more;
        updateSummary(payload.summary);
        setLoadMoreState();
      }}

      async function loadMoreTasks() {{
        if (!grid || state.loading || !state.hasMore) return;
        state.loading = true;
        setLoadMoreState();
        try {{
          const payload = await fetchTaskPage(state.loaded, state.pageSize);
          grid.insertAdjacentHTML("beforeend", payload.task_html);
          state.loaded = payload.next_offset;
          state.hasMore = payload.has_more;
          updateSummary(payload.summary);
        }} finally {{
          state.loading = false;
          setLoadMoreState();
        }}
      }}

      loadMoreButton?.addEventListener("click", loadMoreTasks);
      window.addEventListener("scroll", () => {{
        const nearBottom = window.innerHeight + window.scrollY >= document.body.offsetHeight - 900;
        if (nearBottom) void loadMoreTasks();
      }}, {{ passive: true }});
      window.setInterval(() => void refreshVisibleTasks(), 10000);
      setLoadMoreState();
    }})();
  </script>
</body>
</html>"""


def create_workstream_app(
    *,
    workstream: WorkstreamPort,
    intake: OperatorIntakePort,
    stats: OperatorStatsPort,
    authenticator: OperatorAuthenticator | None = None,
) -> FastAPI:
    """Create the workstream API without coupling it to an adapter implementation."""
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

    @app.get("/dashboard/tasks")
    def dashboard_tasks(
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=25, ge=1, le=200),
    ) -> dict[str, object]:
        tasks = _dashboard_tasks(workstream, offset=offset, limit=limit)
        summary = _dashboard_summary(workstream, tasks)
        next_offset = offset + len(tasks)
        return {
            "offset": offset,
            "limit": limit,
            "loaded_count": next_offset,
            "next_offset": next_offset,
            "has_more": next_offset < summary["open_tasks"],
            "summary": summary,
            "task_html": _render_dashboard_task_cards(tasks),
        }

    @app.get("/v1/tasks", response_model=list[OperatorTaskView])
    def list_tasks(
        source: str | None = Query(default=None, min_length=1),
        _identity: OperatorIdentity | None = Depends(authenticate),
    ) -> list[OperatorTaskView]:
        return [
            OperatorTaskView.from_task(task)
            for task in workstream.list_available(source=source)
        ]

    @app.get("/v1/tasks/{task_id}", response_model=OperatorTaskView)
    def get_task(
        task_id: str,
        _identity: OperatorIdentity | None = Depends(authenticate),
    ) -> OperatorTaskView:
        task = workstream.get(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
        return OperatorTaskView.from_task(task)

    @app.post("/v1/submissions", response_model=OperatorSubmissionReceipt)
    def submit_records(
        request: OperatorSubmissionRequest,
        identity: OperatorIdentity | None = Depends(authenticate),
    ) -> OperatorSubmissionReceipt:
        enforce_operator(identity, request.operator_id)
        task = workstream.get(request.task_id)
        if task is None:
            return OperatorSubmissionReceipt(
                submission_id=request.submission_id,
                task_id=request.task_id,
                operator_id=request.operator_id,
                accepted_count=0,
                rejected_count=len(request.records),
                duplicate_count=0,
                status="rejected",
                reasons=["task_not_found"],
            )
        envelope = request.to_internal_envelope(route_key=task.route_key)
        return intake.submit(envelope)

    @app.get("/v1/operators/{operator_id}/stats", response_model=OperatorStats)
    def get_operator_stats(
        operator_id: str,
        identity: OperatorIdentity | None = Depends(authenticate),
    ) -> OperatorStats:
        enforce_operator(identity, operator_id)
        return stats.get_operator_stats(operator_id)

    return app
