# How Operators Store & We Retrieve Data

## The Problem You Raised

**How do we know:**
1. How many operators working?
2. Where each stores data?
3. How they send us data after scraping?

## Solution: Shared Database Model

All operators write to ONE shared database:

```
┌─────────────────────────────────────────────────────────────────┐
│                    SHARED DATABASE (SQLite)                     │
│                     (Single Source of Truth)                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│            OPERATOR_1                   │
│   (Pre-scraping X, time 1845-1850)      │
│                                         │
│   ┌──────────────────────────────┐      │
│   │ INSERT INTO posts            │      │
│   │ (source, label, content,      │      │
│   │  timestamp, operator_id)      │      │
│   └──────────────────────────────┘      │
└─────────────────────────────────────────┘
                   │
                   ▼ (writes to same DB)
┌─────────────────────────────────────────┐
│            OPERATOR_2                   │
│   (Pre-scraping Reddit, time 1845-1850) │
│                                         │
│   ┌──────────────────────────────┐      │
│   │ INSERT INTO posts            │      │
│   │ (source, label, content,      │      │
│   │  timestamp, operator_id)      │      │
│   └──────────────────────────────┘      │
└─────────────────────────────────────────┘
                   │
                   ▼ (writes to same DB)
┌─────────────────────────────────────────┐
│            OPERATOR_3                   │
│   (Pre-scraping X, time 1850-1855)      │
│                                         │
│   ┌──────────────────────────────┐      │
│   │ INSERT INTO posts            │      │
│   │ (source, label, content,      │      │
│   │  timestamp, operator_id)      │      │
│   └──────────────────────────────┘      │
└─────────────────────────────────────────┘
```

## Database Schema

```python
# All operators write to this schema

class Post:
    id: int                 # auto-increment
    source: str             # "X" or "REDDIT"
    label: str              # "$BTC", "bittensor", etc.
    content: str            # actual post text
    username: str           # who posted
    created_at: datetime    # when posted
    scraped_at: datetime    # when we scraped it
    operator_id: str        # WHO scraped it (for tracking!)
    time_bucket: int        # hour bucket
    is_verified: bool        # passed quality check?

class DataBucket:
    """Track which buckets we have"""
    bucket_id: str           # "X_1845_$BTC"
    source: str
    label: str
    time_bucket: int
    count: int              # how many posts
    last_updated: datetime
    operator_ids: list      # which operators contributed
```

## How Retrieval Works

When validator queries:

```
VALIDATOR ──► GetDataEntityBucket(X, 1845, $BTC)

ORCHESTRATOR:
  ┌─────────────────────────────┐
  │ SELECT * FROM posts         │
  │ WHERE source = "X"          │
  │   AND time_bucket = 1845   │
  │   AND label = "$BTC"        │
  └─────────────────────────────┘
                    │
                    ▼
  Returns ALL posts from that bucket
  (regardless of which operator scraped them!)
```

**We don't care which operator - we just need the data!**

## How We Track Which Operator Did What

For monitoring/credits, we track:

```python
# Who scraped what (for stats/credits)
operator_stats = {
    "operator_1": {
        "source": "X",
        "time_range": "1845-1850",
        "posts_scraped": 5000,
        "last_updated": "2025-04-07T12:00:00"
    },
    "operator_2": {
        "source": "REDDIT", 
        "time_range": "1845-1850",
        "posts_scraped": 3000,
        "last_updated": "2025-04-07T12:00:00"
    }
}
```

## Summary: Operator Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      OPERATOR DATA MODEL                        │
└─────────────────────────────────────────────────────────────────┘

OPERATOR writes ─────────────────────────────────────────► SHARED DB
    │                                                          │
    │  INSERT INTO posts                                      │
    │  (source, label, content, operator_id, time_bucket)   │
    │                                                          │
    │                                    ORCHESTRATOR reads ──┘
    │                                              │
    │  SELECT * FROM posts                          │
    │  WHERE bucket_id = "X_1845_$BTC"              │
    │                                              │
    │                                              ▼
    │                                    Returns to validator
    │
    └──> We DON'T need to know which operator!
        We just need the data from ANY operator!

─────────────────────────────────────────────────────────────────

KEY POINTS:
1. All operators write to ONE shared database
2. Each post has operator_id (for tracking)
3. Query just looks up by bucket_id
4. Doesn't matter who scraped it!
5. We track stats per operator for credits
```

## How Many Operators?

Based on SN13, typical setup:

| Operator | What it scrapes | Count |
|----------|-----------------|-------|
| Op1 | X posts, time buckets 0-100 | ~5000 posts/hour |
| Op2 | X posts, time buckets 100-200 | ~5000 posts/hour |
| Op3 | Reddit posts, all buckets | ~3000 posts/hour |

**You can have 3-10 operators depending on coverage needed!**

---

Now do you understand how:
- Operators write to shared DB
- We retrieve regardless of who wrote it
- We track who did what for credits

Want me to create code for this?
