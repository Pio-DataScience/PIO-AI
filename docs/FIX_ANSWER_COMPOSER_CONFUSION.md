# Fix: Answer Composer Confusion Between Total and Sample Columns

## Problem

The system was giving inconsistent answers about column counts:

**User Query**: "what is the pio_accounts table about?"

**System Response** (inconsistent):
> "It contains 41 columns, including ACT_STRUCTURE, CONSOL_KEY... The table has a total of 325 columns, with 166 columns required for AML compliance. The columns listed above are the complete and only columns..."

**Why This Is Confusing**:
- Says "41 columns"
- Then says "325 columns total"
- Then says "complete and only columns"
- User doesn't know if there are 41 or 325!

## Root Cause

### What Was Happening

1. **Enhanced search returned 42 results**:
   - 41 individual column documents
   - 1 table summary document with total count

2. **Answer composer extracted**:
   ```python
   table_info = {
       "total_columns": 325,      # From table summary
       "aml_column_count": 166,   # From table summary  
       "columns": [... 41 items ...] # From individual results
   }
   ```

3. **LLM received contradictory prompt**:
   ```
   Total columns: 325
   AML required columns: 166
   
   ACTUAL COLUMNS FOUND IN DATABASE (41 columns):
   - ACT_STRUCTURE
   - CONSOL_KEY
   ...
   
   The columns listed above are the COMPLETE and ONLY columns you should reference.
   ```

4. **LLM was confused** because:
   - "Total: 325" but "showing 41" 
   - "COMPLETE and ONLY columns" contradicts "325 total"
   - No clarification that the 41 is a SAMPLE

### The Conflicting Instructions

**Line 324** in answer_composer.py:
```python
context_parts.append(f"\nACTUAL COLUMNS FOUND IN DATABASE ({len(table_info['columns'])} columns):")
```
→ Says "41 columns" with no mention it's a sample

**Line 358**:
```python
7. Be accurate about the total column count - use the exact number provided: {table_info['total_columns']}
```
→ Says "use 325"

**Line 360**:
```python
The columns listed above are the COMPLETE and ONLY columns you should reference.
```
→ Says the 41 columns are "COMPLETE"

**Result**: LLM tried to reconcile these contradictions and ended up confusing the user!

## Solution Applied

### Changed the Prompt to Distinguish Sample vs Total

**File**: `services/agents/answer_composer.py`

**Lines 324-338** - Added sample detection:
```python
# Determine if we're showing a sample or complete list
is_sample = table_info["total_columns"] and table_info["total_columns"] > len(table_info["columns"])

if table_info["columns"]:
    if is_sample:
        context_parts.append(f"\nSAMPLE OF KEY COLUMNS (showing {len(table_info['columns'])} of {table_info['total_columns']} total columns):")
    else:
        context_parts.append(f"\nCOLUMNS IN DATABASE ({len(table_info['columns'])} columns):")
```

**Lines 351-364** - Clarified the relationship:
```python
if table_info["total_columns"]:
    column_count_statement = f"The {table_info['name']} table contains exactly {table_info['total_columns']} columns in total"
    if table_info["aml_column_count"]:
        column_count_statement += f", with {table_info['aml_column_count']} columns required for AML compliance"
    
    if is_sample:
        sample_clarification = f"\n\nIMPORTANT: The {len(table_info['columns'])} columns listed above are a SAMPLE of the most relevant columns from the database. The table has {table_info['total_columns']} columns total, but only this sample is shown here."
```

**Lines 380-386** - Updated instructions:
```python
STRICT INSTRUCTIONS:
1. State the TOTAL number of columns clearly: {table_info['total_columns']} columns
2. If showing a sample, clearly say "Here are some of the key columns:" NOT "all columns" or "complete list"
3. Use ONLY the column names explicitly listed above
4. Be consistent about the total count vs sample count
```

## Expected Behavior Now

### New Response Format

**User**: "what is the pio_accounts table about?"

**System** (clear and consistent):
> "The PIO_ACCOUNTS table is a database table for managing PIO account data. The table contains exactly **325 columns** in total, with **166 columns required for AML compliance**.
>
> Here are some of the key columns from the database (showing 41 of 325 total):
> - ACCOUNT_NUMBER (VARCHAR2 100 Byte): Unique key per each account
> - ACT_STRUCTURE (VARCHAR2 40 Byte): Account structure  
> - CONSOL_KEY (VARCHAR2 100 Byte): Used for T24
> - AC_DESC (VARCHAR2 200 Byte): Description of the account
> ... (and 37 more sample columns)
>
> The complete table has all 325 columns available in the database."

### Key Improvements

1. **Clear total**: "325 columns in total"
2. **Clear sample**: "showing 41 of 325 total"
3. **No contradiction**: Doesn't say the sample is "complete"
4. **Consistent numbers**: 325 is always the total, 41 is always the sample

## Testing

### Test Case 1: Table Overview Query

**Input**: "what is PIO_ACCOUNTS about?"

**Expected**:
- ✅ States total: "325 columns"
- ✅ States sample: "showing 41 of 325"
- ✅ Lists AML count: "166 AML required"
- ✅ No contradiction between numbers

### Test Case 2: All Columns Request

**Input**: "list all columns in PIO_ACCOUNTS"

**Expected**:
- ✅ Still returns sample (41 columns) due to retrieval limits
- ✅ Clarifies: "showing 41 of 325 total columns"
- ✅ Suggests: "The complete table has all 325 columns"

### Test Case 3: Small Table (Complete Results)

**Input**: "what is SMALL_TABLE about?" (table with < 50 columns)

**Expected**:
- ✅ If all columns retrieved: "50 columns (complete list)"
- ✅ No "sample" language
- ✅ Says "COLUMNS IN DATABASE" not "SAMPLE"

## Why The Enhanced Search Is Still Working

The logs show enhanced search IS working:
```
🧠 VectorRetriever: Enhanced search enabled with query reformulation

VectorRetriever: Query reformulated - 
Original: 'what is the pio_accounts table about?' 
→ Reformulated: 'table PIO_ACCOUNTS complete metadata structure columns count' 
Intent: table_metadata 
Complete metadata: True

VectorRetriever: Enhanced search returned 42 results
```

The issue was NOT with retrieval (we got the table summary with correct totals), but with how the answer composer presented those results to the LLM.

## Summary

**Problem**: LLM received contradictory information about column counts
**Root Cause**: Prompt didn't distinguish between "total columns" and "sample shown"  
**Fix**: Clarified prompt to explicitly state when showing a sample vs complete list
**Impact**: Responses will now be clear and consistent about column counts

The fix ensures users understand:
- The TOTAL number of columns in the table
- That they're seeing a SAMPLE of the most relevant columns
- How many columns are in the sample
- No false claims about completeness
