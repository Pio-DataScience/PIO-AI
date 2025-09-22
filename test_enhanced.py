#!/usr/bin/env python3
"""Test enhanced query processing."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def test_enhanced_query():
    """Test enhanced query processing."""
    
    print("=== Testing Enhanced Query Processing ===")
    
    # Test keyword extraction
    print("\n1. Testing keyword extraction:")
    try:
        from services.retriever.query_enhancement import enhance_query_with_keywords
        
        test_query = "give me an overview about the AML outlier detection phases like the global_outlier.py file"
        enhanced = enhance_query_with_keywords(test_query)
        print(f"Original: {test_query}")
        print(f"Enhanced: {enhanced}")
        
    except Exception as e:
        print(f"   Enhancement ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Test enhanced BM25 search
    print("\n2. Testing enhanced BM25 search:")
    try:
        from services.indexer.bm25_index import search_bm25
        from services.retriever.query_enhancement import enhance_query_with_keywords
        
        original_query = "Tell me about the AI AML system"
        enhanced_query = enhance_query_with_keywords(original_query)
        
        print(f"Original query: {original_query}")
        print(f"Enhanced query: {enhanced_query}")
        
        original_results = search_bm25('AI_AML', original_query, 3)
        enhanced_results = search_bm25('AI_AML', enhanced_query, 3)
        
        print(f"Original results: {len(original_results)}")
        print(f"Enhanced results: {len(enhanced_results)}")
        
        for r in enhanced_results:
            print(f"  - {r['path']}: {r['score']:.3f}")
            
    except Exception as e:
        print(f"   Enhanced search ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Test global_outlier specific query
    print("\n3. Testing global_outlier query:")
    try:
        from services.retriever.query_enhancement import enhance_query_with_keywords
        from services.indexer.bm25_index import search_bm25
        
        query = "give me an overview about the AML outlier detection phases like the global_outlier.py file"
        enhanced = enhance_query_with_keywords(query)
        results = search_bm25('AI_AML', enhanced, 5)
        
        print(f"Query: {query}")
        print(f"Enhanced: {enhanced}")
        print(f"Results: {len(results)}")
        
        for r in results:
            print(f"  - {r['path']}: {r['score']:.3f}")
            
    except Exception as e:
        print(f"   Global outlier test ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_enhanced_query()