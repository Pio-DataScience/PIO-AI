"""
Test what PIO_ACCOUNTS data is actually available in vector database
"""

import chromadb
from chromadb.config import Settings
from pathlib import Path

def analyze_pio_accounts_data():
    # Connect to ChromaDB
    warehouse_path = Path(__file__).parent.parent / "warehouse"
    chroma_path = warehouse_path / "vectors"
    
    client = chromadb.PersistentClient(
        path=str(chroma_path),
        settings=Settings(anonymized_telemetry=False, allow_reset=True)
    )
    
    collection = client.get_collection("aml_dictionary_metadata_bge")
    
    print("🔍 ANALYZING PIO_ACCOUNTS DATA IN VECTOR DATABASE")
    print("=" * 60)
    
    # Get all documents
    all_results = collection.get(include=['metadatas', 'documents'])
    
    # Find PIO_ACCOUNTS related documents
    table_summary = None
    pio_columns = []
    
    for doc, metadata in zip(all_results['documents'], all_results['metadatas']):
        if metadata and metadata.get('table_name') == 'PIO_ACCOUNTS':
            if metadata.get('entity_type') == 'table_summary':
                table_summary = doc
            elif metadata.get('entity_type') == 'column':
                pio_columns.append({
                    'name': metadata.get('column_name'),
                    'document': doc,
                    'metadata': metadata
                })
    
    print(f"\n📋 QUERY 1: 'What does PIO_ACCOUNTS table do?'")
    print(f"{'='*50}")
    
    if table_summary:
        print("✅ TABLE SUMMARY FOUND - LLM will have good context:")
        print(f"Content preview: {table_summary[:400]}...")
        print("\n🎯 LLM Response Quality: EXCELLENT ✅")
    else:
        print("❌ NO TABLE SUMMARY - LLM will have limited context")
        print("🎯 LLM Response Quality: POOR ❌")
    
    print(f"\n📋 QUERY 2: 'Tell me about the 20th column in PIO_ACCOUNTS'")
    print(f"{'='*60}")
    
    # Sort columns by name to get consistent ordering
    pio_columns.sort(key=lambda x: x['name'])
    
    print(f"Total PIO_ACCOUNTS columns available: {len(pio_columns)}")
    print("\nAvailable columns (first 25):")
    
    for i, col_info in enumerate(pio_columns[:25], 1):
        marker = "👉 20TH" if i == 20 else f"{i:2d}."
        print(f"  {marker} {col_info['name']}")
    
    if len(pio_columns) >= 20:
        twentieth_column = pio_columns[19]  # 0-indexed
        print(f"\n✅ 20TH COLUMN EXISTS: {twentieth_column['name']}")
        print(f"Document content: {twentieth_column['document'][:300]}...")
        print("\n🎯 LLM Response for 20th column: WILL WORK ✅")
        
        # Show what data types and details are available
        metadata = twentieth_column['metadata']
        print(f"\nAvailable metadata for {twentieth_column['name']}:")
        for key, value in metadata.items():
            if value and key != 'entity_type':
                print(f"  - {key}: {value}")
                
    else:
        print(f"\n❌ 20TH COLUMN DOES NOT EXIST")
        print(f"   Only {len(pio_columns)} columns available in vector database")
        print("\n🎯 LLM Response for 20th column: WILL FAIL ❌")
        print("   LLM will say: 'Column not found' or 'Unable to locate'")
    
    print(f"\n🎯 SUMMARY:")
    print(f"{'='*40}")
    print(f"✅ Table overview query: {'WORKS' if table_summary else 'FAILS'}")
    print(f"✅ 20th column query: {'WORKS' if len(pio_columns) >= 20 else 'FAILS'}")
    print(f"📊 Available columns: {len(pio_columns)} out of ~325 actual columns")
    print(f"📈 Coverage: {len(pio_columns)/325*100:.1f}% of full PIO_ACCOUNTS table")

if __name__ == "__main__":
    analyze_pio_accounts_data()