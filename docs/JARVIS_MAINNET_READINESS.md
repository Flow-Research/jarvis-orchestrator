# Jarvis Mainnet Readiness Package

For a short non-technical summary, read `docs/JARVIS_SN13_EXECUTIVE_READINESS.md`.

## Purpose

This document answers one question directly:

What does Jarvis Orchestrator need, in money and infrastructure terms, to move SN13 to mainnet safely?

This document defines the Jarvis-owned deployment package. It is separate from the SN13 runtime readiness spec and separate from the personal-operator skill. It covers:

- Jarvis-owned chain and infrastructure costs
- Jarvis deployment topology
- Jarvis-owned archive/storage costs
- personal-operator external requirements
- mainnet blockers that still exist today

## Live Cost Snapshot

### The Number That Matters For Joining SN13

Jarvis is joining SN13 as a miner hotkey on an existing subnet. The correct cost signal for that action is the subnet registration monitor path.

Observed on `2026-04-22`:

- `jarvis-miner monitor price 13` on `finney` returned `0.039943 TAO`

Indicative fiat conversion:

- Coinbase showed `TAO = $257.32` when crawled `5 days` before `2026-04-22`
- `0.039943 TAO * $257.32 ~= $10.28`

Operational rule:

- Jarvis reads the live join fee from `jarvis-miner monitor price 13`
- Jarvis joins through the registration monitor and the auto-register policy
- `jarvis-miner network price --network mainnet --subnet 13` is not the SN13 hotkey join budget number
- the chain-level `network price` output is a different burn signal and is excluded from the SN13 neuron-registration budget line item

## Jarvis-Owned Requirements

### Chain And Wallet

Jarvis needs:

- one coldkey funded with TAO on `finney`
- one hotkey for the SN13 miner identity
- wallet files mounted into the deployment host or containers
- enough TAO to cover dynamic neuron registration plus operational buffer

- keep at least `1 TAO` liquid in the coldkey before enabling SN13 auto-register

This `1 TAO` number is the Jarvis operating buffer. It is not an upstream rule. The observed fee is lower today, but the fee is dynamic and the monitor must not run against a near-zero wallet.

### Core Services Jarvis Must Run

The current production-shape Jarvis stack has these always-on service roles:

1. `registration-monitor`
   Uses `jarvis-miner monitor watch` for live SN13 registration pricing, threshold detection, and auto-register.
2. `workstream-api`
   Uses `jarvis-miner workstream serve` to expose the Garden-authenticated Workstream HTTP boundary.
3. `sn13-scheduler`
   Uses `jarvis-miner sn13 scheduler run` to refresh Gravity/DD and publish economics-safe work.
4. `jarvis-admin`
   Runs one-off CLI commands for ops, readiness checks, status, and incident response.

Auto-join is controlled by the registration monitor service:

- `jarvis-miner monitor watch` is the canonical join path
- `JARVIS_MONITOR_AUTO_REGISTER=1` arms auto-join
- `JARVIS_MONITOR_PRICE_THRESHOLD_TAO` defines the trigger
- `JARVIS_MONITOR_MAX_SPEND_TAO` defines the hard ceiling
- `monitor watch` now keeps live burn cost, auto-join state, and deregistration watch state visible in one screen

Current state:

- the SN13 listener runtime entrypoint now exists in `subnets/sn13/listener/listener.py`
- the default deployment package still does not include a validator-serving container because live validator capture verification is still open

### Minimum Server Baselines

Jarvis has two baselines:

#### Baseline A: Runnable Today

This covers the services that are real today:

- registration monitor
- workstream API
- scheduler
- admin CLI
- SQLite

Jarvis minimum deployment baseline for that stack:

- `2 vCPU`
- `4 GB RAM`
- `80 GB SSD/NVMe`
- `1 public IPv4`
- Docker Engine and Docker Compose
- persistent wallet mount
- persistent data mount

- DigitalOcean currently lists a `4 GiB / 2 vCPU / 80 GiB` Basic Droplet at `$24/month`
- this is the first simple VM tier that cleanly fits the current Jarvis daemons plus SQLite and export staging

This is a Jarvis deployment estimate, not an upstream SN13 hardware rule.

#### Baseline B: Mainnet Target Once Listener And Export Are Live

Jarvis mainnet target baseline for real validator serving plus export pressure:

- `4 vCPU`
- `8 GB RAM`
- `160 GB SSD/NVMe`
- `1 public IPv4`
- sustained outbound bandwidth
- persistent snapshot/backup policy

- the listener will add always-on validator-serving load
- parquet export and archive jobs increase disk and CPU pressure
- SQLite compaction, workstream API, scheduler, and validator responses should not all contend on the smallest machine tier

DigitalOcean currently lists an `8 GiB / 4 vCPU / 160 GiB` Basic Droplet at `$48/month`.

### Ports And Network

Jarvis needs:

- one public HTTP endpoint for the workstream API, default `8787`
- one future public axon/listener endpoint for SN13 miner traffic after the real listener runtime is added
- outbound internet access for:
  - Bittensor RPC/WebSocket access
  - Gravity/DD refresh
  - upstream S3 auth/upload flow
  - archive S3 uploads when enabled

### Persistent Storage

Jarvis persistent paths:

- `data/workstream.sqlite3`
- `data/monitor_state.json`
- `subnets/sn13/data/sn13.sqlite3`
- `subnets/sn13/cache/gravity/`
- `subnets/sn13/exports/`

Current storage rule:

- canonical SQLite is the miner truth
- local parquet export is staging only
- local export staging should be deleted only after upstream upload and Jarvis archive upload both succeed

## Why Jarvis Maintains Its Own Archive S3

Jarvis does not need its own bucket for the upstream SN13 validation destination because upstream uses a presigned upload path.

Jarvis maintains its own archive bucket when archive mode is enabled for these reasons:

- internal audit trail
- replay and incident investigation
- retention independent of upstream storage lifecycle
- recovery of exported artifacts without rebuilding from scratch
- operator accounting and payout dispute support
- migration safety if upstream upload flow changes

Archive rule:

- before dual-upload is enabled, the Jarvis archive bucket can stay off
- after dual-upload is enabled, the Jarvis archive bucket is required

Jarvis archive configuration:

- `JARVIS_SN13_ARCHIVE_S3_BUCKET`
- `JARVIS_SN13_ARCHIVE_S3_REGION`
- `JARVIS_SN13_ARCHIVE_S3_PREFIX`
- lifecycle policy
- local retention policy

## Jarvis Cost Surfaces

### One-Time Or Variable Chain Cost

- SN13 neuron registration fee
- this is dynamic and must be read from the monitor path

### Monthly Or Ongoing Jarvis Costs

- VM or bare-metal server
- disk growth for SQLite and export staging
- outbound bandwidth
- Jarvis-owned archive S3, if enabled
- backups or snapshots
- monitoring and CI

### Current Official Price Anchors

DigitalOcean official pricing:

- `2 GiB / 1 vCPU / 50 GiB` Basic Droplet: `$12/month`
- `4 GiB / 2 vCPU / 80 GiB` Basic Droplet: `$24/month`
- `8 GiB / 4 vCPU / 160 GiB` Basic Droplet: `$48/month`

AWS S3 pricing anchors for US East:

- S3 Standard storage: `$0.023/GB-month`
- PUT/LIST requests: `$0.005 per 1,000`
- GET requests: `$0.0004 per 1,000`

Practical archive examples, excluding tax:

- `100 GB` archive at S3 Standard storage only: about `$2.30/month`
- `1 TB` archive at S3 Standard storage only: about `$23/month`

These are storage-only anchors. Full archive spend also includes request volume, lifecycle transitions, retrieval, and transfer-out.

## Personal Operator Requirements

This section is separate from Jarvis-owned infrastructure. Personal operators are external suppliers.

Jarvis publishes these as operator prerequisites. They are not Jarvis server environment variables:

- `WORKSTREAM_API_BASE_URL`
- Garden-authenticated user/session context
- a source access path accepted by the task contract
- enough provider quota and proxy budget to finish before task expiry
- UTC-safe timestamp handling
- local dedupe before submission
- ability to submit source-native records that match the task contract exactly

External source requirements for SN13 operators:

- compliant X/Twitter access path
- compliant Reddit access path
- any future provider needed for new sources such as YouTube transcripts

Macrocosm documentation explicitly describes Apify and Reddit setup paths for Data Universe miners. In Jarvis, those source credentials belong to the personal operator or provider fulfilling the task, not to Jarvis itself.

## Deployment Package In This Repo

The repo now includes:

- `Dockerfile`
- `docker-compose.yaml`
- `deploy/jarvis.mainnet.env`
- `deploy/monitor.mainnet.yaml`
- `scripts/run_sn13_listener.sh`
- `scripts/run_sn13_scheduler.sh`

The monitor service reads its runtime policy from `deploy/jarvis.mainnet.env`. The YAML file is only the structural template.

### What Compose Runs Today

```text
registration-monitor
workstream-api
sn13-scheduler
jarvis-admin
```

Daemon model:

- in containerized deployment, Docker restart policies are the service supervisor
- for non-containerized deployment, the committed SN13 listener runtime needs a dedicated process supervisor such as `systemd` or `pm2`

Optional runtime profile:

- `docker compose --profile listener up sn13-listener` starts the committed SN13 listener container
- the listener profile is present for deployment wiring and capture work
- production readiness still depends on live capture verification

### What Compose Keeps Deliberate

The Compose stack includes the listener only behind the `listener` profile.

That profile must not be treated as production-ready until these are true:

- live validator captures are verified
- deployed listener runtime behavior is verified
- the runtime serves canonical SQLite through the protocol adapter

## Mainnet Blockers Still Open

Jarvis is not yet ready to claim full SN13 mainnet readiness because these production items are still open:

1. Live verification of the committed SN13 listener runtime serving validators from canonical SQLite.
2. Archive/upload pipeline wired end to end.
3. Live validator capture and request-shape verification.
4. Persistent operator accounting ledger.
5. Multi-node replay protection and API edge hardening.

Those are not optional polish items. They are real production blockers.

## Immediate Budget Envelope

Clean SN13 mainnet pilot budget envelope:

- SN13 join fee read live from `jarvis-miner monitor price 13`
- at least `1 TAO` liquid registration buffer on the coldkey
- one `4 GB / 2 vCPU / 80 GB` VM if only the currently committed daemons are running
- preferably one `8 GB / 4 vCPU / 160 GB` VM before enabling the real listener and heavier export pressure
- optional archive S3 beginning at roughly `$2.30/month` per `100 GB` of S3 Standard storage before request and transfer charges

## Sources

- Bittensor wallet and hotkey docs: `https://docs.learnbittensor.org/keys/wallets`
- Bittensor permissions and register/pow-register overview: `https://docs.learnbittensor.org/btcli/btcli-permissions`
- Taostats neuron registration overview: `https://docs.taostats.io/docs/node-registration`
- Macrocosm Data Universe overview and miner/S3 model: `https://github.com/macrocosm-os/data-universe`
- Macrocosm validating docs: `https://docs.macrocosmos.ai/subnets/subnet-13-data-universe/subnet-13-validating`
- AWS S3 pricing: `https://aws.amazon.com/s3/pricing/`
- DigitalOcean Droplet pricing: `https://www.digitalocean.com/pricing/droplets`
- Coinbase TAO price page: `https://www.coinbase.com/price/bittensor/`
