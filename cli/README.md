# Jarvis Orchestrator CLI Admin Guide

`jarvis-miner` is the admin/control-plane entrypoint for Jarvis Orchestrator.

Jarvis administrators use it for wallet checks, subnet registration checks, miner listener lifecycle, SN13 Gravity refresh, workstream task planning, local simulations, readiness gates, and cost calculations.

Personal operators do not use this CLI. Personal operators use the workstream HTTP API implemented in `workstream/api/`.

## Install

From the repo root:

```bash
uv pip install --python .venv/bin/python -e .
ln -sf /home/abiorh/flow/jarvis-orchestrator/.venv/bin/jarvis-miner ~/.local/bin/jarvis-miner
```

Verify:

```bash
jarvis-miner --version
jarvis-miner --help
```

Jarvis administrators should use `jarvis-miner`. `python -m cli` is only a packaging/debug fallback.

For the deployment package, see [docs/JARVIS_MAINNET_READINESS.md](/home/abiorh/flow/jarvis-orchestrator/docs/JARVIS_MAINNET_READINESS.md) and [compose.yaml](/home/abiorh/flow/jarvis-orchestrator/compose.yaml).

For the current runnable local SN13 operator flow, read [docs/RUN_SN13_LOCALLY.md](/home/abiorh/flow/jarvis-orchestrator/docs/RUN_SN13_LOCALLY.md).

## Root Options

```bash
jarvis-miner [OPTIONS] COMMAND [ARGS]...
```

| Option | Meaning |
| --- | --- |
| `--version` | Print CLI version. |
| `-c, --config PATH` | Use a specific config file instead of `miner_tools/config/config.yaml`. |
| `-v, --verbose` | Print extra runtime details for supported commands. |
| `--help` | Show command help. |

The root command prints the `JARVIS ORCHESTRATOR` banner and lists command groups.

## Command Groups

| Group | Purpose |
| --- | --- |
| `wallet` | Local wallet inspection and creation helpers. |
| `network` | Subnet burn price, registration, and metagraph checks. |
| `miner` | Start, stop, status, and logs for subnet listener processes. |
| `monitor` | Registration price monitoring, auto-register, floor detection, and deregister checks. |
| `workstream` | Admin-controlled durable workstream and HTTP server for personal operators. |
| `sn13` | Data Universe operations: Gravity, planning, readiness, simulation. |
| `config` | Show and validate Jarvis config. |

Backward-compatible root aliases are also available for the old registration monitor CLI:

```bash
jarvis-miner watch
jarvis-miner price 13
jarvis-miner status
jarvis-miner info
jarvis-miner register 13 --dry-run
jarvis-miner deregister-check
jarvis-miner validate
jarvis-miner config-show
```

The preferred modern form is `jarvis-miner monitor ...`, but the aliases are kept so older runbooks do not break.

## Workstream Admin Commands

Personal operators do not run these commands. Jarvis administrators run them to expose and inspect the workstream HTTP boundary that operators call.

```bash
JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON='{"operator_1":"<shared-secret>"}' \
jarvis-miner workstream serve
```

Auth is required by default. For local-only unsigned development, set:

```bash
export JARVIS_WORKSTREAM_REQUIRE_AUTH=0
```

Default stores:

```text
JARVIS_WORKSTREAM_DB_PATH=data/workstream.sqlite3
JARVIS_SN13_DB_PATH=subnets/sn13/data/sn13.sqlite3
```

`JARVIS_WORKSTREAM_OPERATOR_SECRETS_JSON` is the server-side allowlist of personal operators that may call the workstream API. This is not a scraper credential and not a Bittensor wallet.

Runtime network/auth controls:

```text
JARVIS_WORKSTREAM_HOST=127.0.0.1
JARVIS_WORKSTREAM_PORT=8787
JARVIS_WORKSTREAM_MAX_CLOCK_SKEW_SECONDS=300
```

Admin inspection commands:

```bash
jarvis-miner workstream status --json-output
jarvis-miner workstream tasks --json-output
jarvis-miner workstream tasks --status open
jarvis-miner workstream tasks --status completed
```

`workstream status` shows runtime config, auth state, durable workstream counts, and SN13 canonical/audit counts.

`workstream tasks` lists tasks from the durable workstream store with status, target, accepted progress, and quantity.

Machine-readable admin commands accept both `--json-output` and the shorter `--json`.

In the default SN13 runtime, operator stats are also durable. `GET /v1/operators/{operator_id}/stats` is backed by canonical SN13 SQLite quality facts, not by the in-memory test helper in `workstream/stats.py`.

`GET /v1/tasks` does not require an `operator_id` query parameter. When auth is enabled, identity comes from the signed headers.

## SN13 Normal Workflow

This is the normal local/testnet sequence for SN13:

```bash
jarvis-miner sn13 readiness --network testnet --skip-chain --registered
jarvis-miner sn13 dd refresh
jarvis-miner sn13 dd show
jarvis-miner sn13 economics estimate --source X --label '#bittensor'
jarvis-miner sn13 economics s3-cost --storage-gb-month 100 --storage-usd-per-gb-month 0.023
jarvis-miner sn13 plan tasks --json-output
jarvis-miner sn13 plan publish --json-output
jarvis-miner workstream serve
jarvis-miner sn13 simulate cycle --target-items 2 --max-tasks 2 --json-output
```

The production meaning of this flow:

```text
real Gravity/DD -> policy + SQLite coverage -> workstream task contracts
-> publish to durable workstream -> workstream HTTP task discovery/submissions
-> quality gate -> canonical SQLite
-> validator index/bucket/content responses
```

SN13 is not a general validator-task decomposition path. Validators query miner data. Jarvis proactively creates operator scrape tasks from real Gravity demand and coverage gaps.

The old experimental validator-query decomposition scripts were removed. The supported path is workstream-published scrape demand plus intake enforcement.

## SN13 Planning And Publication

Planning and publication are separate on purpose.

Use planning to inspect what Jarvis wants:

```bash
jarvis-miner sn13 plan tasks --sample-dd --json-output
```

Use publication to write those tasks into the durable workstream:

```bash
jarvis-miner sn13 plan publish --sample-dd --json-output
```

`sn13 plan publish` is now economics-gated. Jarvis refuses any task whose economics inputs are missing or blocked. A publish run can therefore produce a mix of:

- published tasks
- refused tasks with explicit blockers

Publication mode is open competitive intake. Tasks are visible to eligible operators through the API, and any operator may submit valid records against the task while it remains open.

Jarvis closes the task when:

- accepted progress reaches the task cap
- or the task expires

This writes to:

```text
data/workstream.sqlite3
```

by default, or to `--workstream-db-path` when overridden.

## SN13 Scheduler

Manual refresh and publication are still available, but the intended admin path is the scheduler:

```bash
jarvis-miner sn13 scheduler run \
  --max-task-cost 20 \
  --expected-reward 30 \
  --expected-submitted 1200 \
  --expected-accepted 900 \
  --duplicate-rate 0.04 \
  --rejection-rate 0.10 \
  --validation-pass-probability 0.95 \
  --payout-basis accepted_scorable_record
```

For a one-shot cycle:

```bash
jarvis-miner sn13 scheduler run --once ...
```

Default scheduler interval is `1200` seconds. This matches the upstream Dynamic Desirability cadence better than manual invocation because validator desirability commits are designed around roughly 20-minute update windows.

The scheduler does three things in order:

1. refresh the real Gravity cache
2. plan tasks from current SQLite coverage
3. publish only tasks that pass economics gates

The listener should not own this loop. The listener serves validators from canonical SQLite. The scheduler updates demand and publishes work into the workstream.

## SN13 Economics Commands

Jarvis separates cost questions by what can be known.

```bash
jarvis-miner monitor price 13
```

Returns the current subnet registration burn cost from the configured network.

```bash
jarvis-miner sn13 economics estimate --help
```

Calculates task-level total cost, accepted-scorable unit cost, quality-adjusted unit cost, expected margin, S3 storage owner, and take/refuse blockers. The command does not invent revenue. `--expected-reward` must be supplied by the operator from a real forecast or observed settlement data.

```bash
jarvis-miner sn13 economics s3-cost --help
```

Calculates Jarvis-owned archive S3 cost from explicit usage and unit prices. It does not include upstream presigned destination storage because that path is controlled by the upstream auth flow; it also does not include operator payout, provider cost, export CPU, local disk, retries, or risk reserve.

## SN13 Gravity Commands

### Refresh Real Gravity

```bash
jarvis-miner sn13 dd refresh
jarvis-miner sn13 dd refresh --json-output
jarvis-miner sn13 dd refresh --timeout-seconds 60
```

Default source:

```text
https://raw.githubusercontent.com/macrocosm-os/gravity/main/total.json
```

Default cache files:

```text
subnets/sn13/cache/gravity/total.json
subnets/sn13/cache/gravity/metadata.json
```

Use `--url` only when intentionally testing another Gravity-compatible aggregate:

```bash
jarvis-miner sn13 dd refresh --url https://example.com/total.json
```

### Show Current Desirability

```bash
jarvis-miner sn13 dd show
jarvis-miner sn13 dd show --file /path/to/total.json
jarvis-miner sn13 dd show --cache-dir /path/to/cache
```

If the cache is missing, run:

```bash
jarvis-miner sn13 dd refresh
```

`--sample-dd` is CI/dev only:

```bash
jarvis-miner sn13 dd show --sample-dd
```

Do not use `--sample-dd` for real operator planning.

## SN13 Planning Commands

Plan open workstream tasks:

```bash
jarvis-miner sn13 plan tasks
jarvis-miner sn13 plan tasks --json-output
jarvis-miner sn13 plan tasks --target-items 250 --recent-buckets 3 --max-tasks 50
```

Useful test form:

```bash
jarvis-miner sn13 plan tasks \
  --db-path /tmp/sn13.sqlite3 \
  --target-items 2 \
  --max-tasks 3 \
  --json-output
```

Important options:

| Option | Meaning |
| --- | --- |
| `--dd-file PATH` | Use a specific Gravity-compatible JSON file. |
| `--cache-dir PATH` | Use a specific Gravity cache directory. |
| `--sample-dd` | Use built-in fake DD records for CI/dev only. |
| `--db-path PATH` | Use a specific SQLite database. |
| `--target-items N` | Desired items per bucket before planner stops filling it. |
| `--recent-buckets N` | Number of recent hourly buckets to plan for default jobs. |
| `--max-tasks N` | Maximum tasks emitted in one planning call. |
| `--json-output`, `--json` | Print machine-readable task contracts. |

`--json-output` emits `OperatorTaskContract` payloads. `sn13 plan publish` writes these contracts into the durable workstream for personal operators.

Published workstream tasks currently expose:

- task target
- expiry
- acceptance cap
- accepted progress
- source-specific contract requirements
- delivery limits
- operator-facing economics facts

Each task contract includes:

- source: `X` or `REDDIT`
- label or keyword
- quantity target
- source-created-at acceptance window
- Gravity desirability job ID and weight
- source-specific required payload fields
- accepted source access/provider paths
- duplicate and quality gate requirements

Jarvis may show Gravity jobs for sources it does not yet support. The planner currently publishes X and Reddit because those are the confirmed validation/export paths.

## SN13 Economics

Run economics before publishing paid or rate-limited operator work:

```bash
jarvis-miner sn13 economics estimate \
  --source X \
  --label '#bittensor' \
  --desirability-job-id gravity_x_bittensor \
  --desirability-weight 2 \
  --quantity-target 1000 \
  --max-task-cost 20 \
  --expected-reward 30 \
  --expected-submitted 1200 \
  --expected-accepted 900 \
  --duplicate-rate 0.04 \
  --rejection-rate 0.10 \
  --validation-pass-probability 0.95 \
  --payout-basis accepted_scorable_record \
  --operator-payout 7 \
  --scraper-provider-cost 4 \
  --proxy-cost 1 \
  --compute-cost 0.5 \
  --risk-reserve 2 \
  --json-output
```

The command returns:

- `can_take_task`
- refusal blockers for missing or unsafe economics
- total task cost
- accepted-scorable unit cost
- quality-adjusted unit cost
- expected margin
- S3 storage cost owner

Use `--s3-mode upstream_presigned` for the upstream Data Universe presigned upload destination. Use `--s3-mode jarvis_archive` for a Jarvis-owned archive-only model. Use `--s3-mode upstream_and_jarvis_archive` for the production dual-upload cost model.

## SN13 Readiness

Run readiness before serving validators or publishing real operator work:

```bash
jarvis-miner sn13 readiness --network testnet
```

Fast local check without chain query:

```bash
jarvis-miner sn13 readiness --network testnet --skip-chain --registered
```

Important options:

| Option | Meaning |
| --- | --- |
| `--network mainnet|testnet` | Target Bittensor network. |
| `--wallet NAME` | Wallet name. |
| `--hotkey NAME` | Hotkey name. |
| `--db-path PATH` | SQLite DB to inspect. |
| `--disk-path PATH` | Disk path used for free-space check. |
| `--export-root PATH` | Export root checked for parquet artifacts. |
| `--skip-chain` | Do not query chain registration. |
| `--registered` | Assume hotkey is registered for local checks. |

Exit code `2` means Jarvis is not ready to serve validators.

Readiness does not decide whether X, Reddit, or future source tasks should be published. DD, planner support, and economics refusal decide publication; intake and quality gates enforce submitted records.

## SN13 Simulation

Simulation is for validating Jarvis internals before relying on live testnet traffic.

### Full Local Cycle

```bash
jarvis-miner sn13 simulate cycle
jarvis-miner sn13 simulate cycle --json-output
jarvis-miner sn13 simulate cycle --target-items 2 --max-tasks 2 --json-output
```

This exercises:

- Gravity/DD loading
- planner
- operator task contract
- simulated operator submissions
- quality gate
- SQLite storage
- validator protocol adapter
- local parquet export

Options:

| Option | Meaning |
| --- | --- |
| `--dd-file PATH` | Use a specific DD JSON file. |
| `--cache-dir PATH` | Use a specific Gravity cache directory. |
| `--sample-dd` | Use fake DD fixture for CI/dev only. |
| `--db-path PATH` | SQLite DB path. |
| `--export-root PATH` | Local export directory. |
| `--operators N` | Number of simulated operators. |
| `--target-items N` | Items per planned bucket. |
| `--recent-buckets N` | Number of recent hourly buckets. |
| `--max-tasks N` | Maximum planned tasks. |
| `--miner-hotkey TEXT` | Hotkey string used in export path. |
| `--no-export` | Skip parquet export. |
| `--json-output` | Print machine-readable report. |

### Operator Push Simulation

```bash
jarvis-miner sn13 simulate operator --source X --label "#bittensor" --count 5
jarvis-miner sn13 simulate operator --source REDDIT --label "r/Bittensor_" --count 5
```

Options:

| Option | Meaning |
| --- | --- |
| `--db-path PATH` | SQLite DB path. |
| `--source X|REDDIT` | Source to simulate. |
| `--label TEXT` | Label/subreddit/hashtag. |
| `--operator-id TEXT` | Simulated operator ID. |
| `--count N` | Number of records to push. |
| `--job-id TEXT` | Provenance job ID. |

### Validator Query Simulation

```bash
jarvis-miner sn13 simulate validator --query index
jarvis-miner sn13 simulate validator --query bucket --source X --label "#bittensor"
jarvis-miner sn13 simulate validator --query contents --source REDDIT --label "r/Bittensor_"
jarvis-miner sn13 simulate validator --query bucket --json-output
```

Options:

| Option | Meaning |
| --- | --- |
| `--db-path PATH` | SQLite DB path. |
| `--query index|bucket|contents` | Validator request type to simulate. |
| `--source X|REDDIT` | Source for bucket/content query. |
| `--label TEXT` | Label for bucket/content query. |
| `--time-bucket INTEGER` | Specific hour bucket. Defaults to current bucket. |
| `--limit INTEGER` | Max returned entities. |
| `--json-output` | Print machine-readable response. |

## Miner Lifecycle

`miner start/status/logs/stop` remain the generic lifecycle commands for subnet runtime scripts. SN13's old experimental listener runtime was removed because it mixed validator serving with operator task decomposition. The current SN13 listener entrypoint serves canonical SQLite through the protocol adapter and records captures through the protocol observer. Live validator captures are still required before treating that runtime as production-verified.

Start a subnet runtime when the subnet has a supported entrypoint:

```bash
jarvis-miner miner start --subnet 13 --network testnet --wallet sn13miner_nopw
```

For local protocol work without chain advertisement, run the listener directly in offline mode:

```bash
uv run python subnets/sn13/listener/listener.py --wallet sn13miner --network finney --offline
```

Check status:

```bash
jarvis-miner miner status --subnet 13
```

Watch logs:

```bash
jarvis-miner miner logs --subnet 13 --lines 100
```

Stop:

```bash
jarvis-miner miner stop --subnet 13
```

Runtime files:

```text
subnets/sn13/state.json
subnets/sn13/listener.log
subnets/sn13/listener/captures/
subnets/sn13/data/sn13.sqlite3
subnets/sn13/exports/
subnets/sn13/cache/gravity/
```

Listener verification commands:

```bash
jarvis-miner sn13 listener status
jarvis-miner sn13 listener verify
jarvis-miner sn13 listener verify --json-output
```

`sn13 listener status` shows process state plus capture summary.

`sn13 listener verify` checks whether captured live traffic covers the three grounded SN13 query types:

- `GetMinerIndex`
- `GetDataEntityBucket`
- `GetContentsByBuckets`

## Monitor Commands

The monitor commands restore the original registration-price monitor behavior inside the modern `jarvis-miner` CLI.

Use this when you are watching subnet registration burn prices, auto-registering when prices fall below configured thresholds, detecting price floors, or monitoring hotkeys for deregistration.

### Live Monitor

```bash
jarvis-miner monitor watch
jarvis-miner watch
jarvis-miner -v monitor watch
```

This starts:

- price polling for enabled configured subnets
- threshold/floor alerts
- signal-file writes when configured
- auto-registration for subnets with `auto_register: true`
- max-spend enforcement for subnets with `max_spend_tao`
- deregistration monitoring for configured `deregister` hotkeys
- automatic Jarvis-hotkey deregistration tracking on auto-register subnets

Default watch mode uses a live dashboard that keeps the current burn cost, threshold state, auto-join state, and deregistration watch state visible without flooding the terminal. Use `-v` when you need detailed per-poll logs.

### Price Check

```bash
jarvis-miner monitor price
jarvis-miner monitor price 13
jarvis-miner price 13
```

This uses the monitor config thresholds and prints current burn cost, threshold ratio, and status.

Use `network price` only for a simple chain burn-cost check. Use `monitor price` when you want configured thresholds, price-source behavior, and monitor context.

### Monitor Status

```bash
jarvis-miner monitor status
jarvis-miner status
```

Reads:

```text
{global.data_dir}/monitor_state.json
```

Shows last price, trend, reading count, min/max/average, floor events, sparkline, and poll count.

### Subnet Info

```bash
jarvis-miner monitor info
jarvis-miner info
```

Shows configured subnets with chain information such as burn, price, TAO in, tempo, and symbol.

### Burned Register

```bash
jarvis-miner monitor register 13 --dry-run
jarvis-miner monitor register 13 --wallet sn13miner_nopw --hotkey default --dry-run
jarvis-miner monitor register 13 --wallet sn13miner_nopw --hotkey default
jarvis-miner register 13 --dry-run
```

This uses the wallet config from `miner_tools/config/config.yaml` unless overridden.

Options:

| Option | Meaning |
| --- | --- |
| `--wallet, -w` | Override configured wallet name. |
| `--hotkey, -k` | Override configured hotkey name. |
| `--dry-run` | Show the intended registration without burning TAO. |
| `--yes, -y` | Skip confirmation. Use carefully. |

### Deregister Check

```bash
jarvis-miner monitor deregister-check
jarvis-miner deregister-check
```

Checks each configured `deregister` hotkey and reports whether it is still registered on its subnet.

If a subnet has `auto_register: true` and no explicit `deregister` entries, the command tracks the Jarvis monitor wallet hotkey on that subnet automatically.

### Monitor Wallet

```bash
jarvis-miner monitor wallet
```

Shows the monitor-configured wallet, hotkey, balance, registration list, auto-register subnets, and deregister watch count.

This is separate from the modern `jarvis-miner wallet ...` group.

### Monitor Config and Validation

```bash
jarvis-miner monitor config
jarvis-miner config-show
jarvis-miner monitor validate
jarvis-miner validate
jarvis-miner monitor validate --check-webhooks
```

`monitor config` is the detailed monitor view: thresholds, alert channels, adaptive polling, floor detection, signal files, auto-register, and deregister entries.

## Network Commands

Check registration cost:

```bash
jarvis-miner network price --network testnet --subnet 13
jarvis-miner network price --network mainnet --subnet 13
```

Show subnet metagraph summary:

```bash
jarvis-miner network info --network testnet --subnet 13
```

Register a wallet on a subnet:

```bash
jarvis-miner network register --network testnet --subnet 13 --wallet sn13miner_nopw
```

## Wallet Commands

Show configured wallets:

```bash
jarvis-miner wallet info --network testnet
jarvis-miner wallet info --network testnet --all
```

Show balances and active stakes:

```bash
jarvis-miner wallet balances --wallet sn13miner_nopw --network testnet
```

Create wallet/hotkey helpers:

```bash
jarvis-miner wallet create --name sn13miner
jarvis-miner wallet create-hotkey --name sn13miner --subnet 13
```

Use faucet only on testnet:

```bash
jarvis-miner wallet faucet --wallet sn13miner
```

## Config Commands

Show config:

```bash
jarvis-miner config show
jarvis-miner -c miner_tools/config/config.yaml config show
```

Validate config:

```bash
jarvis-miner config validate
jarvis-miner -c miner_tools/config/config.yaml config validate
```

## Common Failures

### `No Gravity cache found`

Run:

```bash
jarvis-miner sn13 dd refresh
```

Then retry:

```bash
jarvis-miner sn13 dd show
jarvis-miner sn13 plan tasks
```

### `readiness` exits with code `2`

Jarvis is not ready to serve validators. Read the failed checks table. Common causes:

- wallet hotkey missing
- hotkey not registered
- production listener runtime not implemented or not running
- disk below minimum
- economics inputs missing
- export artifacts missing for S3 readiness

### `plan tasks` emits no tasks

Check:

```bash
jarvis-miner sn13 dd show
jarvis-miner sn13 plan tasks --target-items 250 --recent-buckets 3 --max-tasks 50 --json-output
```

Possible causes:

- SQLite already has enough coverage for the requested buckets
- the DD jobs are outside the current planning window
- the jobs are for a source not enabled in `PlannerConfig.supported_sources`
- the wrong `--db-path`, `--dd-file`, or `--cache-dir` was used

### `simulate cycle` produces many skipped exports

This can be normal with real Gravity: the simulation may create data for only one or a few planned tasks, while export evaluates every Gravity job and skips jobs with no matching local canonical data.

Use a smaller local run:

```bash
tmpdir=$(mktemp -d)
jarvis-miner sn13 simulate cycle \
  --db-path "$tmpdir/sn13.sqlite3" \
  --export-root "$tmpdir/exports" \
  --target-items 1 \
  --max-tasks 1 \
  --json-output
```

## Development Checks

Focused checks for CLI/SN13 work:

```bash
.venv/bin/ruff check cli/main.py subnets/sn13/gravity.py subnets/sn13/simulator.py subnets/sn13/tasks.py subnets/sn13/planner.py tests/test_cli.py tests/test_sn13_gravity.py tests/test_sn13_simulator.py tests/test_sn13_tasks.py tests/test_sn13_planner.py
.venv/bin/pytest -q tests/test_cli.py tests/test_sn13_*.py
```

Full test slice currently includes Testcontainers and requires Docker:

```bash
.venv/bin/pytest -q tests/test_cli.py tests/test_sn13_*.py
```
