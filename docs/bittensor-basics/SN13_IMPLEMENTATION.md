# Bittensor Subnet 13 - Data Universe Implementation Guide

## Testnet Status

**Testnet Subnet 13: `dataverse`**
- Has 151 miners
- This is our testnet target

## Wallet Setup Required

We need to create a wallet to participate. Options:

1. **Use btcli** - Run interactively to create wallet:
   ```bash
   # Create coldkey
   btcli wallet new_coldkey --wallet.name testminer
   
   # Create hotkey
   btcli wallet new_hotkey --wallet.name testminer --wallet.hotkey miner1
   
   # Get testnet TAO from faucet: https://test.faucet.taostats.io/
   
   # Register on testnet
   btcli subnet register --netuid 13 --wallet.name testminer --wallet.hotkey miner1 --subtensor.network test
   ```

## SN13 Miner Code Structure

```
sn13_miner/
├── neurons/
│   └── miner.py          # Main miner implementation
├── scraping/
│   ├── coordinator.py    # Coordinates scraping tasks
│   ├── provider.py       # Provides scraper instances
│   ├── x/               # X (Twitter) scrapers
│   └── reddit/           # Reddit scrapers
├── storage/
│   └── sqlite_miner_storage.py  # Data storage
├── common/
│   ├── protocol.py       # Synapse definitions
│   └── data/             # Data models
└── rewards/              # Reward mechanisms
```

## How Tasks Flow (From Validator to Miner)

```
VALIDATOR sends request ──────────────────────────────────► MINER

Request Types:
1. GetMinerIndex
   └── "What data do you have?"
   └── Returns: compressed index of all buckets

2. GetDataEntityBucket  
   └── "Give me data from bucket X"
   └── Returns: actual data entities

3. GetContentsByBuckets
   └── "Verify this data is real"
   └── Returns: sample content for validation
```

## What Our Implementation Needs

For our agent-based task distribution:

```python
# We intercept these functions and route to our agents:

async def get_index(self, synapse: GetMinerIndex) -> GetMinerIndex:
    # 1. Get current index from storage
    # 2. Optionally: trigger agents to fetch fresh data
    # 3. Return index
    
async def get_data_entity_bucket(self, synapse: GetDataEntityBucket) -> GetDataEntityBucket:
    # 1. Parse what bucket is requested
    # 2. Route to appropriate agent (X agent, Reddit agent, etc.)
    # 3. Get data from agents
    # 4. Return data entities

async def get_contents_by_buckets(self, synapse: GetContentsByBuckets) -> GetContentsByBuckets:
    # 1. Validator wants to verify our data
    # 2. Return sample content
    # 3. This affects our credibility score!
```

## Agent Task Distribution Design

```
                    ┌─────────────────┐
                    │   VALIDATOR     │
                    │   (Queries)     │
                    └────────┬────────┘
                             │
                             ▼
                ┌────────────────────────┐
                │    TASK ROUTER         │
                │  (Parse request type)  │
                └───────────┬────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
   ┌─────────┐        ┌──────────┐       ┌──────────┐
   │ X Agent │        │ Reddit   │       │ YouTube  │
   │         │        │ Agent    │       │ Agent    │
   └─────────┘        └──────────┘       └──────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                            ▼
                ┌────────────────────────┐
                │   RESPONSE BUILDER     │
                │  (Compile results)     │
                └───────────┬────────────┘
                            │
                            ▼
                    ┌─────────────┐
                    │   VALIDATOR │
                    │   (Scores)  │
                    └─────────────┘
```

## Next Steps

1. Create wallet with btcli (needs interactive terminal)
2. Register on testnet SN13
3. Set up SN13 miner code
4. Modify to connect to our agent system
5. Test end-to-end