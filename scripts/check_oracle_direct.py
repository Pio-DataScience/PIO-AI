"""
Check Oracle database embeddings collection with proper embedding handling
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
    
    oracle_collection = None
    for collection in collections:
        print(f"- {collection.name} (count: {collection.count()})")
        if "aml_dictionary_metadata" in collection.name:
            oracle_collection = collection
            print(f"  >>> ORACLE EMBEDDINGS COLLECTION FOUND: {collection.name}")
    
    if not oracle_collection:
        print("No Oracle embeddings collection found!")
        return
    
    # Get a few documents to see the structure
    print(f"\nAnalyzing Oracle collection: {oracle_collection.name}")
    print(f"Total items: {oracle_collection.count()}")
    
    # Get some sample documents
    all_docs = oracle_collection.get()
    
    print(f"\nSample documents structure:")
    print(f"Total documents: {len(all_docs['ids'])}")
    
    # Look for NEW_OPENED_ACC in documents
    new_opened_acc_found = []
    pio_accounts_docs = []
    
    for i, (doc_id, document, metadata) in enumerate(zip(all_docs['ids'], all_docs['documents'], all_docs['metadatas'])):
        if 'NEW_OPENED_ACC' in document:
            new_opened_acc_found.append({
                'id': doc_id,
                'document': document,
                'metadata': metadata
            })
        
        if 'PIO_ACCOUNTS' in document and 'column' in metadata.get('entity_type', ''):
            pio_accounts_docs.append({
                'id': doc_id,
                'column': metadata.get('column_name', 'Unknown'),
                'metadata': metadata
            })
    
    print(f"\nNEW_OPENED_ACC search results:")
    print(f"Found {len(new_opened_acc_found)} documents containing 'NEW_OPENED_ACC'")
    
    for item in new_opened_acc_found:
        print(f"\nID: {item['id']}")
        print(f"Metadata: {item['metadata']}")
        print(f"Document preview: {item['document'][:300]}...")
    
    print(f"\nPIO_ACCOUNTS columns found: {len(pio_accounts_docs)}")
    pio_accounts_columns = [doc['column'] for doc in pio_accounts_docs]
    print(f"PIO_ACCOUNTS column names: {sorted(pio_accounts_columns)}")
    
    # Search for similar columns to NEW_OPENED_ACC
    similar_columns = [col for col in pio_accounts_columns if 'OPEN' in col.upper() or 'NEW' in col.upper() or 'ACC' in col.upper()]
    print(f"\nColumns similar to NEW_OPENED_ACC: {similar_columns}")

if __name__ == "__main__":
    check_oracle_embeddings()