#!/usr/bin/env python3
"""Debug enhancement integration."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def debug_enhancement_integration():
    """Debug enhancement integration step by step."""
    
    print("=== Debugging Enhancement Integration ===")
    
    try:
        from services.retriever.query_enhancement import enhance_query_with_keywords
        from services.indexer.bm25_index import search_bm25
        
        # Test the problematic query
        original_query = "Tell me about the AI AML system"
        
        print(f"1. Original query: '{original_query}'")
        
        # Test enhancement
        enhanced_query = enhance_query_with_keywords(original_query)
        print(f"2. Enhanced query: '{enhanced_query}'")
        
        # Test both queries
        print(f"\n3. Testing original query:")
        original_results = search_bm25('AI_AML', original_query, 5)
        print(f"   Results: {len(original_results)}")
        for r in original_results[:3]:
            print(f"   - {r['path']}: {r['score']:.3f}")
        
        print(f"\n4. Testing enhanced query:")
        enhanced_results = search_bm25('AI_AML', enhanced_query, 5)
        print(f"   Results: {len(enhanced_results)}")
        for r in enhanced_results[:3]:
            print(f"   - {r['path']}: {r['score']:.3f}")
        
        # Test each word in enhanced query individually
        enhanced_words = enhanced_query.split()
        print(f"\n5. Testing individual enhanced words:")
        for word in enhanced_words:
            if word.strip():
                word_results = search_bm25('AI_AML', word.strip(), 3)
                print(f"   '{word}': {len(word_results)} results")
        
        # Test a working query for comparison
        print(f"\n6. Testing known good query 'class':")
        class_results = search_bm25('AI_AML', 'class', 3)
        print(f"   Results: {len(class_results)}")
        for r in class_results[:2]:
            print(f"   - {r['path']}: {r['score']:.3f}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_enhancement_integration()