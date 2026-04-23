---
name: jarvis-test-runner
description: Use when validating Jarvis changes without relying on manual testing. Runs the repo's lint, focused pytest slices, coverage gate, skill validation, and Testcontainers integration checks. Use after code changes, before merge, when a regression is suspected, or when CLI, workstream, storage, or SN13 runtime paths changed.
---

# Jarvis Test Runner

Use the repo root and prefer `.venv/bin/...` commands. Do not claim a path is verified unless the command was actually run.

## Default Sequence

1. Run `ruff` on the touched Python files first.
2. Run the smallest relevant pytest slice for the changed area.
3. Run the full non-integration coverage gate if the change touches shared behavior, CLI, workstream, storage, runtime wiring, or SN13.
4. Run the Testcontainers integration test when export/runtime/container boundaries might be affected.
5. If project-local skills changed, run the skill validator too.

## Common Commands

Focused CLI and workstream slice:

```bash
.venv/bin/pytest -q tests/test_cli.py tests/test_workstream.py tests/test_workstream_api.py tests/test_sn13_workstream_api.py tests/test_engineering_governance.py
```

Focused SN13 slice:

```bash
.venv/bin/pytest -q tests/test_sn13_*.py -m 'not integration'
```

Full non-integration gate:

```bash
.venv/bin/pytest -q \
  tests/test_engineering_governance.py \
  tests/test_cli.py \
  tests/test_workstream.py \
  tests/test_workstream_api.py \
  tests/test_sn13_*.py \
  -m 'not integration' \
  --cov=workstream \
  --cov=subnets.sn13 \
  --cov-report=term-missing \
  -W error::ResourceWarning
```

Integration gate:

```bash
.venv/bin/pytest -q -m integration tests/test_sn13_testcontainers.py
```

Lint:

```bash
.venv/bin/ruff check <touched-paths>
```

Skill validation:

```bash
.venv/bin/python /home/abiorh/.codex/skills/.system/skill-creator/scripts/quick_validate.py <skill-path>
```

## Scope Rules

Use focused tests when:

- the change is isolated to one command group
- the change is isolated to one adapter or storage helper
- the full gate would only repeat the same signal

Escalate to the full non-integration gate when:

- CLI command names, help text, or runtime wiring changed
- workstream models, store, or auth changed
- SN13 intake, storage, planner, readiness, or economics changed
- docs/assertion tests changed

Run integration when:

- export format or runtime boundary changed
- containerized checks could regress
- a previous failure suggests environment/runtime drift

## Reporting

Return:

- commands run
- pass/fail result for each command
- failures summarized with the first real root cause
- whether coverage stayed above the repo floor of 80%
- whether integration was run or intentionally skipped

Do not paste large logs unless the exact lines are needed to explain the failure.
