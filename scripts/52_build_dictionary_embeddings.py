"""
Production script to build comprehensive embeddings from BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH
This creates detailed embeddings with column descriptions, data types, and AML flags.
"""

import os
import sys
import json
import time
import pandas as pd
import oracledb
import chromadb
from chromadb.config import Settings
from pathlib import Path

def get_oracle_connection():
    """Get Oracle database connection using config file."""
    try:
        # Use the actual connection details from the config
        username = "BI_DWH"
        password = "BI_DWH"
        dsn = "192.168.30.43:1521/OPENBI2"
        
        print(f"Connecting to Oracle database: {dsn}")
        connection = oracledb.connect(
            user=username,
            password=password,
            dsn=dsn
        )
        print("✅ Database connection successful")
        return connection
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

def create_comprehensive_embeddings():
    """Create comprehensive embeddings from the dictionary table."""
    
    print("🚀 Building comprehensive database embeddings from dictionary table...")
    
    # Get database connection
    conn = get_oracle_connection()
    if not conn:
        return False
    
    try:
        # Get comprehensive dictionary data
        print("\n📊 Retrieving comprehensive dictionary data...")
        
        dictionary_query = """
        SELECT 
            TABLE_NAME,
            COLUMN_NAME,
            OBJECT_NAME,
            COLUMN_DESCRIPTION_ENG,
            COLUMN_DESCRIPTION_NATIVE,
            COLUMN_DATA_TYPE,
            MANDATORY_M_O,
            MANDAOTRY_AML_Y_N,
            MANDAOTRY_GOAML_Y_N,
            MANDAOTRY_KYC_OPTIMIZER_Y_N,
            MANDATORY_FATCA_Y_N,
            MANDATORY_GATCA_Y_N,
            COMMENTS,
            LOOKUP_TABLE_NAME
        FROM BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH
        ORDER BY TABLE_NAME, COLUMN_NAME
        """
        
        print("Executing dictionary query...")
        df = pd.read_sql(dictionary_query, conn)
        
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
        table_groups = df.groupby('TABLE_NAME')
        
        for table_name, table_df in table_groups:
            
            # 1. Create table-level summary embedding
            aml_columns = table_df[table_df['MANDAOTRY_AML_Y_N'] == 'Y']
            non_aml_columns = table_df[table_df['MANDAOTRY_AML_Y_N'] != 'Y']
            
            # Build comprehensive table summary
            table_summary = f"""TABLE: {table_name}
TOTAL_COLUMNS: {len(table_df)}
AML_COLUMNS: {len(aml_columns)}
NON_AML_COLUMNS: {len(non_aml_columns)}

DESCRIPTION: Database table containing {len(table_df)} columns, with {len(aml_columns)} columns used by the AML Engine for compliance monitoring.

AML_RELEVANT_COLUMNS: {', '.join(aml_columns['COLUMN_NAME'].tolist())}

ALL_COLUMNS_SUMMARY:
{chr(10).join([f"- {row['COLUMN_NAME']} ({row['COLUMN_DATA_TYPE']}) - {row['COLUMN_DESCRIPTION_ENG'] or row['OBJECT_NAME'] or 'No description'} [AML: {row['MANDAOTRY_AML_Y_N']}]" for _, row in table_df.iterrows()])}
"""
            
            documents.append(table_summary.strip())
            
            # Clean metadata (remove None values for ChromaDB)
            table_metadata = {
                'entity_type': 'table_summary',
                'table_name': table_name,
                'total_columns': len(table_df),
                'aml_columns': len(aml_columns),
                'non_aml_columns': len(non_aml_columns),
                'aml_column_list': ', '.join(aml_columns['COLUMN_NAME'].tolist()),
                'has_aml_columns': len(aml_columns) > 0
            }
            
            metadatas.append(table_metadata)
            ids.append(f"table_summary_{table_name}")
            
            # 2. Create individual column embeddings with rich context
            for idx, row in table_df.iterrows():
                # Build comprehensive column description
                description = row['COLUMN_DESCRIPTION_ENG'] or row['OBJECT_NAME'] or 'No description available'
                
                # Build system usage flags
                system_usage = []
                if row['MANDAOTRY_AML_Y_N'] == 'Y':
                    system_usage.append("AML Engine")
                if row['MANDAOTRY_GOAML_Y_N'] == 'Y':
                    system_usage.append("GOAML Reporting")
                if row['MANDAOTRY_KYC_OPTIMIZER_Y_N'] == 'Y':
                    system_usage.append("KYC Optimizer")
                if row['MANDATORY_FATCA_Y_N'] == 'Y':
                    system_usage.append("FATCA Compliance")
                if row['MANDATORY_GATCA_Y_N'] == 'Y':
                    system_usage.append("GATCA Compliance")
                
                usage_text = f"Used by: {', '.join(system_usage)}" if system_usage else "Not used by compliance systems"
                
                column_doc = f"""TABLE: {table_name}
COLUMN: {row['COLUMN_NAME']}
FULL_COLUMN_NAME: {table_name}.{row['COLUMN_NAME']}
OBJECT_NAME: {row['OBJECT_NAME'] or 'N/A'}
DATA_TYPE: {row['COLUMN_DATA_TYPE']}
DESCRIPTION: {description}
MANDATORY_OPTIONAL: {row['MANDATORY_M_O'] or 'N/A'}

SYSTEM_USAGE: {usage_text}
AML_MANDATORY: {row['MANDAOTRY_AML_Y_N']}
GOAML_REPORTING: {row['MANDAOTRY_GOAML_Y_N']}
KYC_OPTIMIZER: {row['MANDAOTRY_KYC_OPTIMIZER_Y_N']}
FATCA_COMPLIANCE: {row['MANDATORY_FATCA_Y_N']}
GATCA_COMPLIANCE: {row['MANDATORY_GATCA_Y_N']}

LOOKUP_TABLE: {row['LOOKUP_TABLE_NAME'] or 'None'}
COMMENTS: {row['COMMENTS'] or 'None'}

BUSINESS_CONTEXT: This column is {'required' if row['MANDATORY_M_O'] == 'M' else 'optional'} and {'is used by the AML Engine for compliance monitoring and analysis' if row['MANDAOTRY_AML_Y_N'] == 'Y' else 'is not directly used by the AML Engine'}.
"""
                
                documents.append(column_doc.strip())
                
                # Clean metadata (remove None values and convert to proper types)
                column_metadata = {
                    'entity_type': 'column',
                    'table_name': table_name,
                    'column_name': row['COLUMN_NAME'],
                    'full_column_name': f"{table_name}.{row['COLUMN_NAME']}",
                    'data_type': str(row['COLUMN_DATA_TYPE']) if row['COLUMN_DATA_TYPE'] else 'Unknown',
                    'aml_mandatory': str(row['MANDAOTRY_AML_Y_N']) == 'Y',
                    'goaml_reporting': str(row['MANDAOTRY_GOAML_Y_N']) == 'Y',
                    'kyc_optimizer': str(row['MANDAOTRY_KYC_OPTIMIZER_Y_N']) == 'Y',
                    'fatca_compliance': str(row['MANDATORY_FATCA_Y_N']) == 'Y',
                    'gatca_compliance': str(row['MANDATORY_GATCA_Y_N']) == 'Y',
                    'is_mandatory': str(row['MANDATORY_M_O']) == 'M',
                    'has_description': bool(row['COLUMN_DESCRIPTION_ENG']),
                    'has_lookup_table': bool(row['LOOKUP_TABLE_NAME']),
                    'system_count': len(system_usage)
                }
                
                metadatas.append(column_metadata)
                # Create unique ID with row index to avoid duplicates
                ids.append(f"column_{table_name}_{row['COLUMN_NAME']}_{idx}")
        
        print(f"✅ Created {len(documents)} embedding documents")
        print(f"   - Table summaries: {len([d for d in metadatas if d['entity_type'] == 'table_summary'])}")
        print(f"   - Column details: {len([d for d in metadatas if d['entity_type'] == 'column'])}")
        
        # Initialize ChromaDB
        print("\n🗄️ Initializing ChromaDB...")
        warehouse_path = Path(__file__).parent.parent / "warehouse"
        chroma_path = warehouse_path / "vectors"
        
        chroma_client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Create new collection for comprehensive data
        collection_name = "aml_dictionary_metadata"
        
        # Delete existing collection if it exists
        try:
            chroma_client.delete_collection(collection_name)
            print(f"🗑️ Deleted existing collection: {collection_name}")
        except:
            pass
        
        # Create new collection
        collection = chroma_client.create_collection(
            name=collection_name,
            metadata={"description": "Comprehensive AML database metadata from dictionary table with column details, descriptions, and system usage flags"}
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
            "PIO_ACCOUNTS columns",
            "ACCOUNT_NUMBER column description",
            "AML mandatory fields",
            "customer identification columns",
            "transaction amount fields"
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
                    entity_type = metadata['entity_type']
                    if entity_type == 'table_summary':
                        print(f"   Result {i+1}: Table Summary - {metadata['table_name']} ({metadata['aml_columns']} AML columns)")
                    else:
                        print(f"   Result {i+1}: Column - {metadata['full_column_name']} (AML: {metadata['aml_mandatory']})")
                    print(f"   Content preview: {doc[:100]}...")
            else:
                print("   No results found")
        
        # Save statistics
        aml_columns_count = len([m for m in metadatas if m['entity_type'] == 'column' and m['aml_mandatory']])
        table_summaries_count = len([m for m in metadatas if m['entity_type'] == 'table_summary'])
        
        stats = {
            'creation_time': time.time(),
            'total_documents': len(documents),
            'table_summaries': table_summaries_count,
            'column_details': len(documents) - table_summaries_count,
            'aml_mandatory_columns': aml_columns_count,
            'collection_name': collection_name,
            'source_table': 'BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH',
            'total_source_records': len(df),
            'unique_tables': len(table_groups)
        }
        
        warehouse_path.mkdir(exist_ok=True)
        stats_file = warehouse_path / "dictionary_embeddings_stats.json"
        with open(stats_file, 'w') as f:
            json.dump(stats, f, indent=2)
        
        print(f"\n📊 Saved statistics to: {stats_file}")
        print(f"✅ Comprehensive dictionary embeddings creation completed!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating comprehensive embeddings: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 Starting comprehensive dictionary embeddings creation...")
    
    success = create_comprehensive_embeddings()
    
    if success:
        print("\n✅ SUCCESS: Comprehensive dictionary embeddings created!")
        print("\nNext steps:")
        print("1. Update the web chat to use the new 'aml_dictionary_metadata' collection")
        print("2. Test queries about specific tables and columns")
        print("3. The LLM should now provide detailed column information with descriptions and AML usage")
        print("4. Try asking: 'What are the columns in PIO_ACCOUNTS table?'")
        print("5. Try asking: 'What is the ACCOUNT_NUMBER column used for?'")
    else:
        print("\n❌ FAILED: Could not create comprehensive dictionary embeddings")