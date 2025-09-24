"""
Smart embedding script that tests with 1 chunk first, then processes all data.
This prevents wasting time on full runs that might fail.
"""

import os
import sys
import json
import time
import pandas as pd
import chromadb
from chromadb.config import Settings
from pathlib import Path
from sentence_transformers import SentenceTransformer

def test_embedding_pipeline():
    """Test the embedding pipeline with just a few records to verify correctness."""
    print("🧪 TESTING PHASE: Testing embedding pipeline with small sample...")
    
    # Initialize BGE model
    print("Loading BGE model...")
    try:
        model = SentenceTransformer('BAAI/bge-large-en-v1.5')
        embedding_dim = model.get_sentence_embedding_dimension()
        print(f"✅ BGE model loaded (dimension: {embedding_dim})")
    except Exception as e:
        print(f"❌ Failed to load BGE model: {e}")
        return False, None, None
    
    # Setup ChromaDB for testing
    try:
        warehouse_path = Path(__file__).parent.parent / "warehouse"
        chroma_path = warehouse_path / "vectors"
        
        client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Create a test collection
        test_collection_name = "test_bge_embeddings"
        
        # Delete test collection if it exists
        try:
            client.delete_collection(test_collection_name)
        except:
            pass
            
        collection = client.create_collection(
            name=test_collection_name,
            metadata={"description": "Test collection for BGE embeddings"}
        )
        print(f"✅ Test collection created: {test_collection_name}")
        
    except Exception as e:
        print(f"❌ Failed to setup ChromaDB: {e}")
        return False, None, None
    
    # Load and test with sample data
    try:
        csv_file = warehouse_path / "dictionary_table_sample.csv"
        if not csv_file.exists():
            print(f"❌ CSV file not found: {csv_file}")
            return False, None, None
            
        df = pd.read_csv(csv_file)
        print(f"📊 Loaded CSV with {len(df)} total records")
        
        # Take just first 3 records for testing
        test_df = df.head(3)
        print(f"🧪 Testing with {len(test_df)} records")
        
        # Create test documents
        test_docs = []
        test_metadatas = []
        test_ids = []
        
        for idx, row in test_df.iterrows():
            # Create table summary
            table_content = f"""Table: {row['TABLE_NAME']}
Description: Table containing {row['TABLE_NAME']} data
Sample Column: {row['COLUMN_NAME']} ({row['COLUMN_DATA_TYPE']})
Column Description: {row.get('COLUMN_DESCRIPTION_ENG', 'No description available')}
AML Required: {row.get('MANDAOTRY_AML_Y_N', 'Unknown')}
Risk Assessment: {row.get('MANDAOTRY_RISK_ASSESMENTS_Y_N', 'Unknown')}"""
            
            test_docs.append(table_content)
            test_metadatas.append({
                'table_name': str(row['TABLE_NAME']),
                'entity_type': 'table_summary',
                'aml_required': str(row.get('MANDAOTRY_AML_Y_N', 'Unknown')),
                'column_sample': str(row['COLUMN_NAME'])
            })
            test_ids.append(f"test_table_{idx}")
        
        print(f"📝 Created {len(test_docs)} test documents")
        
        # Generate embeddings for test
        print("🔄 Generating test embeddings...")
        test_embeddings = model.encode(test_docs).tolist()
        print(f"✅ Generated {len(test_embeddings)} embeddings with dimension {len(test_embeddings[0])}")
        
        # Add to test collection
        collection.add(
            documents=test_docs,
            embeddings=test_embeddings,
            metadatas=test_metadatas,
            ids=test_ids
        )
        print(f"✅ Added {len(test_docs)} documents to test collection")
        
        # Test search functionality
        test_query = "customer data"
        query_embedding = model.encode([test_query])[0].tolist()
        
        search_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=2
        )
        
        print(f"🔍 Test search for '{test_query}':")
        if search_results['documents'] and search_results['documents'][0]:
            for i, (doc, distance) in enumerate(zip(search_results['documents'][0], search_results['distances'][0])):
                similarity = 1 - distance
                print(f"  Result {i+1}: Similarity {similarity:.3f}")
                print(f"  Content: {doc[:100]}...")
        
        # Clean up test collection
        client.delete_collection(test_collection_name)
        print("🧹 Cleaned up test collection")
        
        print("\n✅ TEST PHASE COMPLETED SUCCESSFULLY!")
        print(f"   - BGE model working: ✅")
        print(f"   - ChromaDB working: ✅") 
        print(f"   - Embedding dimension: {len(test_embeddings[0])}")
        print(f"   - Search working: ✅")
        
        return True, model, client
        
    except Exception as e:
        print(f"❌ Test phase failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None, None

def create_production_embeddings(model, client):
    """Create production embeddings after successful test."""
    print("\n🚀 PRODUCTION PHASE: Creating full embeddings...")
    
    try:
        warehouse_path = Path(__file__).parent.parent / "warehouse"
        csv_file = warehouse_path / "dictionary_table_sample.csv"
        
        df = pd.read_csv(csv_file)
        print(f"📊 Processing {len(df)} total records")
        
        # Delete existing collection if it exists
        collection_name = "aml_dictionary_metadata_bge"
        try:
            client.delete_collection(collection_name)
            print(f"🗑️ Deleted existing collection: {collection_name}")
        except:
            pass
        
        # Create new collection
        collection = client.create_collection(
            name=collection_name,
            metadata={"description": "AML Dictionary metadata with BGE embeddings", "model": "BAAI/bge-large-en-v1.5"}
        )
        print(f"✅ Created production collection: {collection_name}")
        
        # Process in batches to manage memory
        batch_size = 100
        total_docs = 0
        
        for batch_start in range(0, len(df), batch_size):
            batch_end = min(batch_start + batch_size, len(df))
            batch_df = df.iloc[batch_start:batch_end]
            
            print(f"📦 Processing batch {batch_start//batch_size + 1}/{(len(df)-1)//batch_size + 1} ({batch_start+1}-{batch_end} of {len(df)})")
            
            batch_docs = []
            batch_metadatas = []
            batch_ids = []
            
            # Group by table for this batch
            for table_name, table_group in batch_df.groupby('TABLE_NAME'):
                # Create table summary
                columns_info = []
                aml_columns = []
                
                for _, row in table_group.iterrows():
                    col_info = f"{row['COLUMN_NAME']} ({row['COLUMN_DATA_TYPE']})"
                    if str(row.get('COLUMN_DESCRIPTION_ENG', '')).strip():
                        col_info += f": {row['COLUMN_DESCRIPTION_ENG']}"
                    columns_info.append(col_info)
                    
                    if str(row.get('MANDAOTRY_AML_Y_N', '')).upper() == 'Y':
                        aml_columns.append(row['COLUMN_NAME'])
                
                table_summary = f"""Table: {table_name}
Description: Database table containing {len(table_group)} columns
Columns: {'; '.join(columns_info[:10])}{'...' if len(columns_info) > 10 else ''}
AML Columns: {len(aml_columns)} AML-required columns
Total Columns: {len(table_group)}
Business Purpose: Data storage and analysis table"""
                
                batch_docs.append(table_summary)
                batch_metadatas.append({
                    'table_name': str(table_name),
                    'entity_type': 'table_summary',
                    'column_count': len(table_group),
                    'aml_column_count': len(aml_columns)
                })
                batch_ids.append(f"table_summary_{table_name}")
                
                # Create individual column embeddings
                for idx, (_, row) in enumerate(table_group.iterrows()):
                    column_content = f"""Column: {row['COLUMN_NAME']}
Table: {table_name}
Data Type: {row['COLUMN_DATA_TYPE']}
Description: {row.get('COLUMN_DESCRIPTION_ENG', 'No description available')}
AML Required: {row.get('MANDAOTRY_AML_Y_N', 'Unknown')}
Risk Assessment: {row.get('MANDAOTRY_RISK_ASSESMENTS_Y_N', 'Unknown')}
Business Context: Column in {table_name} table for data analysis and reporting"""
                    
                    batch_docs.append(column_content)
                    batch_metadatas.append({
                        'table_name': str(table_name),
                        'column_name': str(row['COLUMN_NAME']),
                        'entity_type': 'column',
                        'data_type': str(row['COLUMN_DATA_TYPE']),
                        'aml_required': str(row.get('MANDAOTRY_AML_Y_N', 'Unknown')),
                        'risk_assessment': str(row.get('MANDAOTRY_RISK_ASSESMENTS_Y_N', 'Unknown')),
                        'description': str(row.get('COLUMN_DESCRIPTION_ENG', ''))
                    })
                    batch_ids.append(f"column_{table_name}_{row['COLUMN_NAME']}_{idx}")
            
            # Generate embeddings for batch
            print(f"🔄 Generating embeddings for {len(batch_docs)} documents...")
            batch_embeddings = model.encode(batch_docs, show_progress_bar=True).tolist()
            
            # Add to collection
            collection.add(
                documents=batch_docs,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                ids=batch_ids
            )
            
            total_docs += len(batch_docs)
            print(f"✅ Added batch to collection. Total documents: {total_docs}")
        
        # Final verification
        final_count = collection.count()
        print(f"\n🎯 PRODUCTION PHASE COMPLETED!")
        print(f"   - Total documents created: {final_count}")
        print(f"   - Collection name: {collection_name}")
        print(f"   - Model: BAAI/bge-large-en-v1.5")
        
        # Test production search
        test_query = "customer identification"
        query_embedding = model.encode([test_query])[0].tolist()
        search_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=3
        )
        
        print(f"\n🔍 Production search test for '{test_query}':")
        if search_results['documents'] and search_results['documents'][0]:
            for i, (doc, distance, metadata) in enumerate(zip(
                search_results['documents'][0], 
                search_results['distances'][0],
                search_results['metadatas'][0]
            )):
                similarity = 1 - distance
                print(f"  Result {i+1}: {metadata.get('table_name', 'Unknown')} - Similarity {similarity:.3f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Production phase failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main execution with test-first approach."""
    print("🎯 Smart Embedding Pipeline: Test First, Then Embed All")
    print("=" * 60)
    
    # Phase 1: Test with small sample
    test_success, model, client = test_embedding_pipeline()
    
    if not test_success:
        print("\n❌ TEST FAILED - Stopping execution to prevent waste")
        print("Please fix the issues above before proceeding.")
        return False
    
    # Ask for confirmation before proceeding
    print("\n" + "=" * 60)
    print("🎯 Test completed successfully!")
    print("Ready to proceed with full embedding creation?")
    print("This will process all data and may take several minutes...")
    
    # For automation, we'll proceed automatically after test success
    # In interactive mode, you could add input() here
    print("✅ Proceeding with production embedding creation...")
    
    # Phase 2: Create all embeddings
    production_success = create_production_embeddings(model, client)
    
    if production_success:
        print("\n🎉 SUCCESS: All embeddings created successfully!")
        print("You can now use the 'aml_dictionary_metadata_bge' collection in your web chat.")
        return True
    else:
        print("\n❌ PRODUCTION FAILED - But test data shows the pipeline works")
        print("Check the errors above and try again.")
        return False

if __name__ == "__main__":
    success = main()
    if success:
        print("\n✅ PIPELINE COMPLETED SUCCESSFULLY!")
    else:
        print("\n❌ PIPELINE FAILED - Please check errors above")