# SN13 Economics Specification

## Purpose

This document is the operating specification for SN13 money, storage, and payout decisions.

Jarvis does not publish real paid operator work unless these facts are explicit:

- who pays
- what unit is being paid for
- what the maximum spend is
- what quality result creates payout
- what storage/export path is used
- what validation risk can zero the reward

Unknown economics means blocked production publication. Unknown economics is not an assumption.

## Direct Answers

### Is the upstream SN13 S3 bucket paid by Jarvis?

No Jarvis-owned bucket is required for the upstream SN13 validation destination. Upstream SN13 documents the miner upload path as a presigned URL flow:

- miners request upload access from an auth server
- miners sign an auth commitment with the hotkey
- miners upload parquet files under `hotkey={miner_hotkey}/job_id={job_id}/...`
- the auth server handles the actual S3 credentials
- the auth server handles the actual S3 credentials
- validators discover and validate uploaded files

Jarvis still pays local costs around this flow:

- export CPU
- local disk staging
- outbound bandwidth from the Jarvis server/provider
- retry cost
- failed-validation waste

### Is the Jarvis archive S3 bucket paid by Jarvis?

Yes. The Jarvis archive bucket is a Jarvis-owned paid bucket. It is separate from the upstream presigned validation destination.

Jarvis pays:

- archive object storage
- PUT/GET/list/request costs
- lifecycle transition costs
- retrieval costs
- data transfer out
- monitoring/management costs if enabled

### When do we know how much we are paid?

Final miner revenue is not known at task publication time.

Bittensor emissions are distributed after subnet scoring/consensus. SN13 also gates reward on validation. Therefore:

- before work: Jarvis knows cost estimates and spend caps
- during work: Jarvis knows actual submitted/accepted/rejected/duplicate counts
- after validation/emission: Jarvis knows actual reward and margin

The CLI must never claim final revenue before validation and emission settlement. It can calculate expected margin only from an explicit `--expected-reward` input.

### Can the CLI tell us how much we are paying?

Yes, in three separate ways:

```bash
# Chain registration burn cost
jarvis-miner monitor price 13

# Task-level cost, unit cost, margin, and take/refuse blockers
jarvis-miner sn13 economics estimate --help

# Jarvis-owned archive S3 cost from explicit usage and region prices
jarvis-miner sn13 economics s3-cost --help
```

The CLI does not fetch live AWS/Apify prices. Prices are region/provider/account-specific. The operator passes current unit prices from official provider billing pages or actual bills.

Jarvis uses two S3 paths:

1. Upstream SN13 validation path: presigned destination controlled by the upstream auth flow.
2. Jarvis archive path: Jarvis-owned paid bucket used as a parallel archive after export.

Cost ownership:

| Storage path | Who owns/pays | Jarvis cost exposure |
| --- | --- | --- |
| Upstream presigned SN13 validation upload | Upstream/auth-server controlled destination | local export CPU/disk, upload bandwidth, retries, failed validation waste |
| Jarvis local SQLite/parquet staging | Jarvis | machine disk, backup, compaction, maintenance |
| Jarvis-owned archive S3 bucket | Jarvis | object storage, requests, retrieval, data transfer, lifecycle, monitoring |

This means the question "is our S3 bucket paid?" has two answers:

1. For upstream validator upload, Jarvis currently uses the upstream presigned destination model, not a Jarvis-owned AWS bucket.
2. For the Jarvis archive, the bucket is paid by Jarvis and must be modeled before use.

## Archive Policy

Jarvis archives exported parquet objects in a Jarvis-owned S3 bucket as a parallel export job when archive mode is enabled.

Required archive configuration:

| Config | Required | Meaning |
| --- | --- | --- |
| `JARVIS_SN13_ARCHIVE_S3_BUCKET` | yes | Jarvis-owned archive bucket. |
| `JARVIS_SN13_ARCHIVE_S3_REGION` | yes | Explicit AWS region, for example US or Europe. |
| `JARVIS_SN13_ARCHIVE_S3_PREFIX` | yes | Prefix for subnet/job/hotkey partitioning. |
| lifecycle policy | yes | Expire or transition archived objects by age/class. |
| local retention policy | yes | Delete local parquet staging only after upstream upload and archive upload both succeed. |

Default deployment choice: use one explicit primary region. Do not use "global" as a cost or compliance answer. Start with a US region unless compliance, latency, or operator geography requires Europe. Any region change must update the cost model because storage, request, retrieval, and transfer prices are region-specific.

Local storage rule:

- canonical SQLite remains the active miner truth while records are still needed for validator serving
- parquet export staging is temporary
- exported parquet files are deleted locally after upstream upload and Jarvis archive upload both succeed
- canonical SQLite retention/compaction must be governed by SN13 freshness and validator-serving requirements, not by archive success alone

## Cost Surfaces

Jarvis has these cost surfaces:

| Surface | Unit | Paid by | Notes |
| --- | --- | --- | --- |
| Bittensor registration | TAO burn per subnet registration | Jarvis | Variable chain cost. Must be checked before registration. |
| Always-on miner server | machine-hour/month | Jarvis | CPU machine; no GPU requirement for SN13 miner baseline. |
| Local SQLite storage | GB-month and disk headroom | Jarvis | Canonical serving store; retention must follow freshness and validator-serving needs. |
| Parquet export | CPU, local disk, files generated | Jarvis | Required for S3 validation path. |
| Upload bandwidth | GB uploaded/retried | Jarvis/server provider | Even presigned uploads consume outbound bandwidth from Jarvis. |
| Jarvis S3 archive | GB-month, requests, lifecycle, retrieval | Jarvis | Paid parallel archive path for exported parquet. |
| Validator response bandwidth | request count and bytes served | Jarvis/server provider | Depends on live validator query volume. |
| Apify/X scraping | provider usage units | Jarvis or operator, depending task contract | Paid source path unless operator absorbs it. |
| Reddit scraping | account/API usage/rate limit | Jarvis or operator | Free personal account path can still have rate-limit/compliance constraints. |
| Custom operator scraping | payout per accepted unit | Jarvis | Must be tied to accepted, valid, non-duplicate data. |
| Bad data | wasted scrape cost plus credibility risk | Jarvis primarily | Rejections, duplicates, failed validation, low scraper success. |
| Monitoring/CI | CI minutes, Docker, test infra | Jarvis | Must be included for production discipline. |

## Reward and Validation Risk

SN13 validation is not just "upload many rows." Upstream validation checks can zero out reward if validation fails.

Known validation gates from upstream documentation:

| Gate | Current documented threshold |
| --- | --- |
| Duplicate rate | must be at or below 10% |
| Scraper success | must be at or above 80% |
| Job match rate | must be at or above 95% |
| Filename format | enforced from December 2, 2025 |
| Filename record count | claimed count must match actual rows |

Economic implication:

- a cheap operator is expensive if their data fails validation
- a high-volume scrape is bad if it misses the Gravity job requirement
- duplicates are a direct cost and a validation risk
- payout must be based on accepted quality, not submitted volume

## Revenue Timing

SN13 is competitive. A task that produces valid data still does not create guaranteed revenue.

Revenue depends on:

- SN13 validator scoring
- miner credibility
- data value and freshness
- duplicate factor
- job completion
- competing miners' scores
- Bittensor subnet emission distribution

Operating rule:

```text
expected_reward_value is an input, not a fact
actual_reward_value is known only after scoring/emission settlement
```

Jarvis pays operators only under the task contract. Operator payout accounting must support reserve/holdback when validation can fail after submission.

## Unit Economics Formula

Jarvis calculates economics at task, job, source, operator, archive, and daily levels.

### Per Task

```text
task_cost =
    operator_payout
  + scraper_provider_cost
  + proxy_cost
  + compute_cost
  + local_storage_cost
  + export_staging_cost
  + upload_bandwidth_cost
  + retry_cost
  + risk_reserve
  + jarvis_archive_bucket_cost
```

```text
accepted_scorable_unit_cost =
  task_cost / max(accepted_scorable_records, 1)
```

```text
quality_adjusted_unit_cost =
  task_cost / max(accepted_scorable_records * validation_pass_probability, 1)
```

### Per Operator

```text
operator_effective_cost =
  total_paid_to_operator / max(operator_accepted_scorable_records, 1)
```

```text
operator_quality_score =
  accepted_scorable_records / max(total_submitted_records, 1)
```

### Break-Even

```text
expected_margin =
  expected_reward_value
  - total_expected_cost
  - risk_reserve
```

Jarvis does not publish a task when:

```text
expected_margin < 0
```

or when required inputs are unknown.

## CLI Cost Commands

### Registration Burn

```bash
jarvis-miner monitor price 13
```

This reads the current subnet registration burn price from the configured network.

### Task Economics

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
  --upload-bandwidth-cost 0.1 \
  --risk-reserve 2
```

This returns:

- `can_take_task`
- blockers
- total task cost
- accepted scorable unit cost
- quality-adjusted unit cost
- expected margin
- S3 storage cost owner

### Jarvis Archive S3 Cost

```bash
jarvis-miner sn13 economics s3-cost \
  --storage-gb-month 100 \
  --storage-usd-per-gb-month 0.023 \
  --put-requests 10000 \
  --put-usd-per-1000 0.005 \
  --transfer-out-gb 7 \
  --transfer-out-usd-per-gb 0.09
```

This calculates Jarvis-owned archive cost only. It does not include operator payout, provider cost, export CPU, local disk, validator serving bandwidth, or risk reserve. Use `sn13 economics estimate` to combine all task costs.

## Required Inputs Before Assigning Real Operator Work

Every real task needs:

| Input | Required |
| --- | --- |
| `source` | yes |
| `label` or `keyword` | yes |
| Gravity job ID and weight | yes |
| source time window | yes |
| quantity target | yes |
| max accepted task cost | yes |
| expected accepted scorable records | yes |
| expected duplicate rate | yes |
| expected rejection rate | yes |
| operator payout rule | yes |
| provider/source cost estimate | yes |
| bandwidth/export estimate | yes |
| validation risk reserve | yes |

Cannot-take-task rule:

Jarvis does not publish any real paid operator task until those inputs exist or are explicitly set to zero with a reason.

The task contract exposes the operator-facing economics:

- payout basis
- payable record cap
- duplicate/rejected/invalid records are not payable
- validation failure can zero payable records
- operator must estimate its own provider/proxy/compute cost before execution

## Metrics Jarvis Must Collect

### Source/Provider Metrics

- scrape start/end time
- provider used
- provider request count
- provider compute units or billable usage
- proxy bandwidth, if any
- records fetched
- records submitted

### Quality Metrics

- accepted scorable count
- accepted non-scorable count
- rejected count
- duplicate count
- missing-field count
- payload mismatch count
- empty-content count
- job match failures

### Storage/Export Metrics

- canonical bytes stored
- local DB size
- parquet file count
- parquet bytes generated
- upload bytes
- upload retries
- archive bytes uploaded
- archive object count
- archive storage class
- local staging bytes deleted
- validation pass/fail, when available

### Economic Metrics

- cost per submitted record
- cost per accepted record
- cost per accepted scorable record
- operator effective cost
- source effective cost
- daily spend
- remaining budget
- expected margin

## S3 Cost Modeling

If Jarvis uses only upstream presigned upload:

```text
jarvis_s3_storage_cost = 0 for upstream-owned destination
jarvis_export_cost = local_export_cpu + local_disk + outbound_upload_bandwidth + retries
```

If Jarvis creates its own archive bucket:

```text
jarvis_archive_bucket_cost =
    storage_gb_month_cost
  + put_request_cost
  + get_request_cost
  + lifecycle_transition_cost
  + data_retrieval_cost
  + data_transfer_out_cost
  + monitoring_cost
```

AWS states that S3 pricing depends on storage, requests/retrieval, data transfer, management, replication, and other features. This must be region-specific before we quote a dollar amount.

If Jarvis dual-uploads to upstream validation and Jarvis archive:

```text
dual_upload_cost =
    upstream_presigned_export_cost
  + jarvis_archive_bucket_cost
  + additional_retry_cost
```

Archive success does not make raw local data disposable by itself. Jarvis deletes temporary parquet staging after both uploads succeed. Jarvis retains or compacts canonical SQLite according to freshness, validator-serving, and re-export requirements.

## Operator Payout Rule

Operators should not be paid for raw submitted volume.

Default payout basis:

```text
payable_records =
  accepted_scorable_records
  - duplicate_penalty
  - rejection_penalty
  - validation_failure_penalty
```

Minimum policy:

- duplicates are not payable
- rejected records are not payable
- records outside task window are not payable
- source payload mismatch is not payable
- repeated low quality reduces publication priority
- validation failure can claw back or reserve payout under the task contract

## Source-Specific Economic Notes

### X

Current enabled paths:

- Apify token path
- Macrocosmos/API provider path, if configured
- Jarvis-approved operator provider path

Economic risk:

- X scraping is likely paid or provider-constrained
- account/proxy/provider costs can dominate record value
- scraping must target Gravity labels/keywords precisely

### Reddit

Current enabled paths:

- Apify token path
- free Reddit account credential path
- Jarvis-approved operator provider path

Economic risk:

- free account path can still be constrained by rate limits and compliance
- Apify/provider path is paid
- subreddit/keyword mismatch creates job-match risk

## Decision Gates

### Can Serve Validators

This is a readiness question:

- registered hotkey
- listener online
- local DB healthy
- enough disk
- validator protocol path working

### Jarvis Can Publish Operator Task

This is an economic and quality question:

- approved source/operator delivery path available
- operator quality above floor
- operator capacity known
- task max cost set
- expected unit cost below cap
- budget available
- task maps to real Gravity demand
- task contract exposes upload limits and payout economics

### Jarvis Can Intake Operator Upload

This is an intake enforcement question:

- local DB healthy
- disk above blocker floor
- submitted task ID exists
- source payload schema passes
- source URI is unique
- source time window matches task
- label/keyword target matches task
- submitted count and bytes stay within task limits

### Jarvis Can Export To Upstream S3 Validation

This is an upstream validation question:

- hotkey can sign auth commitment
- parquet files are generated
- filenames and row counts are correct
- duplicate/job-match/scraper validation risk is within threshold
- upstream auth URL is configured/reachable

### Jarvis Can Archive To Jarvis S3

This is a paid archive question:

- archive bucket configured
- archive region configured
- archive prefix configured
- lifecycle/retention policy defined
- parquet export exists
- local staging deletion waits for upstream and archive success

## Immediate Implementation Plan

No new feature work until these foundations are complete:

1. `subnets/sn13/economics.py` - done

   Pure models/functions for cost estimates, task caps, operator payout basis, and cannot-take-task decisions.

2. `tests/test_sn13_economics.py` - done

   Deterministic tests for formulas, missing-input blocking, S3 ownership modes, and payout calculations.

3. CLI command - done

   ```bash
   jarvis-miner sn13 economics estimate
   jarvis-miner sn13 economics estimate --json-output
   ```

4. Readiness capability naming and archive gate - done

   Readiness separates validator serving, operator intake, task publication, upstream S3 export, and Jarvis archive.

5. Readiness/planner economics integration - done

   Economics gates must refuse real task publication when required cost, quality, and margin inputs are missing.

6. Runtime metrics - pending

   Store task cost estimate, actual accepted counts, rejection counts, export bytes, archive bytes, local staging deletion bytes, and operator payout basis.

7. Operator contract update - done

   `OperatorTaskContract` includes upload limits, payout basis, payable cap, source requirements, minimum requirements, and intake-enforced quality rules.

## Production Blocker Ledger

These values are required before automated paid publication. They are not optional and they must not be guessed.

| Required value | Current status |
| --- | --- |
| Confirmed live upstream S3 auth/API behavior | pending live test |
| Average bytes per accepted X record after parquet export | pending measurement |
| Average bytes per accepted Reddit record after parquet export | pending measurement |
| Actual provider cost per 1,000 accepted X records | pending provider/account data |
| Actual provider cost per 1,000 accepted Reddit records | pending provider/account data |
| Operator payout rate that keeps operators viable and Jarvis margin positive | pending pilot data |
| Expected daily validator query bandwidth | pending live capture |
| Expected reward/share target that makes SN13 worth running | pending scoring/emission observation |
| Archive region and lifecycle class | pending deployment decision |
| Canonical SQLite retention/compaction window | pending validator-serving and re-export policy |

Blocked means Jarvis may run local/testnet simulation, but it does not publish automated real paid operator work.

## Sources

- Macrocosm Data Universe S3 validation: `https://github.com/macrocosm-os/data-universe/blob/main/docs/s3_validation.md`
- Macrocosm Data Universe miner docs: `https://github.com/macrocosm-os/data-universe/blob/main/docs/miner.md`
- Macrocosm Data Universe README/incentive mechanism: `https://github.com/macrocosm-os/data-universe`
- Bittensor emissions: `https://docs.learnbittensor.org/learn/emissions`
- AWS S3 pricing: `https://aws.amazon.com/s3/pricing/`
- Apify pricing: `https://apify.com/pricing`
