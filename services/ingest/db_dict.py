"""
Database dictionary and schema information reader.
"""

import yaml
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any
import sys
import os

# Package root
PACKAGE_ROOT = Path(__file__).resolve().parents[3]


def get_db_dict_path() -> Path:
    """Get path to database dictionary directory."""
    return PACKAGE_ROOT / "warehouse" / "db" / "oracle"


def read_table_definitions() -> Dict[str, Any]:
    """Read table DDL definitions if available."""
    ddl_path = get_db_dict_path() / "ddl"
    tables = {}
    
    if not ddl_path.exists():
        return tables
    
    for ddl_file in ddl_path.glob("*.sql"):
        table_name = ddl_file.stem.upper()
        try:
            with open(ddl_file, 'r', encoding='utf-8') as f:
                tables[table_name] = {
                    'ddl': f.read(),
                    'file': str(ddl_file)
                }
        except Exception as e:
            print(f"Warning: Could not read DDL for {table_name}: {e}")
    
    return tables


def read_table_comments() -> Dict[str, Dict[str, str]]:
    """Read table and column comments if available."""
    comments_path = get_db_dict_path() / "comments.yaml"
    
    if not comments_path.exists():
        return {}
    
    try:
        with open(comments_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: Could not read comments.yaml: {e}")
        return {}


def read_table_relationships() -> Dict[str, List[Dict[str, str]]]:
    """Read table relationships if available."""
    rel_path = get_db_dict_path() / "relationships.yaml"
    
    if not rel_path.exists():
        return {}
    
    try:
        with open(rel_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: Could not read relationships.yaml: {e}")
        return {}


def read_table_profiles() -> Dict[str, Dict[str, Any]]:
    """Read table data profiles if available."""
    profiles_path = get_db_dict_path() / "profiles.yaml"
    
    if not profiles_path.exists():
        return {}
    
    try:
        with open(profiles_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: Could not read profiles.yaml: {e}")
        return {}


def describe_table(table_name: str) -> Optional[Dict[str, Any]]:
    """Get comprehensive table description."""
    table_name = table_name.upper()
    
    # Gather all available information
    ddl_info = read_table_definitions().get(table_name, {})
    comments = read_table_comments().get(table_name, {})
    relationships = read_table_relationships().get(table_name, [])
    profiles = read_table_profiles().get(table_name, {})
    
    if not any([ddl_info, comments, relationships, profiles]):
        return None
    
    return {
        'table_name': table_name,
        'ddl': ddl_info.get('ddl', ''),
        'table_comment': comments.get('table_comment', ''),
        'columns': comments.get('columns', {}),
        'relationships': relationships,
        'profile': profiles
    }


def describe_column(table_name: str, column_name: str) -> Optional[Dict[str, Any]]:
    """Get specific column information."""
    table_info = describe_table(table_name)
    
    if not table_info:
        return None
    
    column_name = column_name.upper()
    columns = table_info.get('columns', {})
    column_info = columns.get(column_name)
    
    if not column_info:
        return None
    
    return {
        'table_name': table_name.upper(),
        'column_name': column_name,
        'comment': column_info,
        'table_comment': table_info.get('table_comment', '')
    }


def search_schema_terms(search_term: str) -> List[Dict[str, Any]]:
    """Search for tables/columns containing a term."""
    results = []
    search_term = search_term.upper()
    
    # Search table names and comments
    comments = read_table_comments()
    for table_name, table_data in comments.items():
        # Check table name
        if search_term in table_name:
            results.append({
                'type': 'table',
                'table_name': table_name,
                'match_type': 'table_name',
                'match_text': table_name
            })
        
        # Check table comment
        table_comment = table_data.get('table_comment', '')
        if search_term in table_comment.upper():
            results.append({
                'type': 'table',
                'table_name': table_name,
                'match_type': 'table_comment',
                'match_text': table_comment
            })
        
        # Check column names and comments
        columns = table_data.get('columns', {})
        for column_name, column_comment in columns.items():
            if search_term in column_name:
                results.append({
                    'type': 'column',
                    'table_name': table_name,
                    'column_name': column_name,
                    'match_type': 'column_name',
                    'match_text': column_name
                })
            
            if search_term in column_comment.upper():
                results.append({
                    'type': 'column',
                    'table_name': table_name,
                    'column_name': column_name,
                    'match_type': 'column_comment',
                    'match_text': column_comment
                })
    
    return results