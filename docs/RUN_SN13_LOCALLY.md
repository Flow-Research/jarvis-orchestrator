# Run SN13 Locally

Last updated: 2026-04-23

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
- the published operator skill at `docs/skills/jarvis-workstream/SKILL.md`

Personal operators do not use the Jarvis admin CLI.

## Option A: Company Tester Mode With Docker Compose

This is the default local deployment mode for internal testers.

It runs:

- `workstream-api`: dashboard and signed operator API
- `registration-monitor`: burn-cost and registration visibility, with auto-register disabled
- `sn13-scheduler`: real Gravity/DD refresh and task publication loop

It does not run:

- `sn13-listener`: validator-facing listener, only needed for live validator/miner testing

The local operator flow is:

```text
real Gravity/DD -> scheduler -> durable workstream -> operator API -> SN13 intake -> canonical SQLite
```

### 1. Generate Tester Credentials

Generate the persistent tester credential pack:

```bash
python3 scripts/generate_workstream_operator_credentials.py \
  --count 20 \
  --prefix company_tester \
  --base-url http://127.0.0.1:8787
```

This writes stable local files:

```text
data/workstream/tester-pack/operators.server-operator-secrets.json
data/workstream/tester-pack/operators.tester-handoff.json
data/workstream/tester-pack/operators.operators/company_tester_01.json
...
data/workstream/tester-pack/operators.operators/company_tester_20.json
```

The files are intentionally under `data/`, which is gitignored. They are local runtime secrets, not repo files.

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
JARVIS_WORKSTREAM_OPERATOR_SECRETS_FILE=$PWD/data/workstream/tester-pack/operators.server-operator-secrets.json \
  uv run jarvis-miner workstream status --json
```

Open the dashboard:

```text
http://127.0.0.1:8787/
```

### 3. Optional HTTPS With Ngrok

If external testers need HTTPS:

```bash
$HOME/.local/bin/ngrok http 8787
```

Use the generated HTTPS URL to regenerate the same persistent credential files:

```bash
python3 scripts/generate_workstream_operator_credentials.py \
  --count 20 \
  --prefix company_tester \
  --base-url https://YOUR-NGROK-URL

docker compose -f docker-compose.local.yaml restart workstream-api
```

Give each tester exactly one file from:

```text
data/workstream/tester-pack/operators.operators/
```

Do not give testers `operators.server-operator-secrets.json`.

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
JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON={"operator_1":"change-me"}
JARVIS_WORKSTREAM_REQUIRE_AUTH=1
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
export JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON='{"operator_1":"change-me"}'
uv run jarvis-miner workstream serve --host 127.0.0.1 --port 8787
```

Unsigned local-only development:

```bash
export JARVIS_WORKSTREAM_REQUIRE_AUTH=0
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
JARVIS_WORKSTREAM_API_BASE_URL=http://127.0.0.1:8787
JARVIS_OPERATOR_ID=operator_1
JARVIS_OPERATOR_SECRET=change-me
```

Then give the operator the published skill:

- `docs/skills/jarvis-workstream/SKILL.md`

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

1. generate tester credentials with `scripts/generate_workstream_operator_credentials.py`
2. start `workstream-api`, `registration-monitor`, and `sn13-scheduler`
3. confirm the scheduler published real Gravity tasks
4. give each tester one JSON file from `data/workstream/tester-pack/operators.operators/`
5. give testers the published workstream skill
6. let each operator call the API and submit records
7. inspect `uv run jarvis-miner workstream status --json`
8. inspect operator quality stats through the API
