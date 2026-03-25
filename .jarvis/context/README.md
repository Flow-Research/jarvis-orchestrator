# .jarvis/context/ — Knowledge Base Protocol

## Purpose

This directory is the canonical knowledge base for this project. AI agents, Jarvis CLI, and human contributors read these files for project context.

## Loading Order

1. `status.md` — Canonical current-state document for active work and execution truth
2. `roadmap.md` — Canonical phase ordering, milestones, and deferred work
3. `team.md` — Canonical ownership and coordination guide
4. `technical-debt.md` — Canonical debt register for intentional shortcuts and cleanup

## Optional Supporting Docs

- `projects.md` — Workspace or repo inventory when present
- `decisions.md` — Settled architectural decisions when present
- `AGENTS.md` — Full Flow agent protocol for this installed repo

## Memory System

- Scope registry: `scopes/_scopes.yaml`
- Scoped memories: `scopes/{org,project,project/apps/*}/`
- User memories: `private/<username>/`
- Types: fact, decision, preference, event

## Template Syntax

Files may start with `{{global}}`. This is a Jarvis CLI feature; treat as no-op.

## Installed by

[flow-install](https://github.com/Flow-Research/flow-network/tree/main/tools/flow-install)
