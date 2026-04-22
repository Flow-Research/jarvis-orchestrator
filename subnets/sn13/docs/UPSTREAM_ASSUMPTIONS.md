# SN13 Upstream Assumption Ledger

## Purpose

This file records the upstream facts Jarvis currently depends on for SN13.

Every SN13 implementation phase must check this file before changing models, scoring policy, listener protocol, or export behavior.

## Verified Upstream Sources

Primary upstream repository:

- `https://github.com/macrocosm-os/data-universe`

Verified files:

- `common/constants.py`
- `common/data.py`
- `common/protocol.py`
- `docs/scoring.md`
- `docs/dynamic_desirability.md`
- `docs/s3_validation.md`
- `dynamic_desirability/data.py`
- `dynamic_desirability/default.json`

## Current Assumptions

| Area | Jarvis assumption | Upstream source |
| --- | --- | --- |
| Bucket size limit | A data entity bucket is limited to 128 MB. | `common/constants.py`, `docs/scoring.md` |
| Miner index bucket limit | Protocol 4 compressed miner index limit is 350,000 buckets. | `common/constants.py`, `common/data.py`, `docs/scoring.md` |
| Freshness | Default data age limit is 30 days for non-desirable jobs. | `common/constants.py`, `docs/scoring.md`, `docs/dynamic_desirability.md` |
| Time bucket | A time bucket is the hour since epoch derived from source datetime. | `common/data.py` |
| Label length | Labels are limited to 140 characters and normalized lowercase for non-YouTube labels. | `common/constants.py`, `common/data.py` |
| Canonical entity fields | SN13 `DataEntity` contains URI, datetime, source, optional label, content bytes, and content size bytes. | `common/data.py` |
| Bucket identity | Buckets are identified by time bucket, source, and optional label. | `common/data.py` |
| Miner index | Miners expose compressed miner indexes. | `common/data.py`, `common/protocol.py` |
| Compressed index shape | `CompressedMinerIndex` is JSON with `sources` keyed by upstream source ID and values containing compressed buckets with `label`, `time_bucket_ids`, and `sizes_bytes`. | `common/data.py`, `neurons/miner.py` |
| Protocol requests | Main miner query types include `GetMinerIndex`, `GetDataEntityBucket`, and `GetContentsByBuckets`. | `common/protocol.py` |
| Index response field | `GetMinerIndex` responses set `compressed_index_serialized` and `version`. | `common/protocol.py`, `neurons/miner.py` |
| Bucket response field | `GetDataEntityBucket` responses set `data_entities` and `version`. | `common/protocol.py`, `neurons/miner.py` |
| Contents response field | `GetContentsByBuckets` responses set `bucket_ids_to_contents` and `version`. | `common/protocol.py`, `neurons/miner.py` |
| Request limits | Per validation period limits are 1 index request, 1 bucket request, and 5 contents-by-buckets requests. | `common/protocol.py` |
| Dynamic Desirability fields | Jobs include platform/source, label, optional keyword, weight, and optional date range. | `docs/dynamic_desirability.md`, `dynamic_desirability/data.py` |
| Desirable date ranges | Desirable jobs with date ranges score in-range data and score out-of-range data as zero for that job path. | `docs/dynamic_desirability.md` |
| Credibility | Credibility uses alpha 0.15 and exponent 2.5 in score scaling. | `docs/scoring.md` |
| Export filename | Parquet filenames follow `data_YYYYMMDD_HHMMSS_count_16hex.parquet`. | `docs/s3_validation.md` |
| Export row count | Filename count must match actual parquet row count. | `docs/s3_validation.md` |
| Export path | Export files are organized under miner hotkey and job ID. | `docs/s3_validation.md` |
| S3 validation | Validators check filename format, record count, duplicate rate, scraper success, and job match rate. | `docs/s3_validation.md` |
| X export schema | X parquet columns must match the validator expected column set from upstream S3 validation utilities. | `upload_utils/s3_uploader.py`, `vali_utils/s3_utils.py` |
| Reddit export schema | Reddit parquet columns must match the validator expected column set from upstream S3 validation utilities. | `upload_utils/s3_uploader.py`, `vali_utils/s3_utils.py` |

## Known Upstream Tensions

### Source weights differ by source

Observed upstream references are not perfectly consistent:

- `docs/scoring.md` says Reddit `0.55`, X `0.35`, YouTube `0.1`.
- `common/data.py` currently encodes Reddit `0.65`, X `0.35`, and unknown sources as `0`.
- `docs/s3_validation.md` references Reddit `0.65`, X `0.35`.

Jarvis response:

- source weights live in `SN13Policy.source_weights`
- source weights are configurable
- Phase 6 export work must not hardcode source weights into export logic
- before mainnet usage, source weights must be rechecked against the exact upstream release/tag being targeted

### YouTube support requires confirmation

Upstream Dynamic Desirability models include YouTube handling, while older scoring/source references emphasize Reddit and X.

Jarvis response:

- `DataSource.YOUTUBE` exists in local models
- planner/desirability can parse YouTube-style jobs
- operator intake and export support are not complete for YouTube
- Reddit and X remain the implementation baseline until live upstream behavior is confirmed

### S3 validation thresholds differ between docs and current validator code

Observed upstream references are not perfectly consistent:

- `docs/s3_validation.md` says duplicate rate must be `<=10%`.
- current `vali_utils/s3_utils.py` sets `MAX_DUPLICATE_RATE = 5.0`.

Jarvis response:

- local export avoids introducing duplicate rows from rejected/non-canonical submissions
- exact validator thresholds remain external validation policy, not export policy
- before upload automation, validation thresholds must be rechecked against the target upstream release/tag

## Enforcement Rule

No SN13 implementation can introduce a protocol, scoring, or export claim without one of:

- direct upstream source reference
- local test proving the intended adapter behavior
- explicit note in this ledger marking it as a Jarvis-owned internal design decision

## Next Required Review

Before implementing Phase 7 live protocol alignment:

1. Recheck `common/protocol.py`.
2. Recheck `neurons/miner.py` response binding behavior.
3. Capture live validator requests.
4. Add tests that enforce exact synapse response fields.
