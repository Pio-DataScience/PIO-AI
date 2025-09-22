"""
Call & Import Graph Indexer

Analyzes Python files to build a graph of:
- Import relationships (what modules/symbols each file imports)
- Call relationships (what functions/methods each function calls)
"""

import ast
import sqlite3
import sys
import os
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional, Set
from dataclasses import dataclass

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.ingest.normalizer import expand_files, normalize_path_to_posix, normalize_encoding


@dataclass
class ImportInfo:
    """Information about an import statement."""
    file_path: str
    kind: str  # "import" or "importfrom"
    module: str
    name: Optional[str] = None
    asname: Optional[str] = None


@dataclass 
class CallInfo:
    """Information about a function/method call."""
    file_path: str
    caller_qual: str  # qualified name of the calling function
    callee_name: str  # name of the called function/method
    lineno: int


class GraphIndexer:
    """Builds call and import graphs for Python projects."""
    
    def __init__(self):
        self.current_file_path = ""
        self.current_module_path = ""
        self.class_stack = []
        self.function_stack = []
    
    def expand_files(self, root: Path, includes: List[str], excludes: List[str]) -> List[Path]:
        """Get list of Python files to analyze."""
        all_files = expand_files(root, includes, excludes)
        return [f for f in all_files if f.suffix == '.py']
    
    def parse_graph_for_file(self, root: Path, file_path: Path) -> Tuple[List[ImportInfo], List[CallInfo]]:
        """Parse a single Python file for imports and calls."""
        try:
            content = normalize_encoding(file_path)
            tree = ast.parse(content, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"Warning: Could not parse {file_path}: {e}")
            return [], []
        
        # Set up context
        rel_path = file_path.relative_to(root)
        self.current_file_path = normalize_path_to_posix(rel_path)
        self.current_module_path = self._path_to_module(rel_path)
        self.class_stack = []
        self.function_stack = []
        
        # Collect imports and calls
        imports = []
        calls = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.extend(self._extract_imports(node))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self._update_context_stack(node)
            elif isinstance(node, ast.Call):
                call_info = self._extract_call(node)
                if call_info:
                    calls.append(call_info)
        
        return imports, calls
    
    def _path_to_module(self, rel_path: Path) -> str:
        """Convert file path to Python module notation."""
        parts = rel_path.with_suffix('').parts
        return '.'.join(parts)
    
    def _extract_imports(self, node) -> List[ImportInfo]:
        """Extract import information from AST node."""
        imports = []
        
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(
                    file_path=self.current_file_path,
                    kind="import",
                    module=alias.name,
                    name=None,
                    asname=alias.asname
                ))
        
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(ImportInfo(
                    file_path=self.current_file_path,
                    kind="importfrom", 
                    module=module,
                    name=alias.name,
                    asname=alias.asname
                ))
        
        return imports
    
    def _update_context_stack(self, node):
        """Update the current class/function context."""
        if isinstance(node, ast.ClassDef):
            self.class_stack.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.function_stack.append(node.name)
    
    def _get_current_qualifier(self) -> str:
        """Get the qualified name of the current function."""
        parts = [self.current_module_path]
        parts.extend(self.class_stack)
        parts.extend(self.function_stack)
        return '.'.join(parts)
    
    def _extract_call(self, node: ast.Call) -> Optional[CallInfo]:
        """Extract call information from AST Call node."""
        callee_name = self._get_call_name(node.func)
        if not callee_name:
            return None
        
        caller_qual = self._get_current_qualifier()
        if not any(self.function_stack):  # Not inside a function
            return None
        
        return CallInfo(
            file_path=self.current_file_path,
            caller_qual=caller_qual,
            callee_name=callee_name,
            lineno=node.lineno
        )
    
    def _get_call_name(self, node) -> Optional[str]:
        """Extract the called function/method name."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            # For method calls like obj.method()
            parts = []
            current = node
            
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            
            if isinstance(current, ast.Name):
                parts.append(current.id)
                parts.reverse()
                return '.'.join(parts)
        
        return None


def create_graph_schema(con: sqlite3.Connection):
    """Create the database schema for graph index."""
    con.execute("PRAGMA journal_mode=WAL")
    
    # Files table
    con.execute("""
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY
        )
    """)
    
    # Imports table  
    con.execute("""
        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            kind TEXT NOT NULL,
            module TEXT NOT NULL,
            name TEXT,
            asname TEXT,
            FOREIGN KEY (file_path) REFERENCES files (path)
        )
    """)
    
    # Calls table
    con.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            caller_qual TEXT NOT NULL,
            callee_name TEXT NOT NULL,
            lineno INTEGER NOT NULL,
            FOREIGN KEY (file_path) REFERENCES files (path)
        )
    """)
    
    # Create indexes for performance
    con.execute("CREATE INDEX IF NOT EXISTS idx_imports_file_path ON imports (file_path)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_imports_module ON imports (module)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_calls_file_path ON calls (file_path)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_calls_caller_qual ON calls (caller_qual)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_calls_callee_name ON calls (callee_name)")
    
    con.commit()


def build_project_graph(project_name: str, root: Path, includes: List[str], 
                       excludes: List[str], out_db: Path) -> Dict[str, int]:
    """Build call and import graph for a project."""
    indexer = GraphIndexer()
    
    # Get Python files to analyze
    files = indexer.expand_files(root, includes, excludes)
    
    # Create database and schema
    out_db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(out_db)
    create_graph_schema(con)
    
    # Clear existing data
    con.execute("DELETE FROM calls")
    con.execute("DELETE FROM imports") 
    con.execute("DELETE FROM files")
    
    # Process each file
    total_imports = 0
    total_calls = 0
    
    for file_path in files:
        try:
            # Add file to files table
            rel_path = normalize_path_to_posix(file_path.relative_to(root))
            con.execute("INSERT OR IGNORE INTO files (path) VALUES (?)", (rel_path,))
            
            # Parse imports and calls
            imports, calls = indexer.parse_graph_for_file(root, file_path)
            
            # Insert imports
            for imp in imports:
                con.execute("""
                    INSERT INTO imports (file_path, kind, module, name, asname)
                    VALUES (?, ?, ?, ?, ?)
                """, (imp.file_path, imp.kind, imp.module, imp.name, imp.asname))
            
            # Insert calls  
            for call in calls:
                con.execute("""
                    INSERT INTO calls (file_path, caller_qual, callee_name, lineno)
                    VALUES (?, ?, ?, ?)
                """, (call.file_path, call.caller_qual, call.callee_name, call.lineno))
            
            total_imports += len(imports)
            total_calls += len(calls)
            
        except Exception as e:
            print(f"Warning: Error processing {file_path}: {e}")
    
    con.commit()
    con.close()
    
    return {
        'files': len(files),
        'imports': total_imports, 
        'calls': total_calls
    }


def callees_of(con: sqlite3.Connection, caller_qual: str) -> List[Dict[str, Any]]:
    """Get all functions/methods called by a given function."""
    cursor = con.execute("""
        SELECT callee_name, file_path, lineno, COUNT(*) as call_count
        FROM calls 
        WHERE caller_qual = ?
        GROUP BY callee_name, file_path
        ORDER BY call_count DESC
    """, (caller_qual,))
    
    return [
        {
            'callee_name': row[0],
            'file_path': row[1], 
            'first_lineno': row[2],
            'call_count': row[3]
        }
        for row in cursor.fetchall()
    ]


def callers_of(con: sqlite3.Connection, callee_name: str) -> List[Dict[str, Any]]:
    """Get all functions that call a given function/method."""
    cursor = con.execute("""
        SELECT caller_qual, file_path, lineno, COUNT(*) as call_count
        FROM calls
        WHERE callee_name = ? OR callee_name LIKE ?
        GROUP BY caller_qual, file_path
        ORDER BY call_count DESC
    """, (callee_name, f"%.{callee_name}"))
    
    return [
        {
            'caller_qual': row[0],
            'file_path': row[1],
            'first_lineno': row[2], 
            'call_count': row[3]
        }
        for row in cursor.fetchall()
    ]