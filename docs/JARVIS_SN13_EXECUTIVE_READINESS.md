# Jarvis SN13 Executive Readiness

Last updated: 2026-04-22

## Decision Summary

Jarvis is not mainnet-ready for SN13 yet.

The remaining blockers are operational, not conceptual:

1. the SN13 hotkey is not registered on subnet 13 yet
2. the SN13 listener is not running online for validator traffic yet
3. the parquet export and upstream upload path is not complete yet

Everything else is support work around those three items.

## What Jarvis Needs To Spend

### One-time or dynamic chain spend

- SN13 registration burn is dynamic
- current observed SN13 registration cost on `2026-04-22`: `0.039344 TAO`
- using CoinMarketCap's TAO price of `$247.97` crawled on `2026-04-22`, that is about `$9.76`

This fee can move up or down. Jarvis should always read the live number from:

```bash
uv run jarvis-miner -c deploy/monitor.mainnet.yaml monitor price 13
```

### Minimum wallet funding policy

- keep at least `1 TAO` liquid in the Jarvis coldkey before enabling any auto-register path
- at the same `$247.97` reference price, `1 TAO` is about `$247.97`

This is not the join fee. It is the operating buffer so Jarvis does not try to join with an almost-empty wallet.

### Monthly Jarvis infrastructure

Minimum runnable server today:

- `2 vCPU`
- `4 GB RAM`
- `80 GB SSD`
- current DigitalOcean Basic price: `$24/month`

Mainnet target server once listener and export are live:

- `4 vCPU`
- `8 GB RAM`
- `160 GB SSD`
- current DigitalOcean Basic price: `$48/month`

### Optional archive storage

Jarvis does not need its own S3 bucket to upload to the validator path because SN13 uses a presigned upstream upload flow.

Jarvis needs its own S3 bucket only if Jarvis wants its own archive copy for audit, replay, incident review, and recovery.

Current AWS S3 Standard pricing anchor:

- `$0.023` per GB-month storage in S3 Standard
- `100 GB` archive is about `$2.30/month`
- `1 TB` archive is about `$23/month`

This excludes request, retrieval, and transfer charges.

## What Personal Operators Need To Pay

Jarvis does not pay the operator scraping bill directly.

Each personal operator is responsible for its own:

- source/API access
- proxy cost
- compute cost
- local storage
- task execution margin decision

Jarvis only publishes the task contract and enforces acceptance rules at intake.

## Current Blocking Items

Current SN13 readiness status from the repo on `2026-04-22`:

- `hotkey_registered_on_subnet`: blocked
- `listener_running_online`: blocked
- `parquet_export_available`: blocked
- `listener_capture_evidence_present`: warning
- `listener_query_surface_observed`: warning
- `jarvis_archive_bucket_configured`: warning, but only required if Jarvis archive mode is enabled

What this means in plain language:

- Jarvis can already accept operator uploads into canonical SQLite
- Jarvis cannot serve real validator traffic yet
- Jarvis cannot complete validator-facing export yet
- Jarvis has not yet proven real validator request capture on live traffic

## Minimum Go-Live Package

Jarvis can move to an SN13 mainnet trial only after all of these are true:

1. SN13 hotkey is registered
2. listener is online and reachable
3. live validator requests have been captured and verified
4. parquet export and upstream upload path are working end to end
5. workstream API, scheduler, and canonical SQLite remain stable under load

## CEO-Level Budget View

If the team wanted to prepare for a controlled SN13 mainnet trial today, the practical budget line is:

- dynamic join fee: about `$9.76` at the `2026-04-22` observed burn and TAO reference price
- wallet operating buffer: about `$247.97` for `1 TAO`
- minimum server: about `$24/month`
- safer mainnet target server: about `$48/month`
- optional Jarvis archive S3: starts around `$2.30/month` per `100 GB` before request and transfer charges

## Sources

- local live command: `uv run jarvis-miner -c deploy/monitor.mainnet.yaml monitor price 13`
- local live command: `uv run jarvis-miner sn13 readiness --json`
- DigitalOcean pricing: https://www.digitalocean.com/pricing/droplets
- AWS S3 pricing: https://aws.amazon.com/s3/pricing/
- TAO/USD reference: https://coinmarketcap.com/currencies/bittensor/
