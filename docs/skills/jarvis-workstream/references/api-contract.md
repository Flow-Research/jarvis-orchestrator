# Jarvis Workstream API Contract

## Boundary

Personal operators use this API to discover tasks, submit records, and inspect quality counters.

Base URL comes from `JARVIS_WORKSTREAM_API_BASE_URL`.

When auth is enabled, `GET /v1/tasks` does not require an `operator_id` query parameter. Identity comes from the signed headers.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness check. |
| `GET` | `/v1/tasks` | List currently available tasks. |
| `GET` | `/v1/tasks/{task_id}` | Inspect one task and its contract. |
| `POST` | `/v1/submissions` | Submit candidate records for quality-gated intake. |
| `GET` | `/v1/operators/{operator_id}/stats` | Read accepted/rejected/duplicate counters. |

## Submission Receipt

```json
{
  "submission_id": "opsub_...",
  "task_id": "task_1",
  "operator_id": "operator_1",
  "accepted_count": 1,
  "rejected_count": 0,
  "duplicate_count": 0,
  "status": "accepted",
  "reasons": []
}
```

## SN13 Acceptance Rules

SN13 rejects records when:

- the envelope subnet is not `sn13`
- the task does not exist
- the task is cancelled, expired, or already full
- the upload exceeds `contract.delivery_limits`
- source-created-at is outside `contract.acceptance`
- label or keyword does not match the contract
- required source-native fields are missing
- source URI and content URL disagree
- the URI is a duplicate of canonical miner data

Accepted records enter canonical SN13 storage only after intake and quality checks pass.
