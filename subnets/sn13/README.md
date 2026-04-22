# Subnet 13 — Data Universe

This package contains Jarvis's SN13 miner-orchestrator implementation.

Jarvis is the miner identity on SN13. Personal operators scrape data for Jarvis. Jarvis validates those submissions, stores canonical miner data, serves validators, and prepares export data.

## What This Package Builds

```text
SN13 Dynamic Desirability
        |
        v
Jarvis planner decides what data is valuable
        |
        v
Personal operators receive scrape tasks
        |
        v
Operators submit structured source records through the shared workstream API
        |
        v
Jarvis validates, dedupes, and stores accepted data
        |
        v
Jarvis serves validators as the SN13 miner
        |
        v
Jarvis exports canonical data for S3/parquet validation
```

## Current Implementation State

Completed:

- canonical SN13 data model
- structured operator intake model
- durable workstream publication and open competitive task model
- SQLite-only canonical storage
- freshness and scoring policy core
- Dynamic Desirability matching
- quality and rejection layer
- operator demand planner
- operator task contract
- local structured ingestion runtime
- automated DD refresh + economics-gated publication scheduler
- local S3/parquet export artifact generation
- minimum readiness and economic gating for SN13 work acceptance
- removal of old copied upstream docs, mock query scripts, local generated state, and validator-request decomposition prototypes

Next active phase:

- archive/upload pipeline, real listener runtime, and live validator capture

## Code Map

| Concern | Module |
| --- | --- |
| Canonical miner objects | `models.py` |
| Operator submission schema | `intake.py` |
| Freshness, limits, score policy | `policy.py` |
| Dynamic Desirability | `desirability.py` |
| Submission quality gate | `quality.py` |
| Operator demand planning | `planner.py` |
| Operator task and local runtime | `tasks.py` |
| Workstream publication adapter | `workstream.py` |
| Shared API submission adapter | `api_adapter.py` |
| Canonical SQLite storage | `storage.py` |
| Parquet export artifacts | `export.py` |
| Minimum readiness gates | `readiness.py` |
| Validator-facing protocol adapter and capture utilities | `listener/` |
| Upstream synapse response adapter | `listener/protocol_adapter.py` |

## Storage

Canonical database:

```text
subnets/sn13/data/sn13.sqlite3
```

Markdown storage was removed. All accepted data enters SQLite through structured intake and quality checks.

Runtime SQLite files, Gravity cache files, export artifacts, listener logs, and capture files are generated local state and are ignored by git.

## Documentation

Read the design docs before changing SN13 code:

1. `docs/README.md`
2. `docs/GLOSSARY.md`
3. `docs/ARCHITECTURE.md`
4. `docs/DATA_VALUE_AND_INCENTIVES.md`
5. `docs/OPERATOR_CONTRACT.md`
6. `docs/MINIMUM_REQUIREMENTS.md`
7. `docs/IMPLEMENTATION_PLAN.md`
8. `docs/UPSTREAM_ASSUMPTIONS.md`
9. `docs/UPSTREAM_SYNC.md`

## Design Boundary

Operators produce candidate data.

Jarvis decides whether candidate data becomes miner truth.

Validators only interact with Jarvis.

Jarvis does not decompose validator requests into operator tasks. Jarvis publishes desired scrape tasks to the workstream ahead of validator queries and enforces the published contract at intake.

SN13 task intake is competitive, not reserved:

- multiple operators can submit against the same open task
- accepted progress is tracked durably
- duplicate or invalid records are rejected
- tasks close on accepted-cap or expiry
