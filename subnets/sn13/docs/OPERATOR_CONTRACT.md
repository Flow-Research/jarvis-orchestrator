# SN13 Operator Contract

## Purpose

This contract defines how personal operators participate in SN13 through Jarvis.

Operators do not join SN13. Operators do not serve validators. Operators do not write miner truth directly.

Operators receive tasks from Jarvis, scrape source data, and submit structured records. Jarvis validates every submission before it becomes canonical miner data.

SN13 is not a general task-decomposition subnet for Jarvis. Validators query miner data. Jarvis therefore uses real Gravity/Dynamic Desirability plus its current coverage gaps to create proactive scrape tasks for operators.

## Operator Lifecycle

```text
Real Gravity cache + SQLite coverage
        |
        v
Jarvis planner emits OperatorDemand
        |
        v
Runtime creates OperatorTaskContract
        |
        v
Jarvis publishes open task to workstream
        |
        v
Operators inspect open task through the workstream API
        |
        v
Operator executes scrape
        |
        v
Operator submits OperatorSubmission
        |
        v
Jarvis quality gate accepts or rejects
        |
        v
Accepted records enter SQLite canonical storage
```

## Operator Task Contract

Module: `subnets/sn13/tasks.py`

Each workstream task tells an operator:

- task ID
- demand ID
- source
- label
- optional keyword
- source-created-at time window
- quantity target
- priority
- Gravity desirability job ID and weight when present
- expiry
- required source-native payload fields
- allowed source access/provider paths
- upload record and byte limits
- payout basis and payable record cap
- operator cost-estimate requirement
- minimum requirements enforced by intake
- acceptance criteria Jarvis will enforce

Operators must treat tasks as the source of truth for what to scrape.

Jarvis publishes `OperatorTaskContract` payloads to the workstream. Operators do not infer desired topics from validator traffic. Desired topics come from Gravity and policy.

Published tasks are open to operators. Jarvis does not pin SN13 work to specific operators in the normal flow. Multiple operators can compete on the same task while the task remains open.

This is a publish-and-enforce model:

- publish the exact scrape requirement to the workstream
- accept only submissions tied to that requirement
- keep the task open until the accepted-cap is reached or the task expires
- reject records that fail source, time-window, schema, duplicate, byte-limit, or quality rules
- store only accepted records as miner truth

## Task-Level Economics

Each task includes `economics`:

| Field | Meaning |
| --- | --- |
| `payout_basis` | Default is accepted scorable record. |
| `payable_records_cap` | Maximum records payable for this task. |
| `submitted_volume_not_payable` | Raw submitted volume does not earn payout. |
| `duplicate_records_not_payable` | Duplicate URIs are not payable. |
| `rejected_records_not_payable` | Rejected records are not payable. |
| `validation_failure_can_zero_payable_records` | Failed validation can zero payable records. |
| `operator_cost_estimate_required` | Operator must estimate its own scrape/provider/proxy cost before execution. |
| `operator_cost_estimate_currency` | Currency used for operator-side estimate. |

Jarvis does not guarantee operator profitability. The task exposes enough information for an operator to estimate cost before execution. Jarvis pays only under the published payout basis after intake quality gates.

## Upload Limits

Each task includes `delivery_limits`:

| Field | Meaning |
| --- | --- |
| `max_records` | Maximum records Jarvis accepts for this task. Defaults to the task quantity target. |
| `max_content_bytes_per_record` | Maximum content payload size per submitted record. |
| `max_total_content_bytes` | Maximum total content bytes for the task. |
| `uploads_over_limit_rejected` | Over-limit uploads are rejected. |

There is no unlimited upload path. More data is useful only when it is inside the task contract, inside the source time window, not duplicated, and accepted by the quality gate.

## Enforcement Model

Jarvis does not need to pre-verify every operator runtime before task visibility.

The task contract publishes the requirements. Intake enforces the requirements:

- task target must match
- source-created-at must match the task window
- source payload schema must pass
- source URI must be unique
- upload limits must be respected
- rejected data never enters canonical miner storage
- non-payable data does not create payout liability

## Operator Submission

Module: `subnets/sn13/intake.py`

Each submission must include:

| Field | Required | Meaning |
| --- | --- | --- |
| `submission_id` | yes | Idempotency key for this submitted result. |
| `operator_id` | yes | Jarvis-issued operator identity. |
| `source` | yes | Source platform, currently `X` or `REDDIT`. |
| `label` | yes for current flows | Topic/subreddit/hashtag used for bucketing. |
| `uri` | yes | Canonical external source URI. |
| `source_created_at` | yes | Timestamp from the source object. |
| `scraped_at` | yes | Timestamp when the operator collected it. |
| `content` | yes | Source-native structured payload. |
| `provenance` | yes | Scraper/task audit metadata. |

Jarvis derives `time_bucket` from `source_created_at`.

## X Submission Payload

Required content fields:

- `tweet_id`
- `username`
- `text`
- `url`
- `timestamp`

Recommended content fields:

- `tweet_hashtags`
- `media`
- `user_id`
- `user_display_name`
- `user_verified`
- `is_reply`
- `is_quote`
- `conversation_id`
- `in_reply_to_user_id`
- `in_reply_to_username`
- `quoted_tweet_id`
- `like_count`
- `retweet_count`
- `reply_count`
- `quote_count`
- `view_count`
- `bookmark_count`
- `language`
- `scrapedAt`

Validation:

- `url` must match submission `uri` after normalization
- `text` must be non-empty
- required fields must be present
- `source_created_at` must fall inside the task acceptance window
- submission provenance must point back to the published task/job

## Reddit Submission Payload

Required content fields:

- `id`
- `username`
- `url`
- `createdAt`
- one of `body` or `title`

Recommended content fields:

- `communityName`
- `dataType`
- `parentId`
- `media`
- `is_nsfw`
- `score`
- `upvote_ratio`
- `num_comments`
- `scrapedAt`

Validation:

- `url` must match submission `uri` after normalization
- one of `body` or `title` must be non-empty
- required fields must be present
- `source_created_at` must fall inside the task acceptance window
- submission provenance must point back to the published task/job

## Provenance

Required:

- `scraper_id`
- `query_type`

Optional:

- `query_value`
- `job_id`

Provenance is internal audit data. It is used for debugging, operator attribution, replay, and quality review. For Gravity-derived tasks, `job_id` should match the task's `desirability_job_id` or `demand_id`.

## Access and Minimum Capability

Operators execute a task only when they have a valid source path for that task source.

Accepted X paths:

- Apify X actor token path
- Macrocosmos X API key path
- Jarvis-approved X operator provider path

Accepted Reddit paths:

- Reddit API credentials path
- Jarvis-approved Reddit operator provider path

Jarvis readiness decides whether a source task can be published. Operator-level capability decides whether an individual operator should execute a specific task. Intake remains the enforcement boundary.

## Acceptance Outcomes

### `accepted_scorable`

The submission is valid and currently valuable under policy/desirability rules.

### `accepted_non_scorable`

The submission is valid but not currently valuable under scoring rules.

### `rejected`

The submission is invalid or unsafe for miner truth.

Current rejection reasons:

- `duplicate_entity`
- `missing_source_field`
- `source_payload_mismatch`
- `empty_content`

## Operator Quality Stats

Jarvis tracks:

- accepted scorable count
- accepted non-scorable count
- rejection count
- duplicate count
- latest update timestamp

These stats are internal. They will later feed operator ranking, throttling, and payout accounting.

## Current Implementation

Implemented modules:

- `subnets/sn13/intake.py`
- `subnets/sn13/quality.py`
- `subnets/sn13/tasks.py`
- `subnets/sn13/storage.py`

The runtime path already supports:

- planner demand to task conversion
- workstream task contract generation
- structured submission ingestion
- duplicate rejection
- quality classification
- upload limits and economics in task contract
- canonical SQLite storage writes

## Non-Negotiable Rule

Operators submit evidence.

Jarvis decides whether that evidence becomes miner truth.
