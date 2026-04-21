# SN13 Implementation Plan

## Purpose

This document converts the SN13 design into a phased implementation sequence.

The goal is to keep work disciplined:

- one phase at a time
- clear deliverables
- clear exit criteria
- no mixing speculative work with core contract work

## Current State

Already completed:

- SN13 canonical miner model
- operator intake boundary
- SQLite-only storage
- listener serving from canonical storage
- base SN13 docs reset and rewritten
- Phase 1: Policy Core
- Phase 2: Desirability Layer
- Phase 3: Quality and Rejection Layer
- Phase 4: Operator Demand Planner
- Phase 5: Operator Task Contract and Intake Runtime

Current code foundation:

- `subnets/sn13/models.py`
- `subnets/sn13/intake.py`
- `subnets/sn13/policy.py`
- `subnets/sn13/desirability.py`
- `subnets/sn13/quality.py`
- `subnets/sn13/planner.py`
- `subnets/sn13/tasks.py`
- `subnets/sn13/storage.py`
- `subnets/sn13/listener/`

## Phase Order

1. Phase 1: Policy Core
2. Phase 2: Desirability Layer
3. Phase 3: Quality and Rejection Layer
4. Phase 4: Operator Demand Planner
5. Phase 5: Operator Task Contract and Intake Runtime
6. Phase 6: Export and Verification Readiness
7. Phase 7: Live Protocol Alignment
8. Phase 8: Production Hardening

## Phase 1: Policy Core

Status: completed.

### Goal

Define the local policy engine that describes what SN13 values and what Jarvis optimizes for.

### Why first

Without this, operators cannot be told what to scrape, and Jarvis cannot distinguish high-value from low-value data.

### Deliverables

- `subnets/sn13/policy.py`
- policy models for:
  - freshness window
  - bucket size limit
  - miner index bucket limit
  - source weights
  - credibility/scoring constants
  - desirable job override window
- tests for policy defaults and time-window behavior

### Minimum scope

- default freshness rule: 30 days
- bucket size limit: 128 MB
- miner index bucket count limit: 350,000
- configurable source weights
- configurable credibility parameters

### Exit criteria

- policy object can answer:
  - is this entity scorable?
  - why is it non-scorable?
  - what limits apply to this bucket/index?
- tests pass

## Phase 2: Desirability Layer

Status: completed.

### Goal

Represent Dynamic Desirability inside Jarvis in a way the planner can consume.

### Deliverables

- `subnets/sn13/desirability.py`
- local desirability snapshot format
- lookup by:
  - source
  - label
  - optional date range
- freshness override behavior for desirable jobs
- tests for job matching and window behavior

### Minimum scope

- cached desirability snapshot in local storage
- matching function for `source + label + time_bucket`
- default fallback when no desirability job exists

### Exit criteria

- Jarvis can compute whether a bucket is:
  - default-scored
  - desirability-boosted
  - outside valid date range

## Phase 3: Quality and Rejection Layer

Status: completed.

### Goal

Track whether incoming operator data is valid, duplicated, stale, or rejected.

### Deliverables

- storage schema expansion in `subnets/sn13/storage.py`
- rejection table
- operator quality stats table
- duplicate observation table
- `subnets/sn13/quality.py`
- rejection reason constants
- tests for acceptance/rejection paths

### Minimum scope

- classify each submission as:
  - `accepted_scorable`
  - `accepted_non_scorable`
  - `rejected`
- log reason for every rejection
- track duplicate submissions by normalized URI

### Exit criteria

- Jarvis can explain why any submission was rejected
- Jarvis can compute basic operator quality stats

## Phase 4: Operator Demand Planner

Status: completed.

### Goal

Translate policy, desirability, and coverage gaps into concrete scrape demand.

### Deliverables

- `subnets/sn13/planner.py`
- planner input model:
  - current DB coverage
  - desirability snapshot
  - freshness gaps
  - duplication estimate
- planner output model:
  - source
  - label
  - optional keyword
  - time window
  - priority
  - quantity target
  - expiry
- tests for prioritization

### Minimum scope

- prefer fresh high-desirability gaps
- deprioritize already-covered duplicated buckets
- emit deterministic tasks from same input state

### Exit criteria

- planner can produce a ranked scrape queue
- operator demand is generated from actual state, not guesswork

## Phase 5: Operator Task Contract and Intake Runtime

Status: completed.

### Goal

Make Jarvis tell operators exactly what to scrape and accept their results through a real runtime path.

### Deliverables

- `subnets/sn13/tasks.py`
- operator task schema
- intake service or command path for structured submission writes
- storage integration from task output to canonical entities
- tests for end-to-end task -> submission -> storage

### Minimum scope

- one operator task format
- one submission ingestion entrypoint
- direct write into SQLite

### Exit criteria

- operators can receive structured jobs
- operators can submit results without file intermediaries
- Jarvis stores accepted results canonically

## Phase 6: Export and Verification Readiness

Status: implemented locally.

### Goal

Prepare canonical data for SN13-compatible export and future validation needs.

### Deliverables

- `subnets/sn13/export.py`
- parquet export from canonical SQLite
- filename rules
- path rules
- tests for row count and naming correctness
- tests for source-specific X and Reddit schemas

### Minimum scope

- export accepted canonical records only
- deterministic filename generation
- row count in filename must match actual row count
- exact upstream X and Reddit column sets

### Exit criteria

- Jarvis can generate export files from SQLite correctly
- export logic is not coupled to operator data directly
- generated parquet files can be read and row-count checked locally

### Remaining follow-up

- implement authenticated S3 upload around generated artifacts
- confirm live validator behavior for partitioned paths and upload API responses

## Phase 7: Live Protocol Alignment

Status: adapter implemented; live capture still required.

### Goal

Use real SN13 captures to tighten listener behavior and response shape.

### Deliverables

- `subnets/sn13/listener/protocol_adapter.py`
- exact `GetMinerIndex.compressed_index_serialized` response binding
- exact `GetDataEntityBucket.data_entities` response binding
- exact `GetContentsByBuckets.bucket_ids_to_contents` response binding
- compatibility tests for protocol field names and compressed index shape
- refreshed capture corpus
- query inventory
- documented request/response differences from earlier assumptions

### Minimum scope

- bind response fields according to upstream `common/protocol.py`
- serialize compressed miner index according to upstream `common/data.py`
- verify actual live query payloads
- verify timeout behavior empirically

### Exit criteria

- adapter tests prove upstream field names and compressed index shape
- listener behavior reflects live SN13 traffic, not mock assumptions
- real validator captures confirm request version, timeout, and payload shape

## Phase 8: Production Hardening

### Goal

Stabilize SN13 for repeated real operation.

### Deliverables

- migration handling for SQLite schema changes
- operator replay/backfill support
- monitoring metrics
- cleanup jobs
- runbook

### Minimum scope

- health checks
- recovery behavior
- basic maintenance commands

### Exit criteria

- SN13 subsystem can run without manual repo surgery each time

## Working Rule

Only one phase is actively implemented at a time.

Allowed overlap:

- minor bugfixes in earlier phases
- tests/docs updates needed by the active phase

Not allowed:

- jumping ahead into export or orchestration before policy and quality exist

## Immediate Next Step

Start Phase 6 by implementing:

- `subnets/sn13/export.py`
- parquet export from canonical SQLite
- tests for filename, row count, and source-specific schema

That is the next correct unit of work.
