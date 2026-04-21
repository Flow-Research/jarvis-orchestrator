# SN13 Architecture

## Executive Summary

Jarvis operates on SN13 as a miner orchestration system.

Jarvis registers and serves as the miner. Personal operators do the scraping work outside the subnet. Operators submit source-native records to Jarvis. Jarvis validates, normalizes, deduplicates, stores, indexes, serves, and exports the data according to the SN13 miner contract.

This is an accountable miner-orchestration model. Jarvis is the accountable miner. Operators are upstream suppliers.

## System Contract

```text
Dynamic Desirability + Policy
        |
        v
Planner creates scrape demand
        |
        v
Operators receive tasks and scrape data
        |
        v
Operators submit structured records
        |
        v
Jarvis quality gate validates submissions
        |
        v
Accepted records enter canonical SQLite storage
        |
        v
Jarvis builds MinerIndex and bucket responses
        |
        v
Validators query Jarvis as the SN13 miner
        |
        v
Jarvis exports canonical data to S3/parquet when required
```

## Ownership Boundaries

| Capability | Owner | Notes |
| --- | --- | --- |
| Subnet registration | Jarvis | Jarvis owns the hotkey/miner identity. |
| Scraping execution | Operators | Operators collect raw public data. |
| Task selection | Jarvis | Planner decides what operators scrape. |
| Submission validation | Jarvis | Quality layer accepts or rejects every record. |
| Canonical miner storage | Jarvis | SQLite is the source of miner truth. |
| Miner index generation | Jarvis | Built only from accepted canonical records. |
| Validator responses | Jarvis | Served from canonical storage only. |
| S3/parquet export | Jarvis | Export is derived from canonical storage only. |
| Credibility risk | Jarvis | Validator failures affect Jarvis miner credibility. |
| Operator accounting | Jarvis | Operator quality/credit stats are internal. |

## External SN13 Contract

SN13 validators expect miners to expose data through these core concepts:

- `DataEntity`
- `DataEntityBucketId`
- `DataEntityBucket`
- `MinerIndex`
- `GetMinerIndex`
- `GetDataEntityBucket`
- `GetContentsByBuckets`

Jarvis mirrors those concepts in `subnets/sn13/models.py`.

Jarvis-specific metadata, such as `operator_id`, task assignment, scrape provenance, and payout attribution, is stored outside the canonical miner entity. It never defines validator-facing truth.

## Subsystems

### 1. Policy Core

Module: `subnets/sn13/policy.py`

Responsibilities:

- default freshness window
- bucket size limit
- miner index bucket count limit
- source weights
- credibility constants
- scorable versus non-scorable classification
- desirable date-window override support

Policy answers:

- is this entity scorable under the default freshness rule?
- does this desirable job override freshness?
- why is the entity not scorable?
- what protocol limits apply?

### 2. Dynamic Desirability

Module: `subnets/sn13/desirability.py`

Responsibilities:

- parse upstream Gravity-style desirability jobs
- normalize `platform`, `label`, `keyword`, and date windows
- match jobs against source/label/time buckets
- choose the highest-weight matching job
- feed desirable windows into policy classification

Desirability drives operator demand. Operators scrape the tasks Jarvis emits, not arbitrary labels.

### 3. Planner

Module: `subnets/sn13/planner.py`

Responsibilities:

- compare desirability jobs against current miner coverage
- identify underfilled buckets
- rank work by desirability weight, source weight, and freshness
- emit deterministic `OperatorDemand`

Planner output is the source of truth for operator scrape assignments.

### 4. Operator Task Runtime

Module: `subnets/sn13/tasks.py`

Responsibilities:

- convert `OperatorDemand` into pullable `OperatorTask`
- assign tasks to operators when requested
- ingest structured operator submissions
- run quality checks before storage writes

The current runtime is local/in-process. The production workstream transport will wrap this contract without changing the underlying task or submission schema.

### 5. Intake

Module: `subnets/sn13/intake.py`

Responsibilities:

- define `OperatorSubmission`
- require source, label, URI, timestamps, content, and provenance
- normalize labels, URIs, and timestamps
- convert accepted submissions into canonical `DataEntity`

Operators submit to intake. Operators do not write canonical miner records directly.

### 6. Quality Gate

Module: `subnets/sn13/quality.py`

Responsibilities:

- validate source-specific fields
- detect missing content
- detect URL/payload mismatch
- classify duplicate submissions
- classify accepted submissions as scorable or non-scorable
- return explicit reasons for rejection

Rejected data is audited but never enters canonical miner storage.

### 7. Canonical Storage

Module: `subnets/sn13/storage.py`

Storage backend:

- SQLite only

Tables:

- `data_entities`
- `operator_submissions`
- `rejected_submissions`
- `duplicate_observations`
- `operator_quality_stats`

Storage responsibilities:

- store accepted canonical entities
- preserve operator audit trail
- record rejection reasons
- record duplicate observations
- produce bucket queries
- produce miner index summaries
- expose operator quality stats

### 8. Miner Listener

Module: `subnets/sn13/listener/`

Responsibilities:

- listen as Jarvis miner on SN13
- handle `GetMinerIndex`
- handle `GetDataEntityBucket`
- handle `GetContentsByBuckets`
- record protocol observations
- serve from canonical SQLite storage

The listener does not perform fresh scraping on the validator hot path.

Current implementation status:

- the listener can attach SN13-style handlers and capture request shape
- the listener reads from canonical SQLite storage
- `protocol_adapter.py` binds exact upstream response field names:
  - `compressed_index_serialized`
  - `data_entities`
  - `bucket_ids_to_contents`
- compressed miner index output uses Macrocosm's `sources -> compressed buckets` shape
- live validator capture is still required before production readiness

### 9. Export Layer

Module: `subnets/sn13/export.py`

Responsibilities:

- generate parquet files from canonical SQLite only
- enforce source-specific export schema
- enforce filename record count correctness
- prepare S3-compatible file layout

Current implementation status:

- local parquet artifacts are generated for X and Reddit
- filenames follow `data_YYYYMMDD_HHMMSS_count_16hex.parquet`
- filename row count is validated against generated row count
- output paths include miner hotkey and Gravity job ID
- S3 API upload is not implemented in this module

## End-to-End Runtime Flow

### Planning Flow

1. Jarvis loads or refreshes Dynamic Desirability.
2. Jarvis reads current miner coverage from SQLite.
3. Planner computes underfilled desirable buckets.
4. Planner emits ranked operator demand.
5. Runtime converts demand into operator tasks.

### Operator Ingestion Flow

1. Operator pulls a task.
2. Operator scrapes source-native records.
3. Operator submits structured records to Jarvis.
4. Quality checker validates the submission.
5. Duplicate submissions are audited and rejected.
6. Valid submissions are classified as scorable or non-scorable.
7. Accepted submissions are stored canonically.
8. Operator stats are updated.

### Validator Serve Flow

1. Validator asks for miner index.
2. Jarvis builds index from canonical SQLite rows.
3. Validator selects bucket and requests data.
4. Jarvis returns canonical entities from storage.
5. Validator verifies data and assigns score/credibility impact.

### Export Flow

1. Export reads accepted canonical data.
2. Export builds source-specific rows.
3. Export writes parquet with correct record-count filename.
4. Export prepares files for S3 upload path.

## Current Guarantees

The current implementation guarantees:

- no markdown storage path remains
- canonical miner entities do not contain `operator_id`
- `time_bucket` is derived from source timestamp
- duplicates are detected before overwriting miner truth
- invalid operator submissions are rejected and audited
- planner demand is based on desirability and current coverage
- local operator runtime writes through quality checks
- local parquet export reads accepted canonical storage only
- local parquet export enforces upstream X and Reddit column sets

## Remaining Work

The remaining major gaps are:

- S3 API upload wrapper around generated parquet artifacts
- live SN13 protocol alignment from real captures
- production workstream transport
- robust migrations for SQLite schema changes
- operator payout/credit accounting beyond quality stats

## Non-Negotiable Design Rule

Jarvis must never expose unvalidated operator data to validators.

The only validator-facing data is accepted canonical data.
