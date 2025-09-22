"""
Standalone script to explore the BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH table
This script connects directly to the database without dependencies on other modules.
"""

import os
import sys
import pandas as pd
import oracledb
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

def explore_dictionary_table():
    """Explore the structure and content of the dictionary table."""
    
    print("🔍 Exploring BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH table...")
    
    # Get database connection
    conn = get_oracle_connection()
    if not conn:
        return None
    
    try:
        # First, let's check if the table exists and get its structure
        print("\n📋 Getting dictionary table structure...")
        
        structure_query = """
        SELECT COLUMN_NAME, DATA_TYPE, NULLABLE, DATA_DEFAULT
        FROM ALL_TAB_COLUMNS 
        WHERE OWNER = 'BI_DWH' 
        AND TABLE_NAME = 'PIO_BANKBI_DICTIONARY_COL_DWH'
        ORDER BY COLUMN_ID
        """
        
        print("Executing structure query...")
        structure_df = pd.read_sql(structure_query, conn)
        
        if not structure_df.empty:
            print(f"\n✅ Dictionary table has {len(structure_df)} columns:")
            print(structure_df.to_string(index=False))
        else:
            print("❌ Could not retrieve table structure - table may not exist or no access")
            return None
            
        # Now let's get sample data from the dictionary table
        print("\n📊 Getting sample data from dictionary table...")
        
        sample_query = """
        SELECT * FROM (
            SELECT *
            FROM BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH
            ORDER BY TABLE_NAME, COLUMN_NAME
        ) WHERE ROWNUM <= 10
        """
        
        print("Executing sample data query...")
        sample_df = pd.read_sql(sample_query, conn)
        
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
            return None
            
        # Get count of tables and columns
        print("\n📈 Getting statistics...")
        
        stats_query = """
        SELECT 
            COUNT(DISTINCT TABLE_NAME) as Total_Tables,
            COUNT(*) as Total_Columns,
            COUNT(CASE WHEN MANDAOTRY_AML_Y_N = 'Y' THEN 1 END) as AML_Columns,
            COUNT(CASE WHEN MANDAOTRY_AML_Y_N = 'N' THEN 1 END) as Non_AML_Columns
        FROM BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH
        """
        
        stats_df = pd.read_sql(stats_query, conn)
        
        if not stats_df.empty:
            print(f"\n📊 Dictionary Table Statistics:")
            for col in stats_df.columns:
                print(f"  {col}: {stats_df[col].iloc[0]}")
        
        # Get sample of AML-specific columns
        print("\n🎯 Getting AML-specific columns sample...")
        
        aml_query = """
        SELECT * FROM (
            SELECT 
                TABLE_NAME, 
                COLUMN_NAME, 
                COLUMN_DESCRIPTION_ENG,
                COLUMN_DATA_TYPE,
                MANDAOTRY_AML_Y_N
            FROM BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH
            WHERE MANDAOTRY_AML_Y_N = 'Y'
            ORDER BY TABLE_NAME, COLUMN_NAME
        ) WHERE ROWNUM <= 10
        """
        
        aml_df = pd.read_sql(aml_query, conn)
        
        if not aml_df.empty:
            print(f"\n✅ Sample AML-specific columns:")
            print(aml_df.to_string(index=False))
        
        # Save sample data to CSV for analysis
        print("\n💾 Saving sample dictionary data to CSV...")
        
        full_query = """
        SELECT * FROM (
            SELECT *
            FROM BI_DWH.PIO_BANKBI_DICTIONARY_COL_DWH
            ORDER BY TABLE_NAME, COLUMN_NAME
        ) WHERE ROWNUM <= 1000
        """
        
        full_df = pd.read_sql(full_query, conn)
        
        if not full_df.empty:
            warehouse_path = Path(__file__).parent.parent / "warehouse"
            warehouse_path.mkdir(exist_ok=True)
            
            output_file = warehouse_path / "dictionary_table_sample.csv"
            full_df.to_csv(output_file, index=False)
            print(f"✅ Saved {len(full_df)} sample records to: {output_file}")
            
            # Also save just AML columns
            if 'MANDAOTRY_AML_Y_N' in full_df.columns:
                aml_full_df = full_df[full_df['MANDAOTRY_AML_Y_N'] == 'Y']
                aml_output_file = warehouse_path / "dictionary_table_aml_sample.csv"
                aml_full_df.to_csv(aml_output_file, index=False)
                print(f"✅ Saved {len(aml_full_df)} AML sample records to: {aml_output_file}")
            
        return full_df
        
    except Exception as e:
        print(f"❌ Error exploring dictionary table: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    finally:
        conn.close()

def analyze_table_coverage(df):
    """Analyze which tables have the most AML-relevant columns."""
    if df is None or df.empty:
        return
        
    print("\n🔍 Analyzing table coverage...")
    
    # Check if required columns exist
    if 'MANDAOTRY_AML_Y_N' not in df.columns:
        print("❌ MANDAOTRY_AML_Y_N column not found in data")
        return
    
    # Group by table and analyze AML column coverage
    table_analysis = df.groupby('TABLE_NAME').agg({
        'COLUMN_NAME': 'count',
        'MANDAOTRY_AML_Y_N': lambda x: (x == 'Y').sum()
    }).rename(columns={
        'COLUMN_NAME': 'Total_Columns',
        'MANDAOTRY_AML_Y_N': 'AML_Columns'
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
    print("🚀 Starting dictionary table exploration...")
    print("📝 Note: This script requires Oracle database credentials")
    print("   Set environment variables: ORACLE_USERNAME, ORACLE_PASSWORD, ORACLE_HOST, ORACLE_PORT, ORACLE_SERVICE")
    print("")
    
    df = explore_dictionary_table()
    
    if df is not None:
        analyze_table_coverage(df)
        print("\n✅ Dictionary table exploration completed!")
        print("\nNext steps:")
        print("1. Review the saved CSV files in warehouse/")
        print("2. Use this data to build comprehensive embeddings")
        print("3. Include column descriptions, data types, and AML flags in embeddings")
    else:
        print("\n❌ Failed to explore dictionary table")
        print("Please check database credentials and table access permissions")