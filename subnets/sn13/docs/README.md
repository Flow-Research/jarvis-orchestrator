# SN13 Design Docs

This directory is the canonical design package for Jarvis on Subnet 13.

Jarvis is the subnet-facing miner. Personal operators are upstream data producers. Jarvis owns the miner contract, the quality gate, the canonical database, validator responses, and export readiness.

## Reading Order

1. `GLOSSARY.md`
2. `ARCHITECTURE.md`
3. `DATA_VALUE_AND_INCENTIVES.md`
4. `OPERATOR_CONTRACT.md`
5. `MINIMUM_REQUIREMENTS.md`
6. `IMPLEMENTATION_PLAN.md`
7. `UPSTREAM_ASSUMPTIONS.md`
8. `UPSTREAM_SYNC.md`

## Current Build State

Completed:

- canonical SN13 data models
- structured operator intake model
- SQLite-only canonical storage
- policy and freshness classification
- Dynamic Desirability job matching
- quality/rejection decisions
- operator demand planning
- operator task contract and local ingestion runtime
- durable workstream publication
- signed FastAPI operator boundary
- SN13 workstream API routing from generic submission envelope into SN13 intake
- local parquet export from canonical SQLite
- minimum SN13 readiness and economic gates
- separated readiness capabilities for validator serving, operator intake, task publication, upstream S3 export, and Jarvis S3 archive
- operator task contracts include delivery limits and operator-facing payout economics
- obsolete copied upstream docs, mock query scripts, and validator-request decomposition prototypes removed

Next active phase:

- Jarvis archive upload implementation
- production listener runtime from real validator captures

## Code Map

| Concern | Module |
| --- | --- |
| Canonical miner objects | `subnets/sn13/models.py` |
| Operator submission schema | `subnets/sn13/intake.py` |
| SN13 policy and freshness | `subnets/sn13/policy.py` |
| SN13 economics and cost gates | `subnets/sn13/docs/ECONOMICS.md` |
| SN13 economics model | `subnets/sn13/economics.py` |
| Dynamic Desirability matching | `subnets/sn13/desirability.py` |
| Quality and rejection decisions | `subnets/sn13/quality.py` |
| Operator demand generation | `subnets/sn13/planner.py` |
| Operator task and ingestion runtime | `subnets/sn13/tasks.py` |
| SN13 workstream adapter | `subnets/sn13/workstream.py` |
| SN13 workstream API adapter | `subnets/sn13/api_adapter.py` |
| Canonical SQLite storage | `subnets/sn13/storage.py` |
| Parquet export artifacts | `subnets/sn13/export.py` |
| Jarvis archive upload | planned: `subnets/sn13/archive.py` |
| Minimum readiness gates | `subnets/sn13/readiness.py` |
| Validator-facing protocol adapter and capture utilities | `subnets/sn13/listener/` |
| Upstream synapse response adapter | `subnets/sn13/listener/protocol_adapter.py` |
| Shared workstream store/models | `workstream/` |
| Shared FastAPI workstream transport | `workstream/api/` |

## End-to-End Flow

```text
Dynamic Desirability -> Planner -> OperatorTaskContract
-> Durable Workstream -> Workstream API submit
-> OperatorSubmission -> Quality Gate -> SQLite Canonical Storage
-> MinerIndex/Bucket Serving -> Upstream S3 Export + Jarvis S3 Archive
```

Jarvis publishes scrape requirements to the durable workstream. Tasks are open to all operators through the workstream API. Operators deliver candidate records against the published contract, and intake enforces the task contract before any record becomes miner truth. Tasks close on accepted-cap or expiry. SN13 does not use a live validator-query decomposition path.

## Design Rule

Every document and module must preserve this boundary:

```text
Operators produce data.
Jarvis decides whether that data becomes miner truth.
Validators only see Jarvis.
```
