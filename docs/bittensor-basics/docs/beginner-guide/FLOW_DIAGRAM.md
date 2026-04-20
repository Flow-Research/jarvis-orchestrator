# 🔄 Bittensor Subnet Flow Diagrams

Quick visual reference for understanding the subnet flow.

## 📊 Complete Request-Response Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         VALIDATOR SIDE                                  │
└─────────────────────────────────────────────────────────────────────────┘

[neurons/validator.py]
    │
    │ __init__()
    │ • Load state
    │ • Custom setup
    │
    ▼
[template/base/validator.py]
    │
    │ __init__()
    │ • Create dendrite (query tool)
    │ • Initialize scores array
    │ • Setup axon (optional)
    │
    ▼
[template/base/neuron.py]
    │
    │ __init__()
    │ • Load wallet
    │ • Connect subtensor
    │ • Load metagraph
    │ • Check registration
    │ • Assign UID
    │
    ▼
    ┌─────────────────────────────────────┐
    │         MAIN RUN LOOP               │
    │      (Every Epoch)                 │
    └──────────────┬──────────────────────┘
                   │
                   ▼
    ┌─────────────────────────────────────┐
    │  [template/validator/forward.py]     │
    │                                     │
    │  1. Select Miners                  │
    │     get_random_uids()               │
    │                                     │
    │  2. Create Query                    │
    │     Dummy(dummy_input=step)         │
    │                                     │
    │  3. Query Miners                    │
    │     dendrite(axons, synapse)        │
    └──────────────┬──────────────────────┘
                   │
                   │ Network Request
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          MINER SIDE                                     │
└─────────────────────────────────────────────────────────────────────────┘

[template/base/miner.py]
    │
    │ Axon receives request
    │ Routes to attached functions
    │
    ▼
[neurons/miner.py]
    │
    │ 1. blacklist()
    │    ├─► Check if registered?
    │    ├─► Check if validator?
    │    └─► Return (allow/reject, reason)
    │
    │ 2. priority()
    │    ├─► Get caller UID
    │    ├─► Get caller stake
    │    └─► Return priority float
    │
    │ 3. forward()
    │    ├─► Process synapse
    │    ├─► Set dummy_output
    │    └─► Return synapse
    │
    ▼
[template/protocol.py]
    │
    │ Serialize response
    │ Send back to validator
    │
    ▼
                   │
                   │ Network Response
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         VALIDATOR SIDE                                  │
│                      (Processing Response)                               │
└─────────────────────────────────────────────────────────────────────────┘

[template/validator/reward.py]
    │
    │ reward(query, response)
    │ • Compare query vs response
    │ • Return 1.0 if correct, 0.0 if wrong
    │
    │ get_rewards(query, responses)
    │ • Score all responses
    │ • Return numpy array
    │
    ▼
[template/base/validator.py]
    │
    │ update_scores(rewards, uids)
    │ • Update moving average
    │ • self.scores[uid] = alpha * reward + (1-alpha) * old_score
    │
    │ set_weights()
    │ • Normalize scores
    │ • Process weights
    │ • Convert to uint16
    │ • Submit to chain
    │
    ▼
    ┌─────────────────────────────────────┐
    │      NEXT EPOCH                     │
    │   (Repeat cycle)                    │
    └─────────────────────────────────────┘
```

---

## 🎯 Miner Request Processing Flow

```
Request Arrives
    │
    ▼
┌─────────────────┐
│  Axon Server    │  (template/base/miner.py)
│  Receives       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  blacklist()    │  (neurons/miner.py)
│                 │
│  • Check hotkey │
│  • Check reg    │
│  • Return bool  │
└────────┬────────┘
         │
         │ If rejected → End
         │ If allowed  ↓
         ▼
┌─────────────────┐
│  priority()     │  (neurons/miner.py)
│                 │
│  • Get stake    │
│  • Return float │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  forward()      │  (neurons/miner.py)
│                 │
│  • Process      │
│  • Set output   │
│  • Return       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Response       │
│  Sent Back      │
└─────────────────┘
```

---

## ✅ Validator Validation Cycle Flow

```
Epoch Starts
    │
    ▼
┌─────────────────────────┐
│  forward()               │  (template/validator/forward.py)
│                         │
│  1. Select Miners        │
│     └─► get_random_uids()│
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  2. Create Query        │
│     └─► Dummy(...)      │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  3. Query Miners        │
│     └─► dendrite(...)  │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  4. Get Responses       │
│     └─► List[synapse]   │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  5. Score Responses     │  (template/validator/reward.py)
│     └─► get_rewards()  │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  6. Update Scores       │  (template/base/validator.py)
│     └─► update_scores() │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  7. Set Weights         │  (template/base/validator.py)
│     └─► set_weights()  │
└────────┬────────────────┘
         │
         ▼
    Next Epoch
```

---

## 📁 File Dependency Graph

```
template/base/neuron.py (Foundation)
    │
    ├──► template/base/miner.py
    │       │
    │       └──► neurons/miner.py
    │               │
    │               └──► template/protocol.py
    │
    └──► template/base/validator.py
            │
            ├──► neurons/validator.py
            │       │
            │       └──► template/validator/forward.py
            │               │
            │               ├──► template/validator/reward.py
            │               └──► template/utils/uids.py
            │
            └──► template/base/utils/weight_utils.py
```

---

## 🔑 Key Data Structures Flow

```
VALIDATOR:
┌──────────────┐
│  Query       │  Dummy(dummy_input=5)
└──────┬───────┘
       │
       │ Network
       │
       ▼
┌──────────────┐
│  Response    │  Dummy(dummy_output=10)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Reward      │  [1.0, 0.0, 1.0, ...]  (numpy array)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Scores       │  [0.95, 0.10, 0.88, ...]  (moving average)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Weights     │  [uint16, uint16, ...]  (normalized, on-chain)
└──────────────┘
```

---

## 🎓 Learning Order Visualization

```
START HERE
    │
    ▼
[1] template/base/neuron.py
    │  Foundation - Understand this first!
    │
    ├──► [2] template/protocol.py
    │       │  Communication protocol
    │       │
    │       ├──► [3] template/base/miner.py
    │       │       │  Miner base class
    │       │       │
    │       │       └──► [4] neurons/miner.py
    │       │               │  YOUR miner logic
    │       │               │
    │       │               └──► [PRACTICE] Modify forward()
    │       │
    │       └──► [5] template/base/validator.py
    │               │  Validator base class
    │               │
    │               ├──► [6] neurons/validator.py
    │               │       │  YOUR validator setup
    │               │       │
    │               ├──► [7] template/validator/forward.py
    │               │       │  Validation cycle
    │               │       │
    │               │       └──► [PRACTICE] Modify selection
    │               │
    │               └──► [8] template/validator/reward.py
    │                       │  Scoring logic
    │                       │
    │                       └──► [PRACTICE] Modify reward()
    │
    └──► [9] template/utils/config.py
            │  Configuration
            │
            └──► [10] template/utils/uids.py
                    │  Helper functions
```

---

## 🚀 Quick Reference: What Each File Does

| File | Purpose | Key Function | When to Modify |
|------|---------|--------------|----------------|
| `base/neuron.py` | Foundation | `__init__()`, `sync()` | Rarely |
| `protocol.py` | Communication | `Dummy` class | **Always** |
| `base/miner.py` | Miner setup | `run()`, axon setup | Rarely |
| `neurons/miner.py` | Miner logic | `forward()`, `blacklist()` | **Always** |
| `base/validator.py` | Validator setup | `set_weights()`, `update_scores()` | Rarely |
| `neurons/validator.py` | Validator init | `__init__()`, `forward()` | Sometimes |
| `validator/forward.py` | Validation cycle | `forward()` | **Always** |
| `validator/reward.py` | Scoring | `reward()`, `get_rewards()` | **Always** |
| `utils/config.py` | Configuration | `add_args()` | Sometimes |
| `utils/uids.py` | Miner selection | `get_random_uids()` | Sometimes |

---

## 💡 Concept Map

```
BITTENSOR SUBNET
    │
    ├──► WALLET
    │       ├──► Coldkey (identity)
    │       └──► Hotkey (subnet key)
    │
    ├──► SUBTENSOR
    │       └──► Blockchain interface
    │
    ├──► METAGRAPH
    │       ├──► Network state
    │       ├──► UIDs
    │       ├──► Stakes
    │       └──► Axons (IPs/ports)
    │
    ├──► MINER
    │       ├──► Axon (server)
    │       ├──► Receives requests
    │       └──► Processes & responds
    │
    └──► VALIDATOR
            ├──► Dendrite (client)
            ├──► Queries miners
            ├──► Scores responses
            └──► Sets weights
```

---

**See BEGINNER_GUIDE.md for detailed explanations and tasks!**

