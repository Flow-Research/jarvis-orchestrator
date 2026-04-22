# Run SN13 Locally

Last updated: 2026-04-22

## What Works Today

This repo already supports the current Jarvis operator flow:

1. Jarvis publishes SN13 tasks into the durable workstream
2. personal operators discover tasks through the workstream API
3. personal operators submit records through the workstream API
4. SN13 intake validates, rejects, deduplicates, and stores accepted data in canonical SQLite

This is the runnable path today.

## What Is Not Ready Yet

These parts are still not end-to-end complete:

- live validator traffic verification on the SN13 listener
- upstream parquet export and upload path
- Jarvis-owned archive upload pipeline

So the current local flow is:

```text
planner -> durable workstream -> workstream API -> SN13 intake -> canonical SQLite
```

not:

```text
planner -> workstream -> intake -> canonical SQLite -> live validator service -> upstream upload
```

## Who Uses What

Jarvis admin uses:

- `jarvis-miner`
- Docker Compose or direct CLI process management

Personal operators use:

- the workstream HTTP API
- the published operator skill at [docs/skills/jarvis-workstream/SKILL.md](/home/abiorh/flow/jarvis-orchestrator/docs/skills/jarvis-workstream/SKILL.md)

Personal operators do not use the Jarvis admin CLI.

## Option A: Start The Runnable Stack With Docker Compose

Edit the deployment env used by Compose:

```bash
$EDITOR deploy/jarvis.mainnet.env
```

Set at minimum:

```bash
JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON={"operator_1":"change-me"}
JARVIS_WORKSTREAM_REQUIRE_AUTH=1
JARVIS_MONITOR_AUTO_REGISTER=0
```

If you want task publication without depending on live Gravity during local development, publish sample tasks manually before or after starting Compose:

```bash
uv run jarvis-miner sn13 plan publish \
  --sample-dd \
  --json-output \
  --max-task-cost 20 \
  --expected-reward 30 \
  --expected-submitted 1200 \
  --expected-accepted 900 \
  --duplicate-rate 0.04 \
  --rejection-rate 0.10 \
  --validation-pass-probability 0.95 \
  --payout-basis accepted_scorable_record
```

Then start the current runnable services:

```bash
docker compose up -d registration-monitor workstream-api sn13-scheduler
```

Check status:

```bash
docker compose ps
uv run jarvis-miner workstream status --json
uv run jarvis-miner workstream tasks --json
```

The optional listener container exists, but it is not part of the current local operator flow:

```bash
docker compose --profile listener up -d sn13-listener
```

## Option B: Start The Runnable Stack Directly With CLI

### 1. Publish some SN13 tasks

For local development, use built-in sample DD:

```bash
uv run jarvis-miner sn13 plan publish \
  --sample-dd \
  --json-output \
  --max-task-cost 20 \
  --expected-reward 30 \
  --expected-submitted 1200 \
  --expected-accepted 900 \
  --duplicate-rate 0.04 \
  --rejection-rate 0.10 \
  --validation-pass-probability 0.95 \
  --payout-basis accepted_scorable_record
```

### 2. Start the workstream API

Authenticated local run:

```bash
export JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON='{"operator_1":"change-me"}'
uv run jarvis-miner workstream serve --host 127.0.0.1 --port 8787
```

Unsigned local-only development:

```bash
export JARVIS_WORKSTREAM_REQUIRE_AUTH=0
uv run jarvis-miner workstream serve --host 127.0.0.1 --port 8787
```

### 3. Optional scheduler loop

```bash
uv run jarvis-miner sn13 scheduler run --once \
  --sample-dd \
  --max-task-cost 20 \
  --expected-reward 30 \
  --expected-submitted 1200 \
  --expected-accepted 900 \
  --duplicate-rate 0.04 \
  --rejection-rate 0.10 \
  --validation-pass-probability 0.95 \
  --payout-basis accepted_scorable_record
```

### 4. Verify the admin side

```bash
uv run jarvis-miner workstream status --json
uv run jarvis-miner workstream tasks --json
uv run jarvis-miner sn13 readiness --json
```

## Personal Operator Startup

An external operator agent needs only these values:

```bash
JARVIS_WORKSTREAM_API_BASE_URL=http://127.0.0.1:8787
JARVIS_OPERATOR_ID=operator_1
JARVIS_OPERATOR_SECRET=change-me
```

Then give the operator the published skill:

- [docs/skills/jarvis-workstream/SKILL.md](/home/abiorh/flow/jarvis-orchestrator/docs/skills/jarvis-workstream/SKILL.md)

That skill tells the operator how to:

- check `/health`
- list `GET /v1/tasks`
- inspect `GET /v1/tasks/{task_id}`
- submit `POST /v1/submissions`
- inspect `GET /v1/operators/{operator_id}/stats`

## Current Meaning Of End To End

Today, "end to end" means:

```text
Jarvis publishes work
-> operator agent sees the task
-> operator agent submits records
-> Jarvis intake accepts or rejects them
-> accepted records land in canonical SQLite
```

Today, "end to end" does not yet mean:

```text
accepted records are already being served to real validators
or
accepted records are already exported and uploaded upstream
```

## Recommended Demo Sequence

If you want to show this to another person right now, use this exact sequence:

1. `uv run jarvis-miner sn13 plan publish --sample-dd ...`
2. `uv run jarvis-miner workstream serve`
3. `uv run jarvis-miner workstream tasks --json`
4. give the operator agent the workstream skill plus its three env vars
5. let the operator call the API and submit records
6. inspect `uv run jarvis-miner workstream status --json`
7. inspect operator quality stats through the API
