# Data Flow: Where Does Data Go?

## Two Types of Data Flow in SN13:

### 1. INTERNAL (For Fast Lookup)
```
Operators → SHARED SQLITE DB → Our Orchestrator (fast lookup)
```
- Internal database for quick retrieval
- When validator queries, we lookup here first

### 2. EXTERNAL (For Validator Verification)
```
Operators → S3 → HuggingFace (public) → Validators can verify
```
- Data uploaded to S3 (public bucket)
- Synced to HuggingFace 
- Validators can download and verify our data is real!

---

## The Real SN13 Flow:

```
VALIDATOR                       ORCHESTRATOR                      EXTERNAL
   │                                │                                │
   │                                │  ┌────────────────────────┐  │
   │                                │  │ Operators continuously │  │
   │                                │  │ scrape & write to DB   │  │
   │                                │  │ + upload to S3        │  │
   │                                │  └───────────┬────────────┘  │
   │                                │              │               │
   │  GetDataEntityBucket          │              ▼               │
   │──────────────────────────────►│     ┌──────────────┐         │
   │                                │     │ SHARED DB    │         │
   │                                │     │ (SQLite)     │         │
   │                                │     └──────┬───────┘         │
   │                                │            │                 │
   │                                │   LOOKUP ──┤                 │
   │                                │            │                 │
   │◄───────────────────────────────│   RETURN DATA              │
   │                                │            │                 │
   │                                │            ▼                 │
   │                                │   ┌──────────────┐           │
   │                                │   │ UPLOAD TO S3│           │
   │                                │   │ (for verify)│           │
   │                                │   └──────────────┘           │
   │                                │            │                 │
   │                                │            ▼                 │
   │                                │   ┌──────────────┐           │
   │                                │   │ HuggingFace  │           │
   │                                │   │ (public)     │           │
   │                                │   └──────────────┘           │
```

---

## Do WE Need S3/HuggingFace?

For **testnet/demo** - NO, we can skip this!

For **production** - YES, because:

1. **Validators verify** - They download from S3 to check data is real
2. **Credibility** - If we don't upload, validators think data is fake
3. **Trust** - Public storage = verifiable = higher scores

---

## Our Simplified Flow (For Now):

```
┌─────────────────────────────────────────────────────────────────┐
│                    SIMPLIFIED (NO S3)                           │
└─────────────────────────────────────────────────────────────────┘

VALIDATOR ──► QUERY ──► LOOKUP IN SQLite ──► RETURN DATA

Operators write to SQLite DB only
We skip S3 upload for now (can add later)

This works for learning/testing!
For real money - need S3 upload for verification
```

---

## Summary:

| What | Where | Why |
|------|-------|-----|
| **Our lookup** | SQLite DB | Fast when queried |
| **Validator verification** | S3/HuggingFace | Proves data is real |
| **For now** | SQLite only | Learn first |
| **For production** | Add S3 upload | Required for scores |

---

So to answer your question:

**YES** - In real SN13, data goes to S3/HuggingFace for validators to verify.

**For now** - We just store in SQLite and return directly.

**The flow is:**
- Validator queries → We lookup in DB → Return data
- ALSO we upload to S3 (in background) so validator can verify later

Want me to update the workflow to include this S3 upload part?
