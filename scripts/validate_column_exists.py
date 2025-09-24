#!/usr/bin/env python3
"""
Script to validate if a specific column exists in the vector database.
This helps debug LLM hallucination issues where columns are mentioned but don't exist.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.agents.langgraph_orchestrator import VectorOnlyRetriever
import asyncio


async def validate_column_exists(column_name: str, table_name: str = None):
    """
    Validate if a specific column exists in the vector database.
    
    Args:
        column_name: The exact column name to search for
        table_name: Optional table name to filter results
    """
    print(f"🔍 Validating column: {column_name}")
    if table_name:
        print(f"📊 In table: {table_name}")
    print("=" * 60)
    
    try:
        # Initialize vector retriever
        retriever = VectorOnlyRetriever()
        await retriever.initialize()
        print("✅ Vector retriever initialized")
        
        # Search for exact column name
        exact_search = f"column_name:{column_name}"
        if table_name:
            exact_search += f" table_name:{table_name}"
            
        print(f"\n🔎 Searching for exact match: '{exact_search}'")
        exact_results = await retriever.search(exact_search, top_k=10)
        
        # Check for exact matches
        exact_matches = []
        for result in exact_results:
            meta = result.get('metadata', {})
            col_name = meta.get('column_name', '')
            tab_name = meta.get('table_name', '')
            
            if col_name.upper() == column_name.upper():
                if not table_name or tab_name.upper() == table_name.upper():
                    exact_matches.append(result)
        
        print(f"\n📊 EXACT MATCHES FOUND: {len(exact_matches)}")
        
        if exact_matches:
            print("\n✅ COLUMN EXISTS!")
            for i, match in enumerate(exact_matches):
                meta = match.get('metadata', {})
                content = match.get('content', '')
                score = match.get('similarity_score', 0)
                
                print(f"\n--- Match {i+1} ---")
                print(f"Column: {meta.get('column_name', 'Unknown')}")
                print(f"Table: {meta.get('table_name', 'Unknown')}")
                print(f"Data Type: {meta.get('data_type', 'Unknown')}")
                print(f"Score: {score:.4f}")
                print(f"Content Preview: {content[:200]}...")
        else:
            print("\n❌ COLUMN NOT FOUND!")
            
            # Try fuzzy search
            print(f"\n🔍 Trying fuzzy search for '{column_name}'...")
            fuzzy_results = await retriever.search(column_name, top_k=15)
            
            similar_columns = []
            for result in fuzzy_results:
                meta = result.get('metadata', {})
                col_name = meta.get('column_name', '')
                tab_name = meta.get('table_name', '')
                score = result.get('similarity_score', 0)
                
                if col_name and score > 0.3:  # Reasonable similarity threshold
                    similar_columns.append({
                        'column': col_name,
                        'table': tab_name,
                        'data_type': meta.get('data_type', 'Unknown'),
                        'score': score
                    })
            
            if similar_columns:
                print(f"\n🔍 SIMILAR COLUMNS FOUND ({len(similar_columns)}):")
                for i, col in enumerate(similar_columns[:10]):
                    print(f"{i+1:2}. {col['column']} in {col['table']} ({col['data_type']}) - Score: {col['score']:.4f}")
            else:
                print("\n❌ No similar columns found either")
                
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


async def search_columns_by_keyword(keyword: str, table_name: str = None):
    """
    Search for columns containing a specific keyword.
    """
    print(f"\n🔍 Searching for columns containing: '{keyword}'")
    if table_name:
        print(f"📊 In table: {table_name}")
    print("=" * 60)
    
    try:
        retriever = VectorOnlyRetriever()
        await retriever.initialize()
        
        # Search for keyword
        search_query = keyword
        if table_name:
            search_query += f" {table_name}"
            
        results = await retriever.search(search_query, top_k=20)
        
        # Filter and organize results
        matching_columns = []
        for result in results:
            meta = result.get('metadata', {})
            content = result.get('content', '')
            
            col_name = meta.get('column_name', '')
            tab_name = meta.get('table_name', '')
            data_type = meta.get('data_type', 'Unknown')
            score = result.get('similarity_score', 0)
            
            # Check if keyword appears in column name or content
            if (keyword.upper() in col_name.upper() or 
                keyword.upper() in content.upper()):
                
                if not table_name or tab_name.upper() == table_name.upper():
                    matching_columns.append({
                        'column': col_name,
                        'table': tab_name,
                        'data_type': data_type,
                        'score': score,
                        'content': content[:200]
                    })
        
        print(f"\n📊 COLUMNS CONTAINING '{keyword}': {len(matching_columns)}")
        
        if matching_columns:
            # Sort by score
            matching_columns.sort(key=lambda x: x['score'], reverse=True)
            
            for i, col in enumerate(matching_columns[:15]):
                print(f"\n--- Result {i+1} ---")
                print(f"Column: {col['column']}")
                print(f"Table: {col['table']}")
                print(f"Data Type: {col['data_type']}")
                print(f"Score: {col['score']:.4f}")
                print(f"Content: {col['content']}...")
        else:
            print(f"\n❌ No columns found containing '{keyword}'")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")


async def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python validate_column_exists.py <column_name> [table_name]")
        print("  python validate_column_exists.py NEW_OPENED_ACC")
        print("  python validate_column_exists.py NEW_OPENED_ACC PIO_ACCOUNTS")
        print("  python validate_column_exists.py --keyword OPENED")
        return
    
    if sys.argv[1] == "--keyword":
        if len(sys.argv) < 3:
            print("Please provide a keyword to search for")
            return
        keyword = sys.argv[2]
        table_name = sys.argv[3] if len(sys.argv) > 3 else None
        await search_columns_by_keyword(keyword, table_name)
    else:
        column_name = sys.argv[1]
        table_name = sys.argv[2] if len(sys.argv) > 2 else None
        await validate_column_exists(column_name, table_name)


if __name__ == "__main__":
    asyncio.run(main())