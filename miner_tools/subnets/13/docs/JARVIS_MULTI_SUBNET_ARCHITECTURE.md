# Jarvis Multi-Subnet Orchestrator Architecture

## The Vision: One System, Multiple Subnets

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         JARVIS ORCHESTRATOR                               │
│                    (Handles ALL Subnets, Any Task Type)                    │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │  SUBNET 13  │     │  SUBNET 18  │     │  SUBNET 50  │
    │ Data Univ.  │     │   Zeus      │     │   Synth     │
    └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
           │                   │                   │
           ▼                   ▼                   ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                    SUBNET HANDLERS                            │
    │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐        │
    │  │ SN13 Handler│   │ SN18 Handler│   │ SN50 Handler│        │
    │  │             │   │             │   │             │        │
    │  │ - GetIndex  │   │ - Predict  │   │ - Synthetic│        │
    │  │ - GetBucket │   │ - Query API│   │ - Generate │        │
    │  │ - GetContent│   │ - Score    │   │ - Validate│        │
    │  └─────────────┘   └─────────────┘   └─────────────┘        │
    └──────────────────────────────────────────────────────────────┘
                                │
                                ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                     WORKSTREAM (Unified Task Queue)          │
    │                                                                 │
    │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ │
    │  │ Task Queue │ │ Task Queue │ │ Task Queue │ │ Task Queue │ │
    │  │   (SN13)   │ │   (SN18)   │ │   (SN50)   │ │   (SNXX)   │ │
    │  └────────────┘ └────────────┘ └────────────┘ └────────────┘ │
    │                                                                 │
    │              All Subnets Use Same Queue System!               │
    └──────────────────────────────────────────────────────────────┘
                                │
                                ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                    PERSONAL OPERATORS                         │
    │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐          │
    │  │X Scraper│  │Reddit   │  │API Query│  │GPU Task │          │
    │  │Operator │  │Operator │  │Operator │  │Operator │          │
    │  └─────────┘  └─────────┘  └─────────┘  └─────────┘          │
    │                                                                 │
    │         Operators handle ANY subnet task!                     │
    └──────────────────────────────────────────────────────────────┘
                                │
                                ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                     SHARED DATABASE                           │
    │  ┌────────────┐ ┌────────────┐ ┌────────────┐                 │
    │  │ SN13 Data  │ │ SN18 Data  │ │ SN50 Data  │                 │
    │  └────────────┘ └────────────┘ └────────────┘                 │
    │                                                                 │
    │              One DB, Multiple Subnet Data                    │
    └──────────────────────────────────────────────────────────────┘
```

---

## Core Architecture Components

### 1. SUBNET ADAPTER LAYER

Each subnet has its own adapter that knows:
- What queries it receives
- How to decompose tasks
- How to aggregate results
- What operators needed

```python
class SubnetAdapter(ABC):
    """Base class for all subnet handlers"""
    
    @abstractmethod
    def can_handle(self, query_type: str) -> bool:
        """Can this adapter handle this query type?"""
        
    @abstractmethod
    def decompose_task(self, query, bucket_id) -> List[Task]:
        """Decompose into smaller tasks"""
        
    @abstractmethod
    def aggregate_results(self, results: List[Any]) -> Any:
        """Aggregate operator results back"""
        
    @abstractmethod
    def get_required_operators(self) -> List[str]:
        """What operators are needed for this subnet"""
        
    @abstractmethod
    def internal_quality_check(self, results) -> bool:
        """Check quality before sending to validator"""
```

### 2. SUBNET 13 ADAPTER (Data Universe)

```python
class SN13Adapter(SubnetAdapter):
    """SN13 Data Universe specific logic"""
    
    def can_handle(self, query_type: str) -> bool:
        return query_type in ["GetMinerIndex", "GetDataEntityBucket", "GetContentsByBuckets"]
    
    def decompose_task(self, query, bucket_id) -> List[Task]:
        """
        SN13 Decomposition Rules:
        - Count > 500: Split by time chunks (500 each)
        - Count < 500: Single operator
        """
        count = bucket_id.get("estimated_count", 100)
        
        if count > 500:
            # Split into chunks
            chunks = []
            for i in range(0, count, 500):
                chunks.append(Task(
                    subnet=13,
                    task_type="scrape",
                    params={**bucket_id, "range": f"{i}-{i+500}"},
                    operator_type="x_scraper" if bucket_id["source"] == "X" else "reddit_scraper"
                ))
            return chunks
        else:
            # Single task
            return [Task(
                subnet=13,
                task_type="scrape",
                params=bucket_id,
                operator_type="x_scraper" if bucket_id["source"] == "X" else "reddit_scraper"
            )]
    
    def aggregate_results(self, results: List) -> DataEntityBucket:
        """SN13: Deduplicate by content hash"""
        unique = {}
        for r in results:
            key = hash(r.content)
            if key not in unique:
                unique[key] = r
        return list(unique.values())
    
    def internal_quality_check(self, results) -> bool:
        """SN13: Min 50% count, valid content, correct label"""
        # Check minimum count
        # Check content validity
        # Check label matching
        return True
```

### 3. SUBNET 18 ADAPTER (Zeus - Prediction)

```python
class SN18Adapter(SubnetAdapter):
    """SN18 Zeus Prediction specific logic"""
    
    def can_handle(self, query_type: str) -> bool:
        return query_type in ["Prediction", "Query"]
    
    def decompose_task(self, query, params) -> List[Task]:
        """
        SN18 Decomposition:
        - Historical data fetch
        - Model inference
        - Result compilation
        """
        return [
            Task(subnet=18, task_type="fetch_history", params=params),
            Task(subnet=18, task_type="inference", params=params),
            Task(subnet=18, task_type="compile", params=params)
        ]
    
    def aggregate_results(self, results: List) -> Prediction:
        """SN18: Compile prediction from parts"""
        return compile_prediction(results)
    
    def get_required_operators(self) -> List[str]:
        return ["data_fetcher", "model_runner", "result_compiler"]
```

### 4. SUBNET 50 ADAPTER (Synth - Synthetic Data)

```python
class SN50Adapter(SubnetAdapter):
    """SN50 Synthetic Data specific logic"""
    
    def can_handle(self, query_type: str) -> bool:
        return query_type in ["Generate", "Validate"]
    
    def decompose_task(self, query, params) -> List[Task]:
        """
        SN50 Decomposition:
        - Generate multiple synthetic samples
        - Can parallelize across operators
        """
        num_samples = params.get("num_samples", 100)
        
        tasks = []
        chunk_size = 10
        for i in range(0, num_samples, chunk_size):
            tasks.append(Task(
                subnet=50,
                task_type="generate",
                params={**params, "start": i, "end": i+chunk_size},
                operator_type="synthetic_generator"
            ))
        return tasks
    
    def aggregate_results(self, results: List) -> SyntheticDataset:
        """SN50: Combine into dataset"""
        return combine_samples(results)
```

---

## Unified Workstream System

### Task Schema (Works for ALL Subnets)

```python
@dataclass
class UniversalTask:
    task_id: str              # unique ID
    subnet_id: int           # which subnet (13, 18, 50, etc.)
    query_type: str          # what kind of query
    task_type: str           # "scrape", "generate", "predict", etc.
    params: dict             # all the parameters
    operator_type: str       # which operator can handle this
    priority: int            # 1=high, 5=low
    deadline: datetime       # when it must complete
    status: str             # QUEUED, RUNNING, COMPLETED, FAILED
    created_at: datetime
    completed_at: datetime
    
    # Subnet-specific data
    bucket_id: dict          # for SN13
    prediction_params: dict  # for SN18
    generation_params: dict  # for SN50
```

### Task Router

```python
class TaskRouter:
    """Routes tasks to correct handlers based on subnet"""
    
    def __init__(self):
        self.adapters = {
            13: SN13Adapter(),
            18: SN18Adapter(),
            50: SN50Adapter(),
        }
    
    def route(self, query, subnet_id) -> UniversalTask:
        adapter = self.adapters[subnet_id]
        
        # Get bucket_id or params
        bucket_id = self.extract_bucket(query)
        
        # Decompose into tasks
        tasks = adapter.decompose_task(query, bucket_id)
        
        # Return first task (will queue rest)
        return tasks[0]
```

---

## Complete Multi-Subnet Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPLETE MULTI-SUBNET FLOW                              │
└─────────────────────────────────────────────────────────────────────────────┘

VALIDATOR  ──────────►

┌─────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATOR                                    │
└─────────────────────────────────────────────────────────────────────────┘

    ┌───────────────────────────────────────────────────────────────────┐
    │ 1. PARSE QUERY                                                     │
    │    - subnet_id: 13                                                 │
    │    - query_type: GetDataEntityBucket                              │
    │    - bucket_id: {source: X, label: $BTC, time: 1845}             │
    └───────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌───────────────────────────────────────────────────────────────────┐
    │ 2. ROUTE TO SUBNET ADAPTER                                        │
    │    - SN13Adapter handles this query                               │
    │    - adapter.can_handle("GetDataEntityBucket") = TRUE            │
    └───────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌───────────────────────────────────────────────────────────────────┐
    │ 3. DECOMPOSE TASK (Subnet-Specific!)                              │
    │    - SN13: count=1500 > 500 → chunk by time (3 chunks)          │
    │    - SN18: 3-step pipeline                                        │
    │    - SN50: parallel generation                                     │
    └───────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌───────────────────────────────────────────────────────────────────┐
    │ 4. CREATE UNIVERSAL TASKS                                          │
    │    Task1: subnet=13, op_type=x_scraper, range=0-500            │
    │    Task2: subnet=13, op_type=x_scraper, range=500-1000           │
    │    Task3: subnet=13, op_type=x_scraper, range=1000-1500          │
    └───────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌───────────────────────────────────────────────────────────────────┐
    │ 5. ADD TO WORKSTREAM QUEUE                                        │
    │    (Unified queue works for ALL subnets!)                         │
    └───────────────────────────────────────────────────────────────────┘
                                    │
            ┌─────────────────────┬─────────────────────┐
            │                     │                     │
            ▼                     ▼                     ▼
    ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
    │ Operator 1  │       │ Operator 2  │       │ Operator 3  │
    │ X Scraper   │       │ X Scraper   │       │ X Scraper   │
    │ (completes) │       │ (completes) │       │ (completes) │
    └──────┬──────┘       └──────┬──────┘       └──────┬──────┘
           │                     │                     │
           └─────────────────────┼─────────────────────┘
                                 │
                                 ▼
    ┌───────────────────────────────────────────────────────────────────┐
    │ 6. COLLECT RESULTS (by task_id)                                    │
    │    - Task1 returns 500 posts                                      │
    │    - Task2 returns 500 posts                                      │
    │    - Task3 returns 500 posts                                      │
    └───────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
    ┌───────────────────────────────────────────────────────────────────┐
    │ 7. AGGREGATE (Subnet-Specific!)                                   │
    │    - SN13Adapter.aggregate_results()                            │
    │    - Deduplicate by content hash                                  │
    └───────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
    ◄───────────────────────────────────────────────────────────────────┘
    │ 8. RETURN TO VALIDATOR                                            │
    └───────────────────────────────────────────────────────────────────┘
```

---

## How Subnets Are Configured

```python
# config.yaml
subnets:
  - netuid: 13
    name: "Data Universe"
    adapter: "SN13Adapter"
    operators_needed:
      - x_scraper
      - reddit_scraper
    decomposition_rules:
      chunk_threshold: 500
      chunk_size: 500
      
  - netuid: 18
    name: "Zeus"
    adapter: "SN18Adapter"
    operators_needed:
      - data_fetcher
      - model_runner
      - result_compiler
      
  - netuid: 50
    name: "Synth"
    adapter: "SN50Adapter"
    operators_needed:
      - synthetic_generator
```

---

## Summary: Key Architecture Points

1. **One Orchestrator** - Handles ALL subnets
2. **Subnet Adapters** - Each subnet has its own handler
3. **Decomposition Rules** - Subnet-specific (500 for SN13, pipeline for SN18)
4. **Unified Task Queue** - Works for ANY subnet
5. **Operator Pool** - Reusable across subnets
6. **Shared Database** - Stores all subnet data

---

This architecture lets us:
- Add new subnets easily (just add adapter)
- Use same workstream for everything
- Each subnet has optimized decomposition
- Operators can work on any subnet task

Want me to create the actual code skeleton for this architecture?
