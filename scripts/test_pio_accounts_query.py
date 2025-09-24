"""
Test what happens when querying PIO_ACCOUNTS table details
"""

import chromadb
from chromadb.config import Settings
from pathlib import Path

def test_pio_accounts_queries():
    # Connect to ChromaDB
    warehouse_path = Path(__file__).parent.parent / "warehouse"
    chroma_path = warehouse_path / "vectors"
    
    client = chromadb.PersistentClient(
        path=str(chroma_path),
        settings=Settings(anonymized_telemetry=False, allow_reset=True)
    )
    
    collection = client.get_collection("aml_dictionary_metadata_bge")
    
    print("🔍 TESTING PIO_ACCOUNTS QUERIES")
    print("=" * 50)
    
    # Query 1: Table overview
    print("\n📋 Query 1: 'What does PIO_ACCOUNTS table do?'")
    results1 = collection.query(
        query_texts=["PIO_ACCOUNTS table purpose functionality"],
        n_results=3
    )
    
    print(f"Results found: {len(results1['documents'][0])}")
    for i, (doc, metadata) in enumerate(zip(results1['documents'][0], results1['metadatas'][0])):
        entity_type = metadata.get('entity_type', 'unknown')
        if entity_type == 'table_summary':
            print(f"✅ Table Summary Found:")
            print(f"   Content: {doc[:200]}...")
        else:
            table = metadata.get('table_name', 'unknown')
            column = metadata.get('column_name', 'unknown') 
            print(f"   Column result: {table}.{column}")
    
    # Query 2: Specific column by position
    print(f"\n📋 Query 2: 'Tell me about the 20th column in PIO_ACCOUNTS'")
    results2 = collection.query(
        query_texts=["PIO_ACCOUNTS 20th column twentieth column position"],
        n_results=5
    )
    
    print(f"Results found: {len(results2['documents'][0])}")
    print("Available PIO_ACCOUNTS columns in vector DB:")
    
    # Get all PIO_ACCOUNTS columns
    all_results = collection.get(include=['metadatas'])
    pio_columns = []
    for metadata in all_results['metadatas']:
        if (metadata and 
            metadata.get('entity_type') == 'column' and 
            metadata.get('table_name') == 'PIO_ACCOUNTS'):
            pio_columns.append(metadata.get('column_name'))
    
    pio_columns.sort()
    print(f"Total PIO_ACCOUNTS columns in vector DB: {len(pio_columns)}")
    
    for i, col in enumerate(pio_columns[:25], 1):  # Show first 25
        marker = "👉" if i == 20 else "  "
        print(f"{marker} {i:2d}. {col}")
    
    if len(pio_columns) >= 20:
        print(f"\n✅ 20th column EXISTS: {pio_columns[19]}")
        # Query specifically for the 20th column
        results3 = collection.query(
            query_texts=[f"PIO_ACCOUNTS {pio_columns[19]} column details"],
            n_results=3
        )
        print(f"Direct query results: {len(results3['documents'][0])}")
        if results3['documents'][0]:
            print(f"✅ Found details for {pio_columns[19]}:")
            print(f"   {results3['documents'][0][0][:300]}...")
    else:
        print(f"\n❌ 20th column does NOT exist in vector DB")
        print(f"   Only {len(pio_columns)} columns available")
        print(f"   LLM would respond: 'Column not found' or provide incomplete info")

if __name__ == "__main__":
    test_pio_accounts_queries()