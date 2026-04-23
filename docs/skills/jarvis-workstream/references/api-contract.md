# Jarvis Workstream API Contract

## Boundary

Personal operators use this API to discover tasks, submit records, and inspect quality counters.

Base URL comes from `JARVIS_WORKSTREAM_API_BASE_URL`.

When auth is enabled, `GET /v1/tasks` does not require an `operator_id` query parameter. Identity comes from the signed headers.

Jarvis does not provide source scraper credentials through this API. Source credentials, provider access, quota, and execution cost belong to the operator.

## Credentials

Operators receive either runtime environment values or a per-operator tester JSON file.

Tester JSON fields:

```json
{
  "base_url": "https://example.ngrok-free.app",
  "operator_id": "company_tester_01",
  "operator_secret": "secret-value"
}
```

Map these to:

- `base_url` -> `JARVIS_WORKSTREAM_API_BASE_URL`
- `operator_id` -> `JARVIS_OPERATOR_ID`
- `operator_secret` -> `JARVIS_OPERATOR_SECRET`

The server-side secret map is private infrastructure and is never needed by an operator agent.

## Authentication

`GET /health` and the human dashboard are public. Treat every `/v1/*` endpoint as signed.

Required headers:

- `x-jarvis-operator`: configured operator id
- `x-jarvis-timestamp`: Unix timestamp in seconds
- `x-jarvis-nonce`: unique value per request
- `x-jarvis-signature`: hex HMAC-SHA256 signature

Canonical string:

```text
JARVIS-OPERATOR-HMAC-SHA256
<METHOD>
<PATH_WITH_QUERY>
<SHA256_HEX_BODY>
<TIMESTAMP>
<NONCE>
```

`PATH_WITH_QUERY` must include the exact query string when present. For example, if calling `/v1/tasks?source=SOURCE_NAME`, sign that full path with query.

The HMAC key is `JARVIS_OPERATOR_SECRET`. Reusing a nonce or signing with the wrong path, body hash, timestamp, or secret returns `401`.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness check. |
| `GET` | `/v1/tasks` | List currently available tasks. |
| `GET` | `/v1/tasks/{task_id}` | Inspect one task and its contract. |
| `POST` | `/v1/submissions` | Submit candidate records for quality-gated intake. |
| `GET` | `/v1/operators/{operator_id}/stats` | Read accepted/rejected/duplicate counters. |

`GET /v1/tasks` supports optional filters:

- `source`: source or work category, when the deployment exposes a useful source filter
- `subnet`: internal routing namespace, only when the deployment or task owner explicitly tells you to filter by it

The `operator_id` in a submission envelope and stats path must match the signed identity. A mismatch returns `403`.

## Submission Envelope

```json
{
  "task_id": "<copy task.task_id>",
  "operator_id": "company_tester_01",
  "subnet": "<copy task.subnet>",
  "records": [
    {
      "uri": "https://source.example/item/1",
      "source_created_at": "2026-04-22T10:02:00+00:00",
      "content": {
        "required_field_from_contract": "source-native value",
        "url": "https://source.example/item/1"
      }
    }
  ]
}
```

Envelope and record models are strict. Unknown top-level fields are rejected. Put source-native fields inside `records[*].content`.

All external datetimes must include an explicit timezone offset. Use `Z` or `+00:00`; do not send naive timestamps such as `2026-04-22T10:02:00`.

The `subnet` field is the current API name for the routing namespace that selects the correct intake adapter. Operators should copy it from the task response and should not need to know where the work originated.

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

## Acceptance Rules

Jarvis rejects records when:

- the envelope routing namespace does not match the task
- the task does not exist
- the task is cancelled, expired, or already full
- the upload exceeds `contract.delivery_limits`
- source-created-at is outside `contract.acceptance`
- target, label, keyword, or category does not match the contract
- required source-native fields are missing
- source URI and content URL disagree
- the URI is a duplicate of already accepted canonical data

The task contract is authoritative:

- `contract.source_requirements.required_content_fields` lists required source-native fields.
- `contract.source_requirements.any_of_content_fields` lists alternative field groups.
- `contract.acceptance` defines source-created-at and target gates.
- `contract.minimum_requirements` gives a plain-language checklist for the task.

Accepted records enter canonical storage only after intake and quality checks pass.

Accepted counters are quality/accounting signals. They are not final subnet payment guarantees.
