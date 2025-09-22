"""
AST tools for code structure analysis using the symbols database.
"""

import sqlite3
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.ingest.manifest_reader import get_project_by_name


def sanitize_project_name(name: str) -> str:
    """Sanitize project name for filesystem use."""
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)


def get_symbols_db_path(project: str) -> Path:
    """Get path to symbols database for project."""
    package_root = Path(__file__).resolve().parents[3]
    sanitized_name = sanitize_project_name(project)
    return package_root / "indexes" / "symbols" / f"{sanitized_name}.sqlite"


def where_is_line(project: str, rel_posix: str, line: int) -> Optional[Dict[str, Any]]:
    """
    Find the enclosing AST node for a specific line in a file.
    
    Args:
        project: Project name from manifest
        rel_posix: Relative POSIX path under project root
        line: 1-based line number
        
    Returns:
        Dictionary with node information or None if not found
    """
    # Validate project exists
    try:
        get_project_by_name(project)
    except ValueError:
        raise ValueError(f"Project '{project}' not found in manifest")
    
    # Get symbols database path
    db_path = get_symbols_db_path(project)
    
    if not db_path.exists():
        raise FileNotFoundError(f"Symbols index not found for project '{project}'. Build it first with build_ast_index.py")
    
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        
        # Find the most specific (smallest) node that contains the line
        cursor = con.execute("""
            SELECT kind, qualname, start_line, end_line, start_col, end_col
            FROM symbols 
            WHERE file_path = ? AND start_line <= ? AND end_line >= ?
            ORDER BY (end_line - start_line), start_line
            LIMIT 1
        """, (rel_posix, line, line))
        
        row = cursor.fetchone()
        con.close()
        
        if row:
            return {
                'kind': row['kind'],
                'qualname': row['qualname'],
                'start_line': row['start_line'],
                'end_line': row['end_line'],
                'start_col': row['start_col'],
                'end_col': row['end_col'],
                'file_path': rel_posix,
                'line': line
            }
        
        return None
        
    except sqlite3.Error as e:
        raise ValueError(f"Error querying symbols database: {e}")


def get_symbols_in_file(project: str, rel_posix: str) -> List[Dict[str, Any]]:
    """
    Get all symbols (functions, classes, etc.) in a file.
    
    Args:
        project: Project name from manifest
        rel_posix: Relative POSIX path under project root
        
    Returns:
        List of symbol dictionaries
    """
    # Validate project exists
    try:
        get_project_by_name(project)
    except ValueError:
        raise ValueError(f"Project '{project}' not found in manifest")
    
    # Get symbols database path
    db_path = get_symbols_db_path(project)
    
    if not db_path.exists():
        return []
    
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        
        cursor = con.execute("""
            SELECT kind, qualname, start_line, end_line, start_col, end_col
            FROM symbols 
            WHERE file_path = ?
            ORDER BY start_line, start_col
        """, (rel_posix,))
        
        symbols = []
        for row in cursor.fetchall():
            symbols.append({
                'kind': row['kind'],
                'qualname': row['qualname'],
                'start_line': row['start_line'],
                'end_line': row['end_line'],
                'start_col': row['start_col'],
                'end_col': row['end_col'],
                'file_path': rel_posix
            })
        
        con.close()
        return symbols
        
    except sqlite3.Error:
        return []


def find_symbol_by_name(project: str, symbol_name: str, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Find symbols by name across the project.
    
    Args:
        project: Project name from manifest
        symbol_name: Name or qualified name to search for
        kind: Optional filter by symbol kind (function, class, etc.)
        
    Returns:
        List of matching symbols
    """
    # Validate project exists
    try:
        get_project_by_name(project)
    except ValueError:
        raise ValueError(f"Project '{project}' not found in manifest")
    
    # Get symbols database path
    db_path = get_symbols_db_path(project)
    
    if not db_path.exists():
        return []
    
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        
        # Search by qualified name or simple name
        if kind:
            cursor = con.execute("""
                SELECT kind, qualname, start_line, end_line, start_col, end_col, file_path
                FROM symbols 
                WHERE (qualname = ? OR qualname LIKE ?) AND kind = ?
                ORDER BY file_path, start_line
            """, (symbol_name, f"%.{symbol_name}", kind))
        else:
            cursor = con.execute("""
                SELECT kind, qualname, start_line, end_line, start_col, end_col, file_path
                FROM symbols 
                WHERE qualname = ? OR qualname LIKE ?
                ORDER BY file_path, start_line
            """, (symbol_name, f"%.{symbol_name}"))
        
        symbols = []
        for row in cursor.fetchall():
            symbols.append({
                'kind': row['kind'],
                'qualname': row['qualname'],
                'start_line': row['start_line'],
                'end_line': row['end_line'],
                'start_col': row['start_col'],
                'end_col': row['end_col'],
                'file_path': row['file_path']
            })
        
        con.close()
        return symbols
        
    except sqlite3.Error:
        return []


def get_function_signature(project: str, rel_posix: str, line: int) -> Optional[str]:
    """
    Get function signature for a function at a specific line.
    
    Args:
        project: Project name from manifest
        rel_posix: Relative POSIX path under project root
        line: Line number within the function
        
    Returns:
        Function signature string or None
    """
    symbol = where_is_line(project, rel_posix, line)
    
    if not symbol or symbol['kind'] not in ('function', 'method', 'async_function'):
        return None
    
    # For now, return the qualified name
    # Could be enhanced to parse actual signature from source
    return symbol['qualname']


def get_class_members(project: str, class_qualname: str) -> List[Dict[str, Any]]:
    """
    Get all members (methods, properties) of a class.
    
    Args:
        project: Project name from manifest
        class_qualname: Qualified name of the class
        
    Returns:
        List of class member symbols
    """
    # Validate project exists
    try:
        get_project_by_name(project)
    except ValueError:
        raise ValueError(f"Project '{project}' not found in manifest")
    
    # Get symbols database path
    db_path = get_symbols_db_path(project)
    
    if not db_path.exists():
        return []
    
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        
        # Find methods and properties of the class
        cursor = con.execute("""
            SELECT kind, qualname, start_line, end_line, start_col, end_col, file_path
            FROM symbols 
            WHERE qualname LIKE ? AND kind IN ('method', 'property', 'async_method')
            ORDER BY start_line
        """, (f"{class_qualname}.%",))
        
        members = []
        for row in cursor.fetchall():
            members.append({
                'kind': row['kind'],
                'qualname': row['qualname'],
                'start_line': row['start_line'],
                'end_line': row['end_line'],
                'start_col': row['start_col'],
                'end_col': row['end_col'],
                'file_path': row['file_path']
            })
        
        con.close()
        return members
        
    except sqlite3.Error:
        return []


def get_symbols_stats(project: str) -> Optional[Dict[str, Any]]:
    """
    Get statistics about symbols in the project.
    
    Args:
        project: Project name from manifest
        
    Returns:
        Statistics dictionary or None if no index
    """
    # Validate project exists
    try:
        get_project_by_name(project)
    except ValueError:
        raise ValueError(f"Project '{project}' not found in manifest")
    
    # Get symbols database path
    db_path = get_symbols_db_path(project)
    
    if not db_path.exists():
        return None
    
    try:
        con = sqlite3.connect(db_path)
        
        # Get total counts by kind
        cursor = con.execute("""
            SELECT kind, COUNT(*) as count
            FROM symbols 
            GROUP BY kind
            ORDER BY count DESC
        """)
        
        by_kind = {}
        total = 0
        for row in cursor.fetchall():
            kind, count = row
            by_kind[kind] = count
            total += count
        
        # Get file count
        cursor = con.execute("SELECT COUNT(DISTINCT file_path) FROM symbols")
        file_count = cursor.fetchone()[0]
        
        con.close()
        
        return {
            'total_symbols': total,
            'files_with_symbols': file_count,
            'by_kind': by_kind
        }
        
    except sqlite3.Error:
        return None