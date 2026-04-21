#!/usr/bin/env python3
"""
Mock Task Listener - Simulates validator queries to understand task structure.

Run this to see what different query types look like.
This is purely for understanding the protocol.
"""

import asyncio
import json
from datetime import datetime


class MockQuery:
    """Represents different validator query types."""

    # SN13 Data Universe queries
    SN13_GET_MINER_INDEX = {
        "name": "GetMinerIndex",
        "description": "Validator asks: What data do you have?",
        "purpose": "Build index of all miners' data holdings",
        "returns": {
            "compressed_index_serialized": "JSON of all DataEntityBuckets (source + time + label + count)"
        },
        "task_decomposition": "None - this is just index query, no work to do",
    }

    SN13_GET_DATA_ENTITY_BUCKET = {
        "name": "GetDataEntityBucket",
        "description": "Validator asks: Give me data from bucket X",
        "purpose": "Fetch actual data (posts, tweets, comments)",
        "payload": {
            "data_entity_bucket_id": "(source, time_bucket_id, label)"
            # Example: (DataSource.X, 1845, "$BTC")
            # Meaning: X posts about BTC from hour 1845
        },
        "task_decomposition": "Could split by time range or label",
    }

    SN13_GET_CONTENTS = {
        "name": "GetContentsByBuckets",
        "description": "Validator asks: Verify this data is real",
        "purpose": "Verify data authenticity and quality",
        "task_decomposition": "Return sample content for verification",
    }

    # Generic synapse fields (all queries have these)
    COMMON_FIELDS = {
        "dendrite": "Who sent the query (validator hotkey)",
        "dendrite.hotkey": "Validator's SS58 address",
        "version": "Protocol version",
        "timestamp": "When query was made",
    }


def print_query_analysis():
    """Print analysis of different query types."""

    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    VALIDATOR QUERY TYPES - ANALYSIS                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────────────────────────────┐
│ SUBNET 13: DATA UNIVERSE (Data Scraping)                                     │
└──────────────────────────────────────────────────────────────────────────────┘

QUERY 1: GetMinerIndex
────────────────────────────────────────────────────────────────────────────────
Validator asks: "What data do you have?"

📥 INPUT:  None (empty request)
📤 OUTPUT: CompressedMinerIndex
   └── List of all DataEntityBuckets
       ├── source: X or REDDIT
       ├── time_bucket_id: hour (e.g., 1845 = this hour)
       ├── label: topic (e.g., "$BTC", "bittensor")
       └── scorable_bytes: amount of data

🔄 TASK DECOMPOSITION:
   • No task - this is just reporting what you have
   • Validators use this to know WHO to query for WHAT data
   • They build a map: "I need $BTC data → query Miner X, Y, Z"

💡 WORK FLOW:
   Validator → GetMinerIndex → Build data map → Pick buckets → Query specific data


QUERY 2: GetDataEntityBucket  
────────────────────────────────────────────────────────────────────────────────
Validator asks: "Give me data from bucket X"

📥 INPUT:  data_entity_bucket_id = (source, time_bucket_id, label)
   Example: (X, 1845, "$BTC")
   
📤 OUTPUT: List[DataEntity]
   ├── content: actual text
   ├── created_at: timestamp
   ├── source: platform
   ├── label: topic
   └── various metadata fields

🔄 TASK DECOMPOSITION:
   Could split by:
   • Time range: "get data from hours 1840-1850"
   • Label: "get all $BTC, $ETH, $SOL"
   • Content limit: "first 100 posts"

💡 WORK FLOW:
   Validator → GetDataEntityBucket(bucket_id) → Return actual data → Validator scores


QUERY 3: GetContentsByBuckets
────────────────────────────────────────────────────────────────────────────────
Validator asks: "Verify this data is real"

📥 INPUT:  List of bucket_ids to verify
   
📤 OUTPUT: Actual content for verification
   • Validator checks: is this real? is it duplicated? is it correct label?

🔄 TASK DECOMPOSITION:
   • Return sample content (usually 10 random items)
   • No computation - just return what's stored

💡 WORK FLOW:
   Validator → GetContents → Verify → Update miner credibility score → Adjust weights


┌──────────────────────────────────────────────────────────────────────────────┐
│ SUBNET 1: APEX (LLM Inference)                                               │
└──────────────────────────────────────────────────────────────────────────────┘

QUERY: Prompt
────────────────────────────────────────────────────────────────────────────────
Validator asks: "Answer this prompt"

📥 INPUT:  synapse with prompt text
   
📤 OUTPUT: Model completion / response

🔄 TASK DECOMPOSITION:
   • Could split prompt into chunks
   • Could run multiple models
   • Could retry on failure

💡 THIS IS HEAVIER COMPUTE - different from SN13


┌──────────────────────────────────────────────────────────────────────────────┐
│ SUBNET 18: ZEUS (Prediction Markets)                                        │
└──────────────────────────────────────────────────────────────────────────────┘

QUERY: Prediction
────────────────────────────────────────────────────────────────────────────────
Validator asks: "What's your prediction for X?"

🔄 TASK DECOMPOSITION:
   • Historical data fetch
   • Model inference  
   • Format response

┌──────────────────────────────────────────────────────────────────────────────┐
│ SUBNET 27: COMPUTE (GPU Compute)                                            │
└──────────────────────────────────────────────────────────────────────────────┘

QUERY: Compute Job
────────────────────────────────────────────────────────────────────────────────
Validator asks: "Run this computation"

🔄 TASK DECOMPOSITION:
   • Job parsing (what to run)
   • Resource allocation
   • Execution
   • Result return


═══════════════════════════════════════════════════════════════════════════════

KEY INSIGHT: Each subnet has DIFFERENT query types and task structures!

• SN13 (Data): Simple data retrieval - fetch and return
• SN1 (Apex): Inference - run model, return completion
• SN18 (Zeus): Prediction - analyze, predict, return
• SN27 (Compute): Job execution - run code, return result

The JARVIS ORCHESTRATOR needs to handle EACH differently!

For SN13 (our focus):
1. Listen for GetMinerIndex → build data map
2. Listen for GetDataEntityBucket → route to scraping operators
3. Listen for GetContents → verify data
4. Aggregate results → return to validator

═══════════════════════════════════════════════════════════════════════════════
""")


def simulate_get_index_query():
    """Simulate what a GetMinerIndex query looks like."""

    query = {
        "type": "GetMinerIndex",
        "version": 4,
        "dendrite": {
            "hotkey": "5Dnd2UyzWzKeAi74Z54yBW5rvrx8ppzHpT1JhNvqSankzhzU",
            "uuid": "abc-123-def",
        },
        "timestamp": datetime.now().isoformat(),
    }

    response = {
        "type": "GetMinerIndex",
        "compressed_index_serialized": json.dumps(
            {
                "buckets": [
                    {"source": "X", "time_bucket": 1845, "label": "$BTC", "count": 1500},
                    {"source": "X", "time_bucket": 1845, "label": "$ETH", "count": 800},
                    {"source": "REDDIT", "time_bucket": 1845, "label": "bittensor", "count": 2000},
                    {"source": "X", "time_bucket": 1844, "label": "$BTC", "count": 1200},
                ],
                "total_bytes": 5_500_000,
                "last_updated": "2025-04-06T12:00:00Z",
            },
            indent=2,
        ),
    }

    print("\n📤 EXAMPLE: GetMinerIndex Response")
    print(json.dumps(response, indent=2))


def simulate_get_bucket_query():
    """Simulate what a GetDataEntityBucket query looks like."""

    query = {
        "type": "GetDataEntityBucket",
        "version": 4,
        "data_entity_bucket_id": {"source": "X", "time_bucket_id": 1845, "label": "$BTC"},
        "dendrite": {"hotkey": "5Dnd2UyzWzKeAi74Z54yBW5rvrx8ppzHpT1JhNvqSankzhzU"},
    }

    response = {
        "type": "GetDataEntityBucket",
        "data_entities": [
            {
                "content": "Bitcoin just hit $75K! 🚀",
                "created_at": "2025-04-06T11:30:00Z",
                "source": "X",
                "label": "$BTC",
                "username": "crypto_king",
                "followers": 50000,
            },
            {
                "content": "Analysis: Why $BTC will reach $100K in 2025",
                "created_at": "2025-04-06T11:25:00Z",
                "source": "X",
                "label": "$BTC",
                "username": "btc_analyst",
                "followers": 25000,
            },
        ],
    }

    print("\n📤 EXAMPLE: GetDataEntityBucket Response")
    print(json.dumps(response, indent=2))


def task_decomposition_example():
    """
    Show how we would decompose a task.

    Scenario: Validator asks for bucket (X, 1845, $BTC)
    That's 1500 posts - too many for one agent!
    """

    decomposition = {
        "original_request": {"source": "X", "time_bucket": 1845, "label": "$BTC", "count": 1500},
        "decomposition_strategy": "chunk_by_time",
        "chunks": [
            {
                "chunk_id": 1,
                "source": "X",
                "time_bucket": 1845,
                "label": "$BTC",
                "time_range": "11:00-11:20",
                "estimated_count": 500,
                "assigned_to": "operator_1",
            },
            {
                "chunk_id": 2,
                "source": "X",
                "time_bucket": 1845,
                "label": "$BTC",
                "time_range": "11:20-11:40",
                "estimated_count": 500,
                "assigned_to": "operator_2",
            },
            {
                "chunk_id": 3,
                "source": "X",
                "time_bucket": 1845,
                "label": "$BTC",
                "time_range": "11:40-12:00",
                "estimated_count": 500,
                "assigned_to": "operator_3",
            },
        ],
        "aggregation": "Combine all results → return to validator",
    }

    print("\n📤 EXAMPLE: Task Decomposition")
    print(json.dumps(decomposition, indent=2))


if __name__ == "__main__":
    print_query_analysis()
    simulate_get_index_query()
    simulate_get_bucket_query()
    task_decomposition_example()
