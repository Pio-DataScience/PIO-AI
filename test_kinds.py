#!/usr/bin/env python3
"""Test BM25 result kinds."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def test_bm25_kinds():
    """Test what kinds BM25 returns."""
    
    print("=== Testing BM25 Result Kinds ===")
    
    try:
        from services.indexer.bm25_index import search_bm25
        
        # Test a known working query
        results = search_bm25('AI_AML', 'class', 5)
        
        print(f"Found {len(results)} results for 'class':")
        for i, result in enumerate(results):
            print(f"  {i}: {result['path']}")
            print(f"     kind: '{result.get('kind', 'MISSING')}' (type: {type(result.get('kind'))})")
            print(f"     project: '{result.get('project', 'MISSING')}'")
            print(f"     score: {result.get('score', 'MISSING')}")
            print(f"     snippet: {result.get('snippet', 'MISSING')[:50]}...")
            print()
    
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_bm25_kinds()