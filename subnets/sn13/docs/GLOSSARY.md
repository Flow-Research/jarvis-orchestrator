# SN13 Glossary

## Jarvis

The subnet-facing miner-orchestrator.

Jarvis owns the SN13 miner identity, stores canonical data, serves validators, manages operators, and absorbs credibility risk.

## Operator

A personal agent or external worker that performs scraping work for Jarvis.

Operators do not join SN13 directly. Operators receive tasks from Jarvis and submit structured records back to Jarvis.

## Candidate Data

Data submitted by an operator before Jarvis accepts it.

Candidate data is not miner truth. It becomes miner truth only after validation, dedupe, and storage acceptance.

## Canonical Data

Data accepted into Jarvis SQLite storage as miner truth.

Canonical data is the only data Jarvis uses for miner index generation, bucket responses, and export.

## DataEntity

The atomic SN13 data record.

In Jarvis this is defined in `subnets/sn13/models.py`.

## DataEntityBucketId

The identifier for a logical SN13 bucket.

It is composed from:

- source
- time bucket
- label

## Time Bucket

The hour bucket derived from the source-created timestamp.

Operators do not choose this value. Jarvis derives it from `source_created_at`.

## MinerIndex

The summary of buckets Jarvis can serve to validators.

Jarvis builds the miner index from canonical SQLite data.

## Dynamic Desirability

The SN13 mechanism that describes what sources and labels the subnet currently values.

Jarvis uses it to decide what operators scrape.

## Freshness

The time-based value of data.

Jarvis uses a default 30-day freshness window, with Dynamic Desirability date ranges able to override default freshness for specific jobs.

## Scorable Data

Accepted data that is currently valuable under Jarvis policy and desirability rules.

## Non-Scorable Data

Accepted data that is valid but not currently valuable under scoring rules.

Example: data older than the default freshness window with no desirability override.

## Rejected Data

Candidate data that failed quality checks and never entered canonical miner storage.

## OperatorDemand

A planner output describing what data Jarvis needs.

It includes source, label, time bucket, priority, target quantity, and expiry.

## OperatorTask

A work item operators can execute.

It is derived from `OperatorDemand`.

## OperatorSubmission

The structured payload an operator sends back to Jarvis after scraping.

It includes source metadata, content, timestamps, URI, and provenance.

## Provenance

Internal audit metadata that explains how and why a record was collected.

Provenance supports debugging, replay, operator accountability, and payout decisions.

## S3 Export

The export path that converts canonical SQLite records into SN13-compatible parquet files for public dataset/validator workflows.

This is the next active implementation phase.
