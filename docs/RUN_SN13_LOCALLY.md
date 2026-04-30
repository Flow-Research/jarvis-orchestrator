# Run SN13 Locally

Last updated: 2026-04-23

## What Works Today

This repo already supports the current Flow Workstream operator flow:

1. Flow Workstream receives SN13 tasks from Jarvis into the durable workstream
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
- the published operator skill at `docs/skills/flow-workstream/SKILL.md`

Personal operators do not use the internal admin CLI.

## Option A: Company Tester Mode With Docker Compose

This is the default local deployment mode for internal testers.

It runs:

- `workstream-api`: dashboard and Garden-authenticated Workstream API
- `registration-monitor`: burn-cost and registration visibility, with auto-register disabled
- `sn13-scheduler`: real Gravity/DD refresh and task publication loop

It does not run:

- `sn13-listener`: validator-facing listener, only needed for live validator/miner testing

The local operator flow is:

```text
real Gravity/DD -> scheduler -> durable workstream -> Workstream API -> SN13 intake -> canonical SQLite
```

### 1. Configure Garden Auth

Workstream does not generate personal-operator auth material. It trusts Garden identity after verifying it through Garden's internal auth endpoint.

```bash
export GARDEN_BASE_URL=http://localhost:3000
export GARDEN_SERVICE_AUTH_TOKEN='<copy from Garden apps/web/.dev.vars>'
```

For Docker local runs, put the same values in `.env` so Compose can pass them into `workstream-api`.

```text
GARDEN_BASE_URL=<garden-base-url-reachable-from-the-workstream-container>
GARDEN_SERVICE_AUTH_TOKEN=<copy from Garden apps/web/.dev.vars>
```

### 2. Start Tester Mode

Start the current runnable services:

```bash
docker compose -f docker-compose.local.yaml up -d \
  workstream-api \
  registration-monitor \
  sn13-scheduler
```

Check status:

```bash
docker compose -f docker-compose.local.yaml ps
curl http://127.0.0.1:8787/health
uv run jarvis-miner workstream status --json
```

Open the dashboard:

```text
http://127.0.0.1:8787/
```

### 3. Optional HTTPS With Dev Tunnel

If external testers need HTTPS:

```bash
devtunnel host -p 8787 --allow-anonymous
```

Use the generated HTTPS URL as `WORKSTREAM_API_BASE_URL` in Garden or the operator runtime. Do not create Workstream tester secrets.

### 4. Scheduler Behavior

The scheduler is required in tester mode. It creates operator-facing tasks without waiting for validators.

The scheduler does this every cycle:

1. fetches the real public Gravity aggregate
2. parses Dynamic Desirability jobs
3. compares desired jobs against current canonical SQLite coverage
4. applies planner limits and economics refusal
5. publishes accepted tasks into the durable workstream

The default source is real Gravity:

```text
https://raw.githubusercontent.com/macrocosm-os/gravity/main/total.json
```

The scheduler log should show a real DD source and a real job count, for example:

```text
DD jobs: 451
Planned tasks: 446
Published tasks: 446
```

The exact counts change as Gravity changes. In the verified local run on 2026-04-23, the real Gravity payload contained:

```bash
total jobs: 451
X jobs: 281
Reddit jobs: 165
YouTube jobs: 5
currently supported jobs: 446
```

The local tester stack publishes all currently supported X and Reddit jobs for the current planning bucket by default. YouTube jobs are intentionally not published yet because the YouTube intake/export path has not been hardened.

`500` is not an upstream Gravity limit. It is the local tester-mode safety cap, chosen to cover the current `446` supported jobs without cutting them off:

```bash
JARVIS_SN13_MAX_TASKS=500
```

Other local planning settings:

```bash
JARVIS_SN13_TARGET_ITEMS=5
JARVIS_SN13_RECENT_BUCKETS=1
JARVIS_SN13_SCHEDULER_INTERVAL_SECONDS=1200
```

These are real-work tester defaults:

- `TARGET_ITEMS=5` means each task asks for up to 5 accepted records.
- `RECENT_BUCKETS=1` means one current hourly bucket per Gravity job.
- `MAX_TASKS=500` prevents runaway publication if Gravity changes sharply.

Increase volume only when the tester group is ready for more work:

```bash
JARVIS_SN13_TARGET_ITEMS=25
JARVIS_SN13_RECENT_BUCKETS=3
JARVIS_SN13_MAX_TASKS=1500
```

Then restart the scheduler:

```bash
docker compose -f docker-compose.local.yaml restart sn13-scheduler
```

### 5. Listener Stays Off

Do not start the listener for company tester mode. The listener is validator-facing and is only needed when testing live validator/miner behavior:

```bash
docker compose -f docker-compose.local.yaml --profile listener up -d sn13-listener
```

## Option B: Manual Local Admin Flow

Edit the deployment env used by Compose:

```bash
$EDITOR deploy/jarvis.mainnet.env
```

Set at minimum:

```bash
JARVIS_WORKSTREAM_REQUIRE_AUTH=1
GARDEN_BASE_URL=http://localhost:3000
GARDEN_SERVICE_AUTH_TOKEN=<copy from Garden apps/web/.dev.vars>
JARVIS_MONITOR_AUTO_REGISTER=0
```

If you want task publication without depending on live Gravity during local development, publish sample tasks manually:

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

## Option C: Start The Runnable Stack Directly With CLI

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
export GARDEN_BASE_URL=http://localhost:3000
export GARDEN_SERVICE_AUTH_TOKEN='<copy from Garden apps/web/.dev.vars>'
uv run jarvis-miner workstream serve --host 127.0.0.1 --port 8787
```

### 3. Real Gravity scheduler loop

Use this when you want the CLI path to behave like company tester mode:

```bash
uv run jarvis-miner sn13 scheduler run --once \
  --max-task-cost 20 \
  --expected-reward 30 \
  --expected-submitted 1200 \
  --expected-accepted 900 \
  --duplicate-rate 0.04 \
  --rejection-rate 0.10 \
  --validation-pass-probability 0.95 \
  --payout-basis accepted_scorable_record
```

This refreshes real Gravity before planning. Do not pass `--sample-dd` for real tester work.

### 4. Sample scheduler loop

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

### 5. Verify the admin side

```bash
uv run jarvis-miner workstream status --json
uv run jarvis-miner workstream tasks --json
uv run jarvis-miner sn13 readiness --json
```

## Personal Operator Startup

An external operator agent needs only these values:

```bash
WORKSTREAM_API_BASE_URL=http://127.0.0.1:8787
```

Then give the operator the published skill:

- `docs/skills/flow-workstream/SKILL.md`

That skill tells the operator how to:

- check `/health`
- list `GET /v1/tasks`
- inspect `GET /v1/tasks/{task_id}`
- submit `POST /v1/submissions`
- inspect `GET /v1/operators/{garden_user_id}/stats`

Garden supplies `x-garden-user-id`, `x-garden-workspace-id`, and optionally `x-garden-session-token` to authenticated personal operators. Workstream verifies those headers against Garden before serving `/v1/*`.

## Current Meaning Of End To End

Today, "end to end" means:

```text
Flow Workstream publishes work
-> operator agent sees the task
-> operator agent submits records
-> Flow Workstream intake accepts or rejects them
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

1. start Garden and sign in as a personal operator user
2. set `GARDEN_BASE_URL` and `GARDEN_SERVICE_AUTH_TOKEN` for Workstream
3. start `workstream-api`, `registration-monitor`, and `sn13-scheduler`
4. confirm the scheduler published real Gravity tasks
5. give Garden the Workstream base URL and the published workstream skill
6. let the Garden personal operator call the API and submit records with Garden identity headers
7. inspect `uv run jarvis-miner workstream status --json`
8. inspect operator quality stats through the API
