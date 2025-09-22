"""
Production script to build comprehensive embeddings from BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH
This will create detailed embeddings that include column descriptions, data types, and AML flags.
"""

import os
import sys
import json
import time
import numpy as np
from pathlib import Path
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from services.db.metadata_harvester import MetadataHarvester

def create_comprehensive_embeddings():
    """Create comprehensive embeddings from the dictionary table."""
    
    print("🚀 Building comprehensive database embeddings...")
    
    # Initialize components
    harvester = MetadataHarvester()
    
    try:
        # Get comprehensive dictionary data
        print("\n📊 Retrieving comprehensive dictionary data...")
        
        dictionary_query = """
        SELECT 
            TABLE_SCHEMA,
            TABLE_NAME,
            COLUMN_NAME,
            COLUMN_DESCRIPTION_ENG,
            COLUMN_DATA_TYPE,
            MANDATORY_AML_Y_N,
            COLUMN_DEFAULT,
            IS_NULLABLE,
            CHARACTER_MAXIMUM_LENGTH,
            NUMERIC_PRECISION,
            NUMERIC_SCALE,
            ORDINAL_POSITION
        FROM BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH
        ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
        """
        
        print("Executing dictionary query...")
        df = harvester.execute_query(dictionary_query)
        
        if df.empty:
            print("❌ No data retrieved from dictionary table")
            return False
            
        print(f"✅ Retrieved {len(df)} column definitions from dictionary table")
        
        # Create embedding documents
        print("\n🔨 Creating embedding documents...")
        documents = []
        metadatas = []
        ids = []
        
        # Group by table to create both table-level and column-level embeddings
        table_groups = df.groupby(['TABLE_SCHEMA', 'TABLE_NAME'])
        
        for (schema, table), table_df in table_groups:
            full_table_name = f"{schema}.{table}"
            
            # 1. Create table-level summary embedding
            aml_columns = table_df[table_df['MANDATORY_AML_Y_N'] == 'Y']
            non_aml_columns = table_df[table_df['MANDATORY_AML_Y_N'] == 'N']
            
            table_summary = f"""
TABLE: {full_table_name}
SCHEMA: {schema}
TABLE_NAME: {table}
TOTAL_COLUMNS: {len(table_df)}
AML_COLUMNS: {len(aml_columns)}
NON_AML_COLUMNS: {len(non_aml_columns)}

COLUMN SUMMARY:
{chr(10).join([f"- {row['COLUMN_NAME']} ({row['COLUMN_DATA_TYPE']}) - {row['COLUMN_DESCRIPTION_ENG'] or 'No description'} [AML: {row['MANDATORY_AML_Y_N']}]" for _, row in table_df.iterrows()])}

AML_RELEVANT_COLUMNS: {', '.join(aml_columns['COLUMN_NAME'].tolist())}
"""
            
            documents.append(table_summary.strip())
            metadatas.append({
                'entity_type': 'table_summary',
                'table_schema': schema,
                'table_name': table,
                'full_table_name': full_table_name,
                'total_columns': len(table_df),
                'aml_columns': len(aml_columns),
                'non_aml_columns': len(non_aml_columns),
                'aml_column_list': ', '.join(aml_columns['COLUMN_NAME'].tolist())
            })
            ids.append(f"table_summary_{schema}_{table}")
            
            # 2. Create individual column embeddings
            for idx, row in table_df.iterrows():
                column_doc = f"""
TABLE: {full_table_name}
COLUMN: {row['COLUMN_NAME']}
FULL_COLUMN_NAME: {full_table_name}.{row['COLUMN_NAME']}
DATA_TYPE: {row['COLUMN_DATA_TYPE']}
DESCRIPTION: {row['COLUMN_DESCRIPTION_ENG'] or 'No description available'}
AML_MANDATORY: {row['MANDATORY_AML_Y_N']}
NULLABLE: {row['IS_NULLABLE']}
DEFAULT_VALUE: {row['COLUMN_DEFAULT'] or 'None'}
POSITION: {row['ORDINAL_POSITION']}
"""
                
                # Add data type specific details
                if row['CHARACTER_MAXIMUM_LENGTH']:
                    column_doc += f"MAX_LENGTH: {row['CHARACTER_MAXIMUM_LENGTH']}\n"
                if row['NUMERIC_PRECISION']:
                    column_doc += f"PRECISION: {row['NUMERIC_PRECISION']}\n"
                if row['NUMERIC_SCALE']:
                    column_doc += f"SCALE: {row['NUMERIC_SCALE']}\n"
                
                # Add contextual information based on AML relevance
                if row['MANDATORY_AML_Y_N'] == 'Y':
                    column_doc += "USAGE: This column is used by the AML Engine for compliance monitoring and analysis.\n"
                else:
                    column_doc += "USAGE: This column is not directly used by the AML Engine.\n"
                
                documents.append(column_doc.strip())
                metadatas.append({
                    'entity_type': 'column',
                    'table_schema': schema,
                    'table_name': table,
                    'full_table_name': full_table_name,
                    'column_name': row['COLUMN_NAME'],
                    'full_column_name': f"{full_table_name}.{row['COLUMN_NAME']}",
                    'data_type': row['COLUMN_DATA_TYPE'],
                    'aml_mandatory': row['MANDATORY_AML_Y_N'],
                    'is_nullable': row['IS_NULLABLE'],
                    'ordinal_position': row['ORDINAL_POSITION'],
                    'has_description': bool(row['COLUMN_DESCRIPTION_ENG'])
                })
                ids.append(f"column_{schema}_{table}_{row['COLUMN_NAME']}")
        
        print(f"✅ Created {len(documents)} embedding documents")
        print(f"   - Table summaries: {len([d for d in metadatas if d['entity_type'] == 'table_summary'])}")
        print(f"   - Column details: {len([d for d in metadatas if d['entity_type'] == 'column'])}")
        
        # Initialize ChromaDB
        print("\n🗄️ Initializing ChromaDB...")
        warehouse_path = project_root / "warehouse"
        chroma_path = warehouse_path / "vectors"
        
        chroma_client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Create new collection for comprehensive data
        collection_name = "aml_comprehensive_metadata"
        
        # Delete existing collection if it exists
        try:
            chroma_client.delete_collection(collection_name)
            print(f"🗑️ Deleted existing collection: {collection_name}")
        except:
            pass
        
        # Create new collection
        collection = chroma_client.create_collection(
            name=collection_name,
            metadata={"description": "Comprehensive AML database metadata with column details"}
        )
        
        print(f"✅ Created collection: {collection_name}")
        
        # Add documents in batches
        batch_size = 100
        total_batches = (len(documents) + batch_size - 1) // batch_size
        
        print(f"\n📦 Adding {len(documents)} documents in {total_batches} batches...")
        
        for i in range(0, len(documents), batch_size):
            batch_end = min(i + batch_size, len(documents))
            batch_docs = documents[i:batch_end]
            batch_metas = metadatas[i:batch_end]
            batch_ids = ids[i:batch_end]
            
            collection.add(
                documents=batch_docs,
                metadatas=batch_metas,
                ids=batch_ids
            )
            
            batch_num = (i // batch_size) + 1
            print(f"   Batch {batch_num}/{total_batches}: Added {len(batch_docs)} documents")
        
        # Verify collection
        final_count = collection.count()
        print(f"\n✅ Collection created successfully!")
        print(f"   Total documents: {final_count}")
        
        # Test search functionality
        print("\n🔍 Testing search functionality...")
        test_queries = [
            "PIO_AML_CUSTOMERS columns",
            "customer table structure",
            "AML mandatory fields",
            "transaction data columns"
        ]
        
        for query in test_queries:
            results = collection.query(
                query_texts=[query],
                n_results=3
            )
            
            print(f"\n Query: '{query}'")
            if results['documents'][0]:
                for i, doc in enumerate(results['documents'][0][:2]):
                    metadata = results['metadatas'][0][i]
                    print(f"   Result {i+1}: {metadata['entity_type']} - {metadata.get('full_table_name', 'N/A')}")
                    print(f"   Content preview: {doc[:100]}...")
            else:
                print("   No results found")
        
        # Save statistics
        stats = {
            'creation_time': time.time(),
            'total_documents': len(documents),
            'table_summaries': len([d for d in metadatas if d['entity_type'] == 'table_summary']),
            'column_details': len([d for d in metadatas if d['entity_type'] == 'column']),
            'collection_name': collection_name,
            'source_table': 'BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH'
        }
        
        stats_file = warehouse_path / "comprehensive_embeddings_stats.json"
        with open(stats_file, 'w') as f:
            json.dump(stats, f, indent=2)
        
        print(f"\n📊 Saved statistics to: {stats_file}")
        print(f"✅ Comprehensive embeddings creation completed!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating comprehensive embeddings: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        harvester.close()

if __name__ == "__main__":
    print("🚀 Starting comprehensive embeddings creation...")
    
    success = create_comprehensive_embeddings()
    
    if success:
        print("\n✅ SUCCESS: Comprehensive embeddings created!")
        print("\nNext steps:")
        print("1. Update the web chat to use the new 'aml_comprehensive_metadata' collection")
        print("2. Test queries about specific tables and columns")
        print("3. The LLM should now provide detailed column information")
    else:
        print("\n❌ FAILED: Could not create comprehensive embeddings")