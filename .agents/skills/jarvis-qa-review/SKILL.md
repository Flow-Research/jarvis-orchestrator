---
name: jarvis-qa-review
description: Use when reviewing Jarvis changes for correctness, clean architecture, economics, durability, and documentation consistency. Applies to code review, pre-merge QA, release-readiness checks, and any change touching CLI behavior, workstream boundaries, SN13 runtime flow, storage, or operating docs.
---

# Jarvis QA Review

Review from a failure-prevention perspective. Findings come first. Summaries are secondary.

## Review Order

1. Inspect the change set with `git status --short` and `git diff --stat`.
2. Read only the touched files and the closest architecture or operating docs that define their boundary.
3. Check for bugs, regressions, and hidden operational failure paths.
4. Check whether tests and docs moved with the code.
5. Check whether the change preserves Jarvis economic and durability constraints.

## Required Review Questions

For every meaningful change, answer:

- Can this break an existing command, runtime path, or storage invariant?
- Does it introduce an in-memory shortcut on a production path?
- Does it create spend, retries, storage growth, or network cost without an explicit owner or cap?
- Does it violate the boundary `workstream -> intake -> quality gate -> canonical SQLite -> validator/export`?
- Does it make docs, command names, or examples lie?
- Does it need a regression test that is currently missing?

## Jarvis-Specific Review Rules

Reject or flag changes that:

- let operators bypass the workstream/intake/quality path
- let anything other than canonical SQLite define miner truth
- treat sample data as the default operational path
- invent reward claims or cost assumptions without explicit inputs
- hide operational requirements in code without surfacing them in docs or CLI help
- add new CLI surface without help/success/failure tests

## Durability Checks

Prefer durable state for real paths:

- workstream tasks must persist
- SN13 accepted data must persist
- audit facts must persist
- startup configuration failures must fail clearly, not with raw tracebacks

If a path is intentionally in-memory, verify it is test-only or explicitly local-only.

## Economics Checks

Verify:

- cost owner is explicit
- spend caps or blockers exist where needed
- archive/storage behavior is described directly
- acceptance and payout are not conflated
- planner/readiness/economics logic do not silently take unsafe work

## Output Format

Return findings ordered by severity with file references when possible.

If there are no findings, say that explicitly and then list:

- residual risks
- tests that were run or still need to run
- docs or operating assumptions that still need evidence
