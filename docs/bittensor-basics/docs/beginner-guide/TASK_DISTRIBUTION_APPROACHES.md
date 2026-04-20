# 📡 Task Distribution Approaches in Bittensor Subnets

Complete explanation of different ways to send tasks to miners in a subnet, their pros/cons, and when to use each.

## 📋 Table of Contents

1. [Overview](#overview)
2. [Approach 1: Standard Bittensor Synapse](#approach-1-standard-bittensor-synapse)
3. [Approach 2: External API/WebSocket](#approach-2-external-apiwebsocket)
4. [Approach 3: On-Chain Task Storage](#approach-3-on-chain-task-storage)
5. [Approach 4: IPFS/Decentralized Storage](#approach-4-ipfsdecentralized-storage)
6. [Approach 5: Pub/Sub Message Queues](#approach-5-pubsub-message-queues)
7. [Approach 6: Direct HTTP Endpoints](#approach-6-direct-http-endpoints)
8. [Approach 7: Event-Driven Architecture](#approach-7-event-driven-architecture)
9. [Hybrid Approaches](#hybrid-approaches)
10. [Comparison Table](#comparison-table)

---

## 🎯 Overview

There are multiple ways to distribute tasks to miners in a Bittensor subnet. Each has different trade-offs:

```
Task Distribution Methods:

1. Standard Synapse (Validator → Miner)
   └─► Direct query-response pattern

2. External API/WebSocket
   └─► External system pushes tasks

3. On-Chain Storage
   └─► Tasks stored on blockchain

4. IPFS/Decentralized Storage
   └─► Tasks in distributed storage

5. Pub/Sub Queues
   └─► Message broker system

6. Direct HTTP
   └─► Miners expose APIs

7. Event-Driven
   └─► Events trigger tasks
```

---

## 🔄 Approach 1: Standard Bittensor Synapse

### How It Works

**Flow**:
```
Validator → Creates Synapse → Queries Miner → Miner Processes → Returns Response
```

**Characteristics**:
- Validator initiates all requests
- Synchronous request-response pattern
- Tasks are created by validators on-demand
- No external systems needed

### Implementation

**Validator Side** (`template/validator/forward.py`):
```python
async def forward(self):
    # Validator creates task
    synapse = Dummy(dummy_input=5)
    
    # Validator queries miner
    response = await self.dendrite(
        axons=[miner_axon],
        synapse=synapse,
        deserialize=True
    )
    
    # Validator scores response
    reward = score(response)
```

**Miner Side** (`neurons/miner.py`):
```python
async def forward(self, synapse: Dummy) -> Dummy:
    # Miner receives task from validator
    # Process immediately
    synapse.dummy_output = synapse.dummy_input * 2
    return synapse
```

### Pros ✅
- ✅ Fully decentralized (no external dependencies)
- ✅ Built into Bittensor (no extra infrastructure)
- ✅ Validator controls task distribution
- ✅ Simple to implement
- ✅ Works out of the box

### Cons ❌
- ❌ Validator must know what to query
- ❌ No persistent task queue
- ❌ Tasks are ephemeral (lost if miner offline)
- ❌ Limited to validator-initiated tasks
- ❌ Can't handle external events

### Use Cases
- ✅ Simple query-response subnets
- ✅ On-demand computation
- ✅ When validators generate tasks
- ✅ Testing and development

### Examples
- **Subnet 1 (Prompting)**: Validator sends prompts, miner generates responses
- **Template subnet**: Dummy multiplication tasks

---

## 🌐 Approach 2: External API/WebSocket

### How It Works

**Flow**:
```
External System → API/WebSocket → Miner → Processes Task → Stores Result
                                                                    ↓
Validator → Queries Miner → Gets Stored Results → Scores
```

**Characteristics**:
- External system (outside Bittensor) sends tasks
- Miners receive tasks independently of validators
- Tasks are persistent (stored until processed)
- Validators query miners for completed tasks

### Implementation

**External System**:
```python
# External API/WebSocket server
websocket.send({
    "task_id": "123",
    "task_type": "image_classification",
    "data": {"image_url": "https://..."}
})
```

**Miner Side** (`neurons/miner.py`):
```python
class Miner(BaseMinerNeuron):
    def __init__(self):
        # Connect to external WebSocket
        self.ws = WebSocketClient("wss://api.example.com")
        self.ws.on_message = self.handle_task
        self.task_storage = {}
    
    def handle_task(self, message):
        # Receive task from external system
        task = json.loads(message)
        result = self.process_task(task)
        self.task_storage[task['id']] = result
    
    async def forward(self, synapse: TaskQuerySynapse):
        # Validator queries for stored results
        return self.task_storage.get(synapse.task_id)
```

**Validator Side** (`template/validator/forward.py`):
```python
async def forward(self):
    # Query miners for their stored task results
    responses = await self.dendrite(
        axons=[...],
        synapse=TaskQuerySynapse(task_id=None),  # Get all recent
        deserialize=True
    )
    
    # Score based on stored results
    rewards = score_stored_tasks(responses)
```

### Pros ✅
- ✅ External systems can push tasks
- ✅ Tasks persist until processed
- ✅ Decouples task creation from validation
- ✅ Can handle real-time events
- ✅ Supports high-frequency tasks

### Cons ❌
- ❌ Requires external infrastructure
- ❌ Centralized point of failure (API/WebSocket server)
- ❌ Additional complexity
- ❌ Need to manage external systems

### Use Cases
- ✅ Order processing (like TensorUSD)
- ✅ Real-time data processing
- ✅ External event-driven tasks
- ✅ High-frequency task distribution

### Examples
- **TensorUSD Subnet**: External gateway sends buy/sell orders via WebSocket
- **Trading subnets**: External trading signals

---

## ⛓️ Approach 3: On-Chain Task Storage

### How It Works

**Flow**:
```
Task Creator → Stores Task on Blockchain → Miners Read Chain → Process Task
                                                                    ↓
Validator → Queries Miner → Gets Results → Scores
```

**Characteristics**:
- Tasks stored as on-chain data
- Fully decentralized (no external servers)
- Miners read blockchain for tasks
- Tasks are permanent and verifiable

### Implementation

**Task Storage** (On-chain):
```python
# Store task on-chain (using Bittensor's storage or custom pallet)
task_data = {
    "task_id": "123",
    "task_type": "compute",
    "input_data": "...",
    "reward": 100  # TAO reward for completion
}

# Store in on-chain storage
subtensor.set_storage(netuid=1, key="task_123", value=task_data)
```

**Miner Side** (`neurons/miner.py`):
```python
class Miner(BaseMinerNeuron):
    def __init__(self):
        self.processed_tasks = set()
    
    def run(self):
        while True:
            # Read tasks from chain
            tasks = self.subtensor.get_storage(netuid=1, prefix="task_")
            
            for task_id, task_data in tasks.items():
                if task_id not in self.processed_tasks:
                    result = self.process_task(task_data)
                    self.processed_tasks.add(task_id)
                    
                    # Store result on-chain
                    self.subtensor.set_storage(
                        netuid=1,
                        key=f"result_{task_id}",
                        value=result
                    )
```

**Validator Side** (`template/validator/forward.py`):
```python
async def forward(self):
    # Read task results from chain
    for miner_uid in miner_uids:
        results = self.subtensor.get_storage(
            netuid=1,
            prefix=f"result_{miner_uid}_"
        )
        rewards[uid] = score_results(results)
```

### Pros ✅
- ✅ Fully decentralized
- ✅ Tasks are permanent and verifiable
- ✅ No external infrastructure needed
- ✅ Transparent and auditable
- ✅ Tasks can't be lost

### Cons ❌
- ❌ On-chain storage is expensive
- ❌ Limited storage capacity
- ❌ Slower (blockchain confirmation time)
- ❌ Not suitable for high-frequency tasks
- ❌ Requires custom storage pallet

### Use Cases
- ✅ Important, permanent tasks
- ✅ When transparency is critical
- ✅ Low-frequency, high-value tasks
- ✅ Decentralized task markets

### Examples
- **Decentralized compute markets**: Tasks stored on-chain
- **Permanent data processing**: Historical data analysis

---

## 📦 Approach 4: IPFS/Decentralized Storage

### How It Works

**Flow**:
```
Task Creator → Uploads Task to IPFS → Gets CID → Stores CID on-chain/API
                                                                    ↓
Miner → Reads CID → Fetches from IPFS → Processes Task
                                                                    ↓
Miner → Uploads Result to IPFS → Stores Result CID
                                                                    ↓
Validator → Queries Miner → Gets Result CID → Fetches from IPFS → Scores
```

**Characteristics**:
- Tasks stored in IPFS (decentralized file storage)
- Only CID (Content Identifier) stored on-chain
- Large tasks/data supported
- Decentralized storage

### Implementation

**Task Creation**:
```python
import ipfshttpclient

# Create task
task = {
    "task_id": "123",
    "task_type": "image_processing",
    "image_data": large_image_bytes
}

# Upload to IPFS
ipfs = ipfshttpclient.connect()
cid = ipfs.add_json(task)  # Returns CID like "QmXxx..."

# Store CID (on-chain or API)
store_cid("task_123", cid)
```

**Miner Side** (`neurons/miner.py`):
```python
class Miner(BaseMinerNeuron):
    def __init__(self):
        self.ipfs = ipfshttpclient.connect()
        self.processed_cids = set()
    
    def run(self):
        while True:
            # Get task CIDs (from chain or API)
            task_cids = get_pending_task_cids()
            
            for cid in task_cids:
                if cid not in self.processed_cids:
                    # Fetch task from IPFS
                    task = self.ipfs.get_json(cid)
                    
                    # Process task
                    result = self.process_task(task)
                    
                    # Upload result to IPFS
                    result_cid = self.ipfs.add_json(result)
                    self.store_result_cid(task['task_id'], result_cid)
                    self.processed_cids.add(cid)
```

**Validator Side** (`template/validator/forward.py`):
```python
async def forward(self):
    # Query miners for result CIDs
    responses = await self.dendrite(
        axons=[...],
        synapse=ResultCIDQuerySynapse(),
        deserialize=True
    )
    
    # Fetch results from IPFS and score
    for response in responses:
        result = ipfs.get_json(response.result_cid)
        score = evaluate_result(result)
```

### Pros ✅
- ✅ Supports large files/data
- ✅ Decentralized storage
- ✅ Cost-effective (IPFS is free)
- ✅ Permanent storage (if pinned)
- ✅ Can store complex data structures

### Cons ❌
- ❌ Requires IPFS infrastructure
- ❌ Slower than direct storage
- ❌ Need to manage pinning
- ❌ CID management complexity
- ❌ Retrieval can be slow

### Use Cases
- ✅ Large file processing (images, videos)
- ✅ Dataset processing
- ✅ When storage cost matters
- ✅ Decentralized data processing

### Examples
- **Image processing subnets**: Large images in IPFS
- **Dataset analysis**: Datasets stored in IPFS

---

## 📨 Approach 5: Pub/Sub Message Queues

### How It Works

**Flow**:
```
Task Creator → Publishes to Queue (Redis/RabbitMQ) → Miners Subscribe
                                                                    ↓
Miner → Receives Task → Processes → Publishes Result
                                                                    ↓
Validator → Subscribes to Results → Scores
```

**Characteristics**:
- Message broker (Redis, RabbitMQ, Kafka)
- Pub/Sub pattern
- Tasks queued until consumed
- Supports multiple subscribers

### Implementation

**Using Redis Pub/Sub**:

**Task Publisher**:
```python
import redis

redis_client = redis.Redis()

# Publish task
task = {"task_id": "123", "data": "..."}
redis_client.publish("subnet_tasks", json.dumps(task))
```

**Miner Side** (`neurons/miner.py`):
```python
import redis

class Miner(BaseMinerNeuron):
    def __init__(self):
        self.redis = redis.Redis()
        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe("subnet_tasks")
        self.task_results = {}
    
    def run(self):
        # Listen for tasks
        for message in self.pubsub.listen():
            if message['type'] == 'message':
                task = json.loads(message['data'])
                result = self.process_task(task)
                
                # Publish result
                self.redis.publish(
                    f"subnet_results_{self.uid}",
                    json.dumps(result)
                )
```

**Validator Side** (`template/validator/forward.py`):
```python
async def forward(self):
    # Subscribe to miner result channels
    for uid in miner_uids:
        results = redis_client.pubsub()
        results.subscribe(f"subnet_results_{uid}")
        
        # Collect results
        task_results[uid] = collect_recent_results(results)
    
    # Score results
    rewards = score_results(task_results)
```

### Pros ✅
- ✅ Real-time task distribution
- ✅ Scalable (handles many miners)
- ✅ Reliable (message persistence)
- ✅ Supports priority queues
- ✅ Decouples producers/consumers

### Cons ❌
- ❌ Requires message broker infrastructure
- ❌ Centralized broker (unless using decentralized queue)
- ❌ Additional complexity
- ❌ Need to manage broker

### Use Cases
- ✅ High-frequency tasks
- ✅ Real-time processing
- ✅ When you need message persistence
- ✅ Microservices architecture

### Examples
- **Real-time data processing**: Stock prices, sensor data
- **Event-driven subnets**: IoT data processing

---

## 🌍 Approach 6: Direct HTTP Endpoints

### How It Works

**Flow**:
```
Task Creator → HTTP POST to Miner → Miner Processes → Returns Response
                                                                    ↓
Validator → HTTP GET from Miner → Gets Results → Scores
```

**Characteristics**:
- Miners expose HTTP REST APIs
- Direct HTTP communication
- Standard web protocols
- Can be called by anyone

### Implementation

**Miner Side** (`neurons/miner.py`):
```python
from flask import Flask, request, jsonify

class Miner(BaseMinerNeuron):
    def __init__(self):
        super().__init__()
        self.app = Flask(__name__)
        self.setup_routes()
        self.task_results = {}
    
    def setup_routes(self):
        @self.app.route('/task', methods=['POST'])
        def receive_task():
            task = request.json
            result = self.process_task(task)
            self.task_results[task['id']] = result
            return jsonify(result)
        
        @self.app.route('/results/<task_id>', methods=['GET'])
        def get_result(task_id):
            return jsonify(self.task_results.get(task_id))
    
    def run(self):
        # Run HTTP server
        self.app.run(host='0.0.0.0', port=8091)
```

**Task Creator**:
```python
import requests

# Send task to miner
response = requests.post(
    f"http://{miner_ip}:8091/task",
    json={"task_id": "123", "data": "..."}
)
```

**Validator Side** (`template/validator/forward.py`):
```python
async def forward(self):
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        for uid in miner_uids:
            miner_ip = self.metagraph.axons[uid].ip
            
            # Query miner via HTTP
            async with session.get(
                f"http://{miner_ip}:8091/results/recent"
            ) as response:
                results = await response.json()
                task_results[uid] = results
    
    rewards = score_results(task_results)
```

### Pros ✅
- ✅ Standard HTTP (easy integration)
- ✅ Can be called by external systems
- ✅ Simple to implement
- ✅ Works with existing tools
- ✅ RESTful API design

### Cons ❌
- ❌ Requires HTTP server on miners
- ❌ Not using Bittensor's built-in communication
- ❌ Need to manage HTTP endpoints
- ❌ Less secure (unless adding auth)
- ❌ Bypasses Bittensor's network layer

### Use Cases
- ✅ When external systems need direct access
- ✅ REST API integration
- ✅ Web-based task submission
- ✅ Integration with existing systems

### Examples
- **API-based subnets**: External services call miner APIs
- **Web interfaces**: Users submit tasks via web UI

---

## ⚡ Approach 7: Event-Driven Architecture

### How It Works

**Flow**:
```
Event Source → Event Stream → Miners Subscribe → Process Events
                                                                    ↓
Validator → Queries Event Results → Scores
```

**Characteristics**:
- Events trigger task processing
- Event streaming (Kafka, AWS Kinesis)
- Real-time processing
- Event sourcing pattern

### Implementation

**Event Producer**:
```python
from kafka import KafkaProducer

producer = KafkaProducer()

# Produce event
event = {
    "event_type": "image_uploaded",
    "event_id": "123",
    "data": {"image_url": "https://..."}
}

producer.send("subnet_events", json.dumps(event).encode())
```

**Miner Side** (`neurons/miner.py`):
```python
from kafka import KafkaConsumer

class Miner(BaseMinerNeuron):
    def __init__(self):
        self.consumer = KafkaConsumer(
            "subnet_events",
            group_id=f"miner_{self.uid}"
        )
        self.event_results = {}
    
    def run(self):
        for event in self.consumer:
            event_data = json.loads(event.value)
            
            # Process event as task
            result = self.process_event(event_data)
            self.event_results[event_data['event_id']] = result
```

**Validator Side** (`template/validator/forward.py`):
```python
async def forward(self):
    # Query miners for event processing results
    responses = await self.dendrite(
        axons=[...],
        synapse=EventResultQuerySynapse(),
        deserialize=True
    )
    
    # Score based on event processing
    rewards = score_event_results(responses)
```

### Pros ✅
- ✅ Real-time event processing
- ✅ Scalable event streaming
- ✅ Decouples event sources from processing
- ✅ Supports complex event patterns
- ✅ Event replay capability

### Cons ❌
- ❌ Requires event streaming infrastructure
- ❌ Complex setup
- ❌ Need to manage event streams
- ❌ Additional infrastructure cost

### Use Cases
- ✅ Real-time event processing
- ✅ IoT data processing
- ✅ Log analysis
- ✅ Stream processing

### Examples
- **IoT subnets**: Sensor events trigger processing
- **Log analysis**: Log events trigger analysis

---

## 🔀 Hybrid Approaches

### Common Combinations

#### 1. WebSocket + Synapse
```
External System → WebSocket → Miner (stores tasks)
                                    ↓
Validator → Synapse Query → Miner (returns stored results)
```

#### 2. IPFS + On-Chain CIDs
```
Task → IPFS → CID → On-Chain Storage → Miners Read Chain → Fetch IPFS
```

#### 3. API + Pub/Sub
```
API → Publishes to Queue → Miners Subscribe → Process → Results Queue
```

---

## 📊 Comparison Table

| Approach | Decentralization | Complexity | Speed | Cost | Use Case |
|----------|-----------------|------------|-------|------|----------|
| **Standard Synapse** | ✅✅✅ High | ⭐ Low | ⚡⚡⚡ Fast | 💰 Low | Simple queries |
| **External API/WS** | ⚠️ Medium | ⭐⭐ Medium | ⚡⚡⚡ Fast | 💰💰 Medium | External tasks |
| **On-Chain Storage** | ✅✅✅ High | ⭐⭐⭐ High | ⚡ Slow | 💰💰💰 High | Permanent tasks |
| **IPFS Storage** | ✅✅ Medium | ⭐⭐ Medium | ⚡⚡ Medium | 💰 Low | Large files |
| **Pub/Sub Queue** | ⚠️ Low | ⭐⭐⭐ High | ⚡⚡⚡ Fast | 💰💰 Medium | High frequency |
| **HTTP Endpoints** | ⚠️ Low | ⭐⭐ Medium | ⚡⚡⚡ Fast | 💰 Low | External access |
| **Event-Driven** | ⚠️ Low | ⭐⭐⭐ High | ⚡⚡⚡ Fast | 💰💰💰 High | Real-time events |

**Legend**:
- ✅✅✅ = Fully decentralized
- ✅✅ = Mostly decentralized
- ⚠️ = Centralized component
- ⭐ = Complexity level (1-3)
- ⚡ = Speed (1-3)
- 💰 = Cost (1-3)

---

## 🎯 Choosing the Right Approach

### Decision Tree

```
Do you need external systems to send tasks?
├─ NO → Use Standard Synapse
└─ YES
    ├─ Do you need real-time?
    │   ├─ YES → WebSocket or Pub/Sub
    │   └─ NO → API Polling
    │
    ├─ Do you need large file storage?
    │   ├─ YES → IPFS
    │   └─ NO → Continue
    │
    ├─ Do you need full decentralization?
    │   ├─ YES → On-Chain Storage
    │   └─ NO → API/WebSocket
    │
    └─ Do you need event streaming?
        ├─ YES → Event-Driven
        └─ NO → Standard API
```

---

## 💡 Recommendations

### For Most Subnets
**Start with Standard Synapse** - It's simple and works for most cases.

### For External Integration
**Use WebSocket + Synapse Hybrid** - External system pushes tasks, validators query via synapse.

### For Large Data
**Use IPFS + On-Chain CIDs** - Store data in IPFS, reference on-chain.

### For High Frequency
**Use Pub/Sub Queue** - Handles high-frequency tasks efficiently.

---

**See API_WEBSOCKET_INTEGRATION_GUIDE.md for detailed implementation examples!**

