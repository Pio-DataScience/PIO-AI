#!/usr/bin/env python3
"""Debug BM25 search step by step."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from services.indexer.bm25_index import BM25Indexer
from whoosh.index import open_dir
from whoosh.qparser import QueryParser
from whoosh.query import And, Term

def debug_search():
    """Debug the search step by step."""
    
    index_dir = ROOT / "indexes" / "bm25" / "ai_aml"
    project_name = "AI_AML"
    query_text = "class"
    
    ix = open_dir(str(index_dir))
    
    with ix.searcher() as searcher:
        print("=== Step 1: Parse content query ===")
        parser = QueryParser("content", ix.schema)
        content_query = parser.parse(query_text)
        print(f"Content query: {content_query}")
        
        # Test content query alone
        content_results = searcher.search(content_query, limit=5)
        print(f"Content-only results: {len(content_results)}")
        for hit in content_results[:3]:
            print(f"  - {hit['path']} (project: '{hit['project']}')")
        
        print("\n=== Step 2: Create project filter ===")
        project_filter = Term("project", project_name)
        print(f"Project filter: {project_filter}")
        
        # Test project filter alone
        project_results = searcher.search(project_filter, limit=5)
        print(f"Project-only results: {len(project_results)}")
        for hit in project_results[:3]:
            print(f"  - {hit['path']} (project: '{hit['project']}')")
        
        print("\n=== Step 3: Combine queries ===")
        combined_query = And([content_query, project_filter])
        print(f"Combined query: {combined_query}")
        
        combined_results = searcher.search(combined_query, limit=5)
        print(f"Combined results: {len(combined_results)}")
        for hit in combined_results:
            print(f"  - {hit['path']} (project: '{hit['project']}')")

if __name__ == "__main__":
    debug_search()