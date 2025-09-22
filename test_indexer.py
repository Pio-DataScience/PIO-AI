#!/usr/bin/env python3
"""Test the actual BM25Indexer search method directly."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from services.indexer.bm25_index import BM25Indexer

def test_indexer_search():
    """Test the BM25Indexer search method directly."""
    
    indexer = BM25Indexer()
    
    # Test the class method directly
    print("Testing BM25Indexer.search_bm25() method:")
    try:
        results = indexer.search_bm25("AI_AML", "class", top_k=3)
        print(f"Found {len(results)} results")
        for r in results:
            print(f"  - {r.path}: {r.score:.3f}")
    except Exception as e:
        print(f"Error in indexer.search_bm25(): {e}")
        import traceback
        traceback.print_exc()
    
    # Test the convenience function
    print("\nTesting search_bm25() convenience function:")
    try:
        from services.indexer.bm25_index import search_bm25
        results = search_bm25("AI_AML", "class", top_k=3)
        print(f"Found {len(results)} results")
        for r in results:
            print(f"  - {r['path']}: {r['score']:.3f}")
    except Exception as e:
        print(f"Error in search_bm25(): {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_indexer_search()