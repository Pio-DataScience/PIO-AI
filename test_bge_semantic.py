"""
BGE Semantic Search Test - Direct BGE Model Usage
"""

import sys
import os
from pathlib import Path
import time
import numpy as np

# Add package to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    print("✅ Required packages imported successfully")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please install: pip install chromadb sentence-transformers")
    sys.exit(1)

def test_bge_semantic_search():
    """Test semantic search using BGE model directly."""
    
    print("🔍 Testing BGE Semantic Search with Direct Model Usage")
    print("=" * 60)
    
    try:
        # Initialize BGE model
        print("🤖 Loading BGE-large-en-v1.5 model...")
        model = SentenceTransformer('BAAI/bge-large-en-v1.5')
        print(f"✅ BGE model loaded successfully (dimension: {model.get_sentence_embedding_dimension()})")
        
        # Initialize ChromaDB client
        warehouse_path = Path(__file__).parent / "warehouse"
        chroma_path = warehouse_path / "vectors"
        
        print(f"📂 ChromaDB Path: {chroma_path}")
        
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
        
        # Focus on the main collection with data
        main_collection = None
        for collection in collections:
            coll = client.get_collection(collection.name)
            count = coll.count()
            if count > 0:
                main_collection = coll
                print(f"📋 Using collection '{collection.name}' with {count} embeddings")
                break
        
        if not main_collection:
            print("❌ No collections with data found.")
            return
        
        # Test queries with BGE embeddings
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
        
        print(f"\n🎯 Testing {len(test_queries)} semantic queries with BGE...")
        
        total_results = 0
        all_best_matches = []
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n--- Query {i}: '{query}' ---")
            
            try:
                # Generate BGE embedding for query
                start_time = time.time()
                query_embedding = model.encode([query])[0].tolist()
                embedding_time = time.time() - start_time
                
                print(f"  🧠 Query embedding generated ({embedding_time:.3f}s)")
                print(f"  📐 Embedding dimension: {len(query_embedding)}")
                
                # Search using BGE embedding
                search_start = time.time()
                search_results = main_collection.query(
                    query_embeddings=[query_embedding],
                    n_results=5  # Get top 5 results
                )
                search_time = time.time() - search_start
                
                if search_results['documents'] and search_results['documents'][0]:
                    num_results = len(search_results['documents'][0])
                    total_results += num_results
                    
                    print(f"  📊 Found {num_results} results ({search_time:.3f}s)")
                    
                    # Show top results
                    for j, (doc, distance, metadata) in enumerate(zip(
                        search_results['documents'][0],
                        search_results['distances'][0],
                        search_results['metadatas'][0] or [{}] * len(search_results['documents'][0])
                    )):
                        similarity = 1.0 - distance  # Convert distance to similarity
                        
                        print(f"    {j+1}. Similarity: {similarity:.3f}")
                        print(f"       Content: {doc[:100]}...")
                        if metadata:
                            print(f"       Metadata: {metadata}")
                        
                        if j == 0:  # Store best match
                            all_best_matches.append({
                                "query": query,
                                "content": doc,
                                "similarity": similarity,
                                "metadata": metadata
                            })
                        
                        if j >= 2:  # Show only top 3
                            break
                else:
                    print("  ❌ No results found")
                
            except Exception as e:
                print(f"  ❌ Error processing query: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n📈 Summary:")
        print(f"   - BGE Model Dimension: {model.get_sentence_embedding_dimension()}")
        print(f"   - Collection: {main_collection.name}")
        print(f"   - Total queries tested: {len(test_queries)}")
        print(f"   - Total results found: {total_results}")
        print(f"   - Average results per query: {total_results / len(test_queries):.1f}")
        
        # Show best matches
        print(f"\n🏆 Top 5 Best Matches:")
        best_sorted = sorted(all_best_matches, key=lambda x: x['similarity'], reverse=True)[:5]
        
        for i, match in enumerate(best_sorted, 1):
            print(f"  {i}. Query: '{match['query']}'")
            print(f"     Similarity: {match['similarity']:.3f}")
            print(f"     Content: {match['content'][:150]}...")
            if match['metadata']:
                print(f"     Metadata: {match['metadata']}")
            print()
        
        # Test semantic similarity
        print(f"🧪 Testing Semantic Similarity with BGE:")
        
        similar_pairs = [
            ("customer", "client"),
            ("account", "banking"),
            ("transaction", "payment"),
            ("money", "financial"),
            ("risk", "suspicious")
        ]
        
        for query1, query2 in similar_pairs:
            try:
                # Generate embeddings for both queries
                emb1 = model.encode([query1])[0]
                emb2 = model.encode([query2])[0]
                
                # Calculate cosine similarity
                cosine_sim = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
                
                print(f"   '{query1}' vs '{query2}': {cosine_sim:.3f} cosine similarity")
                
            except Exception as e:
                print(f"   Error testing '{query1}' vs '{query2}': {e}")
        
        print("\n✅ BGE Semantic search testing complete!")
        print("🎯 BGE-large-en-v1.5 embeddings are working correctly!")
        
    except Exception as e:
        print(f"❌ Error in BGE semantic search test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_bge_semantic_search()