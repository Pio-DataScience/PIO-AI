# Query Processing Flow - Before vs After Fix

## BEFORE (Buggy System)

```
┌─────────────────────────────────────────────────────────────────┐
│ User Query: "what is PIO_ACCOUNTS about?"                       │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ aml_web_chat.py: process_chat_message()                         │
│  - No query understanding                                       │
│  - No context tracking                                          │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ semantic_search()                                                │
│  - Direct embedding: bge_model.encode([query])                  │
│  - No reformulation!                                            │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ ChromaDB: collection.query()                                    │
│  - Query embedding: [0.23, -0.45, 0.67, ...]                   │
│  - n_results: 5 (HARD LIMIT!)                                  │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Results: 2 columns (semantically similar to "about")            │
│  - ACCOUNT_NUMBER                                               │
│  - ACCOUNT_PURPOSE                                              │
│                                                                  │
│ ❌ Missing 363 other columns!                                   │
└─────────────────────────────────────────────────────────────────┘

Follow-up: "no I'm sure there is more check"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ semantic_search()                                                │
│  - Encodes: "no I'm sure there is more check" (literal)        │
│  - NO MEMORY of previous query!                                │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ ChromaDB searches for: "more check"                             │
│ Results: PIO_ACCOUNTS_EXTRA_COL (WRONG TABLE!)                  │
│                                                                  │
│ ❌ Context lost, returns wrong table                            │
└─────────────────────────────────────────────────────────────────┘
```

## AFTER (Fixed System)

```
┌─────────────────────────────────────────────────────────────────┐
│ User Query: "what is PIO_ACCOUNTS about?"                       │
│ Session ID: "user123_session"                                   │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ aml_web_chat.py: process_chat_message(session_id="user123")    │
│  - Routes to semantic_search with session context              │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ semantic_search(query, session_id)                              │
│  - Checks: self.enhanced_search available? ✅ Yes              │
│  - Routes to EnhancedSemanticSearch                            │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ EnhancedSemanticSearch.search()                                 │
│  1. Reformulate query via IntelligentQueryReformulator         │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ IntelligentQueryReformulator.reformulate()                      │
│                                                                  │
│  Step 1: Extract entities                                       │
│   - Table: PIO_ACCOUNTS ✅                                      │
│   - Columns: None                                               │
│                                                                  │
│  Step 2: Check follow-up                                        │
│   - Is follow-up? No (no prior context)                        │
│                                                                  │
│  Step 3: Detect intent                                          │
│   - Pattern match: "what is.*table.*about"                     │
│   - Intent: TABLE_METADATA ✅                                   │
│                                                                  │
│  Step 4: Determine complete metadata needed                     │
│   - Intent is TABLE_METADATA? Yes                              │
│   - Complete metadata: TRUE ✅                                  │
│                                                                  │
│  Step 5: Build reformulated query                               │
│   Original: "what is PIO_ACCOUNTS about?"                      │
│   Reformulated: "table PIO_ACCOUNTS complete metadata           │
│                  structure columns count"                       │
│                                                                  │
│  Step 6: Update context                                         │
│   - last_table = "PIO_ACCOUNTS"                                │
│   - last_intent = TABLE_METADATA                               │
│   - turn_count = 1                                             │
│                                                                  │
│  Return: RetrievalQuery(                                        │
│    original="what is PIO_ACCOUNTS about?",                     │
│    reformulated="table PIO_ACCOUNTS complete metadata...",     │
│    intent=TABLE_METADATA,                                      │
│    target_table="PIO_ACCOUNTS",                                │
│    should_retrieve_complete_metadata=TRUE,                     │
│    confidence=1.0                                              │
│  )                                                              │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ EnhancedSemanticSearch.search() [continued]                     │
│                                                                  │
│  2. Check: should_retrieve_complete_metadata? ✅ TRUE          │
│  3. Route to: _retrieve_complete_table_metadata()             │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ _retrieve_complete_table_metadata("PIO_ACCOUNTS")              │
│                                                                  │
│  Strategy 1: Metadata Filter                                    │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ collection.query(                                         │ │
│  │   where={"table_name": {"$eq": "PIO_ACCOUNTS"}},        │ │
│  │   n_results=500  ← HIGH LIMIT!                          │ │
│  │ )                                                         │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                  │
│  If fails:                                                      │
│  Strategy 2: Enhanced Vector Search                             │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ query = "table PIO_ACCOUNTS all columns complete..."     │ │
│  │ embedding = bge_model.encode([query])                    │ │
│  │ collection.query(                                         │ │
│  │   query_embeddings=[embedding],                          │ │
│  │   n_results=500  ← MUCH HIGHER!                         │ │
│  │ )                                                         │ │
│  │ Filter results to target table                           │ │
│  └──────────────────────────────────────────────────────────┘ │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ ChromaDB Results                                                 │
│  - 365 rows returned (ALL columns!) ✅                          │
│  - ACCOUNT_NUMBER, ACCOUNT_PURPOSE, ACCOUNT_TYPE,              │
│    ACCOUNT_STATUS, ACCOUNT_BALANCE, ... (363 more)             │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Post-process results                                            │
│  - Group by table                                               │
│  - Add metadata                                                 │
│  - Format for response                                          │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Return to semantic_search()                                      │
│  - Log reformulation details                                    │
│  - Convert to standard format                                   │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Response to User                                                 │
│  ✅ ALL 365 columns of PIO_ACCOUNTS                             │
│  ✅ Complete table metadata                                      │
│  ✅ Context saved for next query                                │
└─────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════
Follow-up Query: "no I'm sure there is more check"
Session ID: "user123_session" (SAME SESSION)
═══════════════════════════════════════════════════════════════════

                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ IntelligentQueryReformulator.reformulate()                      │
│                                                                  │
│  Step 1: Check context                                          │
│   - Context exists? ✅ Yes                                      │
│   - last_table = "PIO_ACCOUNTS"                                │
│   - last_intent = TABLE_METADATA                               │
│   - turn_count = 1                                             │
│                                                                  │
│  Step 2: Extract entities                                       │
│   - Table in query? No clear match                             │
│                                                                  │
│  Step 3: Detect follow-up                                       │
│   - Pattern check: "no" ✅, "more" ✅                          │
│   - Has context? ✅ Yes (last_table exists)                    │
│   - Is follow-up: TRUE ✅                                      │
│                                                                  │
│  Step 4: Use context table                                      │
│   - No explicit table → Use last_table                         │
│   - table_name = "PIO_ACCOUNTS" (from context!) ✅            │
│                                                                  │
│  Step 5: Detect intent                                          │
│   - "more" keyword + TABLE_METADATA context                    │
│   - Intent: COLUMN_LIST ✅                                      │
│                                                                  │
│  Step 6: Build reformulated query                               │
│   Original: "no I'm sure there is more check"                  │
│   Reformulated: "table PIO_ACCOUNTS all columns list            │
│                  complete structure"                            │
│                                                                  │
│  Step 7: Update context                                         │
│   - last_table = "PIO_ACCOUNTS" (maintained!) ✅              │
│   - last_intent = COLUMN_LIST                                  │
│   - turn_count = 2                                             │
│                                                                  │
│  Return: RetrievalQuery(                                        │
│    original="no I'm sure there is more check",                 │
│    reformulated="table PIO_ACCOUNTS all columns...",           │
│    intent=COLUMN_LIST,                                         │
│    target_table="PIO_ACCOUNTS",  ← CORRECT TABLE! ✅          │
│    should_retrieve_complete_metadata=TRUE,                     │
│    confidence=1.0                                              │
│  )                                                              │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ _retrieve_complete_table_metadata("PIO_ACCOUNTS")              │
│  - Same table as before ✅                                      │
│  - Retrieves all 365 columns again                             │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Response to User                                                 │
│  ✅ PIO_ACCOUNTS (CORRECT TABLE!)                               │
│  ✅ ALL 365 columns shown again                                 │
│  ✅ Context maintained across turns                             │
└─────────────────────────────────────────────────────────────────┘
```

## Key Differences

| Aspect | Before (Buggy) | After (Fixed) |
|--------|---------------|---------------|
| **Query Understanding** | None - raw query to vector DB | Intent detection, entity extraction |
| **Reformulation** | ❌ No | ✅ Yes - optimized for retrieval |
| **Context Tracking** | ❌ None | ✅ Per-session conversation memory |
| **Follow-up Detection** | ❌ Treats as new query | ✅ Detects and uses previous context |
| **Metadata Retrieval** | Top-K similarity (limit: 5) | Complete retrieval (limit: 500) |
| **Table Resolution** | Random match | Context-aware resolution |
| **Results** | Partial (2/365 columns) | Complete (365/365 columns) |

## Example Scenarios

### Scenario 1: Initial Table Query
```
User: "what is PIO_ACCOUNTS about?"

BEFORE:
  → Direct encoding
  → Top 5 similar: 2 columns
  ❌ RESULT: Incomplete

AFTER:
  → Intent: TABLE_METADATA
  → Complete retrieval
  → All columns: 365
  ✅ RESULT: Complete
```

### Scenario 2: Follow-Up Question
```
Turn 1: "what is PIO_ACCOUNTS about?"
Turn 2: "no I'm sure there is more"

BEFORE:
  Turn 1: PIO_ACCOUNTS (2 columns)
  Turn 2: Searches "more" → PIO_ACCOUNTS_EXTRA_COL
  ❌ RESULT: Wrong table

AFTER:
  Turn 1: PIO_ACCOUNTS (365 columns)
          Context saved: last_table=PIO_ACCOUNTS
  Turn 2: Detected follow-up → Uses PIO_ACCOUNTS
  ✅ RESULT: Correct table
```

### Scenario 3: Ambiguous Query
```
User: "show me more columns"

BEFORE:
  → Searches "show me more columns"
  → Random results
  ❌ RESULT: Unpredictable

AFTER:
  → Checks context: last_table exists?
  → If yes: Uses context table
  → If no: Asks for clarification
  ✅ RESULT: Context-aware
```
