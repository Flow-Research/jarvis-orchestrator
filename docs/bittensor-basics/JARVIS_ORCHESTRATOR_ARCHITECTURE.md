# Jarvis Orchestrator - Architecture & Design

## The Vision

Jarvis Orchestrator is a **multi-subnet miner system** that:
1. Registers as miner on multiple Bittensor subnets
2. Receives tasks from validators on each subnet
3. Breaks tasks into chunks and dispatches to **Personal Operators** (agents)
4. Collects results and submits back to validators
5. Earns TAO for completed work

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         JARVIS ORCHESTRATOR                                  │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌────────────────────────────────────────┐
                    │         ORCHESTRATOR                   │
                    │                                        │
                    │  1. Listen for validator queries      │
                    │  2. Decompose tasks                   │
                    │  3. Dispatch to operators              │
                    │  4. Aggregate results                  │
                    │  5. Submit to validators               │
                    └────────────────┬───────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         │                           │                           │
         ▼                           ▼                           ▼
   ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
   │  SUBNET 13  │            │  SUBNET 18  │            │  SUBNET 50  │
   │ Data Univ.  │            │    Zeus     │            │   Synth     │
   └──────┬──────┘            └──────┬──────┘            └──────┬──────┘
          │                          │                          │
          ▼                          ▼                          ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │                     PERSONAL OPERATORS (AGENTS)                  │
   │                                                                  │
   │   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐          │
   │   │ Agent 1 │   │ Agent 2 │   │ Agent 3 │   │ Agent N │          │
   │   │         │   │         │   │         │   │         │          │
   │   │ Scrape  │   │ Scrape  │   │ Scrape  │   │ Scrape  │          │
   │   │ X/Reddit│   │ X/Reddit│   │ X/Reddit│   │ X/Reddit│          │
   │   └─────────┘   └─────────┘   └─────────┘   └─────────┘          │
   └──────────────────────────────────────────────────────────────────┘
```

---

## Multi-Subnet Architecture

### How It Works

Each subnet requires its own:
- **Hotkey** (unique identity)
- **Miner process** (running miner.py)
- **Axon port** (unique port)

But can share:
- **Coldkey** (main wallet, holds TAO)
- **Infrastructure** (server, monitoring)
- **Orchestrator logic** (task distribution)

### Process Structure

```
/jarvis/miners/
├── sn13_data_universe/
│   ├── miner.py         # SN13 specific protocol
│   ├── config.yaml      # netuid=13, port=8091
│   └── hotkey_sn13     # Unique hotkey
├── sn18_zeus/
│   ├── miner.py         # SN18 specific protocol
│   ├── config.yaml      # netuid=18, port=8092
│   └── hotkey_sn18     # Unique hotkey
├── sn50_synth/
│   ├── miner.py         # SN50 specific protocol
│   ├── config.yaml      # netuid=50, port=8093
│   └── hotkey_sn50     # Unique hotkey
```

### Running Multiple Miners

```bash
# Each gets its own PM2 process
pm2 start sn13_data_universe/miner.py --name miner-sn13 -- --netuid 13 --axon.port 8091 --wallet.hotkey hotkey_sn13
pm2 start sn18_zeus/miner.py      --name miner-sn18 -- --netuid 18 --axon.port 8092 --wallet.hotkey hotkey_sn18
pm2 start sn50_synth/miner.py     --name miner-sn50 -- --netuid 50 --axon.port 8093 --wallet.hotkey hotkey_sn50
```

---

## Task Distribution Flow

### Stage 1: Validator → Orchestrator

```
VALIDATOR                  ORCHESTRATOR
    │                          │
    │───GetMinerIndex────────►│ "What data do you have?"
    │◄───Returns index────────│ (list of all data buckets)
    │                          │
    │───GetDataEntityBucket──►│ "Give me X posts about $BTC"
    │◄───Returns data─────────│ (but we need to SCRAPE first!)
```

### Stage 2: Orchestrator → Operators

```
ORCHESTRATOR              PERSONAL OPERATORS
    │                          │
    │───Dispatch Task ────────►│ "Scrape X posts about $BTC"
    │                          │
    │                    ┌─────┴─────┐
    │                    │           │
    │                    ▼           ▼
    │              ┌─────────┐ ┌─────────┐
    │              │ Agent 1 │ │ Agent 2 │
    │              │         │ │         │
    │              │Scrape X │ │Scrape   │
    │              │         │ │Reddit   │
    │              └────┬────┘ └────┬────┘
    │                   │           │
    │                   └─────┬─────┘
    │                         │
    │◄───Results (data)───────┘
```

### Stage 3: Orchestrator → Validator

```
ORCHESTRATOR              VALIDATOR
    │                          │
    │───Return data───────────►│ "Here are the X posts"
    │                          │
    │                    VALIDATOR VERIFIES
    │                    (data is real, correct)
    │                          │
    │◄───Score updated─────────│ "Good data! +TAO"
```

---

## Components to Build

### 1. Miner Tools (Already Built ✅)
- Registration monitor (`miner_tools/monitor.py`)
- Auto-register (`miner_tools/monitor.py` - auto_register)
- Deregister alerts (`miner_tools/deregister.py`)
- Price alerts (`miner_tools/monitor.py`)

### 2. Task Distribution System (To Build)
- Listener for validator queries
- Task decomposition
- Operator dispatch
- Result aggregation

### 3. Personal Operators (Agents)
- Each agent specializes in a scraping type
- X scraper agent
- Reddit scraper agent
- YouTube scraper agent

---

## Development Stages

### Stage 1: Minimal Miner Setup
**Goal**: Get 1 subnet working end-to-end

**Tasks**:
1. ✅ Wallet setup (coldkey + hotkey)
2. ✅ Register on subnet
3. ⏳ Build task listener
4. ⏳ Build simple operator (mock)
5. ⏳ Submit response to validator

### Stage 2: Improve Operators
**Goal**: Multiple working operators

**Tasks**:
1. Build X scraping operator
2. Build Reddit scraping operator
3. Build result aggregation
4. Add compute acquisition (EigenCloud)

### Stage 3: Workstream Environment
**Goal**: Distributed, fair task distribution

**Tasks**:
1. Add gossipsub for discovery
2. Add task queue (Redis?)
3. Add fairness algorithm
4. Add more subnets

---

## SN13 Specific Implementation

For subnet 13 (Data Universe), here's how we intercept tasks:

```python
# In miner.py - override the endpoint handlers

async def get_data_entity_bucket(self, synapse: GetDataEntityBucket) -> GetDataEntityBucket:
    """Override to route to operators instead of local storage."""
    
    bucket_id = synapse.data_entity_bucket_id
    
    # Instead of reading from local DB:
    # 1. Route to appropriate operator(s)
    # 2. Wait for result
    # 3. Return data
    
    result = await self.route_to_operators(
        source=bucket_id.source,
        label=bucket_id.label,
        time_bucket=bucket_id.time_bucket_id
    )
    
    synapse.data_entities = result
    return synapse
```

---

## What's Been Built

| Component | Status | File |
|-----------|--------|------|
| Registration Monitor | ✅ | `miner_tools/monitor.py` |
| Auto-Register | ✅ | `miner_tools/monitor.py` |
| Deregister Alerts | ✅ | `miner_tools/deregister.py` |
| Price Alerts | ✅ | `miner_tools/monitor.py` |
| CLI Commands | ✅ | `miner_tools/cli.py` |

## What's Next

| Component | Priority | Notes |
|-----------|----------|-------|
| Task Listener | High | Intercept validator queries |
| Operator Agent | High | Simple scraping agent |
| Result Aggregation | Medium | Combine operator results |
| Multi-subnet setup | Medium | Expand to more subnets |

---

## Summary

The Jarvis Orchestrator is designed to:
1. **Mine multiple subnets** - each with own hotkey/process
2. **Decompose tasks** - break validator requests into work chunks
3. **Dispatch to operators** - route to specialized agents
4. **Aggregate results** - combine and submit to validators
5. **Earn TAO** - get rewarded for completed work

This is exactly what we started building with `miner_tools` - now we need to extend it with the task distribution layer.