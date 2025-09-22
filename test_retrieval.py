#!/usr/bin/env python3
"""Test retrieval functionality directly."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def test_retrieval():
    """Test the retrieval system step by step."""
    
    print("=== Testing Retrieval System ===")
    
    # Test 1: BM25 search
    print("\n1. Testing BM25 search:")
    try:
        from services.indexer.bm25_index import search_bm25
        results = search_bm25('AI_AML', 'class', top_k=3)
        print(f"   BM25 found {len(results)} results")
        for r in results[:2]:
            print(f"   - {r['path']}: {r['score']:.3f}")
    except Exception as e:
        print(f"   BM25 ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: Query classification
    print("\n2. Testing query classification:")
    try:
        from services.retriever.router import classify_query
        classification = classify_query("Tell me about the AI AML system", "AI_AML")
        print(f"   Query type: {classification.query_type}")
        print(f"   Intent: {classification.intent}")
    except Exception as e:
        print(f"   Classification ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Hybrid retrieval
    print("\n3. Testing hybrid retrieval:")
    try:
        from services.retriever.hybrid import retrieve_with_classification
        hits, classification = retrieve_with_classification("Tell me about the AI AML system", "AI_AML", max_results=5)
        print(f"   Found {len(hits)} hits")
        print(f"   Query type: {classification.query_type}")
        for hit in hits[:3]:
            print(f"   - {hit.source}: {hit.path} (score: {hit.score:.3f})")
    except Exception as e:
        print(f"   Hybrid retrieval ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 4: Full answer pipeline
    print("\n4. Testing full answer pipeline:")
    try:
        from services.llm.answer import answer_with_context
        response = answer_with_context("Tell me about the AI AML system", "AI_AML")
        print(f"   Answer length: {len(response['answer'])}")
        print(f"   Query type: {response['query_type']}")
        print(f"   Citations: {len(response['citations'])}")
        print(f"   Context summary: {response['context_summary'][:100]}...")
    except Exception as e:
        print(f"   Answer pipeline ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_retrieval()