#!/bin/sh
set -eu

: "${JARVIS_SN13_MAX_TASK_COST:?JARVIS_SN13_MAX_TASK_COST is required}"
: "${JARVIS_SN13_EXPECTED_REWARD:?JARVIS_SN13_EXPECTED_REWARD is required}"
: "${JARVIS_SN13_EXPECTED_SUBMITTED:?JARVIS_SN13_EXPECTED_SUBMITTED is required}"
: "${JARVIS_SN13_EXPECTED_ACCEPTED:?JARVIS_SN13_EXPECTED_ACCEPTED is required}"
: "${JARVIS_SN13_DUPLICATE_RATE:?JARVIS_SN13_DUPLICATE_RATE is required}"
: "${JARVIS_SN13_REJECTION_RATE:?JARVIS_SN13_REJECTION_RATE is required}"
: "${JARVIS_SN13_VALIDATION_PASS_PROBABILITY:?JARVIS_SN13_VALIDATION_PASS_PROBABILITY is required}"
: "${JARVIS_SN13_PAYOUT_BASIS:?JARVIS_SN13_PAYOUT_BASIS is required}"

exec jarvis-miner sn13 scheduler run \
  --cache-dir "${JARVIS_SN13_GRAVITY_CACHE_DIR:-/app/subnets/sn13/cache/gravity}" \
  --db-path "${JARVIS_SN13_DB_PATH:-/app/subnets/sn13/data/sn13.sqlite3}" \
  --workstream-db-path "${JARVIS_WORKSTREAM_DB_PATH:-/app/data/workstream.sqlite3}" \
  --target-items "${JARVIS_SN13_TARGET_ITEMS:-5}" \
  --recent-buckets "${JARVIS_SN13_RECENT_BUCKETS:-1}" \
  --max-tasks "${JARVIS_SN13_MAX_TASKS:-10}" \
  --interval-seconds "${JARVIS_SN13_SCHEDULER_INTERVAL_SECONDS:-1200}" \
  --dd-timeout-seconds "${JARVIS_SN13_DD_TIMEOUT_SECONDS:-30}" \
  --max-task-cost "${JARVIS_SN13_MAX_TASK_COST}" \
  --expected-reward "${JARVIS_SN13_EXPECTED_REWARD}" \
  --expected-submitted "${JARVIS_SN13_EXPECTED_SUBMITTED}" \
  --expected-accepted "${JARVIS_SN13_EXPECTED_ACCEPTED}" \
  --duplicate-rate "${JARVIS_SN13_DUPLICATE_RATE}" \
  --rejection-rate "${JARVIS_SN13_REJECTION_RATE}" \
  --validation-pass-probability "${JARVIS_SN13_VALIDATION_PASS_PROBABILITY}" \
  --payout-basis "${JARVIS_SN13_PAYOUT_BASIS}" \
  --operator-payout "${JARVIS_SN13_OPERATOR_PAYOUT:-0}" \
  --scraper-provider-cost "${JARVIS_SN13_SCRAPER_PROVIDER_COST:-0}" \
  --proxy-cost "${JARVIS_SN13_PROXY_COST:-0}" \
  --compute-cost "${JARVIS_SN13_COMPUTE_COST:-0}" \
  --local-storage-cost "${JARVIS_SN13_LOCAL_STORAGE_COST:-0}" \
  --export-staging-cost "${JARVIS_SN13_EXPORT_STAGING_COST:-0}" \
  --upload-bandwidth-cost "${JARVIS_SN13_UPLOAD_BANDWIDTH_COST:-0}" \
  --retry-cost "${JARVIS_SN13_RETRY_COST:-0}" \
  --risk-reserve "${JARVIS_SN13_RISK_RESERVE:-0}" \
  --jarvis-archive-bucket-cost "${JARVIS_SN13_ARCHIVE_BUCKET_COST:-0}" \
  --s3-mode "${JARVIS_SN13_S3_MODE:-upstream_presigned}" \
  --currency "${JARVIS_SN13_CURRENCY:-USD}"
