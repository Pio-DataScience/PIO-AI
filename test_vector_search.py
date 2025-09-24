"""
Quick test of vector search for PIO_ACCOUNTS
"""
import chromadb
from sentence_transformers import SentenceTransformer

# Initialize BGE model
print("🔍 Loading BGE model...")
model = SentenceTransformer('BAAI/bge-large-en-v1.5')

# Initialize ChromaDB
client = chromadb.PersistentClient(path="warehouse/vectors")

# Test both collections
collections = ["aml_tables", "aml_dictionary_metadata_bge"]
query = "PIO_ACCOUNTS table details information"

print(f"\n🔍 Searching for: '{query}'")
print("=" * 50)

query_embedding = model.encode([query])[0].tolist()

for collection_name in collections:
    try:
        collection = client.get_collection(collection_name)
        print(f"\n📊 Collection: {collection_name} ({collection.count()} docs)")
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=5
        )
        
        if results['documents'] and results['documents'][0]:
            for i, (doc, distance, metadata) in enumerate(zip(
                results['documents'][0][:3],
                results['distances'][0][:3], 
                results['metadatas'][0][:3] or [{}] * 3
            )):
                similarity = 1 - distance
                print(f"  {i+1}. Similarity: {similarity:.3f}")
                print(f"     Preview: {doc[:100]}...")
                if metadata:
                    print(f"     Metadata: {metadata}")
                print()
        else:
            print("  No results found")
            
    except Exception as e:
        print(f"  ❌ Error: {e}")

print("✅ Vector search test complete!")