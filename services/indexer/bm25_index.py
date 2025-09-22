"""
BM25 Keyword Index using Whoosh for fast text search.

Provides keyword search over code and documentation files with:
- Per-project indexing
- Code vs text separation
- BM25 scoring with snippets
- Symbol-friendly tokenization
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

# Add package to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.ingest.normalizer import normalize_path_to_posix, normalize_encoding, get_file_kind

# Whoosh imports
from whoosh import fields
from whoosh.index import create_in, open_dir, exists_in
from whoosh.qparser import QueryParser
from whoosh.analysis import StandardAnalyzer
from whoosh.highlight import UppercaseFormatter, ContextFragmenter
import re


def create_symbol_analyzer():
    """Create analyzer optimized for code symbols."""
    return StandardAnalyzer()


@dataclass
class SearchResult:
    """BM25 search result."""
    project: str
    path: str
    kind: str  # "code" or "text"
    score: float
    snippet: str


class BM25Indexer:
    """BM25 keyword indexer for projects."""
    
    def __init__(self):
        self.schema = fields.Schema(
            project=fields.ID(stored=True),
            path=fields.ID(stored=True), 
            kind=fields.ID(stored=True),  # "code" or "text"
            content=fields.TEXT(analyzer=create_symbol_analyzer(), stored=True)
        )
    
    def build_bm25_for_project(self, project_name: str, 
                              files: List[Tuple[Path, str, str]], 
                              out_dir: Path) -> Dict[str, int]:
        """
        Build BM25 index for a project.
        
        Args:
            project_name: Name of the project
            files: List of (abs_path, rel_posix, kind) tuples
            out_dir: Output directory for index
            
        Returns:
            Statistics dict with counts
        """
        # Create output directory
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Create or open index
        if exists_in(str(out_dir)):
            ix = open_dir(str(out_dir))
        else:
            ix = create_in(str(out_dir), self.schema)
        
        # Clear existing documents for this project
        writer = ix.writer()
        try:
            writer.delete_by_term('project', project_name)
            writer.commit()
        except:
            writer.cancel()
        
        stats = {'files': 0, 'code_files': 0, 'text_files': 0, 'total_chars': 0}
        
        # Index each file with a new writer session
        writer = ix.writer()
        try:
            for abs_path, rel_posix, kind in files:
                try:
                    content = normalize_encoding(abs_path)
                    
                    # Add document to index
                    writer.add_document(
                        project=project_name,
                        path=rel_posix,
                        kind=kind,
                        content=content
                    )
                    
                    stats['files'] += 1
                    stats['total_chars'] += len(content)
                    
                    if kind == 'code':
                        stats['code_files'] += 1
                    else:
                        stats['text_files'] += 1
                        
                except Exception as e:
                    print(f"Warning: Could not index {abs_path}: {e}")
            
            writer.commit()
        except Exception as e:
            writer.cancel()
            raise e
        ix.close()
        
        return stats
    
    def search_bm25(self, project_name: str, query: str, top_k: int = 10,
                   index_dir: Optional[Path] = None) -> List[SearchResult]:
        """
        Search BM25 index for a project.
        
        Args:
            project_name: Project to search in
            query: Search query
            top_k: Maximum number of results
            index_dir: Index directory (if None, uses default)
            
        Returns:
            List of search results with scores and snippets
        """
        if index_dir is None:
            # Default index location with sanitized name
            package_root = Path(__file__).resolve().parents[2]  # Fixed: was parents[3]
            sanitized_name = project_name.replace(" ", "_").replace("-", "_").lower()
            index_dir = package_root / "indexes" / "bm25" / sanitized_name
        
        if not index_dir.exists() or not exists_in(str(index_dir)):
            return []
        
        try:
            ix = open_dir(str(index_dir))
            
            with ix.searcher() as searcher:
                # Create query parser
                parser = QueryParser("content", ix.schema)
                query_obj = parser.parse(query)
                
                # Add project filter
                from whoosh.query import And, Term
                project_filter = Term("project", project_name)
                filtered_query = And([query_obj, project_filter])
                
                # Search with highlighting
                results = searcher.search(filtered_query, limit=top_k)
                results.fragmenter = ContextFragmenter(maxchars=200, surround=50)
                results.formatter = UppercaseFormatter()
                
                search_results = []
                for hit in results:
                    # Get highlighted snippet
                    snippet = hit.highlights("content", top=1)
                    if not snippet:
                        # Fallback to truncated content
                        content = hit["content"]
                        snippet = content[:200] + "..." if len(content) > 200 else content
                    
                    search_results.append(SearchResult(
                        project=hit["project"],
                        path=hit["path"],
                        kind=hit["kind"],
                        score=hit.score,
                        snippet=snippet
                    ))
                
                return search_results
                
        except Exception as e:
            print(f"Error searching BM25 index: {e}")
            return []


def build_bm25_for_project(project_name: str, files: List[Tuple[Path, str, str]], 
                          out_dir: Path) -> Dict[str, int]:
    """Convenience function to build BM25 index."""
    indexer = BM25Indexer()
    return indexer.build_bm25_for_project(project_name, files, out_dir)


def search_bm25(project_name: str, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Convenience function to search BM25 index.
    
    Returns results as dict format for compatibility.
    """
    indexer = BM25Indexer()
    results = indexer.search_bm25(project_name, query, top_k)
    
    return [
        {
            'project': r.project,
            'path': r.path, 
            'kind': r.kind,
            'score': r.score,
            'snippet': r.snippet
        }
        for r in results
    ]


def prepare_files_for_indexing(root: Path, includes: List[str], excludes: List[str]) -> List[Tuple[Path, str, str]]:
    """
    Prepare list of files for BM25 indexing.
    
    Returns:
        List of (abs_path, rel_posix, kind) tuples
    """
    from services.ingest.normalizer import expand_files, is_text_file
    
    all_files = expand_files(root, includes, excludes)
    prepared = []
    
    for file_path in all_files:
        if is_text_file(file_path):
            try:
                rel_path = file_path.relative_to(root)
                rel_posix = normalize_path_to_posix(rel_path)
                kind = get_file_kind(file_path)
                prepared.append((file_path, rel_posix, kind))
            except ValueError:
                # Skip files outside root
                continue
    
    return prepared


def get_project_bm25_stats(project_name: str) -> Optional[Dict[str, Any]]:
    """Get statistics about a project's BM25 index."""
    package_root = Path(__file__).resolve().parents[2]  # Fixed: was parents[3]
    sanitized_name = project_name.replace(" ", "_").replace("-", "_").lower()
    index_dir = package_root / "indexes" / "bm25" / sanitized_name
    
    if not index_dir.exists() or not exists_in(str(index_dir)):
        return None
    
    try:
        ix = open_dir(str(index_dir))
        
        with ix.searcher() as searcher:
            # Count documents by project
            from whoosh.query import Term
            project_query = Term("project", project_name)
            results = searcher.search(project_query, limit=None)
            
            stats = {
                'total_documents': len(results),
                'code_documents': 0,
                'text_documents': 0,
                'index_size_mb': 0
            }
            
            for hit in results:
                if hit["kind"] == "code":
                    stats['code_documents'] += 1
                else:
                    stats['text_documents'] += 1
            
            # Get approximate index size
            try:
                index_size = sum(f.stat().st_size for f in index_dir.rglob('*') if f.is_file())
                stats['index_size_mb'] = round(index_size / (1024 * 1024), 2)
            except:
                pass
            
            return stats
            
    except Exception as e:
        print(f"Error getting BM25 stats: {e}")
        return None