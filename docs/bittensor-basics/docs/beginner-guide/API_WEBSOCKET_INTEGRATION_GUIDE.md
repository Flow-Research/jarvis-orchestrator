# 🔌 API & WebSocket Integration Guide

Complete guide for integrating external data sources (API/WebSocket) into your subnet, handling tasks, and implementing EMA validator approach.

## 📋 Table of Contents

1. [Overview](#overview)
2. [Adding API/WebSocket Data to Miner](#adding-apiwebsocket-data-to-miner)
3. [Task Definition & Handling](#task-definition--handling)
4. [Request Format Definition](#request-format-definition)
5. [Miner Task Processing](#miner-task-processing)
6. [Sending Tasks to Validator](#sending-tasks-to-validator)
7. [Validator Logic](#validator-logic)
8. [EMA Validator Approach](#ema-validator-approach)
9. [Complete Workflow](#complete-workflow)
10. [Practical Examples](#practical-examples)

---

## 🎯 Overview

### Standard Bittensor Flow vs API/WebSocket Flow

```
STANDARD FLOW:
Validator → Synapse → Miner → Response → Validator

API/WEBSOCKET FLOW:
External API/WebSocket → Miner → Process → Store → Validator queries → Score
```

---

## 📡 Adding API/WebSocket Data to Miner

### Where to Add Integration

#### Option 1: WebSocket Integration (Real-time)

**File**: `neurons/miner.py`

**What to add**:
1. WebSocket manager class
2. WebSocket connection in `__init__`
3. Task queue for incoming data
4. Background thread for WebSocket

**Example Implementation**:

```python
# neurons/miner.py

import asyncio
import threading
import queue
import websocket
import json
from typing import Dict, Any, Optional

class Miner(BaseMinerNeuron):
    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)
        
        # Add WebSocket manager
        self.ws_manager = WebSocketManager(
            url=config.ws_url,  # e.g., "wss://api.example.com/orders"
            miner=self
        )
        
        # Task queue for incoming data
        self.task_queue = queue.Queue()
        
        # Start WebSocket in background thread
        self.ws_thread = threading.Thread(
            target=self.ws_manager.run,
            daemon=True
        )
        self.ws_thread.start()
        
        bt.logging.info("WebSocket connection started")

# WebSocket Manager Class
class WebSocketManager:
    def __init__(self, url: str, miner: 'Miner'):
        self.url = url
        self.miner = miner
        self.ws = None
        self.running = False
        
    def on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            bt.logging.info(f"Received task: {data}")
            
            # Add to task queue
            self.miner.task_queue.put(data)
            
        except Exception as e:
            bt.logging.error(f"Error processing WebSocket message: {e}")
    
    def on_error(self, ws, error):
        bt.logging.error(f"WebSocket error: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        bt.logging.info("WebSocket connection closed")
    
    def on_open(self, ws):
        bt.logging.info("WebSocket connection opened")
    
    def run(self):
        """Run WebSocket connection"""
        self.running = True
        while self.running:
            try:
                self.ws = websocket.WebSocketApp(
                    self.url,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                    on_open=self.on_open
                )
                self.ws.run_forever()
            except Exception as e:
                bt.logging.error(f"WebSocket connection error: {e}")
                time.sleep(5)  # Reconnect after 5 seconds
```

#### Option 2: REST API Integration (Polling)

**File**: `neurons/miner.py`

**What to add**:
1. API client
2. Polling mechanism
3. Task processing

**Example Implementation**:

```python
# neurons/miner.py

import requests
import time
import threading

class Miner(BaseMinerNeuron):
    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)
        
        # API configuration
        self.api_url = config.api_url  # e.g., "https://api.example.com/tasks"
        self.api_key = config.api_key
        self.poll_interval = config.poll_interval or 10  # seconds
        
        # Task storage
        self.processed_tasks = {}  # {task_id: result}
        
        # Start API polling thread
        self.api_thread = threading.Thread(
            target=self.poll_api,
            daemon=True
        )
        self.api_thread.start()
        
        bt.logging.info("API polling started")
    
    def poll_api(self):
        """Poll API for new tasks"""
        while not self.should_exit:
            try:
                # Fetch new tasks from API
                response = requests.get(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10
                )
                
                if response.status_code == 200:
                    tasks = response.json().get('tasks', [])
                    
                    for task in tasks:
                        task_id = task.get('id')
                        if task_id not in self.processed_tasks:
                            # Process task
                            result = self.process_task(task)
                            self.processed_tasks[task_id] = result
                            
                            bt.logging.info(f"Processed task {task_id}")
                
            except Exception as e:
                bt.logging.error(f"API polling error: {e}")
            
            time.sleep(self.poll_interval)
    
    def process_task(self, task: Dict) -> Dict:
        """Process a single task"""
        # TODO: Implement your task processing logic
        return {"status": "completed", "result": "..."}
```

---

## 📋 Task Definition & Handling

### Where Tasks Are Defined

#### 1. Task Schema Definition

**File**: `template/protocol.py` (or create `template/task.py`)

**Example**:

```python
# template/protocol.py or template/task.py

from dataclasses import dataclass
from typing import Optional, Dict, Any
import bittensor as bt

@dataclass
class Task:
    """Task structure from API/WebSocket"""
    task_id: str
    task_type: str  # e.g., "image_classification", "text_generation"
    input_data: Dict[str, Any]
    timestamp: float
    priority: int = 0

@dataclass
class TaskResult:
    """Task result structure"""
    task_id: str
    status: str  # "completed", "failed", "pending"
    output_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time: Optional[float] = None

# Synapse for validator to query task results
class TaskQuerySynapse(bt.Synapse):
    """Synapse for validators to query miner task results"""
    task_id: Optional[str] = None  # If None, return all recent tasks
    start_time: Optional[float] = None
    
    # Response fields
    tasks: Optional[list] = None  # List of TaskResult
    
    def deserialize(self) -> list:
        """Deserialize task results"""
        return self.tasks or []
```

#### 2. Task Storage

**File**: `neurons/miner.py`

**Where**: Add task storage in `__init__`:

```python
class Miner(BaseMinerNeuron):
    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)
        
        # Task storage
        self.task_storage = {}  # {task_id: TaskResult}
        self.max_stored_tasks = 1000  # Limit storage
        
        # Task processing queue
        self.processing_queue = queue.Queue()
```

---

## 🔄 Request Format Definition

### Where Request Format is Defined

#### 1. WebSocket Message Format

**File**: Create `template/websocket_protocol.py`

**Example**:

```python
# template/websocket_protocol.py

from typing import Dict, Any
from dataclasses import dataclass, asdict
import json

@dataclass
class WebSocketTask:
    """WebSocket task message format"""
    type: str  # "task", "ping", "pong"
    task_id: str
    task_type: str
    data: Dict[str, Any]
    timestamp: float
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, json_str: str) -> 'WebSocketTask':
        """Create from JSON string"""
        data = json.loads(json_str)
        return cls(**data)

@dataclass
class WebSocketResponse:
    """WebSocket response format"""
    type: str  # "response", "error"
    task_id: str
    status: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
```

#### 2. API Request Format

**File**: Create `template/api_protocol.py`

**Example**:

```python
# template/api_protocol.py

from typing import Dict, List, Optional
from pydantic import BaseModel

class APITaskRequest(BaseModel):
    """API task request format"""
    task_id: str
    task_type: str
    input_data: Dict
    priority: int = 0

class APITaskResponse(BaseModel):
    """API task response format"""
    task_id: str
    status: str
    output_data: Optional[Dict] = None
    error: Optional[str] = None

class APITaskListResponse(BaseModel):
    """API task list response"""
    tasks: List[APITaskRequest]
    total: int
    page: int
    page_size: int
```

---

## ⚙️ Miner Task Processing

### Where Task Processing Happens

**File**: `neurons/miner.py`

**Method**: Add `process_task()` method

**Example**:

```python
# neurons/miner.py

class Miner(BaseMinerNeuron):
    
    async def process_task(self, task_data: Dict) -> TaskResult:
        """
        Process a task from API/WebSocket
        
        Args:
            task_data: Task data from API/WebSocket
            
        Returns:
            TaskResult: Processed task result
        """
        task_id = task_data.get('task_id')
        task_type = task_data.get('task_type')
        input_data = task_data.get('input_data', {})
        
        start_time = time.time()
        
        try:
            bt.logging.info(f"Processing task {task_id} of type {task_type}")
            
            # Route to appropriate handler based on task type
            if task_type == "image_classification":
                result = await self.handle_image_classification(input_data)
            elif task_type == "text_generation":
                result = await self.handle_text_generation(input_data)
            else:
                raise ValueError(f"Unknown task type: {task_type}")
            
            processing_time = time.time() - start_time
            
            # Create task result
            task_result = TaskResult(
                task_id=task_id,
                status="completed",
                output_data=result,
                processing_time=processing_time
            )
            
            # Store result
            self.store_task_result(task_result)
            
            return task_result
            
        except Exception as e:
            bt.logging.error(f"Error processing task {task_id}: {e}")
            
            task_result = TaskResult(
                task_id=task_id,
                status="failed",
                error=str(e),
                processing_time=time.time() - start_time
            )
            
            self.store_task_result(task_result)
            return task_result
    
    async def handle_image_classification(self, input_data: Dict) -> Dict:
        """Handle image classification task"""
        # TODO: Implement your image classification logic
        image_url = input_data.get('image_url')
        # Process image...
        return {"class": "cat", "confidence": 0.95}
    
    async def handle_text_generation(self, input_data: Dict) -> Dict:
        """Handle text generation task"""
        # TODO: Implement your text generation logic
        prompt = input_data.get('prompt')
        # Generate text...
        return {"generated_text": "..."}
    
    def store_task_result(self, result: TaskResult):
        """Store task result"""
        self.task_storage[result.task_id] = result
        
        # Limit storage size
        if len(self.task_storage) > self.max_stored_tasks:
            # Remove oldest tasks
            oldest_key = min(self.task_storage.keys())
            del self.task_storage[oldest_key]
```

### Handling Tasks in Forward Method

**File**: `neurons/miner.py`

**Modify**: `forward()` method to handle task queries from validators

**Example**:

```python
# neurons/miner.py

async def forward(
    self, synapse: template.protocol.TaskQuerySynapse
) -> template.protocol.TaskQuerySynapse:
    """
    Handle validator queries for task results
    
    Args:
        synapse: TaskQuerySynapse with task_id or None
        
    Returns:
        TaskQuerySynapse with task results
    """
    if synapse.task_id:
        # Return specific task
        if synapse.task_id in self.task_storage:
            result = self.task_storage[synapse.task_id]
            synapse.tasks = [result]
        else:
            synapse.tasks = []
    else:
        # Return recent tasks
        recent_tasks = list(self.task_storage.values())[-10:]  # Last 10 tasks
        synapse.tasks = recent_tasks
    
    return synapse
```

---

## 📤 Sending Tasks to Validator

### How Validator Queries Miner Tasks

**File**: `template/validator/forward.py`

**Where**: Modify `forward()` function

**Example**:

```python
# template/validator/forward.py

from template.protocol import TaskQuerySynapse

async def forward(self):
    """
    Validator forward pass - queries miners for task results
    """
    # Select miners to query
    miner_uids = get_random_uids(self, k=self.config.neuron.sample_size)
    
    # Query miners for their task results
    responses = await self.dendrite(
        axons=[self.metagraph.axons[uid] for uid in miner_uids],
        synapse=TaskQuerySynapse(
            task_id=None,  # Query all recent tasks
            start_time=time.time() - 3600  # Last hour
        ),
        deserialize=True,
        timeout=12
    )
    
    # Process responses
    miner_task_results = {}
    for uid, response in zip(miner_uids, responses):
        if response and hasattr(response, 'tasks'):
            miner_task_results[uid] = response.tasks
    
    # Score miners based on task results
    rewards = score_task_results(self, miner_task_results)
    
    # Update scores
    self.update_scores(rewards, miner_uids)
```

---

## ✅ Validator Logic

### Where Validator Logic is Defined

#### 1. Scoring Logic

**File**: `template/validator/reward.py`

**Example**:

```python
# template/validator/reward.py

import numpy as np
from typing import Dict, List

def score_task_results(
    self,
    miner_task_results: Dict[int, List]
) -> np.ndarray:
    """
    Score miners based on their task results
    
    Args:
        self: Validator instance
        miner_task_results: {uid: [TaskResult, ...]}
        
    Returns:
        numpy array of rewards
    """
    rewards = np.zeros(len(self.metagraph.hotkeys))
    
    for uid, task_results in miner_task_results.items():
        if not task_results:
            rewards[uid] = 0.0
            continue
        
        # Score based on:
        # 1. Number of completed tasks
        # 2. Task quality
        # 3. Processing time
        
        completed_tasks = [t for t in task_results if t.status == "completed"]
        completion_rate = len(completed_tasks) / len(task_results) if task_results else 0
        
        # Average processing time (lower is better)
        avg_processing_time = np.mean([
            t.processing_time for t in completed_tasks 
            if t.processing_time
        ]) if completed_tasks else float('inf')
        
        # Quality score (simplified - implement your own)
        quality_score = calculate_quality_score(completed_tasks)
        
        # Combined reward
        rewards[uid] = (
            completion_rate * 0.4 +
            (1.0 / (1.0 + avg_processing_time)) * 0.3 +
            quality_score * 0.3
        )
    
    return rewards

def calculate_quality_score(task_results: List) -> float:
    """Calculate quality score for task results"""
    # TODO: Implement your quality scoring logic
    # Example: Check if outputs match expected format, verify correctness, etc.
    return 0.8  # Placeholder
```

#### 2. Forward Pass Logic

**File**: `template/validator/forward.py`

**Complete Example**:

```python
# template/validator/forward.py

import time
import bittensor as bt
from template.protocol import TaskQuerySynapse
from template.validator.reward import score_task_results
from template.utils.uids import get_random_uids

async def forward(self):
    """
    Validator forward pass - complete workflow
    """
    bt.logging.info(f"Starting validation cycle at step {self.step}")
    
    # Step 1: Select miners to query
    miner_uids = get_random_uids(
        self,
        k=min(self.config.neuron.sample_size, self.metagraph.n)
    )
    
    bt.logging.info(f"Querying {len(miner_uids)} miners: {miner_uids}")
    
    # Step 2: Query miners for task results
    try:
        responses = await self.dendrite(
            axons=[self.metagraph.axons[uid] for uid in miner_uids],
            synapse=TaskQuerySynapse(
                task_id=None,  # Get all recent tasks
                start_time=time.time() - 3600  # Last hour
            ),
            deserialize=True,
            timeout=12
        )
    except Exception as e:
        bt.logging.error(f"Error querying miners: {e}")
        return
    
    # Step 3: Process responses
    miner_task_results = {}
    for uid, response in zip(miner_uids, responses):
        if response and hasattr(response, 'tasks') and response.tasks:
            miner_task_results[uid] = response.tasks
            bt.logging.info(
                f"Miner {uid} returned {len(response.tasks)} tasks"
            )
        else:
            bt.logging.warning(f"Miner {uid} returned no tasks")
    
    # Step 4: Score miners
    if miner_task_results:
        rewards = score_task_results(self, miner_task_results)
        bt.logging.info(f"Rewards: {rewards[miner_uids]}")
        
        # Step 5: Update scores
        self.update_scores(rewards, miner_uids)
    else:
        bt.logging.warning("No task results to score")
    
    bt.logging.info("Validation cycle completed")
```

---

## 📈 EMA Validator Approach

### What is EMA?

**EMA (Exponential Moving Average)** smooths out score fluctuations over time, giving more weight to recent performance while maintaining historical context.

### Why Use EMA?

1. **Stability**: Prevents sudden score changes
2. **Fairness**: Rewards consistent performance
3. **Emission Distribution**: More stable emissions for miners

### Implementation

**File**: `template/base/validator.py`

**Modify**: `update_scores()` method

**Example**:

```python
# template/base/validator.py

def update_scores(self, rewards: np.ndarray, uids: List[int]):
    """
    Update scores using EMA (Exponential Moving Average)
    
    Args:
        rewards: Array of rewards for queried miners
        uids: List of UIDs that were queried
    """
    # EMA alpha parameter (0 < alpha <= 1)
    # Lower alpha = more smoothing (slower to change)
    # Higher alpha = less smoothing (faster to change)
    alpha = self.config.neuron.moving_average_alpha  # Default: 0.1
    
    # Ensure rewards is numpy array
    rewards = np.asarray(rewards)
    
    # Create scattered rewards array
    scattered_rewards = np.zeros_like(self.scores)
    scattered_rewards[uids] = rewards
    
    # EMA formula: new_score = alpha * reward + (1 - alpha) * old_score
    self.scores = alpha * scattered_rewards + (1 - alpha) * self.scores
    
    bt.logging.debug(f"Updated scores (EMA alpha={alpha}): {self.scores[uids]}")
```

### EMA Configuration

**File**: `template/utils/config.py`

**Add**: EMA alpha parameter

```python
# template/utils/config.py

def add_validator_args(cls, parser):
    # ... existing args ...
    
    parser.add_argument(
        "--neuron.moving_average_alpha",
        type=float,
        default=0.1,
        help="EMA alpha parameter (0-1). Lower = more smoothing, Higher = faster updates"
    )
```

### EMA Impact on Emissions

**How EMA affects emissions**:

```
Without EMA:
Step 1: Score = 1.0 → Weight = 100%
Step 2: Score = 0.0 → Weight = 0%  (sudden drop!)
Step 3: Score = 1.0 → Weight = 100% (sudden spike!)

With EMA (alpha=0.1):
Step 1: Score = 1.0 → Weight = 100%
Step 2: Score = 0.9 → Weight = 90%  (gradual decrease)
Step 3: Score = 0.91 → Weight = 91% (gradual increase)
```

**Benefits**:
- ✅ Smoother emission distribution
- ✅ Less volatility for miners
- ✅ Rewards consistent performance
- ✅ Prevents gaming (sudden good/bad performance)

---

## 🔄 Complete Workflow

### Full Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    COMPLETE WORKFLOW                            │
└─────────────────────────────────────────────────────────────────┘

1. EXTERNAL DATA SOURCE
   │
   ├──► API (Polling)
   │       │
   │       └──► [neurons/miner.py] poll_api()
   │               │
   │               └──► Task Queue
   │
   └──► WebSocket (Real-time)
           │
           └──► [neurons/miner.py] WebSocketManager
                   │
                   └──► Task Queue

2. MINER PROCESSING
   │
   ├──► [neurons/miner.py] process_task()
   │       │
   │       ├──► Handle task based on type
   │       ├──► Execute task logic
   │       └──► Store result in task_storage
   │
   └──► [neurons/miner.py] forward()
           │
           └──► Return task results when validator queries

3. VALIDATOR QUERYING
   │
   ├──► [template/validator/forward.py] forward()
   │       │
   │       ├──► Select miners (get_random_uids)
   │       ├──► Query miners (dendrite + TaskQuerySynapse)
   │       └──► Receive task results
   │
   └──► [template/validator/reward.py] score_task_results()
           │
           └──► Calculate rewards based on:
               ├──► Completion rate
               ├──► Processing time
               └──► Quality score

4. SCORE UPDATES
   │
   ├──► [template/base/validator.py] update_scores()
   │       │
   │       ├──► Apply EMA smoothing
   │       └──► Update self.scores array
   │
   └──► [template/base/validator.py] set_weights()
           │
           ├──► Normalize scores
           ├──► Process weights
           └──► Submit to chain

5. EMISSIONS
   │
   └──► Chain distributes TAO based on weights
           │
           └──► Miners receive emissions proportional to scores
```

---

## 💡 Practical Examples

### Example 1: Image Classification Subnet

**Task**: Miners classify images from API

**1. Protocol Definition** (`template/protocol.py`):

```python
class ImageClassificationSynapse(bt.Synapse):
    image_url: str
    classification: Optional[str] = None
    confidence: Optional[float] = None
    
    def deserialize(self) -> Dict:
        return {
            "classification": self.classification,
            "confidence": self.confidence
        }
```

**2. Miner Processing** (`neurons/miner.py`):

```python
class Miner(BaseMinerNeuron):
    def __init__(self, config=None):
        super().__init__(config=config)
        # API integration
        self.api_client = APIClient(config.api_url)
        self.image_classifier = ImageClassifier()  # Your ML model
    
    async def forward(self, synapse: ImageClassificationSynapse):
        # Classify image
        result = await self.image_classifier.classify(synapse.image_url)
        synapse.classification = result['class']
        synapse.confidence = result['confidence']
        return synapse
```

**3. Validator Scoring** (`template/validator/reward.py`):

```python
def reward(self, query: ImageClassificationSynapse, response: ImageClassificationSynapse):
    # Compare with ground truth
    ground_truth = self.get_ground_truth(query.image_url)
    
    if response.classification == ground_truth:
        # Reward based on confidence
        return response.confidence
    else:
        return 0.0
```

### Example 2: WebSocket Order Processing (Like TensorUSD)

**Task**: Miners process orders from WebSocket

**1. WebSocket Manager** (`neurons/miner.py`):

```python
class OrderWebSocketManager:
    def on_message(self, ws, message):
        order = json.loads(message)
        # Process order
        self.miner.process_order(order)
```

**2. Order Processing** (`neurons/miner.py`):

```python
def process_order(self, order: Dict):
    order_id = order['id']
    order_type = order['type']  # "buy" or "sell"
    amount = order['amount']
    
    # Execute order
    result = self.execute_order(order_type, amount)
    
    # Store result
    self.order_results[order_id] = result
```

**3. Validator Query** (`template/validator/forward.py`):

```python
async def forward(self):
    # Query miners for order completion
    responses = await self.dendrite(
        axons=[...],
        synapse=OrderQuerySynapse(order_ids=[...]),
        deserialize=True
    )
    
    # Score based on order completion rate
    rewards = score_order_completion(responses)
    self.update_scores(rewards, uids)
```

### Example 3: EMA with Custom Alpha

**Configuration** (`neurons/validator.py`):

```python
class Validator(BaseValidatorNeuron):
    def __init__(self, config=None):
        super().__init__(config=config)
        
        # Custom EMA alpha based on subnet needs
        if config.neuron.moving_average_alpha is None:
            # Adaptive alpha: faster updates for new miners
            self.adaptive_alpha = True
        else:
            self.adaptive_alpha = False
            self.config.neuron.moving_average_alpha = config.neuron.moving_average_alpha
```

**Adaptive EMA** (`template/base/validator.py`):

```python
def update_scores(self, rewards: np.ndarray, uids: List[int]):
    if self.adaptive_alpha:
        # Higher alpha for new miners (faster learning)
        # Lower alpha for established miners (more stability)
        for uid in uids:
            if self.scores[uid] == 0:  # New miner
                alpha = 0.3  # Faster updates
            else:
                alpha = 0.1  # Slower updates
            
            self.scores[uid] = alpha * rewards[uid] + (1 - alpha) * self.scores[uid]
    else:
        # Standard EMA
        alpha = self.config.neuron.moving_average_alpha
        scattered_rewards = np.zeros_like(self.scores)
        scattered_rewards[uids] = rewards
        self.scores = alpha * scattered_rewards + (1 - alpha) * self.scores
```

---

## 📝 Summary: Where to Change What

| What to Change | File | Method/Class |
|----------------|------|--------------|
| **Add WebSocket** | `neurons/miner.py` | `__init__()` + `WebSocketManager` class |
| **Add API Polling** | `neurons/miner.py` | `__init__()` + `poll_api()` method |
| **Define Task Format** | `template/protocol.py` | Create `Task` dataclass |
| **Define Request Format** | `template/protocol.py` | Create synapse class |
| **Process Tasks** | `neurons/miner.py` | `process_task()` method |
| **Handle Validator Queries** | `neurons/miner.py` | `forward()` method |
| **Query Miners** | `template/validator/forward.py` | `forward()` function |
| **Score Tasks** | `template/validator/reward.py` | `score_task_results()` function |
| **Update Scores (EMA)** | `template/base/validator.py` | `update_scores()` method |
| **Configure EMA** | `template/utils/config.py` | `add_validator_args()` |

---

## 🎯 Quick Start Checklist

- [ ] Define task structure in `template/protocol.py`
- [ ] Add WebSocket/API integration to `neurons/miner.py`
- [ ] Implement `process_task()` in miner
- [ ] Modify `forward()` to return task results
- [ ] Update validator `forward()` to query tasks
- [ ] Implement scoring logic in `reward.py`
- [ ] Configure EMA alpha in config
- [ ] Test locally with mock data
- [ ] Deploy to testnet
- [ ] Monitor emissions distribution

---

**See BEGINNER_GUIDE.md for basic concepts and FLOW_DIAGRAM.md for visual flows!**

