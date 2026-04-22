# SN13 Upstream Sync Strategy

## Purpose

Jarvis depends on the SN13 protocol implemented by Macrocosm's `data-universe` repository.

Jarvis must stay compatible with upstream SN13 without becoming a blind copy of upstream code.

The current upstream assumptions are tracked in `UPSTREAM_ASSUMPTIONS.md`.

## Repository Boundary

Jarvis is a miner orchestration system.

Macrocosm `data-universe` is the upstream protocol and implementation reference.

Jarvis does not vendor upstream code as the primary runtime. Jarvis maps upstream protocol requirements into a narrow compatibility boundary.

## Compatibility Boundary

Only these Jarvis areas are directly affected by upstream SN13 changes:

- canonical models
- policy constants
- desirability parser
- listener request/response adapter
- storage bucket/index shape
- export/parquet format

Modules:

- `subnets/sn13/models.py`
- `subnets/sn13/policy.py`
- `subnets/sn13/desirability.py`
- `subnets/sn13/storage.py`
- `subnets/sn13/listener/`
- `subnets/sn13/export.py`

Operator orchestration, workstream routing, operator stats, and payout accounting are Jarvis-owned implementation details.

## Watched Upstream Areas

Track these upstream files/directories:

| Upstream area | Why it matters |
| --- | --- |
| `common/data.py` | Data entity, bucket, source, label, miner index shapes. |
| `common/protocol.py` | Validator/miner synapse request and response contract. |
| `common/constants.py` | Bucket limits, freshness constants, protocol limits. |
| `dynamic_desirability/` | Gravity job schemas and aggregation behavior. |
| `docs/dynamic_desirability.md` | Miner guidance for desirability-driven scraping. |
| `docs/scoring.md` | Incentive, freshness, credibility, and source-weight assumptions. |
| `docs/s3_validation.md` | Export filename, row count, schema, and validation rules. |
| `upload_utils/` | Miner-side upload behavior. |
| `vali_utils/` | Validator-side checks that Jarvis must survive. |

## Sync Process

1. Fetch upstream reference.
2. Diff watched areas against the last reviewed version.
3. Classify changes as:
   - protocol-breaking
   - scoring-policy change
   - export/schema change
   - implementation-only change
4. Update Jarvis compatibility modules deliberately.
5. Add or update tests.
6. Run the SN13 targeted test suite.
7. Update these docs if the design contract changed.

## What Not To Do

- Do not overwrite Jarvis modules with upstream files.
- Do not mix a cloned upstream tree into Jarvis runtime paths.
- Do not allow upstream implementation details to leak into operator orchestration.
- Do not let operator-specific metadata become validator-facing miner data.

## Current Assumptions

Jarvis currently assumes:

- SN13 data is grouped by source, label, and hour bucket.
- `source_created_at` determines bucket assignment.
- accepted canonical data is the only validator-facing truth.
- Dynamic Desirability jobs include platform, label, optional keyword, weight, and optional date range.
- default freshness is 30 days unless a desirable job range applies.
- export must be generated from canonical SQLite only.
- local export currently supports upstream-confirmed X and Reddit parquet schemas.
- YouTube export remains blocked until its validator-facing schema is confirmed.

## Review Cadence

Review upstream before:

- changing listener protocol behavior
- changing canonical models
- implementing or modifying export
- changing scoring/freshness assumptions
- running against mainnet

Review upstream at least once per active SN13 implementation phase.
