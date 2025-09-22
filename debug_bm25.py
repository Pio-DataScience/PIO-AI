#!/usr/bin/env python3
"""Debug BM25 search functionality."""

import sys
from pathlib import Path

# Add the PIO-AI root to path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from services.indexer.bm25_index import BM25Indexer
from whoosh.index import open_dir, exists_in

def debug_index():
    """Debug what's in the BM25 index."""
    index_dir = ROOT / "indexes" / "bm25" / "ai_aml"
    
    print(f"Index directory: {index_dir}")
    print(f"Exists: {index_dir.exists()}")
    print(f"Whoosh exists: {exists_in(str(index_dir))}")
    
    if index_dir.exists() and exists_in(str(index_dir)):
        ix = open_dir(str(index_dir))
        
        with ix.searcher() as searcher:
            # Get all documents
            from whoosh.query import Every
            all_docs = searcher.search(Every(), limit=None)
            print(f"Total documents: {len(all_docs)}")
            
            # Show first few documents
            for i, doc in enumerate(all_docs[:5]):
                print(f"Doc {i}: project='{doc['project']}', path='{doc['path']}', kind='{doc['kind']}'")
            
            # Try a simple search
            from whoosh.qparser import QueryParser
            parser = QueryParser("content", ix.schema)
            
            # Test different queries
            test_queries = ["class", "def", "import", "function"]
            for query_text in test_queries:
                query = parser.parse(query_text)
                results = searcher.search(query, limit=5)
                print(f"Query '{query_text}': {len(results)} results")
                for hit in results:
                    print(f"  - {hit['path']} (score: {hit.score:.3f})")

if __name__ == "__main__":
    debug_index()