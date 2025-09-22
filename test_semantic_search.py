"""
Semantic Search Test with BGE Embeddings via ChromaDB
"""

import sys
import os
from pathlib import Path
import time

# Add package to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import chromadb
from chromadb.config import Settings

def test_semantic_search():
    """Test semantic search functionality with BGE embeddings."""
    
    print("🔍 Testing Semantic Search with BGE Embeddings via ChromaDB")
    print("=" * 60)
    
    # Initialize ChromaDB client
    warehouse_path = Path(__file__).parent / "warehouse"
    chroma_path = warehouse_path / "vectors"
    
    print(f"📂 ChromaDB Path: {chroma_path}")
    
    try:
        client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        print("✅ ChromaDB client initialized successfully")
        
        # List available collections
        collections = client.list_collections()
        print(f"📊 Found {len(collections)} collections:")
        
        for collection in collections:
            print(f"   - {collection.name}")
            
        if not collections:
            print("❌ No collections found. BGE embeddings may not be generated yet.")
            return
        
        # Test queries
        test_queries = [
            "customer account information",
            "transaction data",
            "financial records",
            "payment details", 
            "account balance",
            "banking data",
            "money transfer",
            "suspicious activity",
            "anti money laundering",
            "risk assessment"
        ]
        
        print(f"\n🎯 Testing {len(test_queries)} semantic queries...")
        
        total_results = 0
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n--- Query {i}: '{query}' ---")
            
            query_results = 0
            best_score = 0.0
            best_match = None
            
            # Search in all collections
            for collection in collections:
                try:
                    coll = client.get_collection(collection.name)
                    
                    # Get collection stats
                    coll_count = coll.count()
                    print(f"  Collection '{collection.name}': {coll_count} embeddings")
                    
                    if coll_count == 0:
                        continue
                    
                    # Perform semantic search
                    start_time = time.time()
                    search_results = coll.query(
                        query_texts=[query],
                        n_results=min(5, coll_count)  # Get top 5 results
                    )
                    search_time = time.time() - start_time
                    
                    if search_results['documents'] and search_results['documents'][0]:
                        num_results = len(search_results['documents'][0])
                        query_results += num_results
                        
                        # Find best match in this collection
                        for j, (doc, distance, metadata) in enumerate(zip(
                            search_results['documents'][0],
                            search_results['distances'][0],
                            search_results['metadatas'][0] or [{}] * len(search_results['documents'][0])
                        )):
                            similarity = 1.0 - distance  # Convert distance to similarity
                            
                            if similarity > best_score:
                                best_score = similarity
                                best_match = {
                                    "content": doc[:200] + "..." if len(doc) > 200 else doc,
                                    "similarity": similarity,
                                    "collection": collection.name,
                                    "metadata": metadata
                                }
                            
                            if j == 0:  # Show first result details
                                print(f"    Top result: {similarity:.3f} similarity")
                                print(f"    Content: {doc[:100]}...")
                    
                    print(f"    Search time: {search_time:.3f}s")
                    
                except Exception as e:
                    print(f"    Error searching {collection.name}: {e}")
            
            total_results += query_results
            
            if best_match:
                print(f"  🏆 Best match (similarity: {best_match['similarity']:.3f}):")
                print(f"     Collection: {best_match['collection']}")
                print(f"     Content: {best_match['content']}")
                if best_match['metadata']:
                    print(f"     Metadata: {best_match['metadata']}")
            else:
                print("  ❌ No results found")
            
            print(f"  Total results: {query_results}")
        
        print(f"\n📈 Summary:")
        print(f"   - Total collections: {len(collections)}")
        print(f"   - Total queries tested: {len(test_queries)}")
        print(f"   - Total results found: {total_results}")
        print(f"   - Average results per query: {total_results / len(test_queries):.1f}")
        
        # Test embedding quality
        print(f"\n🧪 Testing Embedding Quality:")
        
        if collections:
            test_collection = collections[0]
            coll = client.get_collection(test_collection.name)
            
            # Test semantic similarity between related terms
            similar_queries = [
                ("customer", "client"),
                ("account", "banking"),
                ("transaction", "payment"),
                ("money", "financial"),
                ("risk", "suspicious")
            ]
            
            print(f"   Testing semantic similarity in '{test_collection.name}':")
            
            for query1, query2 in similar_queries:
                try:
                    results1 = coll.query(query_texts=[query1], n_results=1)
                    results2 = coll.query(query_texts=[query2], n_results=1)
                    
                    if (results1['distances'] and results1['distances'][0] and 
                        results2['distances'] and results2['distances'][0]):
                        
                        sim1 = 1.0 - results1['distances'][0][0]
                        sim2 = 1.0 - results2['distances'][0][0]
                        avg_similarity = (sim1 + sim2) / 2
                        
                        print(f"     '{query1}' vs '{query2}': {avg_similarity:.3f} avg similarity")
                
                except Exception as e:
                    print(f"     Error testing '{query1}' vs '{query2}': {e}")
        
        print("\n✅ Semantic search testing complete!")
        
    except Exception as e:
        print(f"❌ Error initializing ChromaDB: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_semantic_search()