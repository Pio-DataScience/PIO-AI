"""
Quick script to check ChromaDB collection metadata and dimensions
"""
import chromadb
from pathlib import Path

# Initialize ChromaDB client
client = chromadb.PersistentClient(path="warehouse/vectors")

# List all collections
collections = client.list_collections()

print("📊 ChromaDB Collection Analysis")
print("=" * 50)

for collection in collections:
    print(f"\n🗂️  Collection: {collection.name}")
    print(f"   📈 Document count: {collection.count()}")
    
    if collection.count() > 0:
        # Get first document to check embedding dimension
        try:
            sample = collection.get(limit=1, include=['embeddings', 'metadatas'])
            if sample['embeddings'] and len(sample['embeddings']) > 0:
                embedding = sample['embeddings'][0]
                if hasattr(embedding, '__len__'):
                    embedding_dim = len(embedding)
                    print(f"   🔢 Embedding dimension: {embedding_dim}")
                
                # Try to get model info from metadata
                if sample['metadatas'] and len(sample['metadatas']) > 0:
                    metadata = sample['metadatas'][0]
                    if metadata and 'model' in metadata:
                        print(f"   🤖 Model used: {metadata['model']}")
                    if metadata and 'dimension' in metadata:
                        print(f"   📏 Reported dimension: {metadata['dimension']}")
                    
            else:
                print(f"   ⚠️  No embeddings found")
        except Exception as e:
            print(f"   ❌ Error checking collection: {e}")
    else:
        print(f"   📭 Collection is empty")

print("\n✅ Analysis complete!")