# Workstream Architecture

## Purpose

Jarvis uses one operator workstream across all subnets.

Personal operators do not integrate separately with SN13, SN6, or future subnet packages. Operators integrate with the Jarvis workstream HTTP API. Jarvis routes each task and upload to the correct subnet adapter based on the task contract.

## Core Rule

```text
One workstream HTTP API.
One workstream interface.
Many subnet adapters.
Subnet-specific contracts travel inside generic workstream tasks.
```

## Boundary Model

| Layer | Owns | Must Not Own |
| --- | --- | --- |
| `workstream/` | generic task publication, cap tracking, completion, submission envelopes, operator stats models | SN13 policy, source-specific validation, validator protocol |
| `workstream/api/` | HTTP transport implementation for the workstream boundary | subnet business rules |
| `subnets/<subnet>/workstream.py` | converting subnet tasks into generic workstream tasks | HTTP routing, shared operator auth, generic submission flow |
| `subnets/<subnet>/intake.py` | validating subnet-specific records | generic task discovery |
| `subnets/<subnet>/tasks.py` | subnet task contract shape | FastAPI implementation |

## Operator Flow

```text
Jarvis subnet planner
        |
        v
Subnet adapter creates subnet-specific task contract
        |
        v
Generic workstream publishes task with subnet + contract
        |
        v
Workstream API exposes tasks to personal operators
        |
        v
Operators inspect open task
        |
        v
Operator uploads candidate records to shared submission endpoint
        |
        v
Router sends upload to subnet-specific intake adapter
        |
        v
Subnet quality gate accepts, rejects, or marks duplicates
        |
        v
Operator stats update from accepted/rejected facts
```

## Why This Scales Across Subnets

Different subnets will ask for different work:

- SN13 asks for source-native data records.
- A forecasting subnet may ask for forecasts plus evidence.
- A coding or research subnet may ask for files, traces, citations, or result bundles.

The API remains the same because task shape is generic:

- `task_id`
- `subnet`
- `source` or category
- `contract`
- acceptance cap
- accepted progress
- expiry
- operator stats

The subnet-specific part lives inside `contract` and inside the subnet intake adapter.

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
- `docs/skills/jarvis-workstream/SKILL.md`

Store policy:

- `InMemoryWorkstream` is for tests and throwaway local development only.
- `SQLiteWorkstream` is the durable single-node workstream store for Jarvis-controlled deployments.
- `InMemoryOperatorStats` is test-only; the default SN13 runtime reads operator stats from canonical SN13 SQLite through `SN13OperatorStatsAdapter`.
- A distributed deployment can replace `SQLiteWorkstream` with Postgres or another durable queue without changing the workstream HTTP boundary or subnet adapters.

## HTTP Surface

The shared workstream HTTP API exposes:

- `GET /health`
- `GET /v1/tasks`
- `GET /v1/tasks/{task_id}`
- `POST /v1/submissions`
- `GET /v1/operators/{operator_id}/stats`

There is no SN13-specific public API route. SN13-specific logic is selected by the task `subnet` and enforced by the SN13 adapter.

## Submission Model

`POST /v1/submissions` accepts a strict envelope. Extra fields are rejected at the API edge instead of being silently forwarded into SN13 intake.

Required envelope fields:

- `task_id`
- `operator_id`
- `subnet`
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

Source-native payload belongs inside `records[*].content`. Top-level arbitrary record fields are not accepted. SN13 then applies the task contract, source-specific required fields, delivery limits, acceptance window, duplicate checks, and quality gate before any data reaches canonical SQLite.

## HTTP Auth

The workstream HTTP API supports signed requests through `workstream/api/auth.py`.

Signed requests use these headers:

- `x-jarvis-operator`
- `x-jarvis-timestamp`
- `x-jarvis-nonce`
- `x-jarvis-signature`

The signature is HMAC-SHA256 over method, path/query, body hash, timestamp, and nonce. The operator ID in the signed headers must match the operator ID in submission and stats requests. Nonces are rejected on replay inside a single API process.

For multi-process or distributed API deployments, replace the in-memory nonce store with a durable shared nonce store before exposing the API to untrusted operators.

## Admin Runtime

Jarvis administrators can serve the workstream HTTP boundary with:

```bash
JARVIS_OPERATOR_ID=operator_1 \
JARVIS_OPERATOR_SECRET=<shared-secret> \
jarvis-miner workstream serve
```

Default durable stores:

- `JARVIS_WORKSTREAM_DB_PATH=data/workstream.sqlite3`
- `JARVIS_SN13_DB_PATH=subnets/sn13/data/sn13.sqlite3`

For multiple operators, set `JARVIS_OPERATOR_SECRETS_JSON` to a JSON object mapping operator IDs to HMAC secrets. The effective operator count is the number of entries in that map.

Task discovery is:

- `GET /v1/tasks`

There is no required `operator_id` query parameter on task listing. If auth is enabled, the workstream API derives identity from the signed headers.

Jarvis administrators publish SN13 tasks into the durable workstream with:

```bash
jarvis-miner sn13 plan publish --json-output
```

This keeps planning and publication separate:

- `sn13 plan tasks` shows intended work.
- `sn13 plan publish` writes stable task contracts into `SQLiteWorkstream`.

Published tasks are open for competitive submission. The normal SN13 flow is not pinned assignment. Operators discover the same open tasks through the API, then submit results directly against the published contract. Jarvis closes the task when the accepted-cap is reached or the task expires.

Jarvis administrators inspect the runtime with:

```bash
jarvis-miner workstream status --json-output
jarvis-miner workstream tasks --status open --json-output
```

This keeps the control surface simple:

- `workstream serve` runs the HTTP boundary
- `workstream status` reports configuration and counts
- `workstream tasks` shows what is actually published

## Operator Guide

The publishable operator instructions live in [Official Workstream Operator Skill](skills/jarvis-workstream/SKILL.md).

That guide is external-facing. It tells any personal operator agent:

- how to call the workstream API
- how to list and inspect tasks
- how to inspect the `contract`
- how to scrape or execute only what the contract asks for
- how to upload records to `/v1/submissions`
- how to check operator stats

Internal project-local skills under `.agents/skills/` are reserved for Jarvis development and QA workflows.

## Production Gaps

Before real operators use this:

- add task visibility rules by capability
- add persistent accounting ledger
- add rate limits and payload size limits at API edge
- replace in-memory nonce replay protection for distributed deployments
