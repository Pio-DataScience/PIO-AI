#!/usr/bin/env python3
"""
Direct vector database validation script.
This bypasses the API and directly checks the ChromaDB vector database.
"""

import sys
import os
import json

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

try:
    import chromadb
    from chromadb.config import Settings
    print("✅ ChromaDB imported successfully")
except ImportError as e:
    print(f"❌ ChromaDB import failed: {e}")
    print("Install with: pip install chromadb")
    sys.exit(1)


def check_vector_database():
    """Check what's actually stored in the vector database."""
    
    print("🔍 CHECKING VECTOR DATABASE DIRECTLY")
    print("=" * 60)
    
    try:
        # Connect to ChromaDB
        chroma_client = chromadb.PersistentClient(
            path="./warehouse/vectors",
            settings=Settings(allow_reset=True, anonymized_telemetry=False)
        )
        print("✅ Connected to ChromaDB")
        
        # List all collections
        collections = chroma_client.list_collections()
        print(f"\n📁 Found {len(collections)} collections:")
        for collection in collections:
            print(f"  - {collection.name}")
        
        # Check the main metadata collection
        if not collections:
            print("❌ No collections found in vector database!")
            return
        
        # Find the metadata collection
        metadata_collection = None
        for collection in collections:
            if "metadata" in collection.name.lower() or "dictionary" in collection.name.lower():
                metadata_collection = collection
                break
        
        if not metadata_collection:
            metadata_collection = collections[0]  # Use first collection as fallback
        
        print(f"\n🔍 Examining collection: {metadata_collection.name}")
        
        # Get all items from the collection
        all_items = metadata_collection.get()
        print(f"📊 Total items in collection: {len(all_items['ids']) if all_items['ids'] else 0}")
        
        if not all_items['ids']:
            print("❌ Collection is empty!")
            return
        
        # Search for PIO_ACCOUNTS specifically
        pio_accounts_columns = []
        opened_related_columns = []
        
        for i, (doc_id, metadata, document) in enumerate(zip(
            all_items['ids'], 
            all_items['metadatas'] or [{}] * len(all_items['ids']), 
            all_items['documents'] or [''] * len(all_items['ids'])
        )):
            if metadata and isinstance(metadata, dict):
                table_name = metadata.get('table_name', '')
                column_name = metadata.get('column_name', '')
                
                # Check for PIO_ACCOUNTS table
                if table_name == 'PIO_ACCOUNTS' and column_name:
                    data_type = metadata.get('data_type', 'Unknown')
                    aml_required = metadata.get('aml_required', 'Unknown')
                    
                    pio_accounts_columns.append({
                        'column': column_name,
                        'data_type': data_type,
                        'aml_required': aml_required,
                        'content_preview': document[:100] if document else ''
                    })
                    
                    # Check for columns related to "OPENED"
                    if 'OPENED' in column_name.upper() or 'OPEN' in column_name.upper():
                        opened_related_columns.append({
                            'column': column_name,
                            'table': table_name,
                            'data_type': data_type,
                            'content': document[:200] if document else ''
                        })
        
        print(f"\n📊 PIO_ACCOUNTS COLUMNS FOUND: {len(pio_accounts_columns)}")
        
        if pio_accounts_columns:
            # Sort columns alphabetically
            pio_accounts_columns.sort(key=lambda x: x['column'])
            
            print("\n📋 FIRST 20 PIO_ACCOUNTS COLUMNS:")
            for i, col in enumerate(pio_accounts_columns[:20]):
                print(f"{i+1:2}. {col['column']} ({col['data_type']}) - AML: {col['aml_required']}")
            
            if len(pio_accounts_columns) > 20:
                print(f"... and {len(pio_accounts_columns) - 20} more columns")
        
        # Check specifically for NEW_OPENED_ACC
        new_opened_acc_found = False
        for col in pio_accounts_columns:
            if col['column'].upper() == 'NEW_OPENED_ACC':
                new_opened_acc_found = True
                print(f"\n✅ FOUND NEW_OPENED_ACC!")
                print(f"   Data Type: {col['data_type']}")
                print(f"   AML Required: {col['aml_required']}")
                print(f"   Content: {col['content_preview']}")
                break
        
        if not new_opened_acc_found:
            print(f"\n❌ NEW_OPENED_ACC NOT FOUND in vector database")
            
            # Search for similar columns
            similar_columns = []
            for col in pio_accounts_columns:
                if any(word in col['column'].upper() for word in ['NEW', 'OPENED', 'OPEN', 'ACC']):
                    similar_columns.append(col)
            
            if similar_columns:
                print(f"\n🔍 SIMILAR COLUMNS FOUND ({len(similar_columns)}):")
                for col in similar_columns:
                    print(f"  - {col['column']} ({col['data_type']})")
        
        # Show all OPENED/OPEN related columns across all tables
        if opened_related_columns:
            print(f"\n🔍 ALL 'OPENED/OPEN' RELATED COLUMNS ({len(opened_related_columns)}):")
            for col in opened_related_columns:
                print(f"  - {col['column']} in {col['table']} ({col['data_type']})")
                if col['content']:
                    print(f"    {col['content'][:100]}...")
        
        # Search for any mention of NEW_OPENED_ACC in documents
        print(f"\n🔍 SEARCHING DOCUMENT CONTENT FOR 'NEW_OPENED_ACC'...")
        content_matches = []
        
        for i, document in enumerate(all_items['documents'] or []):
            if document and 'NEW_OPENED_ACC' in document.upper():
                content_matches.append({
                    'doc_id': all_items['ids'][i],
                    'content': document[:300],
                    'metadata': all_items['metadatas'][i] if all_items['metadatas'] else {}
                })
        
        if content_matches:
            print(f"✅ Found {len(content_matches)} documents mentioning NEW_OPENED_ACC:")
            for match in content_matches:
                print(f"  Document ID: {match['doc_id']}")
                print(f"  Content: {match['content']}...")
                print(f"  Metadata: {match['metadata']}")
                print()
        else:
            print("❌ No documents found containing 'NEW_OPENED_ACC'")
                
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


def search_csv_files():
    """Check the source CSV files for NEW_OPENED_ACC."""
    
    print("\n" + "=" * 60)
    print("🔍 CHECKING SOURCE CSV FILES")
    print("=" * 60)
    
    csv_files = [
        "./warehouse/dictionary_table_sample.csv",
        "./warehouse/dictionary_table_aml_sample.csv"
    ]
    
    for csv_file in csv_files:
        if os.path.exists(csv_file):
            print(f"\n📄 Checking {csv_file}")
            try:
                with open(csv_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Look for NEW_OPENED_ACC
                found_lines = []
                for i, line in enumerate(lines):
                    if 'NEW_OPENED_ACC' in line.upper():
                        found_lines.append((i+1, line.strip()))
                
                if found_lines:
                    print(f"✅ Found NEW_OPENED_ACC in {len(found_lines)} lines:")
                    for line_num, content in found_lines:
                        print(f"  Line {line_num}: {content}")
                else:
                    print("❌ NEW_OPENED_ACC not found in this file")
                    
                    # Look for similar columns
                    similar_lines = []
                    for i, line in enumerate(lines):
                        if 'PIO_ACCOUNTS' in line and any(word in line.upper() for word in ['NEW', 'OPENED', 'OPEN']):
                            similar_lines.append((i+1, line.strip()))
                    
                    if similar_lines:
                        print(f"🔍 Similar columns in PIO_ACCOUNTS:")
                        for line_num, content in similar_lines[:5]:
                            parts = content.split(',')
                            if len(parts) >= 3:
                                print(f"  {parts[1]} - {parts[2]}")
                            
            except Exception as e:
                print(f"❌ Error reading {csv_file}: {e}")
        else:
            print(f"❌ File not found: {csv_file}")


if __name__ == "__main__":
    check_vector_database()
    search_csv_files()