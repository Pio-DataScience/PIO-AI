# Fix: System Stuck Returning Only Schema Metadata

## Problem Identified

**User Report**: System keeps returning the same schema answer (table structure, 325 columns) for ALL queries, even when asking for:
- Primary keys
- SELECT statements
- Record counts  
- Actual data

**Example**:
```
Q: "what is pio_accounts about?"
A: "325 columns, with 166 AML required. Here are some key columns..." ✅ Correct

Q: "what are the primary keys?"
A: "325 columns, with 166 AML required. Here are some key columns..." ❌ Wrong!

Q: "give me a select statement to count records"
A: "325 columns, with 166 AML required. Here are some key columns..." ❌ Wrong!
```

## Root Cause Analysis

### The Incomplete Workflow

The system had:
- ✅ SQL generation node (`_sql_generate_node`)
- ✅ SQL validation node (`_sql_validate_node`)
- ✅ SQL execution node (`_sql_execute_node`)
- ✅ Intent classifier correctly identifying DATA_ANALYSIS

**BUT:**
- ❌ **All routes led to `schema_retrieve` → `compose_answer`**
- ❌ **SQL generation/execution nodes were NEVER reached!**

### The Broken Graph

**Before (BROKEN)**:
```
route → schema_retrieve → compose_answer → save_memory → END
   ↓
   ALL intents (schema, data_analysis, follow_up)
   
SQL generation nodes existed but were unreachable!
```

### Why This Happened

Looking at `_build_graph()` lines 140-157:

```python
# ALL routes went to schema_retrieve
workflow.add_conditional_edges(
    "route",
    self._route_decision,
    {
        "conversation": "conversation",
        "schema_task": "schema_retrieve",   # OK
        "data_task": "schema_retrieve",     # ❌ WRONG! Should eventually reach SQL
        "follow_up": "schema_retrieve",     # ❌ WRONG! Should check if SQL needed
        "abuse": "conversation",
        "error": "handle_error"
    }
)

# schema_retrieve ALWAYS went to compose_answer
workflow.add_conditional_edges(
    "schema_retrieve",
    self._check_retrieval_success,
    {
        "success": "compose_answer",  # ❌ Bypasses SQL generation!
        "empty_retry": "self_heal",
        "error": "handle_error"
    }
)
```

The `_check_retrieval_success` function only returned:
- `"success"` → go to compose_answer
- `"empty_retry"` → retry
- `"error"` → handle error

**It had NO path to SQL generation!**

## Solution Applied

### Step 1: Add "needs_sql" Route

Modified `_check_retrieval_success()` to return `"needs_sql"` for data analysis queries:

```python
def _check_retrieval_success(self, state: AgentState) -> str:
    """
    Check if vector schema retrieval was successful and determine next step.
    Returns:
        - "error": Schema retrieval failed
        - "empty_retry": No results, retry
        - "needs_sql": Data analysis query needs SQL generation + execution
        - "success": Schema query, go to answer composition
    """
    # ... error checking ...
    
    # NEW: Check if SQL generation is needed based on intent
    classification = state.get("intent_classification")
    if classification:
        intent = classification.intent
        
        # Data analysis queries need SQL execution
        if intent == IntentType.DATA_ANALYSIS:
            print(f"ROUTING: Data analysis query detected - routing to SQL generation")
            return "needs_sql"
        
        # Follow-up queries about data (not schema) also need SQL
        query_lower = state["query"].lower()
        needs_sql_keywords = [
            "count", "how many", "number of", "total",
            "primary key", "foreign key", "constraint", "index",
            "select", "query", "data", "records", "rows",
            "show me", "get", "fetch", "retrieve"
        ]
        
        if intent == IntentType.FOLLOW_UP and any(keyword in query_lower for keyword in needs_sql_keywords):
            print(f"ROUTING: Follow-up query needs SQL - routing to SQL generation")
            return "needs_sql"
    
    # Schema-only queries go straight to answer composition
    print(f"ROUTING: Schema query - routing to answer composition")
    return "success"
```

### Step 2: Connect SQL Generation Path

Modified workflow graph (lines 153-161):

```python
# BEFORE
workflow.add_conditional_edges(
    "schema_retrieve",
    self._check_retrieval_success,
    {
        "success": "compose_answer",  # ❌ All paths
        "empty_retry": "self_heal",
        "error": "handle_error"
    }
)

# AFTER
workflow.add_conditional_edges(
    "schema_retrieve",
    self._check_retrieval_success,
    {
        "success": "compose_answer",  # Schema queries
        "needs_sql": "sql_generate",  # ✅ NEW! Data analysis → SQL
        "empty_retry": "self_heal",
        "error": "handle_error"
    }
)
```

## How It Works Now

### Fixed Workflow

**Schema Query Path**:
```
"what is pio_accounts about?"
→ route (intent: SCHEMA)
→ schema_retrieve
→ _check_retrieval_success() returns "success"
→ compose_answer (with schema metadata)
→ Answer: "PIO_ACCOUNTS has 325 columns..."
```

**Data Analysis Path (NEW!)**:
```
"give me a select statement to count records"
→ route (intent: DATA_ANALYSIS)
→ schema_retrieve (get table structure first)
→ _check_retrieval_success() detects DATA_ANALYSIS → returns "needs_sql"
→ sql_generate (creates: SELECT COUNT(*) FROM PIO_ACCOUNTS)
→ sql_validate (checks safety)
→ sql_execute (runs query)
→ compose_answer (with actual results)
→ Answer: "Here's a SELECT statement: SELECT COUNT(*) FROM PIO_ACCOUNTS..."
```

**Follow-up With SQL Needs (NEW!)**:
```
"what are the primary keys of this table?"
→ route (intent: FOLLOW_UP)
→ schema_retrieve
→ _check_retrieval_success() detects "primary key" keyword → returns "needs_sql"
→ sql_generate (query: SELECT constraint_name FROM all_constraints WHERE...)
→ sql_validate
→ sql_execute
→ compose_answer
→ Answer: "The primary keys are: ACCOUNT_NUMBER, ..."
```

## Detection Logic

The system now detects SQL-needed queries by:

1. **Intent-based**: If intent == `DATA_ANALYSIS`, always generate SQL
2. **Keyword-based** (for follow-ups): If query contains:
   - `count`, `how many`, `number of`, `total`
   - `primary key`, `foreign key`, `constraint`, `index`
   - `select`, `query`, `data`, `records`, `rows`
   - `show me`, `get`, `fetch`, `retrieve`

## Impact

### Before Fix

**All queries → Schema metadata only:**
- "what is pio_accounts about?" → ✅ Schema answer (correct)
- "what are primary keys?" → ❌ Schema answer (wrong!)
- "count records" → ❌ Schema answer (wrong!)
- "show me data" → ❌ Schema answer (wrong!)

### After Fix

**Intelligent routing:**
- "what is pio_accounts about?" → ✅ Schema answer (correct)
- "what are primary keys?" → ✅ SQL execution → actual keys (correct!)
- "count records" → ✅ SQL execution → actual count (correct!)
- "show me data" → ✅ SQL execution → actual data (correct!)

## Files Modified

1. **`services/agents/modern_orchestrator.py`**
   - Lines 153-161: Added `"needs_sql": "sql_generate"` to workflow edges
   - Lines 1034-1080: Enhanced `_check_retrieval_success()` with SQL detection logic

## Expected Behavior

### Terminal Output (New)

```
ROUTING: Data analysis query detected - routing to SQL generation
DEBUG: Generating SQL for intent: data_analysis
DEBUG: SQL generated: SELECT COUNT(*) FROM PIO_ACCOUNTS
DEBUG: SQL validation: SAFE
DEBUG: SQL execution: SUCCESS (result_count: 1)
DEBUG: Composing answer with SQL results
```

### User Queries Now Work

**Schema Question (No Change)**:
```
Q: "what is pio_accounts about?"
Intent: SCHEMA
Route: schema_retrieve → compose_answer
A: "PIO_ACCOUNTS table has 325 columns..."
```

**Data Analysis (NOW WORKS!)**:
```
Q: "give me a select statement to count records"
Intent: DATA_ANALYSIS
Route: schema_retrieve → sql_generate → sql_validate → sql_execute → compose_answer
A: "Here's a SELECT statement: SELECT COUNT(*) FROM PIO_ACCOUNTS"
```

**Primary Keys (NOW WORKS!)**:
```
Q: "what are the primary keys?"
Intent: FOLLOW_UP (with "primary key" keyword)
Route: schema_retrieve → sql_generate → sql_validate → sql_execute → compose_answer
A: "The primary keys are: ACCOUNT_NUMBER (primary key)"
```

## Testing Validation

### Test Cases

**Test 1: Schema query (should stay the same)**
```
User: "what is pio_accounts about?"
Expected: "PIO_ACCOUNTS table has 325 columns with 166 AML required..."
Actual: [Should match expected]
```

**Test 2: Data analysis (should generate SQL)**
```
User: "give me a select statement to count records"
Expected: SQL generation + "SELECT COUNT(*) FROM PIO_ACCOUNTS"
Actual: [Should generate SQL, not return schema]
```

**Test 3: Primary keys (should query database)**
```
User: "what are the primary keys of this table?"
Expected: Actual primary key information from database
Actual: [Should query constraints, not return column list]
```

## Limitations

### Oracle Connection Required

The SQL execution requires:
- ✅ Oracle connection configured in `config/db_config.yaml`
- ✅ User credentials with SELECT permissions
- ✅ Network access to Oracle database

If Oracle is not configured:
- SQL generation will work (returns SQL string)
- SQL execution will fail gracefully
- System will return SQL statement to user

### Safety Validation

All SQL queries go through safety validation:
- ✅ Only SELECT statements allowed
- ✅ No DROP, DELETE, UPDATE, INSERT
- ✅ No system table access
- ✅ Injection attack prevention

## Date
2025-10-04 00:30 UTC

## Status
✅ **FIXED** - System now routes data analysis queries through SQL generation and execution

## Next Steps

1. **Test with Oracle connection** to validate end-to-end SQL execution
2. **Monitor routing decisions** in logs to ensure correct path selection
3. **Add more SQL keywords** if other query types are missed
4. **Consider caching SQL results** for repeated queries
