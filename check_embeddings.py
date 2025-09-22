#!/usr/bin/env python3
"""Check ChromaDB embedding statistics after running 42_embed_aml_catalog.py"""

import os
import sys
import chromadb
from chromadb.config import Settings

def main():
    """Check ChromaDB collection statistics."""
    persist_directory = "warehouse/vectors"
    
    if not os.path.exists(persist_directory):
        print(f"Vector store directory not found: {persist_directory}")
        return
    
    try:
        # Initialize ChromaDB client
        client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Get all collections
        collections = client.list_collections()
        
        print("ChromaDB Collection Statistics:")
        print("=" * 40)
        
        total_embeddings = 0
        for collection in collections:
            count = collection.count()
            total_embeddings += count
            print(f"  {collection.name}: {count} embeddings")
        
        print("-" * 40)
        print(f"Total embeddings: {total_embeddings}")
        
        # If we have table embeddings, show a sample
        for collection in collections:
            if "tables" in collection.name and collection.count() > 0:
                print(f"\nSample from {collection.name}:")
                results = collection.peek(limit=3)
                for i, (doc_id, document, metadata) in enumerate(zip(
                    results['ids'],
                    results['documents'], 
                    results['metadatas']
                )):
                    print(f"  [{i+1}] ID: {doc_id}")
                    print(f"      Text: {document[:100]}...")
                    print(f"      Metadata: {metadata}")
                break
                
    except Exception as e:
        print(f"Error checking ChromaDB: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())