# SN13 Minimum Requirements

This document defines the minimum configuration and resource gates for SN13.

Jarvis has three separate readiness domains:

1. Miner readiness decides whether Jarvis can serve validators.
2. Operator-task readiness decides whether Jarvis can publish workstream tasks and intake operator uploads.
3. Export/archive readiness decides whether Jarvis can upload validator-facing parquet and archive a copy in Jarvis-owned S3.

The machine-readable profile is `subnets/sn13/config/minimum_requirements.yaml`. The pure evaluator is `subnets/sn13/readiness.py`.

## Ground Truth From Upstream

Macrocosm's miner documentation states that SN13 miners:

- do not require a GPU
- can run on a low-tier machine if network bandwidth and disk space are sufficient
- require Python `>=3.10`
- store scraped data in a local database
- must create a Bittensor wallet and register a hotkey
- must run online to respond to validator requests
- support Apify or custom scraper paths
- support a free personal Reddit account path for Reddit scraping

Jarvis does not perform the personal-operator scrape. Operators perform the scrape. Jarvis publishes requirements and enforces them during intake.

The Apify documentation defines `APIFY_API_TOKEN` as the environment variable for Apify access when Jarvis or a Jarvis-approved provider uses Apify.

The Reddit documentation defines the free Reddit account variables:

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USERNAME`
- `REDDIT_PASSWORD`

The S3 validation documentation defines the miner upload path as a presigned URL flow where the miner signs an auth commitment with its hotkey, prepares parquet files, uploads under `hotkey={miner_hotkey}/job_id={job_id}/...`, and must pass filename, record-count, duplicate, scraper, and job-match validation.

Upstream source references:

- `https://github.com/macrocosm-os/data-universe/blob/main/docs/miner.md`
- `https://github.com/macrocosm-os/data-universe/blob/main/docs/apify.md`
- `https://github.com/macrocosm-os/data-universe/blob/main/docs/reddit.md`
- `https://github.com/macrocosm-os/data-universe/blob/main/docs/s3_validation.md`
- `https://github.com/macrocosm-os/data-universe/blob/main/upload_utils/s3_utils.py`
- `https://github.com/macrocosm-os/data-universe/blob/main/neurons/config.py`

## Minimum To Serve Validators

Jarvis serves SN13 validator requests only when all of these are true:

| Gate | Requirement | Source |
| --- | --- | --- |
| Runtime | Python `>=3.10` | Upstream |
| Miner identity | wallet name and hotkey configured | Upstream |
| Registration | hotkey registered on SN13 for the target network | Upstream |
| Process mode | online listener running, not offline mode | Upstream |
| Storage | local database available and disk above Jarvis blocker floor | Upstream + Jarvis |
| Networking | public/reachable axon configuration for online validator traffic | Upstream/Bittensor operational requirement |

Current Jarvis pilot resource floor:

| Resource | Blocker floor | Recommended floor | Authority |
| --- | ---: | ---: | --- |
| GPU | not required | not required | Upstream |
| Free disk | 10 GB | 50 GB | Jarvis pilot gate |
| CPU/RAM | no hard upstream number | low-tier machine acceptable | Upstream |
| Bandwidth | no hard upstream number | stable always-on connectivity | Upstream |

Upstream does not publish exact GB, RAM, CPU, or monthly bandwidth floors. Jarvis uses explicit pilot gates to avoid accepting work that cannot be stored, exported, archived, or served reliably.

## Minimum To Publish Operator Tasks

SN13 rewards data availability and validation quality. Jarvis publishes operator tasks only when the task includes source requirements, intake requirements, upload limits, and payout economics.

This gate is not "Jarvis can scrape." It is "Jarvis can publish a task that an operator can scrape and Jarvis can enforce at upload time."

### X Tasks

Minimum one of:

| Path | Required config | Notes |
| --- | --- | --- |
| Apify | `APIFY_API_TOKEN` | Upstream-supported paid scraper path. |
| Jarvis operator provider | `JARVIS_SN13_X_OPERATOR_ENDPOINT` | Jarvis-owned path for external personal operators/custom scraper providers. |

If neither path is available, Jarvis does not publish real X workstream tasks.

### Reddit Tasks

Minimum one of:

| Path | Required config | Notes |
| --- | --- | --- |
| Apify | `APIFY_API_TOKEN` | Upstream-supported paid scraper path. |
| Free Reddit account | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD` | Upstream-supported free personal Reddit path. |
| Jarvis operator provider | `JARVIS_SN13_REDDIT_OPERATOR_ENDPOINT` | Jarvis-owned path for external personal operators/custom scraper providers. |

If none of these paths are available, Jarvis does not publish real Reddit workstream tasks.

## Minimum To Intake Operator Uploads

Jarvis intakes operator uploads only when all of these are true:

| Gate | Requirement | Enforcement |
| --- | --- | --- |
| Canonical storage | SQLite health check passes | readiness |
| Disk floor | free disk is above blocker floor | readiness |
| Task contract | upload references a current task ID | intake |
| Source schema | content includes source-specific required fields | intake quality gate |
| Target match | source record matches task label or keyword | intake quality gate |
| Time window | source-created-at falls inside task window | intake quality gate |
| Duplicate URI | duplicate source URI is rejected | intake quality gate |
| Upload limit | submitted count and bytes stay within task limits | intake |
| Payout basis | operator receives payout basis before execution | task contract |

Jarvis does not need to pre-verify every operator environment before task visibility. The task contract publishes the requirements. Intake enforces the requirements. Submitted records that fail the contract do not enter canonical miner storage and are not payable.

## Minimum To Export For S3 Validation

Jarvis exports to the upstream SN13 S3 validation path only when all of these are true:

| Gate | Requirement | Source |
| --- | --- | --- |
| S3 auth URL | `JARVIS_SN13_S3_AUTH_URL`, `S3_AUTH_URL`, or upstream default `https://data-universe-api.api.macrocosmos.ai` | Upstream code |
| Hotkey signing | wallet hotkey can sign `s3:data:access:{coldkey}:{hotkey}:{timestamp}` | Upstream code |
| Local export | parquet files exist with upstream filename pattern | Upstream docs/code |
| Job path | files can be uploaded under `job_id={job_id}/data_...parquet` | Upstream docs/code |
| Validation quality | duplicates, scraper validation, and job-match rates are within validator thresholds | Upstream docs/code |

Upstream S3 export is separate from the live listener. A miner can be online without S3 export readiness, but S3 validation and rewards can fail if export artifacts or source authenticity are bad.

## Minimum To Archive In Jarvis-Owned S3

Jarvis archives exported parquet in its own S3 bucket as a parallel export job after canonical export succeeds.

| Gate | Requirement | Notes |
| --- | --- | --- |
| Archive bucket | `JARVIS_SN13_ARCHIVE_S3_BUCKET` | Jarvis-owned paid storage. |
| Archive region | `JARVIS_SN13_ARCHIVE_S3_REGION` | Default deployment target should be explicit; do not rely on SDK defaults. |
| Archive prefix | `JARVIS_SN13_ARCHIVE_S3_PREFIX` | Recommended layout: `sn13/hotkey={hotkey}/job_id={job_id}/...`. |
| Lifecycle policy | required | Expire or transition objects by policy. |
| Local retention policy | required | Delete local parquet staging after upstream upload and archive upload are both confirmed. |

The archive bucket is paid by Jarvis. The upstream presigned destination is not described as Jarvis-owned storage. Dual upload mode means Jarvis pays archive storage, archive requests, lifecycle, and any extra transfer/retry cost created by the archive path.

## Jarvis Economic Gates

These are Jarvis-owned gates. They are not published upstream requirements; they protect Jarvis from taking tasks that are uneconomic or operationally unsafe.

| Gate | Default | Blocks |
| --- | ---: | --- |
| Free disk blocker floor | 10 GB | validator serving, operator intake, and export staging |
| Free disk recommended floor | 50 GB | warning only |
| Operator quality floor | 0.80 | task publication |
| Operator daily capacity floor | 100 items | task publication |
| Operator/source cost budget | required | task publication |
| Rate-limit budget | required | task publication |
| Terms-compliant source access | required | task publication |

The practical economic minimum is therefore:

- one registered SN13 hotkey for the target network
- one always-on CPU machine with Python `>=3.10`, stable bandwidth, SQLite storage, and at least 10 GB free disk for pilot operation
- no GPU requirement
- source access policy for each source Jarvis intends to publish
- an approved source/operator budget before assigning paid or rate-limited work
- hotkey signing plus S3 auth URL before upstream export
- Jarvis archive bucket, region, lifecycle, and retention policy before archive export

## Cannot-Take-Task Rules

Jarvis must reject or defer work in these cases:

| Situation | Decision |
| --- | --- |
| Hotkey is not registered on SN13 | Cannot serve validator work. |
| Listener is offline | Cannot serve validator work. |
| Python is below `3.10` | Cannot run as supported SN13 miner. |
| Local DB health check fails | Cannot serve validators or intake operator uploads. |
| Free disk is below Jarvis blocker floor | Cannot intake operator uploads or stage exports. |
| X source policy is missing | Cannot publish real X operator tasks. |
| Reddit source policy is missing | Cannot publish real Reddit operator tasks. |
| Operator/source budget is missing | Cannot publish source tasks. |
| Hotkey cannot sign S3 commitment | Cannot export to upstream S3 validation path. |
| Parquet export is unavailable | Cannot export or archive S3 data. |
| Archive bucket is missing | Cannot archive to Jarvis-owned S3. |
| Operator quality telemetry is missing | Publish only if the task remains inside Jarvis caps; operators still compete through intake, not assignment. |

## Implementation Mapping

| Requirement area | Implementation |
| --- | --- |
| YAML profile | `subnets/sn13/config/minimum_requirements.yaml` |
| Readiness evaluator | `subnets/sn13/readiness.py` |
| Tests | `tests/test_sn13_readiness.py` |
| Operator task contract | `subnets/sn13/tasks.py` |
| Quality gate | `subnets/sn13/quality.py` |
| Local export | `subnets/sn13/export.py` |

The readiness evaluator is pure. It accepts observed facts from CLI/runtime checks and returns capabilities:

- `can_serve_validators`
- `jarvis_can_intake_operator_uploads`
- `jarvis_can_publish_x_operator_tasks`
- `jarvis_can_publish_reddit_operator_tasks`
- `jarvis_can_export_upstream_s3`
- `jarvis_can_archive_to_jarvis_s3`

This keeps risky network checks out of the policy layer while still making the final accept/reject decision explicit and testable.
