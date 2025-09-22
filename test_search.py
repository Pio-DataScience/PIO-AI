#!/usr/bin/env python3
"""Test BM25 search with exact project name."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from services.indexer.bm25_index import search_bm25

def test_search():
    """Test BM25 search with different project names."""
    
    # Test with exact project name from index
    print("Testing with 'AI_AML':")
    results = search_bm25('AI_AML', 'class', top_k=3)
    print(f"Found {len(results)} results")
    for r in results:
        print(f"  - {r['path']}: {r['score']:.3f}")
    
    print("\nTesting with 'ai_aml':")
    results = search_bm25('ai_aml', 'class', top_k=3) 
    print(f"Found {len(results)} results")
    for r in results:
        print(f"  - {r['path']}: {r['score']:.3f}")

if __name__ == "__main__":
    test_search()