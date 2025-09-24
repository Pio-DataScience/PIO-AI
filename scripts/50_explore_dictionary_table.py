"""
Script to export the COMPLETE BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH table.
Exports ALL tables and columns (no sampling limits) directly to Parquet format.
This replaces the old CSV workflow with high-performance Parquet export.
"""

import os
import sys
import pandas as pd
from pathlib import Path
import oracledb

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Direct import
sys.path.append(str(project_root / "services" / "db"))
from metadata_harvester import MetadataHarvester

def explore_dictionary_table():
    """Explore the structure and content of the dictionary table."""
    
    print("🔍 Exploring BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH table...")
    
    # Initialize metadata harvester
    harvester = MetadataHarvester()
    
    try:
        # First, let's get the structure of the dictionary table itself
        print("\n📋 Getting dictionary table structure...")
        
        structure_query = """
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = 'BI_DWH' 
        AND TABLE_NAME = 'PIO_BANKBI_DICTIONARY_COL_DWH'
        ORDER BY ORDINAL_POSITION
        """
        
        print("Executing structure query...")
        structure_df = harvester.execute_query(structure_query)
        
        if not structure_df.empty:
            print(f"\n✅ Dictionary table has {len(structure_df)} columns:")
            print(structure_df.to_string(index=False))
        else:
            print("❌ Could not retrieve table structure")
            
        # Now let's get sample data from the dictionary table
        print("\n📊 Getting sample data from dictionary table...")
        
        sample_query = """
        SELECT TOP 10 *
        FROM BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH
        ORDER BY TABLE_NAME, COLUMN_NAME
        """
        
        print("Executing sample data query...")
        sample_df = harvester.execute_query(sample_query)
        
        if not sample_df.empty:
            print(f"\n✅ Retrieved {len(sample_df)} sample records:")
            print("\nColumn names in the dictionary table:")
            for i, col in enumerate(sample_df.columns, 1):
                print(f"  {i:2d}. {col}")
            
            print("\n📋 Sample records (first 3 rows):")
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', None)
            pd.set_option('display.max_colwidth', 50)
            
            for idx, row in sample_df.head(3).iterrows():
                print(f"\n--- Record {idx + 1} ---")
                for col in sample_df.columns:
                    value = str(row[col])[:50] if pd.notna(row[col]) else "NULL"
                    print(f"  {col}: {value}")
        else:
            print("❌ Could not retrieve sample data")
            
        # Get count of tables and columns
        print("\n📈 Getting statistics...")
        
        stats_query = """
        SELECT 
            COUNT(DISTINCT TABLE_NAME) as Total_Tables,
            COUNT(*) as Total_Columns,
            COUNT(CASE WHEN MANDATORY_AML_Y_N = 'Y' THEN 1 END) as AML_Columns,
            COUNT(CASE WHEN MANDATORY_AML_Y_N = 'N' THEN 1 END) as Non_AML_Columns
        FROM BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH
        """
        
        stats_df = harvester.execute_query(stats_query)
        
        if not stats_df.empty:
            print(f"\n📊 Dictionary Table Statistics:")
            for col in stats_df.columns:
                print(f"  {col}: {stats_df[col].iloc[0]}")
        
        # Get sample of AML-specific columns
        print("\n🎯 Getting AML-specific columns sample...")
        
        aml_query = """
        SELECT TOP 5 
            TABLE_NAME, 
            COLUMN_NAME, 
            COLUMN_DESCRIPTION_ENG,
            COLUMN_DATA_TYPE,
            MANDATORY_AML_Y_N
        FROM BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH
        WHERE MANDATORY_AML_Y_N = 'Y'
        ORDER BY TABLE_NAME, COLUMN_NAME
        """
        
        aml_df = harvester.execute_query(aml_query)
        
        if not aml_df.empty:
            print(f"\n✅ Sample AML-specific columns:")
            print(aml_df.to_string(index=False))
        
        # Save full data directly to Parquet for high performance
        print("\n💾 Saving COMPLETE dictionary data to Parquet...")
        
        full_query = """
        SELECT *
        FROM BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH
        ORDER BY TABLE_NAME, COLUMN_NAME
        """
        
        full_df = harvester.execute_query(full_query)
        
        if not full_df.empty:
            # Save complete dataset as Parquet (no CSV files)
            output_file = project_root / "warehouse" / "dictionary_data.parquet"
            full_df.to_parquet(output_file, compression='snappy', index=False)
            print(f"✅ Saved COMPLETE {len(full_df)} records to: {output_file}")
            print(f"📊 Tables: {full_df['TABLE_NAME'].nunique()}")
            print(f"📊 Total Columns: {len(full_df)}")
            print(f"📊 AML Columns: {(full_df['MANDATORY_AML_Y_N'] == 'Y').sum()}")
            
            # Also save just AML columns as separate parquet
            aml_full_df = full_df[full_df['MANDATORY_AML_Y_N'] == 'Y']
            aml_output_file = project_root / "warehouse" / "dictionary_aml_only.parquet"
            aml_full_df.to_parquet(aml_output_file, compression='snappy', index=False)
            print(f"✅ Saved {len(aml_full_df)} AML records to: {aml_output_file}")
            
        return full_df
        
    except Exception as e:
        print(f"❌ Error exploring dictionary table: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    finally:
        harvester.close()

def analyze_table_coverage(df):
    """Analyze which tables have the most AML-relevant columns."""
    if df is None or df.empty:
        return
        
    print("\n🔍 Analyzing table coverage...")
    
    # Group by table and analyze AML column coverage
    table_analysis = df.groupby('TABLE_NAME').agg({
        'COLUMN_NAME': 'count',
        'MANDATORY_AML_Y_N': lambda x: (x == 'Y').sum()
    }).rename(columns={
        'COLUMN_NAME': 'Total_Columns',
        'MANDATORY_AML_Y_N': 'AML_Columns'
    })
    
    table_analysis['AML_Percentage'] = (table_analysis['AML_Columns'] / table_analysis['Total_Columns'] * 100).round(1)
    table_analysis = table_analysis.sort_values('AML_Columns', ascending=False)
    
    print(f"\n📊 Top 10 tables by AML column count:")
    print(table_analysis.head(10).to_string())
    
    # Find tables with specific keywords
    aml_tables = table_analysis[table_analysis.index.str.contains('AML|CUSTOMER|TRANSACTION|RISK', case=False, na=False)]
    if not aml_tables.empty:
        print(f"\n🎯 AML-related tables (by name):")
        print(aml_tables.to_string())

if __name__ == "__main__":
    print("🚀 Starting COMPLETE dictionary table export...")
    df = explore_dictionary_table()
    
    if df is not None:
        analyze_table_coverage(df)
        print("\n✅ COMPLETE dictionary table export completed!")
        print("\nNext steps:")
        print("1. Review dictionary_data.parquet in warehouse/ (COMPLETE dataset)")
        print("2. Run: python scripts/57_memory_efficient_embeddings.py")
        print("3. This will create embeddings for ALL tables and columns (not sample)")
        print(f"4. Total data: {len(df):,} records from {df['TABLE_NAME'].nunique()} tables")
    else:
        print("\n❌ Failed to export complete dictionary table")