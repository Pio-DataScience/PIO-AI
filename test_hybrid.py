#!/usr/bin/env python3
"""Test hybrid retriever directly."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def test_hybrid_retriever():
    """Test hybrid retriever directly."""
    
    print("=== Testing Hybrid Retriever ===")
    
    try:
        from services.retriever.hybrid import HybridRetriever
        from services.retriever.router import classify_query
        
        retriever = HybridRetriever()
        
        # Test the natural language query
        query = "Tell me about the AI AML system"
        print(f"\nQuery: {query}")
        
        # Classify the query
        classification = classify_query(query)
        print(f"Classification: {classification.query_type} (confidence: {classification.confidence})")
        
        # Test _search_bm25_code directly
        print(f"\n1. Testing _search_bm25_code:")
        bm25_hits = retriever._search_bm25_code('AI_AML', query, 5)
        print(f"   Found {len(bm25_hits)} BM25 code hits")
        for hit in bm25_hits:
            print(f"   - {hit.path}: {hit.score:.3f}")
        
        # Test full retrieve
        print(f"\n2. Testing full retrieve:")
        hits = retriever.retrieve(query, 'AI_AML', max_results=5)
        print(f"   Found {len(hits)} total hits")
        for hit in hits:
            print(f"   - {hit.path}: {hit.score:.3f} (source: {hit.source})")
            
        # Test with the specific global_outlier query
        outlier_query = "give me an overview about the AML outlier detection phases like the global_outlier.py file"
        print(f"\n3. Testing outlier query: {outlier_query}")
        
        outlier_classification = classify_query(outlier_query)
        print(f"   Classification: {outlier_classification.query_type} (confidence: {outlier_classification.confidence})")
        
        outlier_hits = retriever.retrieve(outlier_query, 'AI_AML', max_results=5)
        print(f"   Found {len(outlier_hits)} hits")
        for hit in outlier_hits:
            print(f"   - {hit.path}: {hit.score:.3f} (source: {hit.source})")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_hybrid_retriever()