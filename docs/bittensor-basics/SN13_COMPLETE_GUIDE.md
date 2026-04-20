# Subnet 13: Data Universe - Complete Technical Guide

## Overview

**Subnet 13 (Data Universe)** is Bittensor's decentralized data scraping subnet. It collects data from social media platforms (X/Twitter, Reddit) and rewards miners for providing fresh, unique, desirable data.

---

## 1. Architecture

### Participants

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SUBNET 13 - DATA UNIVERSE                          │
└─────────────────────────────────────────────────────────────────────────┘

                         ┌─────────────────┐
                         │   VALIDATOR     │
                         │                 │
                         │ - Queries miners│
                         │ - Verifies data │
                         │ - Scores miners │
                         │ - Sets weights  │
                         └────────┬────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │             │
                    ▼             ▼             ▼
              ┌─────────┐  ┌─────────┐  ┌─────────┐
              │ MINER 1 │  │ MINER 2 │  │ MINER N │
              │         │  │         │  │         │
              │ Scrape  │  │ Scrape  │  │ Scrape  │
              │ X,      │  │ X,      │  │ X,      │
              │ Reddit  │  │ Reddit  │  │ Reddit  │
              └─────────┘  └─────────┘  └─────────┘
```

### Key Components

| Component | Description |
|-----------|-------------|
| **Miner** | Scrapes data from X, Reddit; stores in SQLite; responds to validator queries |
| **Validator** | Queries miners for index, verifies data, scores, sets weights on chain |
| **Gravity** | Product for requesting specific data (dynamic desirability) |
| **S3 Storage** | Miners upload data to S3 for public access |
| **Dynamic Desirability** | Voting system determining which data is most valuable |

---

## 2. Task Distribution Flow (How Validators Query Miners)

### Step 1: Validator Gets Miner Index

```
VALIDATOR                                          MINER
   │                                                 │
   │──── GetMinerIndex Request ───────────────────► │
   │                                                 │
   │  Asks: "What data do you have?"                │
   │                                                 │
   │◄─── Returns CompressedMinerIndex ─────────────│
   │     (List of all data buckets + counts)        │
```

**Miner Code** (`neurons/miner.py`):
```python
async def get_index(self, synapse: GetMinerIndex) -> GetMinerIndex:
    """Returns compressed index of all data buckets this miner has."""
    compressed_index = self.storage.get_compressed_index(
        bucket_count_limit=constants.DATA_ENTITY_BUCKET_COUNT_LIMIT_PER_MINER_INDEX_PROTOCOL_4
    )
    synapse.compressed_index_serialized = compressed_index.model_dump_json()
    return synapse
```

**What it returns:**
- List of all DataEntityBuckets (source + time bucket + label)
- Count of data in each bucket
- Total storage used

### Step 2: Validator Requests Specific Data

```
VALIDATOR                                          MINER
   │                                                 │
   │─── GetDataEntityBucket Request ──────────────►│
   │     (Bucket ID: source + time_bucket + label) │
   │                                                 │
   │◄─── Returns DataEntities ──────────────────────│
   │     (Actual posts/tweets/comments)             │
```

**Miner Code**:
```python
async def get_data_entity_bucket(self, synapse: GetDataEntityBucket) -> GetDataEntityBucket:
    """Returns data entities from a specific bucket."""
    synapse.data_entities = self.storage.list_data_entities_in_data_entity_bucket(
        synapse.data_entity_bucket_id
    )
    return synapse
```

### Step 3: Validator Verifies Data (Verification)

```
VALIDATOR                                          MINER
   │                                                 │
   │─── GetContentsByBuckets ─────────────────────►│
   │     (Request sample content for verification)  │
   │                                                 │
   │◄─── Returns Contents ─────────────────────────│
   │     (Actual content to verify)                │
```

**This is critical!** Validator verifies:
- Data is real (not fake)
- Data matches the label
- Data is not duplicated
- Data is from the correct source

---

## 3. Data Model

### DataEntityBucket ID

Every piece of data is identified by a tuple:

```python
(data_source, time_bucket_id, label)
```

| Component | Example | Description |
|-----------|---------|-------------|
| **data_source** | `X`, `REDDIT` | Which platform |
| **time_bucket_id** | `1845` | Hourly bucket (1 per hour) |
| **label** | `$BTC`, `bittensor` | Topic/tag |

### Example Buckets:
- `X_1845_$BTC` = X posts about BTC from hour 1845
- `REDDIT_1845_bittensor` = Reddit posts about bittensor from hour 1845
- `X_1845_$AAPL` = X posts about Apple from hour 1845

---

## 4. Reward Calculation (How Miners Earn TAO)

### Formula

```
miner_score = Σ (data_value × miner_credibility)
```

### Data Value Calculation

**`data_value = source_weight × desirability_weight × time_scalar × bytes`**

#### 1. Source Weight
| Source | Weight |
|--------|--------|
| X (Twitter) | 1.0 |
| Reddit | 0.8 |

#### 2. Desirability Weight (Dynamic)
From **Dynamic Desirability** - what data is currently valuable:
- Data matching current jobs/requests = higher weight
- Default for unmatched data = 0.3 (30%)

#### 3. Time Scalar (Freshness)
```
time_scalar = 1.0 - (data_age_hours / (2 × max_age_hours))

Where:
- max_age_hours = 720 hours (30 days)
- Current data = 1.0
- 30 days old = 0.5
- Older = 0.0 (not scored)
```

#### 4. Bytes
Amount of data in the bucket.

### Miner Credibility

Validators track miner credibility through verification:

```
credibility = verified_checks / total_checks
```

If miner provides fake data repeatedly → credibility drops → rewards drop

### Duplication Factor

```
If N miners have same data:
  value = base_value / N
```

More unique data = more TAO!

---

## 5. Validator Scoring Process

### From `miner_evaluator.py`:

```python
async def eval_miner(self, uid: int):
    """Evaluates a miner in 4 steps:
    
    1. Get latest index from miner
    2. Choose random bucket to query
    3. Verify the data is correct
    4. Update miner's score
    """
    
    # Step 1: Get index
    miner_index = await self.dendrite.query(
        axons[uid],
        GetMinerIndex()
    )
    
    # Step 2: Pick random bucket
    bucket_id = random.choice miner_index.buckets
    
    # Step 3: Query and verify data
    data = await self.dendrite.query(
        axons[uid],
        GetDataEntityBucket(bucket_id)
    )
    
    # Verify it's real
    is_valid = self.verify_data(data)
    
    # Step 4: Update score
    score = calculator.get_score(data, miner_credibility)
    self.scorer.update_score(uid, score)
```

---

## 6. Weight Setting (How TAO Gets Distributed)

### Every Epoch (configurable):

```python
def set_weights():
    """Normalize scores and set on chain."""
    
    # Convert scores to weights (normalize to sum to 1.0)
    weights = softmax(scores)
    
    # Submit to chain
    subtensor.set_weights(
        netuid=13,
        uids=[...],        # Miner UIDs
        weights=[...],     # Normalized weights
    )
    
    # Chain distributes TAO proportionally to weights
```

### TAO Distribution:
```
Miner A (weight=0.5) gets 50% of subnet emissions
Miner B (weight=0.3) gets 30% of subnet emissions
Miner C (weight=0.2) gets 20% of subnet emissions
```

---

## 7. On-Demand Jobs (Gravity Integration)

Validators can also send **on-demand requests**:

```
VALIDATOR                    MINER                      GRAVITY (External)
    │                          │                               │
    │  OnDemandRequest ──────► │                               │
    │                         │                               │
    │                    Scrape data                          │
    │                    for specific                         │
    │                    keywords                              │
    │                         │                               │
    │                    Upload to                           │
    │                    S3                                   │
    │                         │                               │
    │◄─── Confirmation ────────│                              │
    │                         │                              │
    │                         │ ◄─── Job complete ──────────│
    │                         │                               │
    │                         │ ◄─── Query results ─────────│
    │                         │                               │
    │ ◄─ Response (data) ────┘                               │
```

---

## 8. Miner Setup Requirements

### Storage
- SQLite database for data storage
- Min 10GB recommended

### Scraping
- X API access (via Apidojo or similar)
- Reddit API access
- Comply with ToS (no prohibited content)

### S3 Upload (Optional but recommended)
- Upload data to S3 for public validation
- Enables verificaton by validators

---

## 9. Summary: Complete Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    COMPLETE SN13 FLOW                               │
└─────────────────────────────────────────────────────────────────────┘

1. MINER SCRAPES DATA
   ┌──────────┐    ┌──────────┐    ┌──────────┐
   │ Scrap X  │    │Scrap     │    │ Store   │
   │ posts    │───►│ Reddit   │───►│ in DB   │
   └──────────┘    └──────────┘    └──────────┘

2. VALIDATOR QUERIES
   ┌─────────────────┐     ┌─────────────────┐
   │ GetMinerIndex  │────►│ "What do you    │
   │ (ask index)    │◄────│ have?"          │
   └─────────────────┘     └─────────────────┘
   
   ┌──────────────────────────┐
   │ GetDataEntityBucket     │────► "Give me X data from bucket Y"
   │ (request data)          │◄───── [actual data]
   └──────────────────────────┘
   
   ┌──────────────────────────┐
   │ GetContentsByBuckets    │────► "Verify this data is real"
   │ (verify)                │◄───── [verification result]
   └──────────────────────────┘

3. VALIDATOR SCORES
   ┌─────────────────────────────────────┐
   │ score = data_value × credibility   │
   │                                     │
   │ data_value = (                      │
   │   source_weight ×                   │
   │   desirability_weight ×             │
   │   time_scalar ×                     │
   │   bytes                             │
   │ )                                   │
   └─────────────────────────────────────┘

4. WEIGHTS & EMISSIONS
   ┌────────────────────┐     ┌──────────────────────┐
   │ Normalize scores   │────►│ Set weights on chain  │
   │ to weights        │     │ (every epoch)         │
   └────────────────────┘     └──────────────────────┘
                                       │
                                       ▼
                              ┌────────────────────┐
                              │ TAO distributed    │
                              │ proportionally      │
                              └────────────────────┘
```

---

## 10. Key Files Reference

| File | Purpose |
|------|---------|
| `neurons/miner.py` | Miner implementation |
| `neurons/validator.py` | Validator implementation |
| `rewards/data_value_calculator.py` | Reward calculation |
| `rewards/miner_scorer.py` | Score tracking |
| `scraping/coordinator.py` | Data scraping coordination |
| `storage/miner/sqlite_miner_storage.py` | Data storage |
| `common/protocol.py` | Synapse definitions |

---

## What's Next?

Want me to:
1. **Set up a testnet miner** that logs all queries (without actual scraping)?
2. **Create a mock validator** to test task distribution locally?
3. **Build our own task distribution system** based on this understanding?

Let me know!