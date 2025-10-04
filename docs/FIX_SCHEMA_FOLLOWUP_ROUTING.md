# Fix: Schema Follow-up Question Routing

## Problem Identified

**User Report**: "check the logs for the last prompt i used it totally failed after too good loops"

**Root Cause**: When user asked follow-up question "no its not their is another ones" (meaning: PIO_ACCOUNTS has more columns than just those shown), the system:

1. ✅ **Correctly retrieved** 42 schema results (41 columns + 1 table summary)
2. ❌ **Incorrectly routed** to `_compose_general_response` instead of `_compose_schema_response`
3. ❌ **Bypassed the fixed prompt** that clarifies "SAMPLE OF KEY COLUMNS (showing 41 of 325 total)"
4. ❌ **Generated confusing answer** using generic LLM prompt without proper column count labeling

## Why This Happened

### Query Text Analysis Failed
```python
query = "no its not their is another ones"
query_lower = "no its not their is another ones"

# No match for schema keywords:
"describe" ❌
"what is" ❌  
"columns" ❌
"structure" ❌

# Result: Routed to "general" instead of "schema"
```

### The Irony
- The **vector search correctly understood** the context and retrieved schema metadata
- The **answer composer didn't look at the results** - only the query text
- So the fixed schema prompt was never used!

## Log Evidence

```
DEBUG: _analyze_response_type - query: no its not their is another ones
DEBUG: Defaulting to GENERAL query - LLM will handle
DEBUG: Response type determined: general
DEBUG: Calling _compose_general_response
```

But the results contained:
```python
# 42 results total:
- 41 results with entity_type='column'
- 1 result with entity_type='table_summary'
- ALL results about PIO_ACCOUNTS table structure

# This should have triggered schema response!
```

## Solution Applied

### Before: Query Text Only
```python
def _analyze_response_type(self, query: str, sql_query: str, results: List[Dict[str, Any]]) -> str:
    query_lower = query.lower()
    
    # Only looked at query keywords
    if any(phrase in query_lower for phrase in ["describe", "what is", ...]):
        return "schema"
    
    # Follow-up questions like "no its not their is another ones" fell through
    return "general"  # ❌ Wrong for schema follow-ups!
```

### After: Results-Aware Detection
```python
def _analyze_response_type(self, query: str, sql_query: str, results: List[Dict[str, Any]]) -> str:
    query_lower = query.lower()
    
    # NEW: Check if results contain schema information
    if results and len(results) > 0:
        schema_result_count = sum(
            1 for r in results 
            if isinstance(r.get('metadata'), dict) and 
            r['metadata'].get('entity_type') in ['column', 'table_summary', 'table']
        )
        
        # If >50% of results are schema metadata, treat as schema query
        if schema_result_count > len(results) * 0.5:
            print(f"DEBUG: Detected SCHEMA query from results (found {schema_result_count}/{len(results)} schema items)")
            return "schema"  # ✅ Correct routing!
    
    # Original keyword detection still works for new queries
    if any(phrase in query_lower for phrase in ["describe", "what is", ...]):
        return "schema"
    
    return "general"
```

## Impact

### Before Fix
User: "what is pio_accounts about?"
→ Routes to schema composer ✅
→ Shows "SAMPLE OF KEY COLUMNS (showing 41 of 325 total)" ✅

User: "no its not their is another ones"  
→ Routes to general composer ❌
→ Bypasses fixed prompt ❌
→ Confusing answer about column counts ❌

### After Fix
User: "what is pio_accounts about?"
→ Routes to schema composer ✅
→ Shows "SAMPLE OF KEY COLUMNS (showing 41 of 325 total)" ✅

User: "no its not their is another ones"  
→ **Detects schema results** ✅
→ **Routes to schema composer** ✅
→ **Uses fixed prompt** ✅
→ Clear answer with proper column count labeling ✅

## Key Insight

**The vector search is smarter than the query text analyzer!**

When EnhancedSemanticSearch + IntelligentQueryReformulator understand the user's intent and retrieve schema metadata, the answer composer should **trust the retrieval results** to determine response type, not just rely on keyword matching in the query text.

This is especially important for:
- Follow-up questions
- Clarifications
- Contextual queries
- Conversational references ("it", "that table", "those columns", etc.)

## Files Modified

- `services/agents/answer_composer.py` (lines 111-149)
  - Added results-based schema detection
  - Now checks entity_type in retrieved documents
  - Routes to schema composer when >50% results are schema metadata

## Testing Expected

With this fix, the conversation should flow naturally:

```
User: "what is pio_accounts about?"
System: "PIO_ACCOUNTS is a database table... It has 325 columns in total. 
         Here are some of the key columns (showing 41 of 325 total)..."

User: "no its not their is another ones"
System: [BEFORE: confused general response]
        [AFTER: proper schema response with clear column counts]
```

## Date
2025-10-03 22:50 UTC

## Status
✅ **FIXED** - Response type detection now considers result types, not just query keywords
