# SN13 Task Workflow - Complete Design

## The Flow You Described

```
JOIN SUBNET → GET TASK FROM VALIDATOR → DECOMPOSE → SEND TO WORKSTREAM → WAIT → AGGREGATE → SUBMIT TO VALIDATOR
```

This is exactly right! Let me map it out:

---

## 1. JOIN SUBNET (Registration)

```
Wallet → Register on SN13 → Get UID → Start Listening
```

- Coldkey can be same (we have testminer)
- Need new hotkey for SN13
- Once registered, validators can query us

---

## 2. GET TASK FROM VALIDATOR

When validator queries, we receive:

### Query Types:

| Query | What We Get | Work? |
|-------|--------------|-------|
| GetMinerIndex | "What data?" | NO |
| GetDataEntityBucket | "Give me X posts about $BTC" | **YES** |
| GetContents | "Verify this data" | NO |

---

## 3. DECOMPOSE - The Key Part

### When CAN We Decompose?

**YES - Decompose when:**
- Data count > 500 posts (too big for one operator)
- Multiple time ranges in request
- Multiple labels ($BTC, $ETH, $SOL)

**NO - Single Operator Only when:**
- Data count < 100 posts (small, one operator faster)
- Specific single label request
- Specific single time bucket

### How To Decompose:

```
Original Request: GetDataEntityBucket(X, 1845, $BTC) = 1500 posts

┌─────────────────────────────────────────────────────────────────┐
│                    DECISION TREE                                │
└─────────────────────────────────────────────────────────────────┘

Is count > 500?
    │
    ├─► YES → Decompose by TIME CHUNKS
    │        1500 posts ÷ 500 = 3 chunks
    │        Chunk 1: 11:00-11:20 (500 posts) → Operator 1
    │        Chunk 2: 11:20-11:40 (500 posts) → Operator 2  
    │        Chunk 3: 11:40-12:00 (500 posts) → Operator 3
    │
    └─► NO → Single Operator
             500 posts → Operator 1
```

### Decomposition Algorithm:

```python
def should_decompose(bucket_id, count):
    """
    Decide if task should be decomposed
    """
    if count > 500:
        return True, "chunk_by_time"
    elif count > 1000:
        return True, "chunk_by_time_parallel"
    else:
        return False, "single_operator"

def decompose(bucket_id, count, strategy):
    """
    Split into chunks
    """
    if strategy == "chunk_by_time":
        chunks = []
        chunk_size = 500
        for i in range(0, count, chunk_size):
            chunks.append({
                "chunk_id": i // chunk_size,
                "source": bucket_id.source,
                "time_bucket": bucket_id.time_bucket_id,
                "label": bucket_id.label,
                "range": f"{i}-{i+chunk_size}",
                "assigned_to": None  # Will be assigned to operator
            })
        return chunks
```

---

## 4. SEND TO WORKSTREAM

Each chunk becomes a task in workstream:

```
Task ID: uuid-1234
Query: "Scrape X posts about $BTC from hour 1845, range 0-500"
Source: X
Label: $BTC
Time: 1845
Priority: HIGH (validator waiting)
Deadline: 30 seconds (timeout)
```

### Task Schema:

```python
@dataclass
class WorkstreamTask:
    task_id: str              # unique ID
    query_type: str           # "GetDataEntityBucket"
    bucket_id: dict           # source, time_bucket, label
    chunk_info: dict         # range, count
    priority: str            # HIGH, MEDIUM, LOW
    created_at: datetime
    deadline: datetime        # must complete by this
    assigned_operator: str     # which operator
    status: str              # QUEUED, RUNNING, COMPLETED, FAILED
```

---

## 5. WAIT IN QUEUE / GET RESULT

```
┌─────────────────────────────────────────────────────────────────┐
│                     TASK QUEUE                                  │
└─────────────────────────────────────────────────────────────────┘

   ┌─────────┐    ┌─────────┐    ┌─────────┐
   │ Task 1  │    │ Task 2  │    │ Task 3  │    ┌─────────┐
   │ QUEUED  │───►│ RUNNING │───►│ COMPLETE│───►│ AGGREGATE│
   └─────────┘    └─────────┘    └─────────┘    └─────────┘
   
   Operator 1 finishes → Result stored with Task ID
   Query by Task ID → Get all results
```

---

## 6. AGGREGATE RESULTS

After all chunks done:

```python
def aggregate_results(task_ids):
    """
    1. Collect all results by task ID
    2. Deduplicate (remove duplicates)
    3. Sort by timestamp/engagement
    4. Format to protocol
    """
    all_results = []
    
    for task_id in task_ids:
        results = get_results_by_task_id(task_id)
        all_results.extend(results)
    
    # Deduplicate
    unique_results = deduplicate(all_results)
    
    # Sort
    sorted_results = sort_by_time(unique_results)
    
    return sorted_results
```

---

## 7. INTERNAL QUALITY CHECKS (Before Validator)

Before submitting to validator, we check internally:

### Quality Checks:

```python
def internal_quality_check(results):
    """
    Run these checks BEFORE sending to validator
    """
    
    # 1. Minimum count check
    if len(results) < expected_count * 0.5:
        return False, "TOO_FEW_RESULTS"
    
    # 2. Content validation
    for result in results[:10]:  # Check first 10
        if not is_valid_content(result):
            return False, "INVALID_CONTENT"
    
    # 3. Label matching
    for result in results:
        if not matches_label(result, target_label):
            return False, "LABEL_MISMATCH"
    
    # 4. Source verification
    if not all(is_from_correct_source(r, expected_source) for r in results):
        return False, "SOURCE_MISMATCH"
    
    return True, "PASSED"


def is_valid_content(result):
    """Check content is real, not empty, not corrupted"""
    return (
        result.content is not None and
        len(result.content) > 10 and
        not is_garbage(result.content)
    )
```

### If Quality Check FAILS:

```
Quality Check FAILED → 
    Retry operator with different params OR
    Use fallback data (cache) OR
    Return partial with warning
```

---

## 8. SUBMIT TO VALIDATOR

Finally, send aggregated results:

```
VALIDATOR ◄─── Aggregate Results ─── ORCHESTRATOR
```

---

## Complete Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         JARVIS ORCHESTRATOR WORKFLOW                        │
└─────────────────────────────────────────────────────────────────────────────┘

VALIDATOR                                                                  ORCHESTRATOR
    │                                                                         │
    │──── GetDataEntityBucket(bucket_id) ──────────────────────────────────►│
    │                                                                         │
    │                              ┌───────────────────────────────────────┐   │
    │                              │ 1. PARSE TASK                        │   │
    │                              │    - source: X                       │   │
    │                              │    - label: $BTC                    │   │
    │                              │    - count: 1500                     │   │
    │                              └───────────────────┬───────────────────┘   │
    │                                                  │                       │
    │                              ┌───────────────────┴───────────────────┐   │
    │                              │ 2. DECISION: Decompose?              │   │
    │                              │    - count 1500 > 500 = YES          │   │
    │                              │    - Strategy: chunk_by_time         │   │
    │                              └───────────────────┬───────────────────┘   │
    │                                                  │                       │
    │                              ┌───────────────────┴───────────────────┐   │
    │                              │ 3. CHUNK INTO TASKS                  │   │
    │                              │    Task 1: range 0-500    → Op 1   │   │
    │                              │    Task 2: range 500-1000 → Op 2    │   │
    │                              │    Task 3: range 1000-1500→ Op 3    │   │
    │                              └───────────────────┬───────────────────┘   │
    │                                                  │                       │
    │                              ┌───────────────────┴───────────────────┐   │
    │                              │ 4. SEND TO WORKSTREAM                 │   │
    │                              │    - Create Task IDs                  │   │
    │                              │    - Add to queue                     │   │
    │                              │    - Dispatch to operators            │   │
    │                              └───────────────────┬───────────────────┘   │
    │                                                  │                       │
    │                              ┌───────────────────┴───────────────────┐   │
    │                              │ 5. WAIT & COLLECT                    │   │
    │                              │    - Poll for completion             │   │
    │                              │    - Timeout: 30s                    │   │
    │                              │    - All 3 complete?                 │   │
    │                              └───────────────────┬───────────────────┘   │
    │                                                  │                       │
    │                              ┌───────────────────┴───────────────────┐   │
    │                              │ 6. AGGREGATE RESULTS                  │   │
    │                              │    - Collect by task_id              │   │
    │                              │    - Deduplicate                     │   │
    │                              │    - Sort                            │   │
    │                              └───────────────────┬───────────────────┘   │
    │                                                  │                       │
    │                              ┌───────────────────┴───────────────────┐   │
    │                              │ 7. INTERNAL QUALITY CHECK             │   │
    │                              │    - Count check (min 50%)          │   │
    │                              │    - Content validation              │   │
    │                              │    - Label matching                  │   │
    │                              │    - Source verification             │   │
    │                              └───────────────────┬───────────────────┘   │
    │                                                  │                       │
    │                              ┌───────────────────┴───────────────────┐   │
    │                              │ 8. SUBMIT TO VALIDATOR              │   │
    │                              │    - Return data_entities            │   │
    │◄───────────────────────────────────────────────────────────────────────│
    │                                                                         │
    │                              [VALIDATOR SCORES US]                    │
    │                                                                         │
```

---

## Summary: Key Decision Points

| Step | Decision | Rule |
|------|----------|------|
| 1. Parse | Extract bucket_id | source + time + label |
| 2. Decompose? | If count > 500 | YES chunk_by_time, NO single |
| 3. Chunk | Split into 500-post chunks | Each chunk = 1 task |
| 4. Queue | Add to workstream | Each task = 1 operator |
| 5. Wait | Poll for completion | Max 30s timeout |
| 6. Aggregate | Collect all results | Dedupe + sort |
| 7. Quality | Internal checks | Min 50% count, valid content |
| 8. Submit | Return to validator | data_entities |

---

This is the complete workflow! Now you can see:
- When to decompose (count > 500)
- How to chunk (by time ranges)
- How to aggregate (deduplicate)
- How to check quality (before validator)

Want me to create the actual code for this workflow?
