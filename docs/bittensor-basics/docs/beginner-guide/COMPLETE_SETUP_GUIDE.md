# 🚀 Complete Setup Guide: From Zero to Running on Testnet

Complete step-by-step guide from wallet creation to running miners and validators on Bittensor testnet.

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step 1: Wallet Creation](#step-1-wallet-creation)
3. [Step 2: Hotkey Creation](#step-2-hotkey-creation)
4. [Step 3: Get Testnet TAO](#step-3-get-testnet-tao)
5. [Step 4: Find Available Testnet Subnets](#step-4-find-available-testnet-subnets)
6. [Step 5: Register on Subnet](#step-5-register-on-subnet)
7. [Step 6: Install Dependencies](#step-6-install-dependencies)
8. [Step 7: Configure Miner](#step-7-configure-miner)
9. [Step 8: Run Miner](#step-8-run-miner)
10. [Step 9: Configure Validator](#step-9-configure-validator)
11. [Step 10: Run Validator](#step-10-run-validator)
12. [Step 11: Monitor & Verify](#step-11-monitor--verify)
13. [How Miners Get Tasks](#how-miners-get-tasks)
14. [How Miners Process Tasks](#how-miners-process-tasks)
15. [Troubleshooting](#troubleshooting)

---

## ✅ Prerequisites

Before starting, ensure you have:

- Python 3.8+ installed
- Git installed
- Terminal/Command line access
- Internet connection

---

## 🔐 Step 1: Wallet Creation

### Create Coldkey (Wallet)

The coldkey is your main wallet identity. You'll use it to:
- Hold TAO tokens
- Register hotkeys
- Manage your subnet identity

**Command**:
```bash
btcli wallet new_coldkey --wallet.name my_wallet
```

**What happens**:
- Prompts for password (remember this!)
- Creates wallet at `~/.bittensor/wallets/my_wallet/`
- Generates coldkey (main identity)

**Example Output**:
```
Enter password to encrypt key: [password]
Confirm password: [password]
✅ Created coldkey: 5ABC...
```

**Verify wallet created**:
```bash
btcli wallet list
```

**Expected Output**:
```
Wallets
└── Coldkey my_wallet  ss58_address: 5ABC...
```

---

## 🔑 Step 2: Hotkey Creation

Hotkeys are subnet-specific keys. You need one for each subnet you want to participate in.

### Create Hotkey for Miner

**Command**:
```bash
btcli wallet new_hotkey --wallet.name my_wallet --wallet.hotkey miner_hotkey
```

**What happens**:
- Creates hotkey: `~/.bittensor/wallets/my_wallet/hotkeys/miner_hotkey/`
- Generates hotkey address (e.g., `5DEF...`)

**Example Output**:
```
Enter password to encrypt key: [password]
✅ Created hotkey: 5DEF...
```

### Create Hotkey for Validator

**Command**:
```bash
btcli wallet new_hotkey --wallet.name my_wallet --wallet.hotkey validator_hotkey
```

**Verify hotkeys**:
```bash
btcli wallet list
```

**Expected Output**:
```
Wallets
└── Coldkey my_wallet  ss58_address: 5ABC...
    ├── Hotkey miner_hotkey  ss58_address: 5DEF...
    └── Hotkey validator_hotkey  ss58_address: 5GHI...
```

---

## 💰 Step 3: Get Testnet TAO

You need testnet TAO to register on subnets. Testnet TAO is free!

### Option 1: Testnet Faucet (Recommended)

**Visit**: https://test.faucet.taostats.io/

**Steps**:
1. Enter your coldkey address (from Step 1)
2. Click "Get Test TAO"
3. Wait for confirmation (usually instant)

**Verify balance**:
```bash
btcli wallet balance --wallet.name my_wallet --subtensor.network test
```

**Expected Output**:
```
Balance: τ100.000000000
```

### Option 2: Discord Faucet

1. Join Bittensor Discord: https://discord.gg/bittensor
2. Go to #testnet-faucet channel
3. Use command: `!faucet <your_coldkey_address>`
4. Wait for confirmation

---

## 🔍 Step 4: Find Available Testnet Subnets

Before registering, find which subnets are available on testnet.

**Command**:
```bash
btcli subnet list --subtensor.network test
```

**Example Output**:
```
NETUID  NEURONS  MAX_N   DIFFICULTY  TEMPO  EMISSION  BURN(τ)
   1       45     256     10.00 M    100     0.50%    τ1.00000
   3       12     128     5.00 M     100     0.30%    τ1.00000
   5       8      64      2.00 M     100     0.20%    τ1.00000
   ...
```

**Common Testnet Subnets**:
- **NetUID 1**: Template/Prompting subnet (most active)
- **NetUID 3**: Various test subnets
- **NetUID 5**: Smaller test subnets

**Note**: Subnet numbers change frequently on testnet. Always check with `btcli subnet list`.

---

## 📝 Step 5: Register on Subnet

### Register Miner

**Command** (replace `NETUID` with actual subnet number):
```bash
btcli subnet register \
  --netuid NETUID \
  --wallet.name my_wallet \
  --wallet.hotkey miner_hotkey \
  --subtensor.network test
```

**Example** (for NetUID 1):
```bash
btcli subnet register \
  --netuid 1 \
  --wallet.name my_wallet \
  --wallet.hotkey miner_hotkey \
  --subtensor.network test
```

**What happens**:
- Prompts for password
- Checks balance
- Registers hotkey on subnet
- Assigns UID (Unique Identifier)

**Example Output**:
```
Enter password: [password]
>> Continue Registration?
  hotkey:     5DEF...
  coldkey:    5ABC...
  network:    test
  netuid:     1
  burn:       τ1.00000
  Continue? [y/n]: y
✅ Registered on subnet 1 with UID: 45
```

**Save your UID!** You'll need it later.

### Register Validator

**Command**:
```bash
btcli subnet register \
  --netuid NETUID \
  --wallet.name my_wallet \
  --wallet.hotkey validator_hotkey \
  --subtensor.network test
```

**Verify Registration**:
```bash
btcli wallet overview \
  --wallet.name my_wallet \
  --subtensor.network test
```

**Expected Output**:
```
Subnet: 1
COLDKEY  HOTKEY           UID  ACTIVE  STAKE(τ)  ...
my_wallet miner_hotkey    45    True   0.00000   ...
my_wallet validator_hotkey 46   True   0.00000   ...
```

---

## 📦 Step 6: Install Dependencies

### Clone Template Repository

```bash
git clone https://github.com/opentensor/bittensor-subnet-template.git
cd bittensor-subnet-template
```

### Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### Install Requirements

```bash
pip install -e .
```

**Verify Installation**:
```bash
python -c "import bittensor as bt; print(bt.__version__)"
```

---

## ⚙️ Step 7: Configure Miner

### Understanding Miner Task Flow

**How Miners Get Tasks**:

```
┌─────────────────────────────────────────┐
│         TASK DISTRIBUTION               │
└─────────────────────────────────────────┘

Approach 1: Standard Synapse (Built-in)
Validator → Synapse → Miner → Process → Response

Approach 2: External API/WebSocket
External System → API/WS → Miner → Store → Validator Queries

Approach 3: On-Chain Storage
Blockchain → Miner Reads → Process → Store Results

Approach 4: IPFS
IPFS CID → Miner Fetches → Process → Store Results
```

**How Miners Process Tasks**:

```
Task Arrives
    │
    ▼
┌─────────────────┐
│  blacklist()    │  Check if request is allowed
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  priority()     │  Determine processing order
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  forward()      │  Process the task
│                 │  - Execute task logic
│                 │  - Generate result
│                 │  - Return response
└────────┬────────┘
         │
         ▼
    Response Sent
```

### Basic Miner Configuration

Create a config file or use command-line arguments:

**Run Miner** (Standard Synapse approach):
```bash
python neurons/miner.py \
  --netuid NETUID \
  --wallet.name my_wallet \
  --wallet.hotkey miner_hotkey \
  --subtensor.network test \
  --logging.debug
```

**Example** (NetUID 1):
```bash
python neurons/miner.py \
  --netuid 1 \
  --wallet.name my_wallet \
  --wallet.hotkey miner_hotkey \
  --subtensor.network test \
  --logging.debug
```

### Miner with API/WebSocket Integration

If you want to add external task sources, modify `neurons/miner.py`:

```python
# neurons/miner.py

import asyncio
import threading
import queue
import websocket
import json

class Miner(BaseMinerNeuron):
    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)
        
        # Task storage
        self.task_storage = {}
        self.task_queue = queue.Queue()
        
        # WebSocket connection (if using external tasks)
        if config.ws_url:
            self.ws_manager = WebSocketManager(
                url=config.ws_url,
                miner=self
            )
            self.ws_thread = threading.Thread(
                target=self.ws_manager.run,
                daemon=True
            )
            self.ws_thread.start()
        
        bt.logging.info(f"Miner initialized with UID: {self.uid}")
    
    async def forward(self, synapse: template.protocol.Dummy):
        """
        Process task from validator (Standard Synapse approach)
        """
        # Standard processing
        synapse.dummy_output = synapse.dummy_input * 2
        return synapse
    
    def process_external_task(self, task_data: dict):
        """
        Process task from external API/WebSocket
        """
        task_id = task_data.get('task_id')
        result = {
            'task_id': task_id,
            'status': 'completed',
            'result': self.execute_task(task_data)
        }
        self.task_storage[task_id] = result
        return result
```

**Run Miner with WebSocket**:
```bash
python neurons/miner.py \
  --netuid NETUID \
  --wallet.name my_wallet \
  --wallet.hotkey miner_hotkey \
  --subtensor.network test \
  --ws_url wss://api.example.com/tasks \
  --logging.debug
```

---

## 🏃 Step 8: Run Miner

### Start Miner

**Command**:
```bash
python neurons/miner.py \
  --netuid NETUID \
  --wallet.name my_wallet \
  --wallet.hotkey miner_hotkey \
  --subtensor.network test \
  --logging.debug
```

**Expected Output**:
```
2024-01-01 12:00:00 | INFO | Loading wallet...
2024-01-01 12:00:01 | INFO | Wallet: Wallet (Name: 'my_wallet', Hotkey: 'miner_hotkey')
2024-01-01 12:00:02 | INFO | Subtensor: Network: test, Chain: wss://test.finney.opentensor.ai:443
2024-01-01 12:00:03 | INFO | Metagraph: metagraph(netuid:1, n:45, block:12345, network:test)
2024-01-01 12:00:04 | INFO | Running neuron on subnet: 1 with uid 45
2024-01-01 12:00:05 | INFO | Attaching forward function to miner axon.
2024-01-01 12:00:06 | INFO | Axon created: ...
2024-01-01 12:00:07 | INFO | Serving miner axon on network: test with netuid: 1
2024-01-01 12:00:08 | INFO | Miner starting at block: 12345
2024-01-01 12:00:09 | INFO | Miner running... Ready to receive tasks
```

### Miner Task Processing Flow

**When Validator Queries**:

```
1. Validator sends synapse → Miner receives
2. blacklist() checks → Allow/Reject
3. priority() determines → Processing order
4. forward() processes → Executes task
5. Response sent → Back to validator
```

**When External Task Arrives** (if using API/WebSocket):

```
1. External system sends task → WebSocket/API receives
2. Task added to queue → task_queue.put(task)
3. Background thread processes → process_external_task()
4. Result stored → task_storage[task_id] = result
5. Validator queries later → Returns stored results
```

### Verify Miner is Running

**Check logs**:
- Should see "Miner running..." messages
- Should see "Received request from..." when validator queries
- Should see "Processed task..." for each task

**Check on-chain**:
```bash
btcli wallet overview --wallet.name my_wallet --subtensor.network test
```

Should show miner as "ACTIVE: True"

---

## ✅ Step 9: Configure Validator

### Basic Validator Configuration

**Run Validator**:
```bash
python neurons/validator.py \
  --netuid NETUID \
  --wallet.name my_wallet \
  --wallet.hotkey validator_hotkey \
  --subtensor.network test \
  --logging.debug
```

**Example** (NetUID 1):
```bash
python neurons/validator.py \
  --netuid 1 \
  --wallet.name my_wallet \
  --wallet.hotkey validator_hotkey \
  --subtensor.network test \
  --logging.debug
```

### Validator Configuration Options

**Customize validation cycle**:
```bash
python neurons/validator.py \
  --netuid NETUID \
  --wallet.name my_wallet \
  --wallet.hotkey validator_hotkey \
  --subtensor.network test \
  --neuron.sample_size 10 \          # Query 10 miners per cycle
  --neuron.epoch_length 100 \        # Epoch length in blocks
  --neuron.moving_average_alpha 0.1 \ # EMA smoothing
  --logging.debug
```

---

## 🏃 Step 10: Run Validator

### Start Validator

**Command**:
```bash
python neurons/validator.py \
  --netuid NETUID \
  --wallet.name my_wallet \
  --wallet.hotkey validator_hotkey \
  --subtensor.network test \
  --logging.debug
```

**Expected Output**:
```
2024-01-01 12:00:00 | INFO | Loading wallet...
2024-01-01 12:00:01 | INFO | Wallet: Wallet (Name: 'my_wallet', Hotkey: 'validator_hotkey')
2024-01-01 12:00:02 | INFO | Subtensor: Network: test, Chain: wss://test.finney.opentensor.ai:443
2024-01-01 12:00:03 | INFO | Metagraph: metagraph(netuid:1, n:45, block:12345, network:test)
2024-01-01 12:00:04 | INFO | Running neuron on subnet: 1 with uid 46
2024-01-01 12:00:05 | INFO | Dendrite: ...
2024-01-01 12:00:06 | INFO | Building validation weights.
2024-01-01 12:00:07 | INFO | Validator starting at block: 12345
2024-01-01 12:00:08 | INFO | step(0) block(12345)
2024-01-01 12:00:09 | INFO | Querying 10 miners...
2024-01-01 12:00:10 | INFO | Received responses: [...]
2024-01-01 12:00:11 | INFO | Scored responses: [...]
2024-01-01 12:00:12 | INFO | Updated scores
```

### Validator Query Flow

**Each Epoch**:

```
1. Select Miners → get_random_uids(k=10)
2. Create Query → Dummy(dummy_input=step)
3. Query Miners → dendrite(axons, synapse)
4. Receive Responses → List of responses
5. Score Responses → reward(query, response)
6. Update Scores → update_scores(rewards, uids)
7. Set Weights → set_weights() (every epoch)
```

---

## 📊 Step 11: Monitor & Verify

### Check Miner Status

**Command**:
```bash
btcli wallet overview \
  --wallet.name my_wallet \
  --subtensor.network test
```

**Look for**:
- `ACTIVE: True` - Miner is running
- `UID: 45` - Your miner's unique ID
- `STAKE(τ)` - Staked TAO (if any)

### Check Validator Status

Same command, look for validator hotkey:
- `ACTIVE: True` - Validator is running
- `UID: 46` - Your validator's unique ID

### Monitor Logs

**Miner logs should show**:
```
INFO | Received request from validator
INFO | Processing task...
INFO | Task completed
```

**Validator logs should show**:
```
INFO | Querying miners: [45, 12, 33, ...]
INFO | Received responses: [10, 20, 15, ...]
INFO | Scored responses: [1.0, 1.0, 0.0, ...]
INFO | Updated scores
INFO | set_weights on chain successfully!
```

### Check Emissions

**Command**:
```bash
btcli wallet overview \
  --wallet.name my_wallet \
  --subtensor.network test
```

Look at `EMISSION(ρ)` column - this shows your share of emissions.

---

## 🔄 How Miners Get Tasks

### Method 1: Standard Synapse (Built-in)

**Flow**:
```
Validator → Creates Synapse → Queries Miner → Miner Receives in forward()
```

**Code** (`neurons/miner.py`):
```python
async def forward(self, synapse: Dummy) -> Dummy:
    # Task arrives here automatically
    # Process immediately
    synapse.dummy_output = synapse.dummy_input * 2
    return synapse
```

**No additional setup needed!**

### Method 2: External API/WebSocket

**Flow**:
```
External System → API/WebSocket → Miner Receives → Stores in task_storage
                                                              ↓
Validator → Queries Miner → Gets Stored Results
```

**Setup** (`neurons/miner.py`):
```python
class Miner(BaseMinerNeuron):
    def __init__(self, config=None):
        super().__init__(config=config)
        
        # WebSocket for external tasks
        if config.ws_url:
            self.ws = WebSocketManager(config.ws_url, self)
            self.ws.start()
        
        # Task storage
        self.task_storage = {}
    
    def on_websocket_message(self, message):
        """Called when external task arrives"""
        task = json.loads(message)
        result = self.process_task(task)
        self.task_storage[task['id']] = result
    
    async def forward(self, synapse: TaskQuerySynapse):
        """Validator queries for stored tasks"""
        if synapse.task_id:
            return self.task_storage.get(synapse.task_id)
        else:
            # Return recent tasks
            return list(self.task_storage.values())[-10:]
```

### Method 3: Polling API

**Flow**:
```
Miner → Polls API → Gets Tasks → Processes → Stores Results
```

**Setup** (`neurons/miner.py`):
```python
import requests
import threading

class Miner(BaseMinerNeuron):
    def __init__(self, config=None):
        super().__init__(config=config)
        
        # API polling
        if config.api_url:
            self.api_url = config.api_url
            self.poll_thread = threading.Thread(
                target=self.poll_api,
                daemon=True
            )
            self.poll_thread.start()
    
    def poll_api(self):
        """Poll API for new tasks"""
        while True:
            try:
                response = requests.get(self.api_url)
                tasks = response.json().get('tasks', [])
                
                for task in tasks:
                    if task['id'] not in self.task_storage:
                        result = self.process_task(task)
                        self.task_storage[task['id']] = result
            except Exception as e:
                bt.logging.error(f"API polling error: {e}")
            
            time.sleep(10)  # Poll every 10 seconds
```

---

## ⚙️ How Miners Process Tasks

### Task Processing Pipeline

```
┌─────────────────────────────────────────────┐
│         TASK PROCESSING PIPELINE            │
└─────────────────────────────────────────────┘

1. TASK ARRIVAL
   ├─► Standard Synapse: Arrives in forward()
   ├─► WebSocket: Arrives in on_message()
   └─► API: Arrives via polling

2. SECURITY CHECK (blacklist)
   ├─► Check if sender is registered
   ├─► Check if sender is validator (if required)
   └─► Return (allow/reject, reason)

3. PRIORITY ASSIGNMENT (priority)
   ├─► Get sender's stake
   ├─► Calculate priority score
   └─► Return priority float

4. TASK PROCESSING (forward/process_task)
   ├─► Parse task data
   ├─► Execute task logic
   ├─► Generate result
   └─► Return/store result

5. RESPONSE/RESULT
   ├─► Standard: Return synapse immediately
   └─► External: Store in task_storage
```

### Example: Complete Task Processing

**File**: `neurons/miner.py`

```python
class Miner(BaseMinerNeuron):
    def __init__(self, config=None):
        super().__init__(config=config)
        self.task_storage = {}
        self.processed_count = 0
    
    async def blacklist(self, synapse: Dummy) -> Tuple[bool, str]:
        """Step 1: Security check"""
        if synapse.dendrite.hotkey not in self.metagraph.hotkeys:
            return True, "Unregistered hotkey"
        return False, "OK"
    
    async def priority(self, synapse: Dummy) -> float:
        """Step 2: Priority assignment"""
        uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        return float(self.metagraph.S[uid])  # Stake-based priority
    
    async def forward(self, synapse: Dummy) -> Dummy:
        """Step 3: Task processing"""
        bt.logging.info(f"Processing task: input={synapse.dummy_input}")
        
        # Execute task logic
        result = self.execute_task_logic(synapse.dummy_input)
        
        # Set output
        synapse.dummy_output = result
        
        self.processed_count += 1
        bt.logging.info(f"Task completed: output={result}, total={self.processed_count}")
        
        return synapse
    
    def execute_task_logic(self, input_value: int) -> int:
        """Your actual task logic"""
        # Example: Multiply by 2
        return input_value * 2
        
        # Or: Complex computation
        # return complex_algorithm(input_value)
    
    def process_external_task(self, task_data: dict) -> dict:
        """Process task from external source"""
        task_id = task_data.get('task_id')
        task_type = task_data.get('type')
        input_data = task_data.get('data', {})
        
        bt.logging.info(f"Processing external task {task_id} of type {task_type}")
        
        # Route to appropriate handler
        if task_type == "computation":
            result = self.handle_computation(input_data)
        elif task_type == "data_processing":
            result = self.handle_data_processing(input_data)
        else:
            result = {"error": "Unknown task type"}
        
        # Store result
        task_result = {
            'task_id': task_id,
            'status': 'completed',
            'result': result,
            'timestamp': time.time()
        }
        
        self.task_storage[task_id] = task_result
        return task_result
```

---

## 🎯 Complete Workflow Examples

### Example 1: Standard Template Subnet (NetUID 1)

**Full Workflow**:

```bash
# 1. Create wallet
btcli wallet new_coldkey --wallet.name test_wallet

# 2. Create hotkeys
btcli wallet new_hotkey --wallet.name test_wallet --wallet.hotkey miner
btcli wallet new_hotkey --wallet.name test_wallet --wallet.hotkey validator

# 3. Get testnet TAO
# Visit: https://test.faucet.taostats.io/
# Enter your coldkey address

# 4. Check balance
btcli wallet balance --wallet.name test_wallet --subtensor.network test

# 5. List subnets
btcli subnet list --subtensor.network test

# 6. Register miner (NetUID 1)
btcli subnet register \
  --netuid 1 \
  --wallet.name test_wallet \
  --wallet.hotkey miner \
  --subtensor.network test

# 7. Register validator
btcli subnet register \
  --netuid 1 \
  --wallet.name test_wallet \
  --wallet.hotkey validator \
  --subtensor.network test

# 8. Install dependencies
cd bittensor-subnet-template
python -m venv .venv
source .venv/bin/activate
pip install -e .

# 9. Run miner (Terminal 1)
python neurons/miner.py \
  --netuid 1 \
  --wallet.name test_wallet \
  --wallet.hotkey miner \
  --subtensor.network test \
  --logging.debug

# 10. Run validator (Terminal 2)
python neurons/validator.py \
  --netuid 1 \
  --wallet.name test_wallet \
  --wallet.hotkey validator \
  --subtensor.network test \
  --logging.debug
```

### Example 2: Multiple Testnet Subnets

**Register on Multiple Subnets**:

```bash
# Register on NetUID 1
btcli subnet register --netuid 1 --wallet.name test_wallet --wallet.hotkey miner1 --subtensor.network test

# Register on NetUID 3
btcli subnet register --netuid 3 --wallet.name test_wallet --wallet.hotkey miner3 --subtensor.network test

# Register on NetUID 5
btcli subnet register --netuid 5 --wallet.name test_wallet --wallet.hotkey miner5 --subtensor.network test

# Run miners for each subnet
python neurons/miner.py --netuid 1 --wallet.name test_wallet --wallet.hotkey miner1 --subtensor.network test
python neurons/miner.py --netuid 3 --wallet.name test_wallet --wallet.hotkey miner3 --subtensor.network test
python neurons/miner.py --netuid 5 --wallet.name test_wallet --wallet.hotkey miner5 --subtensor.network test
```

---

## 🔧 Troubleshooting

### Issue: "Wallet not found"

**Solution**:
```bash
# Verify wallet exists
btcli wallet list

# If missing, create it
btcli wallet new_coldkey --wallet.name my_wallet
```

### Issue: "Insufficient balance"

**Solution**:
```bash
# Check balance
btcli wallet balance --wallet.name my_wallet --subtensor.network test

# Get testnet TAO from faucet
# Visit: https://test.faucet.taostats.io/
```

### Issue: "Hotkey not registered"

**Solution**:
```bash
# Register hotkey
btcli subnet register \
  --netuid NETUID \
  --wallet.name my_wallet \
  --wallet.hotkey my_hotkey \
  --subtensor.network test
```

### Issue: "Connection error"

**Solution**:
```bash
# Check network connectivity
ping test.finney.opentensor.ai

# Try different endpoint
export BT_SUBTENSOR_NETWORK=test
export BT_SUBTENSOR_CHAIN_ENDPOINT=wss://test.finney.opentensor.ai:443
```

### Issue: "Module not found"

**Solution**:
```bash
# Activate virtual environment
source .venv/bin/activate

# Reinstall
pip install -e .
```

### Issue: Miner not receiving tasks

**Check**:
1. Miner is registered: `btcli wallet overview`
2. Miner is running: Check logs for "Miner running..."
3. Validators are querying: Check validator logs
4. Network connectivity: Can miner reach validators?

---

## 📝 Quick Reference Commands

```bash
# Wallet Management
btcli wallet new_coldkey --wallet.name NAME
btcli wallet new_hotkey --wallet.name NAME --wallet.hotkey HOTKEY
btcli wallet list
btcli wallet balance --wallet.name NAME --subtensor.network test

# Subnet Management
btcli subnet list --subtensor.network test
btcli subnet register --netuid NETUID --wallet.name NAME --wallet.hotkey HOTKEY --subtensor.network test
btcli wallet overview --wallet.name NAME --subtensor.network test

# Running Neurons
python neurons/miner.py --netuid NETUID --wallet.name NAME --wallet.hotkey HOTKEY --subtensor.network test
python neurons/validator.py --netuid NETUID --wallet.name NAME --wallet.hotkey HOTKEY --subtensor.network test
```

---

## 🎓 Next Steps

After setup:
1. ✅ Monitor miner/validator logs
2. ✅ Check emissions distribution
3. ✅ Customize task processing logic
4. ✅ Add external API/WebSocket integration
5. ✅ Deploy to mainnet (after testing)

---

**See other guides for advanced topics:**
- `BEGINNER_GUIDE.md` - Understanding the codebase
- `API_WEBSOCKET_INTEGRATION_GUIDE.md` - Adding external task sources
- `TASK_DISTRIBUTION_APPROACHES.md` - Different task distribution methods

