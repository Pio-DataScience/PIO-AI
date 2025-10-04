# Query Reformulation & Memory Integration Fix

## Problem Summary

The AML web chat system had two critical bugs:

### Bug 1: Raw Queries to Vector Database
**Issue**: User queries like "what is PIO_ACCOUNTS table about?" were passed directly to the vector database without any reformulation or intent understanding.

**Example Failure**:
```
User: "what is pio_accounts table about?"
System: Returns only 2 of 365 columns (ACCOUNT_NUMBER, ACCOUNT_PURPOSE)
Problem: Raw query embedding finds semantically similar individual columns, not complete table metadata
```

**Root Cause**: 
```python
# OLD CODE - Line 462 in aml_web_chat.py
query_embedding = self.bge_model.encode([query])[0].tolist()  # Direct encoding
```

### Bug 2: Lost Context on Follow-Up Questions
**Issue**: Follow-up questions had no memory of previous context, treating each query independently.

**Example Failure**:
```
User: "what is pio_accounts table about?"
System: Returns PIO_ACCOUNTS data (partial)

User: "no I'm sure there is more check"
System: Searches for literal phrase "more check" → Returns PIO_ACCOUNTS_EXTRA_COL (wrong table!)
Problem: No memory that we were discussing PIO_ACCOUNTS
```

**Root Cause**: No conversation context tracking between turns.

---

## Solution Architecture

### 1. Intelligent Query Reformulator (`services/agents/query_reformulator.py`)

**Purpose**: Transform natural language queries into optimized retrieval queries with conversation awareness.

**Key Features**:
- **Intent Detection**: Distinguishes between:
  - `TABLE_METADATA` - Complete table information needed
  - `COLUMN_LIST` - All columns request
  - `COLUMN_DETAILS` - Specific column info
  - `TABLE_PURPOSE` - Business purpose
  - `FOLLOW_UP` - Follow-up question (uses context)

- **Entity Extraction**: Identifies table names and column names from queries using regex patterns

- **Conversation Context**: Tracks:
  - Last discussed table
  - Last discussed columns
  - Previous intent
  - Turn count

- **Query Reformulation**: Converts conversational queries to retrieval-optimized queries
  ```python
  # Example transformations:
  "what is pio_accounts about?" 
  → "table PIO_ACCOUNTS complete metadata structure columns count"
  
  "tell me more"  # Follow-up with context
  → "table PIO_ACCOUNTS additional information columns metadata"
  ```

**Critical Classes**:

```python
class QueryIntent(Enum):
    TABLE_METADATA = "table_metadata"  # Needs ALL columns
    COLUMN_LIST = "column_list"        # List all columns
    FOLLOW_UP = "follow_up"            # Uses conversation context
    # ... more intents

class ConversationContext:
    """Maintains state across conversation turns"""
    last_table: Optional[str]
    last_columns: List[str]
    last_intent: Optional[QueryIntent]
    mentioned_entities: List[str]
    
    def is_follow_up(self, query: str) -> bool:
        """Detect if query is a follow-up"""
        follow_up_patterns = [
            r'\b(those|that|these|them|it)\b',
            r'\b(more|other|additional|rest)\b',
            r'\b(no|but|actually|check|sure)\b',
        ]
        # Returns True if patterns match

class IntelligentQueryReformulator:
    """Main reformulation engine"""
    
    def reformulate(self, query: str, session_id: str) -> RetrievalQuery:
        """
        1. Detect if follow-up → Use context table
        2. Extract entities (table/column names)
        3. Detect intent
        4. Determine if complete metadata needed
        5. Build optimized retrieval query
        """
```

---

### 2. Enhanced Semantic Search (`services/retriever/enhanced_semantic_search.py`)

**Purpose**: Wrap ChromaDB search with intelligent retrieval strategies.

**Key Features**:

#### A. Complete Metadata Retrieval
For table-level queries, retrieve ALL columns not just top-K similar ones:

```python
def _retrieve_complete_table_metadata(self, table_name: str) -> List[Dict]:
    """
    Strategy 1: Filter by table name in metadata
    - Query ChromaDB with WHERE clause: table_name = 'PIO_ACCOUNTS'
    - Returns all 365 columns, not just top 5
    
    Strategy 2: Enhanced vector search with high limit
    - Query: "table PIO_ACCOUNTS all columns complete structure"
    - n_results = 500 (not 5!)
    - Filter results to target table
    
    Strategy 3: Fallback to standard search
    """
```

#### B. Intent-Aware Routing
```python
def search(self, query: str, session_id: str) -> Tuple[List[Dict], RetrievalQuery]:
    """
    1. Reformulate query (via IntelligentQueryReformulator)
    2. Check if complete metadata needed
       - Yes → _retrieve_complete_table_metadata()
       - No → _perform_vector_search()
    3. Post-process based on intent
    4. Return results + reformulation details
    """
```

#### C. Post-Processing
```python
def _post_process_results(self, results: List, retrieval_query: RetrievalQuery):
    """
    - TABLE_METADATA intent → Group by table
    - COLUMN_LIST intent → Ensure all columns included
    - Add metadata about grouping
    """
```

---

### 3. Integration into `aml_web_chat.py`

#### Initialization (Lines 404-422):
```python
# After collections loaded, initialize enhanced search
if primary_collection_name and self.bge_model:
    self.enhanced_search = EnhancedSemanticSearch(
        chroma_client=self.chroma_client,
        bge_model=self.bge_model,
        collection_name=primary_collection_name
    )
    print("🧠 Enhanced semantic search initialized with query reformulation")
```

#### Modified Search Method (Lines 478-560):
```python
def _perform_semantic_search(self, query: str, max_results: int, session_id: str):
    """
    NEW BEHAVIOR:
    1. Try enhanced search first (with reformulation)
       - Log reformulation details
       - Return reformulated results
    
    2. Fallback to standard search if enhanced unavailable
       - Direct query encoding (old behavior)
    """
    
    # Try enhanced search
    if self.enhanced_search:
        results, retrieval_query = self.enhanced_search.search(
            query=query,
            max_results=max_results,
            session_id=session_id
        )
        
        # Log reformulation
        self.logger.info(
            f"Original: '{query}' → Reformulated: '{retrieval_query.reformulated_query}'"
        )
        
        return formatted_results
    
    # Fallback to standard search...
```

#### Session Context Passing (Line 776):
```python
# OLD: search_results = self.semantic_search(message, max_results=5)
# NEW: Pass session_id for conversation context
search_results = self.semantic_search(message, max_results=5, session_id=session_id)
```

---

## How It Fixes The Bugs

### Fix for Bug 1: Complete Metadata Retrieval

**Before**:
```
User: "what is pio_accounts about?"
Query encoding: [0.23, -0.45, 0.67, ...]  # Raw query embedding
ChromaDB search: Top 5 similar embeddings
Result: 2 columns (ACCOUNT_NUMBER, ACCOUNT_PURPOSE) - semantically similar to "about"
```

**After**:
```
User: "what is pio_accounts about?"

Step 1 - Intent Detection:
  Intent: TABLE_METADATA
  Target: PIO_ACCOUNTS
  Complete metadata needed: TRUE

Step 2 - Query Reformulation:
  Original: "what is pio_accounts about?"
  Reformulated: "table PIO_ACCOUNTS complete metadata structure columns count"

Step 3 - Complete Metadata Retrieval:
  Strategy: Filter by table_name = 'PIO_ACCOUNTS'
  Limit: 500 (not 5!)
  Result: ALL 365 columns returned

Output: Complete table description with all columns
```

### Fix for Bug 2: Conversation Context

**Before**:
```
Turn 1:
  User: "what is pio_accounts about?"
  Context: {} (empty)
  Search: "pio_accounts"
  
Turn 2:
  User: "no I'm sure there is more check"
  Context: {} (NO MEMORY!)
  Search: "more check" (literal phrase)
  Result: Wrong table (PIO_ACCOUNTS_EXTRA_COL)
```

**After**:
```
Turn 1:
  User: "what is pio_accounts about?"
  
  Reformulator detects:
    - Intent: TABLE_METADATA
    - Table: PIO_ACCOUNTS
    - Follow-up: False
  
  Context updated:
    - last_table = "PIO_ACCOUNTS"
    - last_intent = TABLE_METADATA
    - turn_count = 1

Turn 2:
  User: "no I'm sure there is more check"
  
  Reformulator detects:
    - Follow-up: TRUE (pattern "no" + "more" matches)
    - Uses context table: PIO_ACCOUNTS
    - Intent: FOLLOW_UP or COLUMN_LIST
  
  Query reformulated:
    Original: "no I'm sure there is more check"
    Reformulated: "table PIO_ACCOUNTS additional information columns metadata"
    
  Result: Searches PIO_ACCOUNTS again (correct table!)
```

---

## Flow Diagram

```
User Query: "what is pio_accounts about?"
    |
    v
[IntelligentQueryReformulator]
    |-- Extract entities: table=PIO_ACCOUNTS
    |-- Detect intent: TABLE_METADATA
    |-- Check follow-up: FALSE
    |-- Determine: needs_complete_metadata=TRUE
    |-- Reformulate: "table PIO_ACCOUNTS complete metadata structure columns count"
    |-- Update context: last_table=PIO_ACCOUNTS
    |
    v
[EnhancedSemanticSearch]
    |-- Route by intent: TABLE_METADATA → complete_metadata_retrieval()
    |-- Strategy 1: Filter ChromaDB by table_name="PIO_ACCOUNTS"
    |-- Set limit: 500 (not 5)
    |-- Retrieve: ALL 365 columns
    |-- Post-process: Group by table
    |
    v
[aml_web_chat.py]
    |-- Format results
    |-- Generate LLM response with complete context
    |-- Return: Full table description
    |
    v
User sees: All 365 columns described

---

Follow-up: "no I'm sure there is more check"
    |
    v
[IntelligentQueryReformulator]
    |-- Check context: last_table=PIO_ACCOUNTS exists
    |-- Detect follow-up: TRUE (patterns: "no", "more")
    |-- Use context table: PIO_ACCOUNTS
    |-- Reformulate: "table PIO_ACCOUNTS additional information columns metadata"
    |
    v
[EnhancedSemanticSearch]
    |-- Route: complete_metadata_retrieval(PIO_ACCOUNTS)
    |-- Retrieve: Same table, all columns
    |
    v
User sees: Still PIO_ACCOUNTS (correct!)
```

---

## Key Implementation Details

### 1. Intent Detection Logic
```python
def _detect_intent(self, query: str, is_follow_up: bool) -> QueryIntent:
    # Priority 1: Follow-up detection
    if is_follow_up and self.context.last_intent == QueryIntent.TABLE_METADATA:
        if 'column' in query or 'more' in query:
            return QueryIntent.COLUMN_LIST
        return QueryIntent.FOLLOW_UP
    
    # Priority 2: Pattern matching
    for intent, patterns in self.INTENT_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(query):
                return intent
    
    # Default: TABLE_METADATA
    return QueryIntent.TABLE_METADATA
```

### 2. Complete Metadata Strategy
```python
def _retrieve_complete_table_metadata(self, table_name: str):
    # Strategy 1: Metadata filter (fastest)
    try:
        results = self.collection.query(
            where={"table_name": {"$eq": table_name}},
            n_results=500  # High limit
        )
        if results and len(results['documents'][0]) > 0:
            return self._format_results(results)
    except Exception as e:
        logger.warning("Metadata filter failed, trying enhanced search")
    
    # Strategy 2: Enhanced vector search
    table_query = f"table {table_name} all columns complete structure"
    query_embedding = self.bge_model.encode([table_query])[0].tolist()
    results = self.collection.query(
        query_embeddings=[query_embedding],
        n_results=500  # Much higher than default 5
    )
    
    # Filter to target table only
    return [r for r in results if self._matches_table(r, table_name)]
```

### 3. Context Propagation
```python
# Session ID flows through:
process_chat_message(session_id) 
  → semantic_search(query, session_id)
    → enhanced_search.search(query, session_id)
      → reformulator.reformulate(query, session_id)
        → Uses/updates ConversationContext per session
```

---

## Testing The Fix

### Test Case 1: Complete Metadata
```python
# Query
query = "what is PIO_ACCOUNTS table about?"

# Expected reformulation
reformulated = "table PIO_ACCOUNTS complete metadata structure columns count"

# Expected behavior
assert retrieval_query.intent == QueryIntent.TABLE_METADATA
assert retrieval_query.target_table == "PIO_ACCOUNTS"
assert retrieval_query.should_retrieve_complete_metadata == True

# Expected results
assert len(results) == 365  # All columns, not 2!
assert all(r['metadata']['table_name'] == 'PIO_ACCOUNTS' for r in results)
```

### Test Case 2: Follow-Up Context
```python
# Turn 1
query1 = "what is pio_accounts about?"
results1, rq1 = enhanced_search.search(query1, session_id="test123")
assert rq1.target_table == "PIO_ACCOUNTS"

# Turn 2 - Follow-up
query2 = "no I'm sure there is more"
results2, rq2 = enhanced_search.search(query2, session_id="test123")

# Should use context from Turn 1
assert rq2.target_table == "PIO_ACCOUNTS"  # Same table!
assert rq2.is_follow_up == True
assert rq2.reformulated_query contains "PIO_ACCOUNTS"
```

### Test Case 3: Intent Detection
```python
test_cases = [
    ("what is pio_accounts about?", QueryIntent.TABLE_METADATA),
    ("list all columns in pio_accounts", QueryIntent.COLUMN_LIST),
    ("what is ACCOUNT_NUMBER column?", QueryIntent.COLUMN_DETAILS),
    ("what is the purpose of this table?", QueryIntent.TABLE_PURPOSE),
    ("show me more", QueryIntent.FOLLOW_UP),  # If after another query
]

for query, expected_intent in test_cases:
    rq = reformulator.reformulate(query)
    assert rq.intent == expected_intent
```

---

## Performance Considerations

1. **Caching**: Query embeddings still cached (30min TTL)
2. **Lazy Loading**: Enhanced search only initialized if conditions met
3. **Fallback**: Standard search available if enhanced search fails
4. **Limits**: Complete metadata uses 500 limit, then filters (acceptable for table metadata)

---

## Configuration

Enhanced search is automatically enabled if:
- ✅ ChromaDB client available
- ✅ BGE model loaded
- ✅ Primary collection exists
- ✅ No dimension mismatches

Logs will show:
```
🧠 Enhanced semantic search initialized with query reformulation
   Primary collection: aml_dictionary_metadata_bge
   Features: Intent detection, complete metadata retrieval, conversation context
```

If disabled:
```
ℹ️ Enhanced search disabled (dimension issues or missing components)
```

---

## Summary

**What Changed**:
1. Added `IntelligentQueryReformulator` - Understands intent, reformulates queries, tracks context
2. Added `EnhancedSemanticSearch` - Routes by intent, retrieves complete metadata when needed
3. Modified `aml_web_chat.py` - Integrates enhanced search, passes session context

**What's Fixed**:
1. ✅ Raw queries now reformulated before vector search
2. ✅ Complete table metadata retrieved (all 365 columns, not 2)
3. ✅ Conversation context tracked across turns
4. ✅ Follow-up questions use previous context

**Backward Compatible**:
- ✅ Fallback to standard search if enhanced unavailable
- ✅ No breaking changes to API
- ✅ Existing functionality preserved

**User Experience**:
- 🎯 "what is pio_accounts about?" → Returns ALL 365 columns
- 🔗 "tell me more" → Remembers we're discussing PIO_ACCOUNTS
- 🧠 Understands intent (metadata vs data vs specific columns)
- 📊 Complete information, not partial samples
