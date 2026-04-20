# SN13 Protocol Discovery

## Purpose

This document is the current working understanding of **Subnet 13 (Data Universe)** in the context of the **Jarvis Miner Orchestrator**.

The goal is not to lock in final architecture yet. The immediate goal is to learn, with as much precision as possible:

- what validators actually send to miners on SN13
- which query types exist in real traffic
- what each request payload looks like
- what validators expect back
- what the real timeout and latency constraints are
- which requests should be answered directly versus routed into the workstream
- which requests can be decomposed and aggregated safely

This is the dependency for almost every later decision in Jarvis.

## Product Context

Jarvis is being built as a **subnet-facing orchestrator** for your broader platform.

The broader platform idea is:

- you and I can bring personal operator agents
- those operators pull tasks from a shared workstream
- Jarvis joins selected Bittensor subnets
- Jarvis receives validator queries as the miner-facing surface
- Jarvis either:
  - answers directly
  - forwards a task to the workstream as-is
  - decomposes a larger request into smaller operator tasks
- Jarvis aggregates the results and returns one final response to the validator
- Jarvis earns on behalf of the orchestrated operator system

For now, the active research target is **SN13 on testnet**.

## Why SN13 Matters

SN13 looks like one of the cleaner early subnets for building this orchestration pattern because the workload appears to be centered on **data discovery**, **data retrieval**, and **data verification** rather than heavy model inference.

That makes it a good place to learn:

- inbound validator protocol shape
- routing logic
- decomposition strategy
- aggregation rules
- timeout behavior
- credibility and verification mechanics

## What We Currently Know

There are two types of knowledge in this repo right now:

1. **Product-direction knowledge**
2. **Protocol hypotheses**

The product direction is now clear.

The protocol details are still partly inferred from the current listener prototypes and design notes. They are not yet fully validated from real captured SN13 traffic.

That distinction matters.

## Current Hypothesized SN13 Query Families

Based on the existing listener code and notes, the current working model is that SN13 validator traffic revolves around three main request types:

### 1. `GetMinerIndex`

Working interpretation:

- validator asks what data the miner has
- miner returns a bucket/index-style summary
- likely used by validator to decide which miner to query for which buckets

Likely characteristics:

- low-cost
- no decomposition needed
- should eventually be served from local inventory or storage metadata

### 2. `GetDataEntityBucket`

Working interpretation:

- validator requests actual data for a specific bucket
- this is the main retrieval path
- this is the most likely candidate for workstream routing or decomposition

Likely characteristics:

- centered around a bucket identifier
- bucket likely includes fields such as source, time bucket, and label/topic
- may require returning actual posts or data entities
- may be the main earning path

### 3. `GetContentsByBuckets`

Working interpretation:

- validator asks for content samples to verify miner quality or authenticity
- this seems closer to verification than fresh retrieval

Likely characteristics:

- probably should be served from stored evidence or cached content
- likely affects credibility scoring
- probably should not be handled like a fresh workstream scraping request

## What We Have Not Proven Yet

These are still open and must be learned from real traffic:

- whether the three query families above are complete
- the exact synapse classes used on live SN13
- the exact field names and nested payload shapes
- whether some fields are optional or always present
- whether validators include timeout values on synapses
- what response structure validators truly expect
- whether some requests are repeated or staged
- whether there are hidden verification or scoring-related request paths
- what the practical timeout budget is on testnet
- whether decomposition is even safe for all retrieval requests

## What We Added To The Repo

To move from assumptions to evidence, the listener has been upgraded from a demo logger into a **protocol recorder**.

### Added file

- [listener/protocol_observer.py](./protocol_observer.py)

This file now records a structured observation for each query, including:

- `query_id`
- UTC timestamp
- query type
- validator hotkey
- synapse class name
- best-effort timeout extraction
- measured local handling latency
- payload
- inferred payload schema
- response payload
- inferred response schema
- dendrite metadata
- axon metadata
- public synapse attributes
- notes and extra metadata

### Updated file

- [listener/listener.py](./listener.py)

This listener now:

- records captures for all three current SN13 handler paths
- writes capture artifacts to disk
- records decomposition metadata on `GetDataEntityBucket`
- prints capture file paths for each observed request
- maintains lightweight summary stats

### Added tests

- [listener/test_protocol_observer.py](./test_protocol_observer.py)

These tests verify the observation and serialization logic independently from the repo’s older test layout.

## Where Captures Are Stored

By default, captures are written under:

```text
listener/captures/
```

Important files:

- `listener/captures/queries.jsonl`
  - append-only stream of all observed queries
- `listener/captures/summary.json`
  - aggregate counts by query type and validator
- `listener/captures/YYYY-MM-DD/<query_id>.json`
  - one full structured observation per query

## Recommended Command To Run The Recorder

There is one important caveat:

`bittensor` appears to interfere with the normal CLI help and argument display in `listener.py`, so the safest way to launch the listener right now is to instantiate `TaskListener` directly from Python.

Run this from the repo root:

```bash
python3 -u -c "import asyncio; from listener.listener import TaskListener; asyncio.run(TaskListener(netuid=13, wallet_name='sn13miner', network='test', capture_dir='listener/captures').start())"
```

If you want to keep the captures somewhere else:

```bash
python3 -u -c "import asyncio; from listener.listener import TaskListener; asyncio.run(TaskListener(netuid=13, wallet_name='sn13miner', network='test', capture_dir='listener/sn13_live_captures').start())"
```

## Useful Follow-Up Commands

Watch the summary file as captures accumulate:

```bash
watch -n 2 'cat listener/captures/summary.json'
```

Inspect the event stream:

```bash
tail -f listener/captures/queries.jsonl
```

List full capture artifacts:

```bash
find listener/captures -type f | sort
```

Pretty-print a specific capture file:

```bash
python3 -m json.tool listener/captures/2026-04-11/<query_id>.json
```

## What To Expect When It Works

When the listener is receiving traffic successfully, the intended observable flow is:

1. Jarvis starts and binds its axon.
2. Jarvis serves on SN13 testnet.
3. A validator sends a request.
4. The listener prints:
   - query type
   - validator hotkey
   - best-effort timeout
   - payload details
   - decomposition details for bucket requests
   - capture file location
5. A structured observation is written to disk.

The exact amount of traffic you receive will depend on:

- whether the wallet/hotkey is actually registered on SN13 testnet
- whether the axon is reachable from validators
- whether validators are actively querying on the network at that time

## Operational Caveats

### Registration

If the hotkey is not registered on SN13 testnet, you may not receive useful live validator traffic.

### Reachability

The current listener binds:

- port `8091`
- IP `127.0.0.1`

That is acceptable for local experimentation, but it may not be enough for real network reachability from external validators. If live traffic does not appear, one likely cause is that the axon is not externally reachable.

### Response payloads are still mock payloads

The listener currently returns mock content. That is acceptable for protocol discovery, but it does not mean the miner is production-correct yet.

### Decomposition is still provisional

The decomposition plan shown for `GetDataEntityBucket` is currently a hypothesis and instrumentation aid. It is not yet the final orchestration policy.

## What We Learned About SN13 So Far

### High-confidence understanding

- SN13 is the current target subnet for learning Jarvis’s subnet-facing orchestration model.
- The likely work split is between discovery, retrieval, and verification style requests.
- `GetDataEntityBucket` is the most important likely retrieval path.
- `GetMinerIndex` looks like a metadata/inventory query, not a workstream query.
- `GetContentsByBuckets` looks like a verification query, not a fresh scraping query.
- The correct next step is protocol observation before architecture lock-in.

### Architectural implication

Jarvis on SN13 is unlikely to be a single generic “run a task” miner.

It will more likely need **query-type-aware routing**:

- inventory query handling
- retrieval query handling
- verification query handling

Only after that should Jarvis decide:

- direct response
- cached response
- workstream pass-through
- decomposed parallel execution

### Strategic implication

For SN13, the first hard problem is not decomposition.

The first hard problem is **truthful protocol understanding**:

- exact request forms
- expected response forms
- timing
- scoring implications

Without that, decomposition design is premature.

## Proposed Research Sequence

This is the recommended order:

1. Capture real SN13 validator traffic.
2. Build a query inventory from the captured files.
3. Group captures by request type and payload shape.
4. Measure real timeout fields and observed latency budgets.
5. Identify which request types are:
   - direct/local
   - cached
   - verification-only
   - retrieval
   - decomposable
6. Define workstream contracts only after the above is stable.
7. Define aggregation rules after real retrieval responses are understood.

## Working Hypothesis For Jarvis On SN13

This is the current likely end-state, still subject to captured evidence:

```text
Validator query
  -> classify query type
  -> if inventory request: answer directly
  -> if verification request: answer from stored evidence
  -> if retrieval request:
       -> determine direct vs decomposed routing
       -> send to workstream or operators
       -> aggregate results
       -> return validator response
```

## Immediate Next Step

The next concrete step is simple:

- run the recorder
- leave it online
- collect real SN13 captures

Once you have even a small set of real capture files, we can convert this document from a hypothesis-driven note into a real SN13 protocol spec.
