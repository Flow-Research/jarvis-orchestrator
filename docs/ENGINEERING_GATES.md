# Engineering Gates

## Purpose

Jarvis is now under a feature freeze for SN13-adjacent work until testing discipline, economics, and architecture gates are explicit and enforced.

No new feature should be accepted because it is interesting or easy. Every change must prove:

- it is testable
- it is economically understood
- it fits the architecture

## Non-Negotiable Gates

### 1. Testing Gate

Every change must declare the test level it affects.

| Change type | Required tests |
| --- | --- |
| Pure policy, planning, economics, scoring, validation | unit tests |
| Storage, export, parser, cache, protocol adapter | unit tests plus fixture/regression tests |
| SQLite behavior | storage tests and migration/backward compatibility checks |
| S3/export path | local parquet tests plus validation-shape tests |
| Docker/container/runtime dependency | Testcontainers integration test |
| CLI behavior | Click runner tests for command success, failure, and JSON output |
| Live subnet behavior | captured request/response fixture before production claim |

Default rule:

- a change without a test is not complete
- a bug fix must include a regression test
- a CLI command must have at least one help/success/failure test
- every economic formula must have deterministic tests with example numbers

## 2. Economics Gate

Every task or feature that can spend resources must answer these before implementation:

| Question | Required answer |
| --- | --- |
| What can this spend? | CPU, disk, bandwidth, S3/object storage, scraper API, proxy, operator payout, TAO registration, validator penalty risk. |
| Who pays? | Jarvis, operator, upstream-provided presigned destination, or external provider. |
| What is the unit? | Per record, per task, per bucket, per job, per GB, per file, per request, per hour, or per subnet. |
| What is the cap? | Hard maximum spend before the task is refused or paused. |
| What is the expected return signal? | Reward share, data value, validation pass, coverage improvement, or strategic learning. |
| What telemetry proves it? | Metrics that show actual cost and actual quality after execution. |

No source task should be published unless Jarvis knows:

- expected scrape cost
- maximum accepted scrape cost
- expected accepted-record count
- expected rejection/duplicate rate
- operator payout model
- storage/export cost impact
- validation failure risk

## 3. Architecture Gate

Every change must fit the existing ownership boundary:

```text
Gravity/DD -> policy -> planner -> operator task contract
-> intake -> quality gate -> canonical SQLite
-> validator adapter/export
```

Rules:

- validators query miner data; they do not define arbitrary workstream tasks
- operators never write canonical miner truth directly
- sample data is never the default operational path
- storage remains SQLite until a migration plan exists
- protocol claims require upstream docs, upstream code, or captured traffic
- economic decisions belong in policy/readiness/planning, not buried in CLI code

## Required Review Checklist

Before merging any non-trivial change, answer:

- What tests prove this?
- What cost can this create?
- What metric will detect if the cost is wrong?
- What architecture boundary does this touch?
- What upstream fact or local capture grounds this?
- What is the rollback path?

## Current Freeze Scope

Feature work is paused until these foundations exist:

| Foundation | Status |
| --- | --- |
| SN13 economics document | done |
| S3 upload cost responsibility clarified | done |
| cost model module and deterministic tests | done |
| CLI command to print economics/readiness | done |
| operator task contract includes expected unit economics | done |
| readiness separates Jarvis, operator, upstream S3, and archive ownership | done |
| planner refuses real work when economics is missing | done |
| runtime metrics capture actual economics and archive deletion | pending |
| CI runs the focused SN13/CLI suite and Testcontainers suite | done |

The freeze remains active while any pending foundation exists.

## Allowed Work During Freeze

Allowed:

- tests
- docs
- economics modeling
- architecture cleanup
- validation and readiness gates
- bug fixes that protect correctness or cost

## Agent-Assisted QA

Jarvis should not rely on manual testing as the default verification path.

Project-local skills in `.agents/skills/` provide repeatable QA workflows:

- `jarvis-test-runner` executes lint, focused tests, full non-integration coverage, and integration gates
- `jarvis-qa-review` reviews changes for correctness, architecture fit, economics, durability, and docs drift

Use these skills to keep verification repeatable and to reduce human review fatigue, but do not treat skill existence as proof. Commands still need to run and results still need to be reported.

Not allowed:

- new subnet integrations
- new workstream features
- new scraping providers
- new production automation
- mainnet claims without economics and validation proof
