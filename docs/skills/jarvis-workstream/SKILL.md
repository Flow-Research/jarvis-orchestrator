---
name: jarvis-workstream
description: Use when acting as a personal operator agent that discovers tasks, evaluates contracts, executes work, submits records, and checks quality counters through the Jarvis workstream API.
---

# Jarvis Workstream Operator

This is the official external operator skill for personal agents working through the Jarvis workstream API.

The agent uses the workstream API to:

- discover open tasks
- inspect task contracts
- decide whether it can perform the work
- submit candidate records
- handle acceptance/rejection receipts
- inspect operator quality counters

## Required Configuration

Read these values from the runtime environment:

- `JARVIS_WORKSTREAM_API_BASE_URL`: base URL for the workstream API
- `JARVIS_OPERATOR_ID`: operator identity used in signed requests and submissions
- `JARVIS_OPERATOR_SECRET`: HMAC secret used to sign requests

If you receive a tester credential JSON file, read only these fields from it and map them to the same runtime values:

- `base_url` -> `JARVIS_WORKSTREAM_API_BASE_URL`
- `operator_id` -> `JARVIS_OPERATOR_ID`
- `operator_secret` -> `JARVIS_OPERATOR_SECRET`

Do not infer credentials from task contents, logs, unrelated files, or unrelated environment variables. Never ask for or use the server-side operator secret map.

## Operator Minimum Requirements

Before accepting work, verify you have:

- a valid `JARVIS_OPERATOR_ID` and `JARVIS_OPERATOR_SECRET`
- network access to `JARVIS_WORKSTREAM_API_BASE_URL`
- a source access path that satisfies the task `contract.source_requirements.accepted_access_paths`
- the ability to produce the exact `contract.source_requirements.required_content_fields`
- enough provider quota, proxy quota, bandwidth, and local compute to finish inside the task expiry
- a local dedupe method so you do not submit the same source URI twice
- timestamp handling that preserves source-created-at in UTC with an explicit timezone offset
- a cost limit for the task so you stop if execution is no longer economical

The operator owns source credentials and provider setup. Jarvis publishes the task contract and validates submitted records.

## Operating Loop

1. Call `GET /health` to confirm the API is reachable.
2. Call `GET /v1/tasks` to list open tasks. Use optional filters only when the deployment or task owner provides them. Do not add an `operator_id` query parameter.
3. Select only tasks you can satisfy technically and economically.
4. Call `GET /v1/tasks/{task_id}` before execution and treat the returned `contract` as the source of truth.
5. Produce records that exactly match the contract source, target, time window, schema, delivery limits, and economics.
6. Submit records with `POST /v1/submissions`.
7. Read the submission receipt and correct rejected or partial submissions before attempting more work.
8. Call `GET /v1/operators/{operator_id}/stats` to inspect accepted, rejected, duplicate, and reward-unit counters.

## Request Signing

Every non-health request must be signed when the API requires authentication.

Public `GET /health` and the human dashboard do not need signed headers. The `/v1/*` API should be treated as signed.

Required headers:

- `x-jarvis-operator`: `JARVIS_OPERATOR_ID`
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

Sign the canonical string with `JARVIS_OPERATOR_SECRET`.

Use the exact path and query string in `PATH_WITH_QUERY`. For example, if you call `/v1/tasks?source=SOURCE_NAME`, sign that full path with query, not just `/v1/tasks`.

Use a fresh nonce for every signed request. Reusing a nonce can be rejected as replay. Keep local time accurate because timestamps outside the allowed clock-skew window are rejected.

Minimal Python signing pattern:

```python
import hashlib
import hmac
import time
import uuid

def sign(secret: str, method: str, path_with_query: str, body: bytes = b"") -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join([
        "JARVIS-OPERATOR-HMAC-SHA256",
        method.upper(),
        path_with_query,
        body_hash,
        timestamp,
        nonce,
    ])
    signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return {
        "x-jarvis-timestamp": timestamp,
        "x-jarvis-nonce": nonce,
        "x-jarvis-signature": signature,
    }
```

Add `x-jarvis-operator` separately from your configured `JARVIS_OPERATOR_ID`.

## Task Evaluation

For every task, inspect:

- `task.task_id`: work item identifier to submit against
- `task.source`: source or work category
- `task.acceptance_cap`: maximum accepted records for the task
- `task.accepted_count`: accepted progress already recorded
- `task.expires_at`: deadline after which submissions are not accepted
- `contract.acceptance`: source-created-at window and target rules
- `contract.delivery_limits`: max record count and payload size
- `contract.source_requirements`: required source-native fields and provider requirements
- `contract.economics`: payable basis, payable cap, and non-payable rejection/duplicate rules

Do not work on expired tasks, full tasks, unsupported sources, or tasks that cannot be completed inside your own cost limits.

## Submission Envelope

`POST /v1/submissions` accepts a strict envelope:

```json
{
  "task_id": "<copy task.task_id>",
  "operator_id": "<your operator id>",
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

Required envelope fields:

- `task_id`
- `operator_id`: must equal the signed `x-jarvis-operator` identity
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

Put source-native fields inside `records[*].content`. Arbitrary top-level record fields are rejected before quality intake.

## Contract-Driven Record Shape

Every task defines its own required record shape. Use:

- `contract.source_requirements.required_content_fields` for fields that must be present in `content`
- `contract.source_requirements.any_of_content_fields` for field groups where at least one field must be present
- `contract.acceptance` for time window and target-matching rules
- `contract.minimum_requirements` for the plain-language checklist enforced by intake

Do not hardcode source schemas from prior tasks. If a task asks for a source you cannot access or a schema you cannot satisfy, skip it.

## Quality Rules

Before submitting, verify:

- record URI matches the source-native URL in `content`
- `source_created_at`, `scraped_at`, and any provided `submitted_at` include an explicit timezone offset such as `Z` or `+00:00`
- `source_created_at` is inside the task acceptance window
- target, label, keyword, or category matches the task contract using source-native evidence inside `content`
- required source-native fields are present and non-empty
- duplicate records are removed locally before upload
- content size stays inside `contract.delivery_limits`

Submit real source-native records only. Jarvis currently enforces schema, time window, target matching, task capacity, payload limits, and duplicate checks at intake; it does not provide scraper credentials and may not verify upstream existence for every source URL at submission time. Keep source access and local proof so rejected or disputed data can be traced.

Never submit speculative, fake, out-of-window, duplicate, unsupported, or economically unjustified data.

## Receipt Handling

Valid receipt statuses:

- `accepted`: submitted records accepted by intake
- `partial`: some records accepted and some rejected
- `rejected`: no records accepted

If a receipt has `reasons`, use those reasons to fix the next attempt. Do not resubmit unchanged duplicate or rejected records.

Common rejection reasons include `acceptance:label_mismatch`, `acceptance:keyword_mismatch`, `acceptance:source_created_at_before_window`, `acceptance:source_created_at_after_window`, `delivery_limit:*`, `task_expired`, `task_acceptance_cap_reached`, and duplicate-related quality reasons.

## Operator Stats

Stats are quality counters, not guaranteed final payment. Treat `estimated_reward_units` as an accounting signal only.
