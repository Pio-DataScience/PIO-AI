"""
Check if Oracle database embeddings collection exists in ChromaDB
"""

import chromadb
from chromadb.config import Settings
from pathlib import Path

def check_oracle_embeddings():
    # Connect to ChromaDB
    warehouse_path = Path(__file__).parent.parent / "warehouse"
    chroma_path = warehouse_path / "vectors"
    
    client = chromadb.PersistentClient(
        path=str(chroma_path),
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=True
        )
    )
    
    print("ChromaDB Collections:")
    collections = client.list_collections()
    for collection in collections:
        print(f"- {collection.name}")
        
        # Check if this is the Oracle embeddings collection
        if "aml_dictionary_metadata" in collection.name:
            print(f"  FOUND ORACLE EMBEDDINGS COLLECTION: {collection.name}")
            print(f"  Items count: {collection.count()}")
            
            # Search for NEW_OPENED_ACC specifically
            results = collection.query(
                query_texts=["NEW_OPENED_ACC column"],
                n_results=5
            )
            
            print(f"  Search results for 'NEW_OPENED_ACC column': {len(results['documents'][0])} results")
            
            if results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i]
                    print(f"    Result {i+1}: {metadata.get('full_column_name', metadata.get('table_name', 'Unknown'))}")
                    if 'NEW_OPENED_ACC' in doc:
                        print(f"      FOUND NEW_OPENED_ACC IN DOCUMENT!")
                        print(f"      Content: {doc[:200]}")
            else:
                print("    No results found for NEW_OPENED_ACC")
            
            # Also search for the table that might contain it
            table_results = collection.query(
                query_texts=["PIO_ACCOUNTS table columns"],
                n_results=3
            )
            
            print(f"  PIO_ACCOUNTS search results: {len(table_results['documents'][0])} results")
            if table_results['documents'][0]:
                for i, doc in enumerate(table_results['documents'][0]):
                    if 'NEW_OPENED_ACC' in doc:
                        print(f"    FOUND NEW_OPENED_ACC in PIO_ACCOUNTS search!")
                        print(f"    Content: {doc[:300]}")

if __name__ == "__main__":
    check_oracle_embeddings()