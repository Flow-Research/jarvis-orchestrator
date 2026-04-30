# Workstream Architecture

## Purpose

Jarvis uses one operator workstream across all task sources and adapter types.

Personal operators do not integrate separately with SN13, ERC-8183, internal campaigns, or future task packages. Operators integrate with the Flow Workstream HTTP API. The orchestrator keeps the internal task route in durable storage and sends each upload to the correct adapter after resolving `task_id`.

## Core Rule

```text
One workstream HTTP API.
One workstream interface.
Many internal adapters.
Task-specific requirements travel inside generic workstream task contracts.
```

## Boundary Model

| Layer | Owns | Must Not Own |
| --- | --- | --- |
| `workstream/` | generic task publication, cap tracking, completion, submission envelopes, operator stats models | SN13 policy, source-specific validation, validator protocol |
| `workstream/api/` | HTTP transport implementation, public task views, auth, submission request parsing, internal route resolution by `task_id` | adapter business rules or public leakage of internal routes |
| adapter publication module | converting adapter-specific demand into generic workstream tasks | HTTP routing, shared operator auth, generic submission flow |
| adapter intake module | validating adapter-specific records or results | generic task discovery |
| adapter task module | adapter task contract shape | FastAPI implementation |

## Operator Flow

```text
Jarvis planner or demand source
        |
        v
Internal adapter creates task-specific contract
        |
        v
Generic workstream persists task with internal route + public contract
        |
        v
Workstream API exposes public task view to personal operators
        |
        v
Operators inspect open task
        |
        v
Operator uploads candidate records to shared submission endpoint
        |
        v
Workstream API resolves task_id to the internal adapter route
        |
        v
Adapter quality gate accepts, rejects, or marks duplicates
        |
        v
Operator stats update from accepted/rejected facts
```

## Why This Scales Across Work Types

Different adapters will ask for different work:

- SN13 asks for source-native data records.
- ERC-8183 work may ask for chain, token, metadata, or protocol-specific evidence.
- Internal campaigns may ask for research, enrichment, verification, or file outputs.
- A forecasting subnet may ask for forecasts plus evidence.
- A coding or research subnet may ask for files, traces, citations, or result bundles.

The API remains the same because task shape is generic:

- `task_id`
- `source` or category
- `contract`
- acceptance cap
- accepted progress
- expiry
- operator stats

The operator-facing part lives inside `contract`. The adapter route remains internal to the orchestrator.

## Current Implementation

Implemented now:

- `workstream/models.py`
- `workstream/ports.py`
- `workstream/store.py`
- `workstream/sqlite_store.py`
- `workstream/stats.py`
- `workstream/api/app.py`
- `workstream/api/auth.py`
- `workstream/api/runtime.py`
- `workstream/api/settings.py`
- `subnets/sn13/workstream.py`
- `subnets/sn13/api_adapter.py`
- `docs/skills/flow-workstream/SKILL.md`

Store policy:

- `InMemoryWorkstream` is for tests and throwaway local development only.
- `SQLiteWorkstream` is the durable single-node store for Flow Workstream deployments.
- `InMemoryOperatorStats` is test-only; the default SN13 runtime reads operator stats from canonical SN13 SQLite through `SN13OperatorStatsAdapter`.
- A distributed deployment can replace `SQLiteWorkstream` with Postgres or another durable queue without changing the workstream HTTP boundary or internal adapters.

## HTTP Surface

The shared workstream HTTP API exposes:

- `GET /`
- `GET /health`
- `GET /v1/tasks`
- `GET /v1/tasks/{task_id}`
- `POST /v1/submissions`
- `GET /v1/operators/{operator_id}/stats`

`GET /` is a read-only human dashboard for runtime inspection. It does not replace the Garden-authenticated Workstream API.

There is no SN13-specific public API route and no public route field in operator task or submission payloads. Adapter selection is internal: Jarvis resolves `task_id` to the durable task route, then calls the matching intake adapter.

## Submission Model

`POST /v1/submissions` accepts a strict public request. Extra fields are rejected at the API edge instead of being silently forwarded into intake.

Required envelope fields:

- `task_id`
- `operator_id`
- `records`

Required record fields:

- `uri`
- `source_created_at`
- `content`

Optional record fields:

- `submission_id`
- `source`
- `label`
- `scraped_at`
- `provenance`

Source-native payload belongs inside `records[*].content`. Top-level arbitrary record fields are not accepted. The orchestrator then attaches the internal route from the durable task record and the selected adapter applies the task contract, source-specific required fields, delivery limits, acceptance window, duplicate checks, and quality gate before any data reaches canonical storage.

## HTTP Auth

The workstream HTTP API uses Garden-backed identity verification through `workstream/api/auth.py`.

Operator-facing requests use Garden identity headers:

- `x-garden-user-id`
- `x-garden-workspace-id`
- `x-garden-session-token` when a Garden session token is available

Workstream calls `{GARDEN_BASE_URL}/api/internal/auth/verify` with `GARDEN_SERVICE_AUTH_TOKEN` and authorizes the request only when Garden returns `ok: true`. Workstream derives the operator id from the verified Garden user id; it does not issue or preload Workstream operator secrets.

## Admin Runtime

Internal administrators can serve the workstream HTTP boundary with:

```bash
GARDEN_BASE_URL=http://localhost:3000 \
GARDEN_SERVICE_AUTH_TOKEN='<garden-service-token>' \
jarvis-miner workstream serve
```

Default durable stores:

- `JARVIS_WORKSTREAM_DB_PATH=data/workstream.sqlite3`
- `JARVIS_SN13_DB_PATH=subnets/sn13/data/sn13.sqlite3`

`GARDEN_BASE_URL` is the Garden deployment Workstream verifies against. For local development this is usually `http://localhost:3000`; for production it is the Garden domain.

Task discovery is:

- `GET /v1/tasks`

There is no required `operator_id` query parameter on task listing. If auth is enabled, the workstream API derives identity from verified Garden headers.

Internal administrators publish SN13 tasks into the durable workstream with:

```bash
jarvis-miner sn13 plan publish --json-output
```

This keeps planning and publication separate:

- `sn13 plan tasks` shows intended work.
- `sn13 plan publish` writes stable task contracts into `SQLiteWorkstream`.

Published tasks are open for competitive submission. The normal SN13 flow is open publication, not per-operator reservation. Operators discover the same open tasks through the API, then submit results directly against the published contract. Flow Workstream closes the task when the accepted-cap is reached or the task expires.

Internal administrators inspect the runtime with:

```bash
jarvis-miner workstream status --json-output
jarvis-miner workstream tasks --status open --json-output
```

This keeps the control surface simple:

- `workstream serve` runs the HTTP boundary
- `/` shows the human-readable runtime dashboard
- `workstream status` reports configuration and counts
- `workstream tasks` shows what is actually published

## Operator Guide

The publishable operator instructions live in [Official Workstream Operator Skill](skills/flow-workstream/SKILL.md).

That guide is external-facing. It tells any personal operator agent:

- how to call the workstream API
- how to list and inspect tasks
- how to inspect the `contract`
- how to scrape or execute only what the contract asks for
- how to upload records to `/v1/submissions`
- how to check operator stats

Internal project-local skills under `.agents/skills/` are reserved for internal development and QA workflows.

## Production Gaps

Before real operators use this:

- add task visibility rules by capability
- add persistent accounting ledger
- add rate limits and payload size limits at API edge
