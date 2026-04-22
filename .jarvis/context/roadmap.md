# Roadmap

## Now

- Complete SN13 production hardening before any mainnet claim.
- Deliver:
  - archive/upload pipeline around canonical export artifacts
  - real listener runtime on canonical SQLite
  - live validator capture with request/response fixture verification
  - persistent operator accounting ledger
  - automated DD refresh/publication operation review

## Next

- harden workstream API edge limits and replay protection
- add operator capability visibility filters
- document final operator settlement/accounting policy

## Later

- multi-node workstream deployment path
- future subnet adapters on the same workstream boundary

## Notes

- SN13 sequencing is documented in `subnets/sn13/docs/IMPLEMENTATION_PLAN.md`.
- The implementation rule is one active phase at a time.
- Upstream SN13 should be treated as a protocol reference, not a codebase to overwrite Jarvis with.
