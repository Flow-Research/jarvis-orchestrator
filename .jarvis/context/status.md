# Status

## Current Focus

- Stabilize Jarvis as the canonical CLI entrypoint.
- Rebuild SN13 around a miner-compatible data contract and phase-gated implementation plan.

## Active Work

- CLI refactor has been aligned and tested against the grouped command surface.
- `cli/main.py` is now the canonical CLI implementation; the old `cli_v2` package and legacy CLI wrappers have been removed.
- `jarvis-miner` is installed as the normal operational entrypoint and linked from `~/.local/bin/jarvis-miner`.
- Operational commands should use `jarvis-miner`; `python -m cli` is only for low-level packaging/debug fallback.
- SN13 has been reset onto:
  - canonical miner models
  - operator intake models
  - SQLite-only storage
  - listener responses from canonical storage
- SN13 Phase 1 is now implemented:
  - `subnets/sn13/policy.py`
  - `tests/test_sn13_policy.py`
  - policy-backed scorable/non-scorable classification
- SN13 Phase 2 is now implemented:
  - `subnets/sn13/desirability.py`
  - `tests/test_sn13_desirability.py`
  - upstream-style Gravity job normalization and matching
- SN13 Phase 3 is now implemented:
  - `subnets/sn13/quality.py`
  - `tests/test_sn13_quality.py`
  - rejection reasons, duplicate classification, and operator quality stats
- SN13 Phase 4 is now implemented:
  - `subnets/sn13/planner.py`
  - `tests/test_sn13_planner.py`
  - ranked operator scrape demand from policy, desirability, and coverage gaps
- SN13 Phase 5 is now implemented:
  - `subnets/sn13/tasks.py`
  - `tests/test_sn13_tasks.py`
  - planner demand -> operator task -> quality-checked ingestion -> SQLite storage
- SN13 Phase 6 is now implemented locally:
  - `subnets/sn13/export.py`
  - `tests/test_sn13_export.py`
  - canonical SQLite -> X/Reddit parquet artifacts
  - upstream filename, row-count, path, and schema checks
- SN13 Phase 7 adapter work is now implemented:
  - `subnets/sn13/listener/protocol_adapter.py`
  - `tests/test_sn13_protocol_adapter.py`
  - exact upstream response fields for index, bucket, and contents requests
  - upstream compressed miner index JSON shape
- SN13 testnet listener is currently running for live capture:
  - wallet: `sn13miner_nopw`
  - hotkey: `5GEjJhnvtvLyvew1Gheq6EfF5wa2C7N1fcpddr7cHM6cV4CK`
  - SN13 testnet UID: `151`
  - process state file: `subnets/sn13/state.json`
  - log file: `subnets/sn13/listener.log`
  - capture dir: `subnets/sn13/listener/captures`
  - current capture state: no live validator requests captured yet
- SN13 design docs have been hardened into a production architecture package:
  - glossary
  - end-to-end architecture
  - data value and incentive model
  - operator contract
  - phased implementation plan
  - upstream assumption ledger
  - upstream sync strategy
- Next active SN13 work is live validator capture and runtime verification.

## Blockers

- No hard blocker at the repo level.
- Production readiness still depends on real validator capture data.
- The configured wallet `sn13miner` is not registered and has `τ0` testnet balance; `sn13miner_nopw` is the registered testnet wallet currently in use.

## Constraints

- Jarvis must remain compatible with upstream SN13 expectations without blindly vendoring upstream runtime code.
- SN13 should be built phase by phase; policy and quality layers must exist before deeper orchestration work.
- The Flow context files are now being used as the canonical execution summary and should stay updated.

## Next Review

- Refresh after real validator captures confirm request version, timeout, and payload shape.
