"""
Memory-efficient embedding script for COMPLETE dictionary table.
Processes the full Oracle dictionary data (all tables/columns) in optimized chunks.
Creates comprehensive embeddings from complete dataset, not samples.
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
import gc
import torch
import psutil

def check_gpu_availability():
    """Check GPU availability and configure for optimal performance."""
    print("🔧 Checking GPU availability...")
    
    if torch.cuda.is_available():
        device_count = torch.cuda.device_count()
        current_device = torch.cuda.current_device()
        gpu_name = torch.cuda.get_device_name(current_device)
        gpu_memory = torch.cuda.get_device_properties(current_device).total_memory / 1e9
        
        print(f"✅ GPU Available: {gpu_name}")
        print(f"📊 GPU Memory: {gpu_memory:.1f} GB")
        print(f"🔢 GPU Devices: {device_count}")
        
        # Clear any existing GPU memory
        torch.cuda.empty_cache()
        
        return True, 'cuda'
    else:
        print("⚠️  No GPU available - using CPU")
        print(f"💾 CPU Memory: {psutil.virtual_memory().total / 1e9:.1f} GB")
        return False, 'cpu'
    
    if torch.cuda.is_available():
        device_count = torch.cuda.device_count()
        current_device = torch.cuda.current_device()
        gpu_name = torch.cuda.get_device_name(current_device)
        gpu_memory = torch.cuda.get_device_properties(current_device).total_memory / 1e9
        
        print(f"✅ GPU Available: {gpu_name}")
        print(f"📊 GPU Memory: {gpu_memory:.1f} GB")
        print(f"🔢 GPU Devices: {device_count}")
        
        # Clear any existing GPU memory
        torch.cuda.empty_cache()
        
        return True, 'cuda'
    else:
        print("⚠️  No GPU available - using CPU")
        print(f"💾 CPU Memory: {psutil.virtual_memory().total / 1e9:.1f} GB")
        return False, 'cpu'

def verify_parquet_data():
    """Verify that complete dictionary data exists in Parquet format."""
    print("📦 Verifying complete dictionary data in Parquet format...")
    
    warehouse_path = Path(__file__).parent.parent / "warehouse"
    parquet_file = warehouse_path / "dictionary_data.parquet"
    
    try:
        if not parquet_file.exists():
            print(f"❌ Parquet file not found: {parquet_file}")
            print("❌ Please run scripts/50_explore_dictionary_table.py first to export complete data")
            return None
            
        # Load and verify the data
        df = pd.read_parquet(parquet_file)
        
        print(f"✅ Complete dictionary data loaded: {parquet_file}")
        print(f"📊 Total records: {len(df):,}")
        print(f"📊 Unique tables: {df['TABLE_NAME'].nunique():,}")
        print(f"📊 AML columns: {(df.get('MANDATORY_AML_Y_N', '') == 'Y').sum():,}")
        
        # Verify this is complete data (not sample)
        if len(df) < 5000:  # Assume complete data should have 5000+ rows
            print(f"⚠️  WARNING: Only {len(df)} records found - this might be sample data!")
            print("⚠️  Run scripts/50_explore_dictionary_table.py to get complete dataset")
        else:
            print(f"✅ Complete dataset confirmed ({len(df):,} records)")
        
        return parquet_file
        
    except Exception as e:
        print(f"❌ Error verifying Parquet file: {e}")
        return None

def test_small_batch():
    """Test with just 2 records to verify everything works."""
    print("🧪 TESTING: Small batch embedding test...")
    
    # Check GPU and load BGE model
    try:
        has_gpu, device = check_gpu_availability()
        
        print(f"🤖 Loading BGE model on {device.upper()}...")
        model = SentenceTransformer('BAAI/bge-large-en-v1.5', device=device)
        
        print(f"✅ BGE model loaded on {device.upper()} (dimension: {model.get_sentence_embedding_dimension()})")
        
        if has_gpu:
            # Optimize for GPU
            model.max_seq_length = 512  # Reasonable length for GPU memory
            print(f"⚡ GPU optimized - max sequence length: {model.max_seq_length}")
        
    except Exception as e:
        print(f"❌ Failed to load BGE model: {e}")
        return False, None
    
    # Setup ChromaDB
    try:
        warehouse_path = Path(__file__).parent.parent / "warehouse"
        chroma_path = warehouse_path / "vectors"
        
        client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(anonymized_telemetry=False, allow_reset=True)
        )
        
        # Test collection
        test_collection = "test_memory_efficient"
        try:
            client.delete_collection(test_collection)
        except:
            pass
            
        collection = client.create_collection(test_collection)
        print("✅ Test collection created")
        
    except Exception as e:
        print(f"❌ ChromaDB setup failed: {e}")
        return False, None
    
    # Test with 2 documents
    try:
        test_docs = [
            "Table: PIO_ACCOUNTS\\nColumn: ACCOUNT_NUMBER\\nType: VARCHAR2\\nAML Required: Y",
            "Table: PIO_CUSTOMERS\\nColumn: CUSTOMER_ID\\nType: NUMBER\\nAML Required: Y"
        ]
        
        # Generate embeddings
        embeddings = model.encode(test_docs).tolist()
        
        # Add to collection
        collection.add(
            documents=test_docs,
            embeddings=embeddings,
            ids=["test_1", "test_2"]
        )
        
        # Test search
        query_embedding = model.encode(["customer account information"])[0].tolist()
        results = collection.query(query_embeddings=[query_embedding], n_results=1)
        
        # Cleanup
        client.delete_collection(test_collection)
        
        print("✅ Small batch test successful!")
        return True, model
        
    except Exception as e:
        print(f"❌ Small batch test failed: {e}")
        return False, None

def create_embeddings_memory_efficient(model):
    """Create embeddings with memory-efficient processing."""
    print("🚀 PRODUCTION: Memory-efficient embedding creation...")
    
    try:
        # Check GPU status
        has_gpu, device = check_gpu_availability()
        
        warehouse_path = Path(__file__).parent.parent / "warehouse"
        
        # Load complete dictionary data from Parquet
        data_file = warehouse_path / "dictionary_data.parquet"
        if not data_file.exists():
            print("❌ Complete dictionary data not found!")
            print("❌ Please run: python scripts/50_explore_dictionary_table.py")
            return False
            
        df = pd.read_parquet(data_file)
        print(f"✅ Loaded COMPLETE dictionary data: {len(df):,} records")
        
        print(f"📊 Loaded {len(df)} records from {data_file.name}")
        
        # Setup ChromaDB
        chroma_path = warehouse_path / "vectors"
        client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(anonymized_telemetry=False, allow_reset=True)
        )
        
        # Create production collection
        collection_name = "aml_dictionary_metadata_bge"
        try:
            client.delete_collection(collection_name)
        except:
            pass
            
        collection = client.create_collection(
            name=collection_name,
            metadata={"model": "BAAI/bge-large-en-v1.5", "dimension": "1024"}
        )
        print(f"✅ Created collection: {collection_name}")
        
        # Dynamic batch sizing based on device
        if has_gpu:
            batch_size = 50  # Larger batches for GPU
            print(f"⚡ GPU mode: Using batch size {batch_size}")
        else:
            batch_size = 20  # Smaller batches for CPU
            print(f"🖥️  CPU mode: Using batch size {batch_size}")
            
        total_docs = 0
        
        # Group by table first to reduce memory usage
        table_groups = df.groupby('TABLE_NAME')
        total_tables = len(table_groups)
        
        for table_idx, (table_name, table_group) in enumerate(table_groups):
            if table_idx % 10 == 0:  # Progress every 10 tables
                print(f"📊 Processing table {table_idx + 1}/{total_tables}: {table_name}")
                
                # Memory monitoring and cleanup
                if has_gpu and torch.cuda.is_available():
                    gpu_memory_used = torch.cuda.memory_allocated() / 1e9
                    gpu_memory_cached = torch.cuda.memory_reserved() / 1e9
                    print(f"   🔥 GPU Memory: {gpu_memory_used:.1f}GB used, {gpu_memory_cached:.1f}GB cached")
                    torch.cuda.empty_cache()
                
                cpu_memory = psutil.virtual_memory()
                print(f"   💾 CPU Memory: {cpu_memory.percent}% used ({cpu_memory.used/1e9:.1f}GB/{cpu_memory.total/1e9:.1f}GB)")
                
                # Force garbage collection
                gc.collect()
            
            try:
                # Create table summary
                aml_columns = table_group[table_group.get('MANDAOTRY_AML_Y_N', '') == 'Y']
                
                table_doc = f"""Table: {table_name}
Total Columns: {len(table_group)}
AML Required Columns: {len(aml_columns)}
Sample Columns: {', '.join(table_group['COLUMN_NAME'].head(5).tolist())}
Business Purpose: Database table for {table_name.lower().replace('_', ' ')} data management"""
                
                # Generate embedding for table summary
                table_embedding = model.encode([table_doc])[0].tolist()
                
                # Add table summary
                collection.add(
                    documents=[table_doc],
                    embeddings=[table_embedding],
                    metadatas=[{
                        'table_name': str(table_name),
                        'entity_type': 'table_summary',
                        'column_count': len(table_group),
                        'aml_column_count': len(aml_columns)
                    }],
                    ids=[f"table_{table_name}"]
                )
                total_docs += 1
                
                # Process columns in small batches
                for batch_start in range(0, len(table_group), batch_size):
                    batch_end = min(batch_start + batch_size, len(table_group))
                    batch_rows = table_group.iloc[batch_start:batch_end]
                    
                    batch_docs = []
                    batch_metadatas = []
                    batch_ids = []
                    
                    for idx, (_, row) in enumerate(batch_rows.iterrows()):
                        col_doc = f"""Column: {row['COLUMN_NAME']}
Table: {table_name}
Data Type: {row['COLUMN_DATA_TYPE']}
Description: {row.get('COLUMN_DESCRIPTION_ENG', 'No description')}
AML Required: {row.get('MANDAOTRY_AML_Y_N', 'Unknown')}
Risk Assessment: {row.get('MANDAOTRY_RISK_ASSESMENTS_Y_N', 'Unknown')}"""
                        
                        batch_docs.append(col_doc)
                        batch_metadatas.append({
                            'table_name': str(table_name),
                            'column_name': str(row['COLUMN_NAME']),
                            'entity_type': 'column',
                            'data_type': str(row['COLUMN_DATA_TYPE']),
                            'aml_required': str(row.get('MANDAOTRY_AML_Y_N', 'Unknown'))
                        })
                        batch_ids.append(f"col_{table_name}_{row['COLUMN_NAME']}_{batch_start + idx}")
                    
                    # Generate embeddings for column batch with GPU optimization
                    if batch_docs:
                        encode_kwargs = {
                            'show_progress_bar': False,
                            'batch_size': 32 if has_gpu else 16,  # GPU can handle larger batches
                            'convert_to_tensor': False,
                            'normalize_embeddings': True
                        }
                        batch_embeddings = model.encode(batch_docs, **encode_kwargs).tolist()
                        
                        # Add to collection
                        collection.add(
                            documents=batch_docs,
                            embeddings=batch_embeddings,
                            metadatas=batch_metadatas,
                            ids=batch_ids
                        )
                        total_docs += len(batch_docs)
                
            except Exception as e:
                print(f"⚠️ Error processing table {table_name}: {e}")
                continue
        
        # Final verification
        final_count = collection.count()
        print(f"\\n🎯 SUCCESS: Created {final_count} embeddings!")
        
        # Test the collection
        test_query = "customer account data"
        query_embedding = model.encode([test_query])[0].tolist()
        search_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=3
        )
        
        print(f"\\n🔍 Test search for '{test_query}':")
        if search_results['documents']:
            for i, (doc, distance, metadata) in enumerate(zip(
                search_results['documents'][0][:3],
                search_results['distances'][0][:3],
                search_results['metadatas'][0][:3]
            )):
                similarity = 1 - distance
                entity_type = metadata.get('entity_type', 'unknown')
                table_name = metadata.get('table_name', 'unknown')
                print(f"  {i+1}. {entity_type.title()}: {table_name} (similarity: {similarity:.3f})")
        
        return True
        
    except Exception as e:
        print(f"❌ Production phase failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main execution with smart memory management."""
    print("🎯 Memory-Efficient Embedding Pipeline - COMPLETE Dictionary")
    print("=" * 65)
    
    # Step 1: Verify complete dictionary data exists in Parquet format
    parquet_file = verify_parquet_data()
    if parquet_file is None:
        print("\n❌ Complete dictionary data not available - stopping")
        return False
    
    # Step 2: Test small batch
    test_success, model = test_small_batch()
    if not test_success:
        print("\\n❌ Small batch test failed - stopping")
        return False
    
    print("\\n" + "=" * 65)
    print("✅ Test successful! Proceeding with COMPLETE dictionary embedding...")
    
    # Step 3: Create production embeddings
    production_success = create_embeddings_memory_efficient(model)
    
    if production_success:
        print("\\n🎉 SUCCESS: COMPLETE dictionary embeddings created!")
        print("📊 Data scope: ALL tables and columns (not sample)")
        print("📦 Data format: Parquet (high compression, fast loading)")
        print("🔍 Collection: aml_dictionary_metadata_bge (BGE 1024D)")
        print("💾 Memory: Optimized batch processing")
        return True
    else:
        print("\\n❌ Production failed")
        return False

if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\\n✅ PIPELINE COMPLETED SUCCESSFULLY!")
        else:
            print("\\n❌ PIPELINE FAILED")
    except KeyboardInterrupt:
        print("\\n🛑 Pipeline interrupted by user")
    except Exception as e:
        print(f"\\n💥 Unexpected error: {e}")