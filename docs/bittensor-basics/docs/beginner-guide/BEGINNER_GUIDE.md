# 🚀 Bittensor Subnet Template - Beginner's Guide

## 📋 Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Complete Flow Diagram](#complete-flow-diagram)
3. [File-by-File Explanation](#file-by-file-explanation)
4. [Learning Path](#learning-path)
5. [Beginner Tasks](#beginner-tasks)

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    BITTENSOR SUBNET ARCHITECTURE                │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────┐         ┌──────────────────────┐
│   VALIDATOR          │         │   MINER              │
│                      │         │                      │
│  ┌────────────────┐  │         │  ┌────────────────┐  │
│  │ BaseValidator  │  │         │  │ BaseMiner      │  │
│  │    Neuron      │  │         │  │    Neuron      │  │
│  └────────┬───────┘  │         │  └────────┬───────┘  │
│           │          │         │           │          │
│  ┌────────▼───────┐  │         │  ┌────────▼───────┐  │
│  │ Validator      │  │         │  │ Miner           │  │
│  │ (neurons/)     │  │         │  │ (neurons/)      │  │
│  └────────┬───────┘  │         │  └────────┬───────┘  │
│           │          │         │           │          │
│  ┌────────▼───────┐  │         │  ┌────────▼───────┐  │
│  │ forward()      │  │◄────────┤  │ forward()      │  │
│  │ reward()       │  │  Query   │  │ blacklist()    │  │
│  └────────────────┘  │         │  │ priority()     │  │
│                       │         │  └────────────────┘  │
│  ┌────────────────┐  │         │                      │
│  │ Dendrite       │──┼─────────┼──► Axon              │
│  │ (Query tool)   │  │         │  │ (Server)         │
│  └────────────────┘  │         │  └────────────────┘  │
└──────────────────────┘         └──────────────────────┘
         │                                    │
         │                                    │
         └──────────┬─────────────────────────┘
                    │
         ┌──────────▼──────────┐
         │   BITTENSOR CHAIN   │
         │                     │
         │  • Metagraph       │
         │  • Weights          │
         │  • Emissions        │
         │  • Registration     │
         └─────────────────────┘
```

---

## 🔄 Complete Flow Diagram

### Full Request-Response Cycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                    VALIDATOR CYCLE (Every Epoch)                    │
└─────────────────────────────────────────────────────────────────────┘

Step 1: INITIALIZATION
┌──────────────────────────────────────────────────────────────┐
│ template/base/neuron.py                                      │
│ • Load wallet                                                │
│ • Connect to subtensor                                       │
│ • Load metagraph (network state)                             │
│ • Check registration                                         │
│ • Assign UID                                                 │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ template/base/validator.py                                   │
│ • Create dendrite (query tool)                               │
│ • Initialize scores array                                    │
│ • Set up axon (optional)                                     │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ neurons/validator.py                                         │
│ • Load state                                                 │
│ • Custom initialization                                      │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   RUN LOOP    │
                    │  (Every epoch)│
                    └───────┬───────┘
                            │
                            ▼
Step 2: VALIDATION CYCLE
┌──────────────────────────────────────────────────────────────┐
│ template/validator/forward.py                                │
│                                                              │
│  1. Select Miners                                            │
│     └─► get_random_uids()                                   │
│                                                              │
│  2. Create Query                                            │
│     └─► Dummy(dummy_input=self.step)                       │
│                                                              │
│  3. Query Miners                                             │
│     └─► self.dendrite(axons=[...], synapse=Dummy(...))    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                    MINER PROCESSING                           │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ template/base/miner.py                                       │
│ • Axon receives request                                      │
│ • Routes to attached functions                               │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ neurons/miner.py                                            │
│                                                              │
│  1. blacklist() ──► Check if request is allowed             │
│     └─► Returns (bool, reason)                             │
│                                                              │
│  2. priority() ──► Determine request priority                │
│     └─► Returns float (higher = more important)            │
│                                                              │
│  3. forward() ──► Process the request                       │
│     └─► synapse.dummy_output = synapse.dummy_input * 2     │
│     └─► Returns synapse                                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ template/protocol.py                                         │
│ • Synapse is serialized and sent back                       │
│ • Validator receives response                               │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
Step 3: SCORING
┌──────────────────────────────────────────────────────────────┐
│ template/validator/reward.py                                │
│                                                              │
│  • reward(query, response) ──► Score single response       │
│    └─► Returns 1.0 if correct, 0.0 if wrong               │
│                                                              │
│  • get_rewards(query, responses) ──► Score all responses   │
│    └─► Returns numpy array of rewards                       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
Step 4: UPDATE SCORES
┌──────────────────────────────────────────────────────────────┐
│ template/base/validator.py                                  │
│                                                              │
│  • update_scores(rewards, uids)                             │
│    └─► Updates moving average of scores                     │
│    └─► self.scores[uid] = alpha * reward + (1-alpha) * old │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
Step 5: SET WEIGHTS
┌──────────────────────────────────────────────────────────────┐
│ template/base/validator.py                                  │
│                                                              │
│  • set_weights()                                            │
│    1. Normalize scores                                      │
│    2. Process weights (template/base/utils/weight_utils.py) │
│    3. Convert to uint16                                     │
│    4. Submit to chain via subtensor.set_weights()          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   NEXT EPOCH  │
                    └───────────────┘
```

---

## 📁 File-by-File Explanation

### 🎯 Core Foundation Files

#### 1. `template/base/neuron.py`
**Purpose**: Base class for ALL neurons (both miners and validators)

**What it does**:
- ✅ Initializes wallet (cryptographic keys)
- ✅ Connects to subtensor (blockchain interface)
- ✅ Loads metagraph (network state - who's registered, UIDs, etc.)
- ✅ Checks registration (ensures hotkey is registered on subnet)
- ✅ Assigns UID (unique identifier on the subnet)
- ✅ Manages epoch synchronization
- ✅ Handles state saving/loading

**Key Methods**:
```python
check_registered()      # Verifies miner/validator is registered
sync()                  # Syncs metagraph and sets weights
should_sync_metagraph() # Determines when to sync
should_set_weights()    # Determines when to set weights (validators only)
save_state()           # Saves state to disk
load_state()            # Loads state from disk
```

**When to modify**: Rarely - this is the foundation

---

#### 2. `template/protocol.py`
**Purpose**: Defines the communication protocol between miners and validators

**What it does**:
- ✅ Defines `Dummy` synapse class (inherits from `bt.Synapse`)
- ✅ Specifies input fields (`dummy_input`)
- ✅ Specifies output fields (`dummy_output`)
- ✅ Provides `deserialize()` method for responses

**Structure**:
```python
class Dummy(bt.Synapse):
    dummy_input: int                    # Validator sends this
    dummy_output: Optional[int] = None  # Miner fills this
    
    def deserialize(self) -> int:
        return self.dummy_output        # Validator reads this
```

**When to modify**: **ALWAYS** - Define your own protocol here!

**Example**: If you want to send text prompts:
```python
class TextPrompt(bt.Synapse):
    prompt: str
    response: Optional[str] = None
```

---

### ⛏️ Miner Files

#### 3. `template/base/miner.py`
**Purpose**: Base class for miners - handles miner-specific setup

**What it does**:
- ✅ Creates axon (server that receives requests)
- ✅ Attaches functions (`forward`, `blacklist`, `priority`)
- ✅ Starts axon server
- ✅ Manages main run loop
- ✅ Handles background threads

**Key Concepts**:
```python
self.axon = bt.axon(...)              # Create server
self.axon.attach(
    forward_fn=self.forward,           # Process requests
    blacklist_fn=self.blacklist,      # Security filter
    priority_fn=self.priority          # Request ordering
)
self.axon.serve(netuid=...)            # Make available on network
self.axon.start()                      # Start listening
```

**When to modify**: Rarely - handles boilerplate

---

#### 4. `neurons/miner.py`
**Purpose**: YOUR custom miner implementation

**What it does**:
- ✅ Inherits from `BaseMinerNeuron`
- ✅ Implements `forward()` - processes requests
- ✅ Implements `blacklist()` - security filtering
- ✅ Implements `priority()` - request prioritization

**Key Methods**:

**`forward()`** - Main processing logic:
```python
async def forward(self, synapse: Dummy) -> Dummy:
    # TODO: Replace with your logic
    synapse.dummy_output = synapse.dummy_input * 2
    return synapse
```

**`blacklist()`** - Security filter:
```python
async def blacklist(self, synapse: Dummy) -> Tuple[bool, str]:
    # Returns (True, reason) to reject
    # Returns (False, reason) to allow
    if not registered:
        return True, "Not registered"
    return False, "OK"
```

**`priority()`** - Request ordering:
```python
async def priority(self, synapse: Dummy) -> float:
    # Higher value = process first
    return self.metagraph.S[caller_uid]  # Stake-based priority
```

**When to modify**: **ALWAYS** - This is YOUR miner logic!

---

### ✅ Validator Files

#### 5. `template/base/validator.py`
**Purpose**: Base class for validators - handles validator-specific setup

**What it does**:
- ✅ Creates dendrite (tool to query miners)
- ✅ Initializes scores array (tracks miner performance)
- ✅ Manages score updates (moving average)
- ✅ Sets weights on-chain
- ✅ Handles metagraph resync

**Key Concepts**:
```python
self.dendrite = bt.dendrite(...)       # Query tool
self.scores = np.zeros(...)            # Miner scores array
self.update_scores(rewards, uids)     # Update scores
self.set_weights()                     # Set weights on-chain
```

**When to modify**: Rarely - handles boilerplate

---

#### 6. `neurons/validator.py`
**Purpose**: YOUR custom validator implementation

**What it does**:
- ✅ Inherits from `BaseValidatorNeuron`
- ✅ Loads state
- ✅ Implements `forward()` - validation cycle

**Key Method**:
```python
async def forward(self):
    # Calls template/validator/forward.py
    return await forward(self)
```

**When to modify**: Sometimes - add custom initialization

---

#### 7. `template/validator/forward.py`
**Purpose**: Defines the validation cycle (what validators do each epoch)

**What it does**:
1. ✅ Selects miners to query (`get_random_uids()`)
2. ✅ Creates query (`Dummy(dummy_input=...)`)
3. ✅ Queries miners (`self.dendrite(...)`)
4. ✅ Gets responses
5. ✅ Scores responses (`get_rewards()`)
6. ✅ Updates scores (`self.update_scores()`)

**Flow**:
```python
async def forward(self):
    # 1. Select miners
    miner_uids = get_random_uids(self, k=10)
    
    # 2. Query them
    responses = await self.dendrite(
        axons=[self.metagraph.axons[uid] for uid in miner_uids],
        synapse=Dummy(dummy_input=self.step),
        deserialize=True
    )
    
    # 3. Score responses
    rewards = get_rewards(self, query=self.step, responses=responses)
    
    # 4. Update scores
    self.update_scores(rewards, miner_uids)
```

**When to modify**: **ALWAYS** - Define YOUR validation logic!

---

#### 8. `template/validator/reward.py`
**Purpose**: Defines how miners are scored

**What it does**:
- ✅ `reward()` - scores a single response
- ✅ `get_rewards()` - scores multiple responses

**Key Functions**:
```python
def reward(query: int, response: int) -> float:
    # Returns 1.0 if correct, 0.0 if wrong
    return 1.0 if response == query * 2 else 0

def get_rewards(self, query: int, responses: List[int]) -> np.ndarray:
    # Returns array of rewards for all responses
    return np.array([reward(query, r) for r in responses])
```

**When to modify**: **ALWAYS** - Define YOUR scoring logic!

---

### 🛠️ Utility Files

#### 9. `template/utils/config.py`
**Purpose**: Handles configuration and CLI arguments

**What it does**:
- ✅ Adds CLI arguments (`--netuid`, `--wallet.name`, etc.)
- ✅ Validates configuration
- ✅ Sets up logging paths

**When to modify**: Sometimes - add custom config options

---

#### 10. `template/utils/uids.py`
**Purpose**: Helper functions for selecting miners

**What it does**:
- ✅ `get_random_uids()` - randomly selects miners to query

**When to modify**: Sometimes - customize miner selection logic

---

#### 11. `template/base/utils/weight_utils.py`
**Purpose**: Processes weights for on-chain submission

**What it does**:
- ✅ Normalizes weights
- ✅ Converts to uint16 format
- ✅ Handles weight limitations

**When to modify**: Rarely - only if you need custom weight processing

---

## 🎓 Learning Path

### Phase 1: Understanding the Foundation (Day 1-2)

**Task 1.1**: Read `template/base/neuron.py`
- Understand how wallets, subtensor, metagraph work
- Trace through `__init__()` method
- Understand `check_registered()` and `sync()`

**Task 1.2**: Read `template/protocol.py`
- Understand what a synapse is
- See how `Dummy` synapse works
- Understand `deserialize()` method

**Task 1.3**: Draw your own diagram
- Draw the relationship between wallet, subtensor, metagraph
- Label what each does

---

### Phase 2: Understanding Miners (Day 3-4)

**Task 2.1**: Read `template/base/miner.py`
- Understand axon creation
- See how `attach()` works
- Understand the run loop

**Task 2.2**: Read `neurons/miner.py`
- Trace through `forward()` method
- Understand `blacklist()` logic
- Understand `priority()` logic

**Task 2.3**: Modify the miner
- Change `forward()` to return `dummy_input * 3` instead of `* 2`
- Add logging to see when requests arrive
- Test locally

---

### Phase 3: Understanding Validators (Day 5-6)

**Task 3.1**: Read `template/base/validator.py`
- Understand dendrite creation
- See how scores array works
- Understand `update_scores()` and `set_weights()`

**Task 3.2**: Read `template/validator/forward.py`
- Trace through the validation cycle
- Understand miner selection
- Understand querying and scoring

**Task 3.3**: Read `template/validator/reward.py`
- Understand reward function
- See how rewards become scores

**Task 3.4**: Modify the validator
- Change reward function to accept responses within ±1
- Add logging to see scores
- Test locally

---

### Phase 4: Building Your Own (Day 7+)

**Task 4.1**: Create custom protocol
- Define a new synapse class (e.g., `TextPrompt`)
- Add your own fields

**Task 4.2**: Modify miner forward()
- Implement your processing logic
- Handle your custom protocol

**Task 4.3**: Modify validator forward()
- Implement your query logic
- Select miners based on your criteria

**Task 4.4**: Modify reward function
- Implement your scoring logic
- Test with different responses

---

## 🏋️ Beginner Tasks

### Task 1: Hello World Modification
**Goal**: Make miner return "Hello, World!"

**Steps**:
1. Open `neurons/miner.py`
2. Find `forward()` method
3. Change:
   ```python
   synapse.dummy_output = synapse.dummy_input * 2
   ```
   To:
   ```python
   synapse.dummy_output = 42  # Or any number
   ```
4. Run miner locally
5. Verify it works

---

### Task 2: Add Logging
**Goal**: See what's happening

**Steps**:
1. In `neurons/miner.py`, add to `forward()`:
   ```python
   bt.logging.info(f"Received input: {synapse.dummy_input}")
   bt.logging.info(f"Sending output: {synapse.dummy_output}")
   ```
2. Run miner and watch logs

---

### Task 3: Custom Blacklist
**Goal**: Reject requests from specific hotkeys

**Steps**:
1. In `neurons/miner.py`, modify `blacklist()`:
   ```python
   blocked_hotkeys = ["5ABC...", "5DEF..."]  # Add hotkeys
   if synapse.dendrite.hotkey in blocked_hotkeys:
       return True, "Blocked hotkey"
   ```

---

### Task 4: Custom Priority
**Goal**: Prioritize requests based on custom logic

**Steps**:
1. In `neurons/miner.py`, modify `priority()`:
   ```python
   # Example: Higher priority for even numbers
   if synapse.dummy_input % 2 == 0:
       return 100.0
   return 1.0
   ```

---

### Task 5: Custom Reward Function
**Goal**: Score miners differently

**Steps**:
1. Open `template/validator/reward.py`
2. Modify `reward()`:
   ```python
   def reward(query: int, response: int) -> float:
       # Accept responses within ±2
       if abs(response - query * 2) <= 2:
           return 1.0
       return 0.0
   ```

---

### Task 6: Custom Miner Selection
**Goal**: Select miners based on stake

**Steps**:
1. Open `template/validator/forward.py`
2. Modify miner selection:
   ```python
   # Select top 10 miners by stake
   stakes = self.metagraph.S
   top_uids = np.argsort(stakes)[-10:]
   miner_uids = top_uids.tolist()
   ```

---

### Task 7: Create New Protocol
**Goal**: Define your own synapse

**Steps**:
1. Open `template/protocol.py`
2. Add new class:
   ```python
   class MySynapse(bt.Synapse):
       text_input: str
       text_output: Optional[str] = None
       
       def deserialize(self) -> str:
           return self.text_output
   ```
3. Update miner and validator to use it

---

## 📊 Data Flow Summary

```
VALIDATOR SIDE:
┌─────────────┐
│ forward()   │ ──► Select miners
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ dendrite()  │ ──► Query miners
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Responses   │ ──► Get results
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ reward()    │ ──► Score responses
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ update_     │ ──► Update scores
│ scores()    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ set_weights │ ──► Submit to chain
└─────────────┘

MINER SIDE:
┌─────────────┐
│ Request     │ ──► Arrives via axon
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ blacklist() │ ──► Security check
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ priority()  │ ──► Determine order
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ forward()   │ ──► Process request
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Response    │ ──► Send back
└─────────────┘
```

---

## 🔑 Key Concepts Cheat Sheet

| Concept | What It Is | Where It's Used |
|---------|------------|-----------------|
| **Synapse** | Communication protocol | `protocol.py` |
| **Axon** | Miner's server | `base/miner.py` |
| **Dendrite** | Validator's query tool | `base/validator.py` |
| **Metagraph** | Network state | `base/neuron.py` |
| **UID** | Unique identifier | `base/neuron.py` |
| **Scores** | Miner performance | `base/validator.py` |
| **Weights** | On-chain scores | `base/validator.py` |
| **Epoch** | Time period | `base/neuron.py` |
| **Blacklist** | Security filter | `neurons/miner.py` |
| **Priority** | Request ordering | `neurons/miner.py` |

---

## 🎯 Next Steps

1. ✅ Read this guide completely
2. ✅ Follow the learning path day by day
3. ✅ Complete beginner tasks
4. ✅ Modify code and test locally
5. ✅ Read real subnet examples (see `subnet_links.py`)
6. ✅ Build your own subnet!

---

## 📚 Additional Resources

- **Bittensor Docs**: https://docs.bittensor.com
- **Template README**: See `README.md`
- **Real Subnets**: See `template/subnet_links.py`
- **Running Locally**: See `docs/running_on_staging.md`

---

**Happy Learning! 🚀**

