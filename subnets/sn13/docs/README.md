# SN13 Design Docs

This directory is the canonical design package for Jarvis on Subnet 13.

Jarvis is the subnet-facing miner. Personal operators are upstream data producers. Jarvis owns the miner contract, the quality gate, the canonical database, validator responses, and export readiness.

## Reading Order

1. `GLOSSARY.md`
2. `ARCHITECTURE.md`
3. `DATA_VALUE_AND_INCENTIVES.md`
4. `OPERATOR_CONTRACT.md`
5. `IMPLEMENTATION_PLAN.md`
6. `UPSTREAM_ASSUMPTIONS.md`
7. `UPSTREAM_SYNC.md`

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
- local parquet export from canonical SQLite

Next active phase:

- live SN13 protocol alignment from real validator captures

## Code Map

| Concern | Module |
| --- | --- |
| Canonical miner objects | `subnets/sn13/models.py` |
| Operator submission schema | `subnets/sn13/intake.py` |
| SN13 policy and freshness | `subnets/sn13/policy.py` |
| Dynamic Desirability matching | `subnets/sn13/desirability.py` |
| Quality and rejection decisions | `subnets/sn13/quality.py` |
| Operator demand generation | `subnets/sn13/planner.py` |
| Operator task and ingestion runtime | `subnets/sn13/tasks.py` |
| Canonical SQLite storage | `subnets/sn13/storage.py` |
| Parquet export artifacts | `subnets/sn13/export.py` |
| Validator-facing listener | `subnets/sn13/listener/` |
| Upstream synapse response adapter | `subnets/sn13/listener/protocol_adapter.py` |

## End-to-End Flow

```text
Dynamic Desirability -> Planner -> OperatorTask -> OperatorSubmission
-> Quality Gate -> SQLite Canonical Storage -> MinerIndex/Bucket Serving
-> Export
```

## Design Rule

Every document and module must preserve this boundary:

```text
Operators produce data.
Jarvis decides whether that data becomes miner truth.
Validators only see Jarvis.
```
