"""
Path and encoding normalization utilities.
"""

from pathlib import Path
from typing import List, Tuple, Optional
import chardet
import os


def normalize_path_to_posix(path: Path) -> str:
    """Convert Windows path to POSIX relative path for storage."""
    return str(path).replace("\\", "/")


def normalize_encoding(file_path: Path) -> str:
    """Read file with proper encoding detection."""
    try:
        # First try UTF-8
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        # Fall back to chardet detection
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            
        detected = chardet.detect(raw_data)
        encoding = detected.get('encoding', 'utf-8')
        
        if encoding:
            try:
                return raw_data.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                # Last resort: replace errors
                return raw_data.decode('utf-8', errors='replace')
        else:
            return raw_data.decode('utf-8', errors='replace')


def convert_notebook_to_py(nb_content: str) -> str:
    """Convert Jupyter notebook content to Python code."""
    try:
        import json
        nb = json.loads(nb_content)
        
        code_cells = []
        for cell in nb.get('cells', []):
            if cell.get('cell_type') == 'code':
                source = cell.get('source', [])
                if isinstance(source, list):
                    code_cells.append(''.join(source))
                else:
                    code_cells.append(source)
        
        return '\n\n'.join(code_cells)
    except Exception:
        # If parsing fails, return empty string
        return ""


def is_text_file(file_path: Path) -> bool:
    """Check if file is a text file we should index."""
    text_extensions = {
        '.py', '.sql', '.md', '.txt', '.yaml', '.yml', 
        '.json', '.toml', '.cfg', '.ini', '.conf',
        '.rst', '.adoc', '.tex', '.html', '.css', '.js',
        '.sh', '.bat', '.ps1', '.dockerfile', '.gitignore'
    }
    
    # Handle files without extensions that are typically text
    text_names = {
        'readme', 'license', 'changelog', 'dockerfile', 
        'makefile', 'requirements'
    }
    
    ext = file_path.suffix.lower()
    name = file_path.name.lower()
    
    return ext in text_extensions or name in text_names


def get_file_kind(file_path: Path) -> str:
    """Determine if file is 'code' or 'text' for indexing."""
    code_extensions = {'.py', '.sql', '.yaml', '.yml', '.json', '.toml', '.cfg', '.ini'}
    
    if file_path.suffix.lower() in code_extensions:
        return "code"
    else:
        return "text"


def expand_files(root: Path, includes: List[str], excludes: List[str]) -> List[Path]:
    """
    Expand file patterns to get list of files to process.
    
    Args:
        root: Project root directory
        includes: List of glob patterns to include
        excludes: List of glob patterns to exclude
        
    Returns:
        List of Path objects for files to process
    """
    from fnmatch import fnmatch
    
    if not root.exists():
        return []
    
    all_files = []
    
    # If no includes specified, default to common patterns
    if not includes:
        includes = ['**/*.py', '**/*.sql', '**/*.md', '**/*.txt', '**/*.yaml', '**/*.yml']
    
    # Collect files matching include patterns
    for pattern in includes:
        all_files.extend(root.glob(pattern))
    
    # Filter out files matching exclude patterns
    filtered_files = []
    for file_path in all_files:
        # Get relative path for pattern matching
        try:
            rel_path = file_path.relative_to(root)
            rel_posix = normalize_path_to_posix(rel_path)
            
            # Check if file should be excluded
            excluded = False
            for exclude_pattern in excludes:
                if fnmatch(rel_posix, exclude_pattern):
                    excluded = True
                    break
            
            if not excluded and file_path.is_file() and is_text_file(file_path):
                filtered_files.append(file_path)
                
        except ValueError:
            # Skip files outside project root
            continue
    
    return filtered_files