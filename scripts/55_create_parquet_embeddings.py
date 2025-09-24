"""
High-performance embeddings creation using Parquet format.
Parquet provides better compression, faster I/O, and schema enforcement compared to CSV.
"""

import os
import sys
import json
import time
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import chromadb
from chromadb.config import Settings
from pathlib import Path
from sentence_transformers import SentenceTransformer
import numpy as np

def convert_csv_to_parquet():
    """Convert CSV data to optimized Parquet format."""
    print("🔄 Converting CSV data to Parquet format for better performance...")
    
    warehouse_path = Path(__file__).parent.parent / "warehouse"
    csv_file = warehouse_path / "dictionary_columns_sample.csv"
    parquet_file = warehouse_path / "dictionary_metadata.parquet"
    
    if not csv_file.exists():
        print(f"❌ CSV file not found: {csv_file}")
        return False
    
    try:
        # Load CSV with optimized data types
        print(f"📊 Loading CSV: {csv_file}")
        df = pd.read_csv(csv_file)
        
        # Optimize data types for better compression and performance
        df = df.astype({
            'TABLE_NAME': 'string',
            'COLUMN_NAME': 'string', 
            'COLUMN_DESCRIPTION_ENG': 'string',
            'COLUMN_DATA_TYPE': 'category',  # Often repeated values
            'MANDAOTRY_AML_Y_N': 'category',  # Y/N values
            'SYSTEM_TYPE': 'category'  # Limited set of system types
        })
        
        # Add computed columns for faster processing
        df['table_column_key'] = df['TABLE_NAME'] + '.' + df['COLUMN_NAME']
        df['is_aml_required'] = (df['MANDAOTRY_AML_Y_N'] == 'Y')
        df['description_length'] = df['COLUMN_DESCRIPTION_ENG'].str.len()
        
        # Save as Parquet with compression
        print(f"💾 Saving as Parquet: {parquet_file}")
        df.to_parquet(
            parquet_file,
            compression='snappy',  # Good balance of speed and compression
            index=False
        )
        
        # Verify the conversion
        df_verify = pd.read_parquet(parquet_file)
        print(f"✅ Parquet conversion successful!")
        print(f"   - Original CSV size: {csv_file.stat().st_size / 1024:.1f} KB")
        print(f"   - Parquet size: {parquet_file.stat().st_size / 1024:.1f} KB")
        print(f"   - Compression ratio: {csv_file.stat().st_size / parquet_file.stat().st_size:.1f}x")
        print(f"   - Records: {len(df_verify):,}")
        print(f"   - Columns: {len(df_verify.columns)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error converting to Parquet: {e}")
        return False

def create_embeddings_from_parquet():
    """Create embeddings from Parquet data with optimized performance."""
    print("🚀 Creating embeddings from optimized Parquet data...")
    
    warehouse_path = Path(__file__).parent.parent / "warehouse"
    parquet_file = warehouse_path / "dictionary_metadata.parquet"
    
    if not parquet_file.exists():
        print(f"❌ Parquet file not found. Converting from CSV first...")
        if not convert_csv_to_parquet():
            return False
    
    try:
        # Load BGE model
        print("🧠 Loading BGE-large-en-v1.5 model...")
        model = SentenceTransformer('BAAI/bge-large-en-v1.5')
        embedding_dimension = model.get_sentence_embedding_dimension()
        print(f"✅ BGE model loaded (dimension: {embedding_dimension})")
        
        # Load Parquet data - much faster than CSV
        print(f"📊 Loading dictionary data from Parquet...")
        start_time = time.time()
        df = pd.read_parquet(parquet_file)
        load_time = time.time() - start_time
        print(f"✅ Loaded {len(df):,} records in {load_time:.2f}s (Parquet advantage!)")
        
        # Group by table for efficient processing
        print("🔨 Creating embedding documents...")
        documents = []
        metadatas = []
        ids = []
        
        table_groups = df.groupby('TABLE_NAME')
        total_tables = len(table_groups)
        
        print(f"Processing {total_tables} tables...")
        
        for table_name, table_data in table_groups:
            # 1. Create optimized table summary
            total_columns = len(table_data)
            aml_columns = table_data['is_aml_required'].sum()
            
            # More efficient string building
            column_samples = table_data.head(10)[['COLUMN_NAME', 'COLUMN_DATA_TYPE', 'COLUMN_DESCRIPTION_ENG']]
            column_list = [f"- {row['COLUMN_NAME']} ({row['COLUMN_DATA_TYPE']}): {row['COLUMN_DESCRIPTION_ENG']}" 
                          for _, row in column_samples.iterrows()]
            
            table_summary = f\"\"\"Table: {table_name}
Owner: BI_DWH
Total Columns: {total_columns}
AML Required Columns: {aml_columns}

Key Columns:
{chr(10).join(column_list)}
{f'... and {total_columns-10} more columns' if total_columns > 10 else ''}

AML Compliance: {'High priority - contains AML-required columns' if aml_columns > 0 else 'Standard table - no specific AML requirements'}
Business Purpose: Data warehouse table containing {total_columns} structured data elements for business intelligence and compliance reporting.\"\"\"
            
            documents.append(table_summary)
            metadatas.append({
                'entity_type': 'table_summary',
                'table_name': table_name,
                'total_columns': int(total_columns),
                'aml_columns': int(aml_columns),
                'owner': 'BI_DWH'
            })
            ids.append(f"table_summary_{table_name}")
            
            # 2. Create column embeddings with vectorized operations
            for idx, (_, row) in enumerate(table_data.iterrows()):
                column_name = row['COLUMN_NAME']
                
                column_doc = f\"\"\"Column: {table_name}.{column_name}
Data Type: {row['COLUMN_DATA_TYPE']}
Description: {row['COLUMN_DESCRIPTION_ENG']}
AML Required: {row['MANDAOTRY_AML_Y_N']}
System Type: {row['SYSTEM_TYPE']}

Business Context: {'This column is mandatory for AML (Anti-Money Laundering) compliance and regulatory reporting' if row['is_aml_required'] else 'Standard business data column for operational and analytical purposes'}
Technical Details: Column {column_name} in table {table_name} stores {row['COLUMN_DESCRIPTION_ENG']} using {row['COLUMN_DATA_TYPE']} data type.\"\"\"
                
                documents.append(column_doc)
                metadatas.append({
                    'entity_type': 'column',
                    'table_name': table_name,
                    'column_name': column_name,
                    'data_type': str(row['COLUMN_DATA_TYPE']),
                    'aml_required': str(row['MANDAOTRY_AML_Y_N']),
                    'description': str(row['COLUMN_DESCRIPTION_ENG']),
                    'system_type': str(row['SYSTEM_TYPE']),
                    'owner': 'BI_DWH'
                })
                ids.append(f"column_{table_name}_{column_name}_{idx}")  # Include index for uniqueness
        
        print(f"✅ Created {len(documents):,} embedding documents")
        print(f"   - {len([d for d in metadatas if d['entity_type'] == 'table_summary'])} table summaries")
        print(f"   - {len([d for d in metadatas if d['entity_type'] == 'column'])} column definitions")
        
        # Setup ChromaDB with performance optimizations
        print("🔗 Setting up high-performance ChromaDB...")
        chroma_path = warehouse_path / "vectors"
        
        client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Delete and recreate collection for clean state
        collection_name = "aml_dictionary_metadata"
        try:
            client.delete_collection(collection_name)
            print(f"🗑️ Deleted existing {collection_name} collection")
        except:
            pass
        
        collection = client.create_collection(
            name=collection_name,
            metadata={"description": "High-performance dictionary metadata with BGE-large-en-v1.5 embeddings"}
        )
        
        # Generate embeddings in optimized batches
        batch_size = 50  # Smaller batches for stability
        total_batches = (len(documents) + batch_size - 1) // batch_size
        
        print(f"🎯 Generating {len(documents):,} embeddings in {total_batches} optimized batches...")
        
        start_embedding_time = time.time()
        
        for i in range(0, len(documents), batch_size):
            batch_num = i // batch_size + 1
            end_idx = min(i + batch_size, len(documents))
            batch_docs = documents[i:end_idx]
            batch_metas = metadatas[i:end_idx]
            batch_ids = ids[i:end_idx]
            
            print(f"   Processing batch {batch_num}/{total_batches} ({len(batch_docs)} documents)...")
            
            # Generate embeddings for batch
            batch_embeddings = model.encode(batch_docs).tolist()
            
            # Add to collection
            collection.add(
                documents=batch_docs,
                metadatas=batch_metas,
                ids=batch_ids,
                embeddings=batch_embeddings
            )
        
        embedding_time = time.time() - start_embedding_time
        print(f"✅ Embedding generation completed in {embedding_time:.1f}s")
        
        # Verify the collection
        final_count = collection.count()
        print(f"✅ Successfully created collection with {final_count:,} documents")
        
        # Performance test
        print("🔍 Performance testing...")
        test_embedding = model.encode(["customer data table"]).tolist()
        
        test_start = time.time()
        test_results = collection.query(
            query_embeddings=test_embedding,
            n_results=5
        )
        test_time = time.time() - test_start
        
        print(f"✅ Search performance test: {test_time*1000:.1f}ms for 5 results")
        
        # Save performance statistics
        stats = {
            'creation_timestamp': time.time(),
            'creation_date': time.strftime('%Y-%m-%d %H:%M:%S'),
            'data_format': 'parquet',
            'total_documents': final_count,
            'table_summaries': len([d for d in metadatas if d['entity_type'] == 'table_summary']),
            'column_definitions': len([d for d in metadatas if d['entity_type'] == 'column']),
            'embedding_model': 'BAAI/bge-large-en-v1.5',
            'embedding_dimension': embedding_dimension,
            'data_load_time_seconds': load_time,
            'embedding_generation_time_seconds': embedding_time,
            'search_test_time_ms': test_time * 1000,
            'parquet_advantages': [
                'Faster data loading',
                'Better compression',
                'Schema enforcement',
                'Type optimization',
                'Column-based storage'
            ]
        }
        
        stats_file = warehouse_path / "parquet_embeddings_stats.json"
        with open(stats_file, 'w') as f:
            json.dump(stats, f, indent=2)
        
        print(f"✅ High-performance embeddings creation completed!")
        print(f"📊 Performance stats saved to: {stats_file}")
        print(f"🎯 Collection '{collection_name}' ready with {final_count:,} BGE-compatible embeddings")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating embeddings from Parquet: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting high-performance Parquet-based embeddings creation...")
    print("Benefits: Faster loading, better compression, schema enforcement")
    
    success = create_embeddings_from_parquet()
    
    if success:
        print("\n✅ SUCCESS: High-performance Parquet embeddings created!")
        print("🔥 Performance improvements:")
        print("   - Faster data loading with Parquet columnar storage")
        print("   - Better compression reducing disk usage")
        print("   - Schema enforcement preventing data type issues")
        print("   - Optimized batch processing for embeddings")
        print("   - BGE-large-en-v1.5 compatibility (1024D)")
    else:
        print("\n❌ FAILED: Could not create high-performance embeddings")
        print("   Please check the error messages above and try again.")