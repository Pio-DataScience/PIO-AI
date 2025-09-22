"""
Schema tools for database dictionary access.
"""

import sys
import os
from typing import Optional, Dict, Any, List

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.ingest.db_dict import (
    describe_table, describe_column, search_schema_terms,
    read_table_definitions, read_table_comments, read_table_relationships
)


def describe_table_safe(name: str) -> Optional[Dict[str, Any]]:
    """
    Get table description with error handling.
    
    Args:
        name: Table name (case-insensitive)
        
    Returns:
        Table description dictionary or None if not found
    """
    try:
        return describe_table(name)
    except Exception as e:
        print(f"Warning: Error describing table {name}: {e}")
        return None


def describe_column_safe(table: str, column: str) -> Optional[Dict[str, Any]]:
    """
    Get column description with error handling.
    
    Args:
        table: Table name (case-insensitive)
        column: Column name (case-insensitive)
        
    Returns:
        Column description dictionary or None if not found
    """
    try:
        return describe_column(table, column)
    except Exception as e:
        print(f"Warning: Error describing column {table}.{column}: {e}")
        return None


def search_schema(search_term: str) -> List[Dict[str, Any]]:
    """
    Search for schema elements containing a term.
    
    Args:
        search_term: Term to search for in table/column names and comments
        
    Returns:
        List of matching schema elements
    """
    try:
        return search_schema_terms(search_term)
    except Exception as e:
        print(f"Warning: Error searching schema: {e}")
        return []


def get_table_relationships(table_name: str) -> List[Dict[str, Any]]:
    """
    Get relationships for a specific table.
    
    Args:
        table_name: Table name to get relationships for
        
    Returns:
        List of relationship dictionaries
    """
    try:
        relationships = read_table_relationships()
        return relationships.get(table_name.upper(), [])
    except Exception as e:
        print(f"Warning: Error getting relationships for {table_name}: {e}")
        return []


def get_related_tables(table_name: str) -> Dict[str, List[str]]:
    """
    Get tables related to the specified table.
    
    Args:
        table_name: Table name to find relations for
        
    Returns:
        Dictionary with 'references' and 'referenced_by' lists
    """
    try:
        table_name = table_name.upper()
        all_relationships = read_table_relationships()
        
        references = []      # Tables this table references (FK -> PK)
        referenced_by = []   # Tables that reference this table (PK <- FK)
        
        # Check relationships where this table is involved
        for table, rels in all_relationships.items():
            for rel in rels:
                if rel.get('foreign_table', '').upper() == table_name:
                    # This table is referenced by 'table'
                    referenced_by.append(table)
                elif table.upper() == table_name and 'foreign_table' in rel:
                    # This table references 'foreign_table'
                    references.append(rel['foreign_table'].upper())
        
        return {
            'references': list(set(references)),
            'referenced_by': list(set(referenced_by))
        }
        
    except Exception as e:
        print(f"Warning: Error getting related tables for {table_name}: {e}")
        return {'references': [], 'referenced_by': []}


def list_all_tables() -> List[str]:
    """
    Get list of all available tables.
    
    Returns:
        List of table names
    """
    try:
        # Get tables from DDL definitions
        ddl_tables = set(read_table_definitions().keys())
        
        # Get tables from comments
        comment_tables = set(read_table_comments().keys())
        
        # Get tables from relationships
        rel_tables = set(read_table_relationships().keys())
        
        # Combine all sources
        all_tables = ddl_tables | comment_tables | rel_tables
        
        return sorted(list(all_tables))
        
    except Exception as e:
        print(f"Warning: Error listing tables: {e}")
        return []


def get_table_columns(table_name: str) -> List[Dict[str, Any]]:
    """
    Get list of columns for a table.
    
    Args:
        table_name: Table name
        
    Returns:
        List of column information dictionaries
    """
    try:
        table_info = describe_table(table_name)
        if not table_info:
            return []
        
        columns = table_info.get('columns', {})
        column_list = []
        
        for column_name, comment in columns.items():
            column_list.append({
                'name': column_name,
                'comment': comment,
                'table': table_name.upper()
            })
        
        return sorted(column_list, key=lambda x: x['name'])
        
    except Exception as e:
        print(f"Warning: Error getting columns for {table_name}: {e}")
        return []


def search_columns(search_term: str) -> List[Dict[str, Any]]:
    """
    Search for columns containing a term.
    
    Args:
        search_term: Term to search for in column names and comments
        
    Returns:
        List of matching columns
    """
    try:
        results = search_schema_terms(search_term)
        return [r for r in results if r['type'] == 'column']
    except Exception as e:
        print(f"Warning: Error searching columns: {e}")
        return []


def search_tables(search_term: str) -> List[Dict[str, Any]]:
    """
    Search for tables containing a term.
    
    Args:
        search_term: Term to search for in table names and comments
        
    Returns:
        List of matching tables
    """
    try:
        results = search_schema_terms(search_term)
        return [r for r in results if r['type'] == 'table']
    except Exception as e:
        print(f"Warning: Error searching tables: {e}")
        return []


def analyze_column_name(column_name: str) -> Dict[str, Any]:
    """
    Analyze a column name to provide insights.
    
    Args:
        column_name: Column name to analyze
        
    Returns:
        Analysis results
    """
    column_name = column_name.upper()
    
    insights = {
        'name': column_name,
        'likely_type': 'unknown',
        'characteristics': []
    }
    
    # Analyze naming patterns
    if column_name.endswith('_ID') or column_name.endswith('_KEY'):
        insights['likely_type'] = 'identifier'
        insights['characteristics'].append('Primary/Foreign Key')
    
    elif column_name.endswith('_DATE') or column_name.endswith('_DT'):
        insights['likely_type'] = 'date'
        insights['characteristics'].append('Date field')
    
    elif column_name.endswith('_TIME') or column_name.endswith('_TS'):
        insights['likely_type'] = 'timestamp'
        insights['characteristics'].append('Timestamp field')
    
    elif column_name.endswith('_FLAG') or column_name.endswith('_IND'):
        insights['likely_type'] = 'boolean'
        insights['characteristics'].append('Boolean indicator')
    
    elif column_name.endswith('_AMT') or column_name.endswith('_AMOUNT'):
        insights['likely_type'] = 'currency'
        insights['characteristics'].append('Monetary amount')
    
    elif column_name.endswith('_CNT') or column_name.endswith('_COUNT'):
        insights['likely_type'] = 'integer'
        insights['characteristics'].append('Count field')
    
    elif column_name.endswith('_PCT') or column_name.endswith('_PERCENT'):
        insights['likely_type'] = 'percentage'
        insights['characteristics'].append('Percentage value')
    
    elif column_name.endswith('_DESC') or column_name.endswith('_DESCRIPTION'):
        insights['likely_type'] = 'text'
        insights['characteristics'].append('Description field')
    
    elif column_name.endswith('_CODE') or column_name.endswith('_CD'):
        insights['likely_type'] = 'code'
        insights['characteristics'].append('Code/Classification')
    
    elif column_name.endswith('_NAME') or column_name.endswith('_NM'):
        insights['likely_type'] = 'text'
        insights['characteristics'].append('Name field')
    
    # Search for this column across tables
    try:
        matches = search_columns(column_name)
        if matches:
            insights['found_in_tables'] = list(set(m['table_name'] for m in matches))
            insights['characteristics'].append(f'Found in {len(insights["found_in_tables"])} table(s)')
        else:
            insights['found_in_tables'] = []
    except:
        insights['found_in_tables'] = []
    
    return insights