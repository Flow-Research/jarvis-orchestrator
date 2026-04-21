# Roadmap

## Now

- Complete SN13 Phase 7 live validator verification.
- Deliver:
  - run listener against testnet with real validator traffic
  - capture request versions, payloads, and timeout values
  - compare captures to protocol adapter assumptions
  - adjust listener only where captures prove a mismatch
  - document final request/response inventory

## Next

- SN13 Phase 8: Production Hardening
- S3 API upload wrapper around local parquet artifacts

## Later

- Full workstream transport integration
- Operator payout/credit accounting beyond basic quality stats

## Notes

- SN13 sequencing is documented in `subnets/sn13/docs/IMPLEMENTATION_PLAN.md`.
- The implementation rule is one active phase at a time.
- Upstream SN13 should be treated as a protocol reference, not a codebase to overwrite Jarvis with.
