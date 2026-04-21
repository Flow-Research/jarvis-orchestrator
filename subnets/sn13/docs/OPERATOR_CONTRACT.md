# SN13 Operator Contract

## Purpose

This contract defines how personal operators participate in SN13 through Jarvis.

Operators do not join SN13. Operators do not serve validators. Operators do not write miner truth directly.

Operators receive tasks from Jarvis, scrape source data, and submit structured records. Jarvis validates every submission before it becomes canonical miner data.

## Operator Lifecycle

```text
Jarvis planner emits OperatorDemand
        |
        v
Runtime creates OperatorTask
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

## Operator Task

Module: `subnets/sn13/tasks.py`

Each task tells an operator:

- task ID
- source
- label
- optional keyword
- time bucket
- quantity target
- priority
- expiry
- assigned operator ID when assigned

Operators must treat tasks as the source of truth for what to scrape.

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

## Provenance

Required:

- `scraper_id`
- `query_type`

Optional:

- `query_value`
- `job_id`

Provenance is internal audit data. It is used for debugging, operator attribution, replay, and quality review.

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
- structured submission ingestion
- duplicate rejection
- quality classification
- canonical SQLite storage writes

## Non-Negotiable Rule

Operators submit evidence.

Jarvis decides whether that evidence becomes miner truth.
