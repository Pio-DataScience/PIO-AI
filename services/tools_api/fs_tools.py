"""
File system tools for safe file access within project boundaries.
"""

import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.ingest.manifest_reader import get_project_by_name
from services.ingest.normalizer import normalize_encoding


def read_file(project: str, rel_posix: str, start: int = 1, end: Optional[int] = None) -> str:
    """
    Read file content within project boundaries.
    
    Args:
        project: Project name from manifest
        rel_posix: Relative POSIX path under project root
        start: Start line number (1-based)
        end: End line number (1-based, inclusive). If None, reads to end.
        
    Returns:
        File content for the specified line range
        
    Raises:
        ValueError: If project not found, path invalid, or access denied
        FileNotFoundError: If file doesn't exist
    """
    # Get project root from manifest
    project_info = get_project_by_name(project)
    project_root = Path(project_info['root_path'])  # Fixed: was 'root'
    
    # Construct file path (convert POSIX back to local path)
    file_path = project_root / rel_posix.replace('/', os.sep)
    
    # Security check: ensure file is within project root
    try:
        file_path = file_path.resolve()
        project_root = project_root.resolve()
        file_path.relative_to(project_root)
    except ValueError:
        raise ValueError(f"Path {rel_posix} is outside project root {project_root}")
    
    # Check file exists
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {rel_posix}")
    
    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {rel_posix}")
    
    # Read file content
    try:
        content = normalize_encoding(file_path)
        lines = content.split('\n')
        
        # Clamp line numbers
        start = max(1, start)
        if end is None:
            end = len(lines)
        else:
            end = min(len(lines), end)
        
        # Extract line range (convert to 0-based indexing)
        selected_lines = lines[start-1:end]
        
        return '\n'.join(selected_lines)
        
    except Exception as e:
        raise ValueError(f"Error reading file {rel_posix}: {e}")


def list_dir_safe(project: str, rel_posix: str = "") -> List[Dict[str, Any]]:
    """
    List directory contents within project boundaries.
    
    Args:
        project: Project name from manifest
        rel_posix: Relative POSIX path under project root (empty for root)
        
    Returns:
        List of directory entries with metadata
        
    Raises:
        ValueError: If project not found or path invalid
    """
    # Get project root from manifest
    project_info = get_project_by_name(project)
    project_root = Path(project_info['root_path'])  # Fixed: was 'root'
    
    # Construct directory path
    if rel_posix:
        dir_path = project_root / rel_posix.replace('/', os.sep)
    else:
        dir_path = project_root
    
    # Security check: ensure path is within project root
    try:
        dir_path = dir_path.resolve()
        project_root = project_root.resolve()
        dir_path.relative_to(project_root)
    except ValueError:
        raise ValueError(f"Path {rel_posix} is outside project root {project_root}")
    
    # Check directory exists
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {rel_posix}")
    
    if not dir_path.is_dir():
        raise ValueError(f"Path is not a directory: {rel_posix}")
    
    # List contents
    entries = []
    
    try:
        for item in dir_path.iterdir():
            try:
                # Get relative path from project root
                rel_item_path = item.relative_to(project_root)
                rel_posix_path = str(rel_item_path).replace(os.sep, '/')
                
                entry = {
                    'name': item.name,
                    'path': rel_posix_path,
                    'is_file': item.is_file(),
                    'is_dir': item.is_dir(),
                    'size': item.stat().st_size if item.is_file() else None,
                    'modified': item.stat().st_mtime
                }
                
                entries.append(entry)
                
            except (OSError, ValueError):
                # Skip files we can't access or are outside project
                continue
        
        # Sort: directories first, then files, alphabetically
        entries.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        
        return entries
        
    except Exception as e:
        raise ValueError(f"Error listing directory {rel_posix}: {e}")


def file_exists(project: str, rel_posix: str) -> bool:
    """
    Check if file exists within project boundaries.
    
    Args:
        project: Project name from manifest
        rel_posix: Relative POSIX path under project root
        
    Returns:
        True if file exists and is accessible
    """
    try:
        # Get project root from manifest
        project_info = get_project_by_name(project)
        project_root = Path(project_info['root_path'])  # Fixed: was 'root'
        
        # Construct file path
        file_path = project_root / rel_posix.replace('/', os.sep)
        
        # Security check
        file_path = file_path.resolve()
        project_root = project_root.resolve()
        file_path.relative_to(project_root)
        
        return file_path.exists() and file_path.is_file()
        
    except (ValueError, FileNotFoundError):
        return False


def get_file_info(project: str, rel_posix: str) -> Optional[Dict[str, Any]]:
    """
    Get file information within project boundaries.
    
    Args:
        project: Project name from manifest
        rel_posix: Relative POSIX path under project root
        
    Returns:
        File information dict or None if not found
    """
    try:
        # Get project root from manifest
        project_info = get_project_by_name(project)
        project_root = Path(project_info['root_path'])  # Fixed: was 'root'
        
        # Construct file path
        file_path = project_root / rel_posix.replace('/', os.sep)
        
        # Security check
        file_path = file_path.resolve()
        project_root = project_root.resolve()
        file_path.relative_to(project_root)
        
        if not file_path.exists():
            return None
        
        stat = file_path.stat()
        
        return {
            'name': file_path.name,
            'path': rel_posix,
            'size': stat.st_size,
            'modified': stat.st_mtime,
            'is_file': file_path.is_file(),
            'is_dir': file_path.is_dir(),
            'extension': file_path.suffix,
            'parent': str(file_path.parent.relative_to(project_root)).replace(os.sep, '/')
        }
        
    except (ValueError, OSError):
        return None


def get_line_count(project: str, rel_posix: str) -> Optional[int]:
    """
    Get number of lines in a text file.
    
    Args:
        project: Project name from manifest
        rel_posix: Relative POSIX path under project root
        
    Returns:
        Number of lines or None if not accessible
    """
    try:
        content = read_file(project, rel_posix)
        return len(content.split('\n'))
    except (ValueError, FileNotFoundError):
        return None


def search_files_by_name(project: str, pattern: str, max_results: int = 50) -> List[Dict[str, Any]]:
    """
    Search for files by name pattern within project.
    
    Args:
        project: Project name from manifest
        pattern: Filename pattern (supports * and ? wildcards)
        max_results: Maximum number of results
        
    Returns:
        List of matching file information
    """
    from fnmatch import fnmatch
    
    try:
        # Get project root from manifest
        project_info = get_project_by_name(project)
        project_root = Path(project_info['root_path'])  # Fixed: was 'root'
        
        matches = []
        
        # Walk the project directory
        for file_path in project_root.rglob('*'):
            if len(matches) >= max_results:
                break
                
            if file_path.is_file() and fnmatch(file_path.name, pattern):
                try:
                    rel_path = file_path.relative_to(project_root)
                    rel_posix = str(rel_path).replace(os.sep, '/')
                    
                    stat = file_path.stat()
                    matches.append({
                        'name': file_path.name,
                        'path': rel_posix,
                        'size': stat.st_size,
                        'modified': stat.st_mtime,
                        'extension': file_path.suffix
                    })
                    
                except (ValueError, OSError):
                    continue
        
        return matches
        
    except Exception:
        return []