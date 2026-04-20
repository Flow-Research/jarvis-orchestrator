#!/usr/bin/env python3
"""
SUBNET 13: Data Universe - Query Types & Task Structure

This is the ONLY subnet we're working with.
Focus: Data scraping from X (Twitter) and Reddit.

We need to understand:
1. What queries validators send
2. What each query means
3. How to decompose tasks
4. How to aggregate results
"""

import json
from datetime import datetime


def sn13_query_types():
    """Document SN13 query types."""

    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║        SUBNET 13: DATA UNIVERSE - COMPLETE QUERY GUIDE                      ║
║                                                                              ║
║        Data Scraping from X (Twitter) and Reddit                            ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────────────────────────────┐
│ QUERY #1: GetMinerIndex                                                      │
└──────────────────────────────────────────────────────────────────────────────┘

PURPOSE: Validator wants to know "What data do you have?"

This is the FIRST query validators make to all miners.
They build a map of: which miners have which data.

📥 INPUT (from validator):
    Empty - just asks for your index

📤 RESPONSE (from miner):
    {
        "buckets": [
            {"source": "X", "time_bucket": 1845, "label": "$BTC", "count": 1500},
            {"source": "X", "time_bucket": 1845, "label": "$ETH", "count": 800},
            {"source": "REDDIT", "time_bucket": 1845, "label": "bittensor", "count": 2000},
            {"source": "X", "time_bucket": 1844, "label": "$BTC", "count": 1200}
        ],
        "total_bytes": 5_500_000,
        "last_updated": "2025-04-06T12:00:00Z"
    }

📋 FIELDS EXPLAINED:
    • source: "X" or "REDDIT" 
    • time_bucket: Hour number (1845 = hour 1845 since epoch)
    • label: Topic/crypto symbol (e.g., "$BTC", "$ETH", "bittensor")
    • count: How many posts in this bucket

🔄 TASK DECOMPOSITION:
    → NO work needed! This is just reporting what you already have.
    → Validators use this to decide WHO to query for WHAT data.

💡 WHAT JARVIS DOES:
    → Return list of all data buckets currently stored


┌──────────────────────────────────────────────────────────────────────────────┐
│ QUERY #2: GetDataEntityBucket                                                │
└──────────────────────────────────────────────────────────────────────────────┘

PURPOSE: Validator wants specific data from a bucket.

This is the WORK - validator is asking for actual data!

📥 INPUT (from validator):
    {
        "data_entity_bucket_id": {
            "source": "X",           # "X" or "REDDIT"
            "time_bucket_id": 1845,   # Which hour
            "label": "$BTC"          # What topic
        }
    }

📤 RESPONSE (from miner):
    {
        "data_entities": [
            {
                "content": "Bitcoin just hit $75K! 🚀",
                "created_at": "2025-04-06T11:30:00Z",
                "source": "X",
                "label": "$BTC",
                "username": "crypto_king",
                "followers": 50000,
                "engagement": 1500
            },
            {
                "content": "Analysis: Why $BTC will reach $100K",
                "created_at": "2025-04-06T11:25:00Z",
                "source": "X", 
                "label": "$BTC",
                "username": "btc_analyst",
                "followers": 25000,
                "engagement": 800
            },
            ...more posts...
        ]
    }

🔍 EXAMPLE BUCKET IDs:
    (X, 1845, "$BTC")     = X posts about Bitcoin from hour 1845
    (X, 1845, "$ETH")    = X posts about Ethereum from hour 1845  
    (REDDIT, 1845, "AI") = Reddit posts about AI from hour 1845
    (X, 1844, "$SOL")    = X posts about Solana from hour 1844

🔄 TASK DECOMPOSITION (THIS IS WHERE WE DO WORK):
    
    Original request: Get all X posts about $BTC from hour 1845 (1500 posts)
    
    Strategy 1: Chunk by time (3 operators)
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ Operator 1  │ │ Operator 2  │ │ Operator 3  │
    │ 11:00-11:20│ │ 11:20-11:40│ │ 11:40-12:00│
    │ 500 posts  │ │ 500 posts  │ │ 500 posts  │
    └─────────────┘ └─────────────┘ └─────────────┘
    
    Strategy 2: Chunk by label (if multiple labels)
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ Operator 1  │ │ Operator 2  │ │ Operator 3  │
    │ $BTC only  │ │ $ETH only   │ │ $SOL only   │
    └─────────────┘ └─────────────┘ └─────────────┘
    
    Strategy 3: Chunk by source
    ┌─────────────┐ ┌─────────────┐ 
    │ Operator 1  │ │ Operator 2  │ 
    │ X posts    │ │ Reddit posts│ 
    └─────────────┘ └─────────────┘ 

💡 WHAT JARVIS DOES:
    1. Parse the bucket_id (source, time_bucket, label)
    2. Decompose into chunks
    3. Dispatch to operators (MOCK for now)
    4. Collect results
    5. Return to validator


┌──────────────────────────────────────────────────────────────────────────────┐
│ QUERY #3: GetContentsByBuckets                                               │
└──────────────────────────────────────────────────────────────────────────────┘

PURPOSE: Validator verifies your data is REAL and CORRECT.

This is validation - they want to check your work quality!

📥 INPUT (from validator):
    {
        "bucket_ids": [
            {"source": "X", "time_bucket_id": 1845, "label": "$BTC"},
            {"source": "X", "time_bucket_id": 1845, "label": "$ETH"}
        ],
        "sample_size": 10
    }

📤 RESPONSE (from miner):
    Returns 10 random posts from each bucket for verification:
    {
        "contents": [
            {"bucket_id": "...", "content": "...", "is_verified": true},
            ...10 samples per bucket...
        ]
    }

🔍 VALIDATOR CHECKS:
    • Is the content real? (not fake/generated)
    • Does it match the label? ($BTC content is actually about BTC)
    • Is it from the correct source? (X post is actually from X)
    • Is it unique? (not duplicated across miners)

💡 CREDIBILITY SCORE:
    • If you pass verification: credibility goes UP
    • If you fail: credibility goes DOWN
    • Lower credibility = lower rewards!

🔄 TASK DECOMPOSITION:
    → No work - just return stored data for verification


═══════════════════════════════════════════════════════════════════════════════
                         REWARD MECHANISM SUMMARY
═══════════════════════════════════════════════════════════════════════════════

DATA VALUE = source_weight × desirability_weight × time_scalar × bytes

• source_weight: X=1.0, Reddit=0.8
• desirability_weight: What "Dynamic Desirability" says is valuable
• time_scalar: Fresh data=1.0, 30 days=0.5, older=0
• bytes: How much data

MINER SCORE = Σ(data_value × miner_credibility)

• miner_credibility: From verification checks (0.0 to 1.0)
• Higher credibility = higher rewards!


═══════════════════════════════════════════════════════════════════════════════
                         COMPLETE TASK FLOW (SN13)
═══════════════════════════════════════════════════════════════════════════════

VALIDATOR                              JARVIS ORCHESTRATOR
    │                                        │
    │──── 1. GetMinerIndex ─────────────────►│ "What do you have?"
    │◄─────── Return bucket list ─────────────│ (no work done)
    │                                        │
    │                                        │ Build data map
    │                                        │
    │──── 2. GetDataEntityBucket ────────────►│ "Give me X $BTC posts"
    │◄─────── [wait for operators] ──────────│
    │                                        │
    │                                   ┌─────┴─────┐
    │                                   │           │
    │                                   ▼           ▼
    │                              ┌─────────┐ ┌─────────┐
    │                              │Op 1     │ │Op 2     │
    │                              │Scrapes  │ │Scrapes  │
    │                              │11:00-20 │ │11:20-40 │
    │                              └────┬────┘ └────┬────┘
    │                                   │           │
    │                                   └─────┬─────┘
    │                                         │
    │◄──── 3. Return data ────────────────────┘
    │                                        │
    │      (VALIDATOR VERIFIES)               │
    │                                        │
    │──── 4. GetContents ────────────────────►│ "Let me verify"
    │◄─────── Return samples ────────────────│
    │                                        │
    │      (UPDATE CREDIBILITY)               │
    │                                        │
    │──── 5. Set Weights ────────────────────►│ Chain: TAO distribution
    │         (every epoch)                   │


═══════════════════════════════════════════════════════════════════════════════
""")


def task_decomposition_examples():
    """Show concrete task decomposition examples."""

    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    TASK DECOMPOSITION EXAMPLES                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

EXAMPLE 1: Small bucket (100 posts)
────────────────────────────────────────────────────────────────────────────────
Request: GetDataEntityBucket(source=X, time_bucket=1845, label="$BTC", count=100)

Decomposition: Single task, no split needed
    → One operator scrapes 100 posts
    → Return directly to validator


EXAMPLE 2: Medium bucket (1000 posts)
────────────────────────────────────────────────────────────────────────────────
Request: GetDataEntityBucket(source=X, time_bucket=1845, label="$BTC", count=1000)

Decomposition: Split by time chunks
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ Operator 1  │ │ Operator 2  │ │ Operator 3  │ │ Operator 4  │
    │ 11:00-11:15│ │ 11:15-11:30│ │ 11:30-11:45│ │ 11:45-12:00│
    │ 250 posts   │ │ 250 posts   │ │ 250 posts   │ │ 250 posts   │
    └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
    
    Merge all results → Return to validator


EXAMPLE 3: Large bucket (10000 posts)
────────────────────────────────────────────────────────────────────────────────
Request: GetDataEntityBucket(source=X, time_bucket=1845, label="$BTC", count=10000)

Decomposition: Split by time + parallel execution
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ Chunk 1     │ │ Chunk 2     │ │ Chunk 3     │ │ Chunk 4     │
    │ 2500 posts  │ │ 2500 posts  │ │ 2500 posts  │ │ 2500 posts  │
    │ Time: 11:00 │ │ Time: 11:20 │ │ Time: 11:40 │ │ Time: 12:00 │
    │ Operator: 1 │ │ Operator: 2 │ │ Operator: 3 │ │ Operator: 4 │
    └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
    
    Merge all results → Return to validator


EXAMPLE 4: Multi-source request
────────────────────────────────────────────────────────────────────────────────
Request: GetDataEntityBucket(source=MIXED, time_bucket=1845, label="$BTC")

Decomposition: Split by source first
    ┌─────────────┐ ┌─────────────┐ 
    │ Operator 1  │ │ Operator 2  │ 
    │ X posts     │ │ Reddit posts│ 
    │ 5000       │ │ 5000        │ 
    └─────────────┘ └─────────────┘ 
    
    Merge all results → Return to validator


╔══════════════════════════════════════════════════════════════════════════════╗
║                    RESULT AGGREGATION RULES                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

1. Collect all results from operators
2. Deduplicate (remove same posts from different operators)
3. Sort by engagement/timestamp (optional)
4. Format to match protocol
5. Return to validator

MERGE LOGIC:
    results = []
    for operator_result in operator_results:
        for post in operator_result:
            if post not in results:
                results.append(post)
    
    return results
""")


def run_mock_demo():
    """Run a mock demonstration."""

    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                         MOCK QUERY DEMO                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

    # Example 1: GetMinerIndex
    print("\n📥 QUERY 1: GetMinerIndex (from validator)")
    print("=" * 60)
    query = {"type": "GetMinerIndex", "version": 4, "dendrite": {"hotkey": "5DVk...validator"}}
    print(json.dumps(query, indent=2))

    print("\n📤 RESPONSE: What data we have")
    print("=" * 60)
    response = {
        "compressed_index": {
            "buckets": [
                {"source": "X", "time_bucket": 1845, "label": "$BTC", "count": 1500},
                {"source": "X", "time_bucket": 1845, "label": "$ETH", "count": 800},
                {"source": "REDDIT", "time_bucket": 1845, "label": "bittensor", "count": 2000},
            ],
            "total_bytes": 4_300_000,
        }
    }
    print(json.dumps(response, indent=2))

    # Example 2: GetDataEntityBucket
    print("\n\n📥 QUERY 2: GetDataEntityBucket (from validator)")
    print("=" * 60)
    query = {
        "type": "GetDataEntityBucket",
        "version": 4,
        "data_entity_bucket_id": {"source": "X", "time_bucket_id": 1845, "label": "$BTC"},
    }
    print(json.dumps(query, indent=2))

    print("\n📤 RESPONSE: Data after operator work")
    print("=" * 60)
    response = {
        "data_entities": [
            {
                "content": "Bitcoin to the moon!",
                "source": "X",
                "created_at": "2025-04-06T11:30:00Z",
            },
            {"content": "$BTC analysis", "source": "X", "created_at": "2025-04-06T11:25:00Z"},
            {
                "content": "Why I'm bullish on BTC",
                "source": "X",
                "created_at": "2025-04-06T11:20:00Z",
            },
        ]
    }
    print(json.dumps(response, indent=2))

    print("\n\n" + "=" * 60)
    print("✅ This is how SN13 queries work!")
    print("=" * 60)


if __name__ == "__main__":
    sn13_query_types()
    task_decomposition_examples()
    run_mock_demo()
