"""
Search tools using BM25 index for grep-like functionality.
"""

import sys
import os
from typing import List, Dict, Any, Optional

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.indexer.bm25_index import search_bm25 as bm25_search
from services.ingest.manifest_reader import get_project_by_name


def grep(project: str, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
    """
    BM25-powered grep-like search within a project.
    
    Args:
        project: Project name from manifest
        query: Search query (can include operators, phrases)
        top_k: Maximum number of results
        
    Returns:
        List of search results with paths, scores, and snippets
    """
    # Validate project exists
    try:
        get_project_by_name(project)
    except ValueError:
        raise ValueError(f"Project '{project}' not found in manifest")
    
    try:
        results = bm25_search(project, query, top_k)
        
        # Enhance results with additional metadata
        enhanced_results = []
        for result in results:
            enhanced = {
                'project': result['project'],
                'path': result['path'],
                'kind': result['kind'],  # 'code' or 'text'
                'score': result['score'],
                'snippet': result['snippet'],
                'match_type': 'content'
            }
            enhanced_results.append(enhanced)
        
        return enhanced_results
        
    except Exception as e:
        print(f"Warning: Error searching project {project}: {e}")
        return []


def search_code_only(project: str, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
    """
    Search only in code files (Python, SQL, config files).
    
    Args:
        project: Project name from manifest
        query: Search query
        top_k: Maximum number of results
        
    Returns:
        List of code search results
    """
    results = grep(project, query, top_k * 2)  # Get more to filter
    code_results = [r for r in results if r['kind'] == 'code']
    return code_results[:top_k]


def search_docs_only(project: str, query: str, top_k: int = 20) -> List[Dict[str, Any]]:
    """
    Search only in documentation files (Markdown, text files).
    
    Args:
        project: Project name from manifest
        query: Search query
        top_k: Maximum number of results
        
    Returns:
        List of documentation search results
    """
    results = grep(project, query, top_k * 2)  # Get more to filter
    doc_results = [r for r in results if r['kind'] == 'text']
    return doc_results[:top_k]


def search_by_file_extension(project: str, query: str, extension: str, top_k: int = 20) -> List[Dict[str, Any]]:
    """
    Search within files of a specific extension.
    
    Args:
        project: Project name from manifest
        query: Search query
        extension: File extension (e.g., '.py', '.sql', '.md')
        top_k: Maximum number of results
        
    Returns:
        List of filtered search results
    """
    results = grep(project, query, top_k * 3)  # Get more to filter
    
    # Filter by extension
    filtered_results = []
    for result in results:
        if result['path'].lower().endswith(extension.lower()):
            filtered_results.append(result)
            if len(filtered_results) >= top_k:
                break
    
    return filtered_results


def search_function_names(project: str, function_name: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Search for function definitions and calls.
    
    Args:
        project: Project name from manifest
        function_name: Function name to search for
        top_k: Maximum number of results
        
    Returns:
        List of function-related search results
    """
    # Search for function definitions and calls
    queries = [
        f"def {function_name}",      # Function definition
        f"async def {function_name}", # Async function definition
        f"{function_name}(",         # Function calls
        f"class {function_name}",    # Class definition (if searching for class)
    ]
    
    all_results = []
    seen_paths = set()
    
    for query in queries:
        results = search_code_only(project, query, top_k)
        for result in results:
            # Avoid duplicates from same file
            path_key = (result['path'], result['snippet'][:50])
            if path_key not in seen_paths:
                seen_paths.add(path_key)
                result['query_type'] = query.split()[0]  # 'def', 'async', function name, or 'class'
                all_results.append(result)
    
    # Sort by score and return top results
    all_results.sort(key=lambda x: x['score'], reverse=True)
    return all_results[:top_k]


def search_imports(project: str, module_name: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Search for import statements.
    
    Args:
        project: Project name from manifest
        module_name: Module/package name to search for
        top_k: Maximum number of results
        
    Returns:
        List of import-related search results
    """
    # Search for various import patterns
    queries = [
        f"import {module_name}",
        f"from {module_name}",
        f"import {module_name}.",
        f"from {module_name}."
    ]
    
    all_results = []
    seen_paths = set()
    
    for query in queries:
        results = search_code_only(project, query, top_k)
        for result in results:
            path_key = (result['path'], result['snippet'][:50])
            if path_key not in seen_paths:
                seen_paths.add(path_key)
                result['import_type'] = 'import' if 'import' in query.split()[0] else 'from_import'
                all_results.append(result)
    
    # Sort by score and return top results
    all_results.sort(key=lambda x: x['score'], reverse=True)
    return all_results[:top_k]


def search_class_usage(project: str, class_name: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Search for class definitions and usage.
    
    Args:
        project: Project name from manifest
        class_name: Class name to search for
        top_k: Maximum number of results
        
    Returns:
        List of class-related search results
    """
    # Search for class patterns
    queries = [
        f"class {class_name}",      # Class definition
        f"{class_name}(",           # Class instantiation
        f"isinstance({class_name}", # Type checking
        f"issubclass({class_name}", # Inheritance checking
        f"extends {class_name}",    # Inheritance (if any JS/other syntax)
    ]
    
    all_results = []
    seen_paths = set()
    
    for query in queries:
        results = search_code_only(project, query, top_k)
        for result in results:
            path_key = (result['path'], result['snippet'][:50])
            if path_key not in seen_paths:
                seen_paths.add(path_key)
                result['usage_type'] = query.split()[0]
                all_results.append(result)
    
    # Sort by score and return top results
    all_results.sort(key=lambda x: x['score'], reverse=True)
    return all_results[:top_k]


def search_constants(project: str, constant_name: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Search for constant definitions and usage.
    
    Args:
        project: Project name from manifest
        constant_name: Constant name to search for (usually UPPERCASE)
        top_k: Maximum number of results
        
    Returns:
        List of constant-related search results
    """
    # Search for constant patterns
    queries = [
        f"{constant_name} =",       # Assignment
        f"{constant_name}:",        # In dictionaries, type hints
        f'"{constant_name}"',       # String literal
        f"'{constant_name}'",       # String literal
        constant_name,              # General usage
    ]
    
    all_results = []
    seen_snippets = set()
    
    for query in queries:
        results = search_code_only(project, query, top_k)
        for result in results:
            # Use snippet to avoid exact duplicates
            snippet_key = result['snippet'][:100]
            if snippet_key not in seen_snippets:
                seen_snippets.add(snippet_key)
                all_results.append(result)
    
    # Sort by score and return top results
    all_results.sort(key=lambda x: x['score'], reverse=True)
    return all_results[:top_k]


def multi_term_search(project: str, terms: List[str], operator: str = "AND", top_k: int = 20) -> List[Dict[str, Any]]:
    """
    Search for multiple terms with AND/OR logic.
    
    Args:
        project: Project name from manifest
        terms: List of search terms
        operator: "AND" or "OR" logic
        top_k: Maximum number of results
        
    Returns:
        List of search results
    """
    if operator.upper() == "AND":
        # For AND, create a single query with all terms
        query = " AND ".join(terms)
        return grep(project, query, top_k)
    
    elif operator.upper() == "OR":
        # For OR, search each term separately and combine results
        all_results = []
        seen_paths = set()
        
        for term in terms:
            results = grep(project, term, top_k)
            for result in results:
                path_key = (result['path'], result['snippet'][:50])
                if path_key not in seen_paths:
                    seen_paths.add(path_key)
                    result['matched_term'] = term
                    all_results.append(result)
        
        # Sort by score and return top results
        all_results.sort(key=lambda x: x['score'], reverse=True)
        return all_results[:top_k]
    
    else:
        raise ValueError("Operator must be 'AND' or 'OR'")


def get_search_stats(project: str) -> Optional[Dict[str, Any]]:
    """
    Get statistics about the search index for a project.
    
    Args:
        project: Project name from manifest
        
    Returns:
        Statistics dictionary or None if no index
    """
    try:
        from services.indexer.bm25_index import get_project_bm25_stats
        return get_project_bm25_stats(project)
    except Exception as e:
        print(f"Warning: Error getting search stats: {e}")
        return None