#!/usr/bin/env python3
"""Test Similarity project search."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def test_similarity_search():
    """Test search in Similarity project."""
    
    print("=== Testing Similarity Project Search ===")
    
    try:
        from services.indexer.bm25_index import search_bm25
        
        # Test searches
        queries = [
            'queue',
            'bulk_all_customers',
            'delta_similarity_translator',
            'class'
        ]
        
        for query in queries:
            results = search_bm25('Similarity', query, 5)
            print(f"\n'{query}': {len(results)} results")
            for r in results[:3]:
                print(f"  - {r['path']}: {r['score']:.3f}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_similarity_search()