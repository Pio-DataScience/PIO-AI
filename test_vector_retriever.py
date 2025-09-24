"""
Test the VectorOnlyRetriever semantic_search method directly
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from services.agents.langgraph_orchestrator import VectorOnlyRetriever

async def test_vector_retriever():
    """Test VectorOnlyRetriever directly."""
    print("🔍 Testing VectorOnlyRetriever...")
    
    # Initialize retriever
    retriever = VectorOnlyRetriever()
    
    # Test semantic search
    query = "tell me about this table in details PIO_ACCOUNTS"
    print(f"\n📝 Query: '{query}'")
    
    results = retriever.semantic_search(query, max_results=5)
    
    print(f"\n✅ Found {len(results)} results:")
    print("=" * 50)
    
    for i, result in enumerate(results[:3]):
        print(f"\n{i+1}. Collection: {result.get('collection', 'unknown')}")
        print(f"   Similarity: {result.get('similarity_score', 0):.3f}")
        print(f"   Content preview: {result.get('content', '')[:200]}...")
        if 'metadata' in result:
            print(f"   Metadata: {result['metadata']}")

if __name__ == "__main__":
    asyncio.run(test_vector_retriever())