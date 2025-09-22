#!/usr/bin/env python3
"""Test different query formats."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def test_query_formats():
    """Test different query formats with BM25."""
    
    print("=== Testing Query Formats ===")
    
    try:
        from services.indexer.bm25_index import search_bm25
        
        # Enhanced query from our system
        enhanced_query = "ai the aml system tell"
        
        # Different query formats to test
        queries_to_test = [
            enhanced_query,                          # Original enhanced
            "ai aml system",                         # Remove stopwords manually
            "ai OR aml OR system",                   # OR query
            "(ai AND aml) OR system",               # Mixed AND/OR
            "ai aml",                               # Just key terms
            "aml system",                           # Fewer terms
            "global_outlier",                       # Known to work
            '"ai aml system"',                      # Phrase query
        ]
        
        for query in queries_to_test:
            results = search_bm25('AI_AML', query, 3)
            print(f"'{query}': {len(results)} results")
            for r in results[:2]:
                print(f"  - {r['path']}: {r['score']:.3f}")
            print()
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_query_formats()