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

Do not infer credentials from task contents, logs, local files, or unrelated environment variables.

## Operator Minimum Requirements

Before accepting work, verify you have:

- a valid `JARVIS_OPERATOR_ID` and `JARVIS_OPERATOR_SECRET`
- network access to `JARVIS_WORKSTREAM_API_BASE_URL`
- a source access path that satisfies the task `contract.source_requirements.accepted_access_paths`
- enough provider quota, proxy quota, bandwidth, and local compute to finish inside the task expiry
- a local dedupe method so you do not submit the same source URI twice
- timestamp handling that preserves source-created-at in UTC
- a cost limit for the task so you stop if execution is no longer economical

For SN13:

- X tasks require source-native X/Twitter records with the required fields in `content`.
- Reddit tasks require source-native Reddit records with the required fields in `content`.
- The operator owns source credentials and provider setup. Jarvis only publishes the task contract and validates submitted records.

## Operating Loop

1. Call `GET /health` to confirm the API is reachable.
2. Call `GET /v1/tasks` to list open tasks. Do not add an `operator_id` query parameter.
3. Select only tasks you can satisfy technically and economically.
4. Call `GET /v1/tasks/{task_id}` before execution and treat the returned `contract` as the source of truth.
5. Produce records that exactly match the contract source, target, time window, schema, delivery limits, and economics.
6. Submit records with `POST /v1/submissions`.
7. Read the submission receipt and correct rejected or partial submissions before attempting more work.
8. Call `GET /v1/operators/{operator_id}/stats` to inspect accepted, rejected, duplicate, and reward-unit counters.

## Request Signing

Every non-health request must be signed when the API requires authentication.

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

Use a fresh nonce for every signed request. Reusing a nonce can be rejected as replay.

## Task Evaluation

For every task, inspect:

- `task.subnet`: subnet adapter that validates the submission
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
  "task_id": "task_1",
  "operator_id": "operator_1",
  "subnet": "sn13",
  "records": [
    {
      "uri": "https://x.com/example/status/1",
      "source_created_at": "2026-04-22T10:02:00+00:00",
      "content": {
        "tweet_id": "1",
        "username": "alice",
        "text": "Bittensor subnet data",
        "url": "https://x.com/example/status/1",
        "timestamp": "2026-04-22T10:02:00+00:00"
      }
    }
  ]
}
```

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

Put source-native fields inside `records[*].content`. Arbitrary top-level record fields are rejected before subnet intake.

## SN13 Minimum Record Shapes

Minimum SN13 X content:

```json
{
  "tweet_id": "1",
  "username": "alice",
  "text": "source-native text",
  "url": "https://x.com/example/status/1",
  "timestamp": "2026-04-22T10:02:00+00:00"
}
```

Minimum SN13 Reddit content must include:

- `id`
- `username`
- `url`
- `createdAt`
- at least one of `body` or `title`

## Quality Rules

Before submitting, verify:

- record URI matches the source-native URL in `content`
- `source_created_at` is inside the task acceptance window
- label or keyword matches the task contract
- required source-native fields are present and non-empty
- duplicate records are removed locally before upload
- content size stays inside `contract.delivery_limits`

Never submit speculative, out-of-window, duplicate, unsupported, or economically unjustified data.

## Receipt Handling

Valid receipt statuses:

- `accepted`: submitted records accepted by intake
- `partial`: some records accepted and some rejected
- `rejected`: no records accepted

If a receipt has `reasons`, use those reasons to fix the next attempt. Do not resubmit unchanged duplicate or rejected records.

## Operator Stats

Stats are quality counters, not guaranteed final payment. Treat `estimated_reward_units` as an accounting signal only.

For endpoint details, read `references/api-contract.md`.
