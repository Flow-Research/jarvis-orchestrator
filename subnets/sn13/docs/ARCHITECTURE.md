# SN13 Architecture

## Executive Summary

Jarvis operates on SN13 as a miner orchestration system.

Jarvis registers and serves as the miner. Personal operators do the scraping work outside the subnet. Operators submit source-native records to Jarvis. Jarvis validates, normalizes, deduplicates, stores, indexes, serves, and exports the data according to the SN13 miner contract.

This is an accountable miner-orchestration model. Jarvis is the accountable miner. Operators are upstream suppliers.

## System Contract

```text
Real Gravity cache + Policy
        |
        v
Planner creates scrape demand
        |
        v
Jarvis publishes open tasks to durable workstream
        |
        v
Operators read open tasks through the workstream API and scrape data
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
        |
        v
Jarvis archives exported parquet to Jarvis-owned S3
```

## Ownership Boundaries

| Capability | Owner | Notes |
| --- | --- | --- |
| Subnet registration | Jarvis | Jarvis owns the hotkey/miner identity. |
| Scraping execution | Operators | Operators collect raw public data. |
| Gravity/DD cache | Jarvis | Jarvis refreshes real public Gravity demand and treats sample DD as development-only. |
| Task publication | Jarvis | Planner decides what operators scrape from real desirability and current coverage gaps. |
| Scrape cost estimate | Operator | Task contract requires operators to estimate their own provider/proxy/compute cost before execution. |
| Submission validation | Jarvis | Quality layer accepts or rejects every record. |
| Canonical miner storage | Jarvis | SQLite is the source of miner truth. |
| Miner index generation | Jarvis | Built only from accepted canonical records. |
| Validator responses | Jarvis | Served from canonical storage only. |
| Upstream S3/parquet export | Jarvis | Export is derived from canonical storage only and uploaded through upstream presigned flow. |
| Jarvis archive S3 | Jarvis | Parallel paid archive path for exported parquet. |
| Local export retention | Jarvis | Temporary parquet staging is deleted only after upstream upload and archive upload both succeed. |
| Minimum readiness and economic gates | Jarvis | Jarvis decides whether it can serve validators, publish tasks, intake uploads, export upstream S3, and archive to Jarvis S3. |
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

Jarvis-specific metadata, such as `operator_id`, scrape provenance, and payout attribution, is stored outside the canonical miner entity. It never defines validator-facing truth.

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

Modules:

- `subnets/sn13/gravity.py`
- `subnets/sn13/desirability.py`

Responsibilities:

- fetch the public Gravity aggregate `total.json`
- cache the real aggregate locally with metadata and content hash
- parse upstream Gravity-style desirability jobs
- normalize `platform`, `label`, `keyword`, and date windows
- match jobs against source/label/time buckets
- choose the highest-weight matching job
- feed desirable windows into policy classification

Desirability drives operator demand. Operators scrape the tasks Jarvis emits, not arbitrary labels. The default operational path is real Gravity cache. Built-in sample demand exists only for tests and local development.

### 3. Planner

Module: `subnets/sn13/planner.py`

Responsibilities:

- compare desirability jobs against current miner coverage
- suppress sources not yet enabled in `PlannerConfig.supported_sources`
- identify underfilled buckets
- rank work by desirability weight, source weight, and freshness
- emit deterministic `OperatorDemand`

Planner output is the source of truth for open workstream demand.

### 4. Operator Task Runtime

Module: `subnets/sn13/tasks.py`

Responsibilities:

- convert `OperatorDemand` into pullable `OperatorTask`
- expose `OperatorTaskContract` for workstream transport
- carry source-specific content fields, access paths, time window, quantity target, expiry, upload limits, payout basis, operator cost-estimate requirement, and acceptance gates
- publish tasks as open work items through the shared workstream API
- ingest structured operator submissions
- run quality checks before storage writes

The current runtime is local/in-process. The production workstream transport should publish `OperatorTaskContract` payloads without changing the underlying task or submission schema.

SN13 does not own the workstream API. SN13 owns the contract adapter in `subnets/sn13/workstream.py`. The shared workstream and FastAPI layers remain subnet-agnostic so future subnets can publish different contracts through the same operator interface.

### 5. Intake

Module: `subnets/sn13/intake.py`

Responsibilities:

- define `OperatorSubmission`
- require source, label, URI, timestamps, content, and provenance
- normalize labels, URIs, and timestamps
- convert accepted submissions into canonical `DataEntity`

Operators submit to intake. Operators do not write canonical miner records directly. Jarvis does not need to pre-verify every operator environment before task visibility; the published task contract defines the requirements and intake enforces them.

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

Canonical SQLite remains the validator-serving truth while data is needed for SN13 responses. Archive success only permits deletion of temporary parquet staging. Canonical retention and compaction are controlled by freshness, validator-serving, and re-export requirements.

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

The listener does not decompose validator requests into operator work. Operator work is created before validator traffic from real Gravity/Dynamic Desirability plus Jarvis coverage gaps. Validators receive only data that has already passed intake and quality checks.

Current implementation status:

- `protocol_adapter.py` binds exact upstream response field names:
  - `compressed_index_serialized`
  - `data_entities`
  - `bucket_ids_to_contents`
- compressed miner index output uses Macrocosm's `sources -> compressed buckets` shape
- `protocol_observer.py` records request and response shape for live capture
- the old experimental listener runtime and validator-request decomposition path have been removed
- live validator capture and a production runtime entrypoint are still required before production readiness

### 9. Export Layer

Module: `subnets/sn13/export.py`

Responsibilities:

- generate parquet files from canonical SQLite only
- enforce source-specific export schema
- enforce filename record count correctness
- prepare S3-compatible file layout
- feed both upstream upload and Jarvis archive upload jobs

Current implementation status:

- local parquet artifacts are generated for X and Reddit
- filenames follow `data_YYYYMMDD_HHMMSS_count_16hex.parquet`
- filename row count is validated against generated row count
- output paths include miner hotkey and Gravity job ID
- S3 API upload is not implemented in this module

### 10. Archive Layer

Planned module: `subnets/sn13/archive.py`

Responsibilities:

- upload exported parquet to `JARVIS_SN13_ARCHIVE_S3_BUCKET`
- require explicit region through `JARVIS_SN13_ARCHIVE_S3_REGION`
- write under a deterministic prefix such as `sn13/hotkey={hotkey}/job_id={job_id}/...`
- record archive object key, size, checksum, storage class, and upload time
- delete local parquet staging only after upstream upload and Jarvis archive upload both succeed
- never delete canonical SQLite rows solely because archive upload succeeded

## End-to-End Runtime Flow

### Planning Flow

1. Jarvis refreshes the real public Gravity aggregate into the local cache.
2. Jarvis reads current miner coverage from SQLite.
3. Planner computes underfilled desirable buckets.
4. Planner emits ranked operator demand.
5. Runtime converts demand into explicit workstream task contracts.
6. Jarvis publishes those contracts to the workstream.

### Operator Ingestion Flow

1. Operator pulls a task.
2. Operator scrapes source-native records.
3. Operator submits structured records to Jarvis.
4. Quality checker validates the submission.
5. Duplicate submissions are audited and rejected.
6. Valid submissions are classified as scorable or non-scorable.
7. Accepted submissions are stored canonically.
8. Operator stats are updated.

The task contract is the permission boundary. Jarvis does not need a separate pre-verification step before task visibility because every accepted record must still match the task target, source, time window, schema, URI rules, byte limits, and quality gates at intake.

### Validator Serve Flow

1. Validator asks for miner index.
2. Jarvis builds index from canonical SQLite rows.
3. Validator selects bucket and requests data.
4. Jarvis returns canonical entities from storage.
5. Validator verifies data and computes score/credibility impact.

### Export Flow

1. Export reads accepted canonical data.
2. Export builds source-specific rows.
3. Export writes parquet with correct record-count filename.
4. Export prepares files for upstream S3 upload path.
5. Upstream upload sends parquet through the presigned SN13 validation flow.
6. Archive upload writes the same parquet to Jarvis-owned S3.
7. Retention cleanup removes local parquet staging after both uploads succeed.

## Current Guarantees

The current implementation guarantees:

- no markdown storage path remains
- canonical miner entities do not contain `operator_id`
- `time_bucket` is derived from source timestamp
- duplicates are detected before overwriting miner truth
- invalid operator submissions are rejected and audited
- planner demand is based on desirability and current coverage
- operational DD planning defaults to real Gravity cache, not sample records
- planner publication currently supports X and Reddit because those are the confirmed validation/export paths
- local operator runtime writes through quality checks
- operator workstream contracts include source requirements and acceptance windows
- operator workstream contracts include upload limits and payout economics
- local parquet export reads accepted canonical storage only
- local parquet export enforces upstream X and Reddit column sets
- no validator-request decomposition path remains in the supported SN13 code

## Remaining Work

The remaining major gaps are:

- upstream S3 API upload wrapper around generated parquet artifacts
- Jarvis archive S3 upload wrapper and retention cleanup
- live SN13 protocol alignment from real captures
- production listener runtime entrypoint
- production workstream transport
- robust migrations for SQLite schema changes
- operator payout/credit accounting beyond quality stats
- planner-level refusal when task economics are incomplete or negative-margin

## Non-Negotiable Design Rule

Jarvis must never expose unvalidated operator data to validators.

The only validator-facing data is accepted canonical data.
